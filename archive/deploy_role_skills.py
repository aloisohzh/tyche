"""Phase 2 driver for the role skills: pack, upload, attach, verify. One target per call.

Nothing in here touches the platform unless you pass --apply, and even then only the one named
target is written. Reads always come first: attach() re-reads the live template, so a skills write
carries the current skills array forward instead of overwriting it from memory (arrays replace
wholesale). The write body is deliberately limited to `name` + `skills`; tools, mcp_servers, vaults,
environment_variables, model and multiagent are never sent by this script, and verify() proves they
did not move.

    python scripts/deploy_role_skills.py pack
    python scripts/deploy_role_skills.py create sentinel-digest            # dry run
    python scripts/deploy_role_skills.py create sentinel-digest --apply
    python scripts/deploy_role_skills.py attach coordinator --skill-id skill_x --version 123 --apply
    python scripts/deploy_role_skills.py roster --apply                       # desk child pins
    python scripts/deploy_role_skills.py cards --apply                        # the two scheduled cards
    python scripts/deploy_role_skills.py grant researcher quote_order_book --apply
    python scripts/deploy_role_skills.py verify coordinator --agent agent_x

Package rules enforced here are the platform's (docs.qoder.com/cloud-agents/api/skills/schemas):
one top-level directory whose name equals the SKILL.md `name`, name ^[a-z0-9][a-z0-9_-]*$ within 64
chars, description within 5,120 chars, and no unquoted ": " inside a frontmatter value, which would
make the YAML parser fall back to line matching and quietly drop keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Both siblings read the PAT from the gitignored .env; nothing here hard-codes a credential.
import cloud_api
import forward

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
PACK_DIR = ROOT / "plans" / "phase2" / "packed"
BASELINE = ROOT / "plans" / "phase2" / "surface-2026-11-21.json"
PLANS_DIR = ROOT / "plans" / "phase2"
DESK_AGENT = "agent_00vtt1wjgm22o20s8ykz"
CLOUD_BASE = "https://api.qoder.com/api/v1/cloud"

# role -> forward template. "coordinator" is the desk head itself.
TEMPLATES = {
    "coordinator": "tmpl_004fa008901a6c256bd0ed3f",
    "researcher": "tmpl_875834770244a9e35c7f6499",
    "auditor": "tmpl_ae317cc0626a4fcc8fa8fad6",
    "executor": "tmpl_bc25a5c313827d53894fd7ff",
}
# skill directory name -> the role whose template should carry it
SKILL_ROLE = {
    "sentinel-digest": "coordinator",
    "exact-order-audit": "auditor",
    "paper-submit-protocol": "executor",
}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def frontmatter(path: Path) -> dict[str, str]:
    """Parse the top-level key/value pairs of a SKILL.md frontmatter block."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise SystemExit(f"{path}: no frontmatter block")
    fields = {}
    for line in match.group(1).splitlines():
        if line and not line.startswith((" ", "#")) and ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def check(path: Path) -> str:
    """Validate one skill against the platform package rules; return its name."""
    fields = frontmatter(path)
    name, desc = fields.get("name", ""), fields.get("description", "")
    problems = []
    if not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"name {name!r} violates ^[a-z0-9][a-z0-9_-]*$ (max 64)")
    if path.parent.name != name:
        problems.append(f"directory {path.parent.name!r} must equal frontmatter name {name!r}")
    if not desc or len(desc) > 5120:
        problems.append(f"description length {len(desc)} is outside 1..5120")
    for key, value in fields.items():
        if ": " in value:
            problems.append(f"{key}: contains ': ' and must be quoted or reworded")
    if problems:
        raise SystemExit(f"{path}: " + "; ".join(problems))
    return name


def pack(name: str) -> Path:
    path = SKILLS_DIR / SKILL_ROLE[name] / name / "SKILL.md"
    check(path)
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = PACK_DIR / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(path, f"{name}/SKILL.md", compress_type=zipfile.ZIP_DEFLATED)
    return zip_path


def multipart(parts: list[tuple[str, tuple[str, bytes, str]] | tuple[str, str]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body: parts are (field, value) or (field, (filename, data, ct))."""
    boundary = "tycheSkillBoundary9f3c21"
    out: list[bytes] = []
    for part in parts:
        out.append(f"--{boundary}\r\n".encode())
        if isinstance(part[1], tuple):
            field, (filename, data, ctype) = part
            out.append(f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode())
            out.append(f"Content-Type: {ctype}\r\n\r\n".encode())
            out.append(data + b"\r\n")
        else:
            field, value = part
            out.append(f'Content-Disposition: form-data; name="{field}"\r\n\r\n'.encode())
            out.append(f"{value}\r\n".encode())
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def post_multipart(path: str, parts, apply: bool) -> dict:
    body, ctype = multipart(parts)
    print(f"POST {CLOUD_BASE}{path}  ({len(body)} bytes)")
    for part in parts:
        if isinstance(part[1], tuple):
            print(f"  file field {part[0]!r}: {part[1][0]}, sha256 {hashlib.sha256(part[1][1]).hexdigest()[:16]}")
        else:
            print(f"  field {part[0]!r}: {part[1]}")
    if not apply:
        print("  dry run: nothing sent (add --apply)")
        return {}
    request = __import__("urllib.request").request.Request(
        CLOUD_BASE + path, data=body, method="POST",
        headers={"Authorization": f"Bearer {forward.pat()}", "Content-Type": ctype},
    )
    with __import__("urllib.request").request.urlopen(request, timeout=60) as response:
        item = json.loads(response.read())
    print(f"  created {item.get('id')} latest_version {item.get('latest_version')}")
    return item


def cmd_pack(args) -> None:
    for name in sorted(SKILL_ROLE):
        zip_path = pack(name)
        print(f"{name}: {zip_path} {zip_path.stat().st_size} bytes "
              f"sha256 {hashlib.sha256(zip_path.read_bytes()).hexdigest()[:16]} -> role {SKILL_ROLE[name]}")


def cmd_create(args) -> None:
    zip_path = pack(args.name)
    role = SKILL_ROLE[args.name]
    parts = [
        ("display_title", f"tyche {role} {args.name}"),
        ("metadata", json.dumps({"role": role, "source_path": f"skills/{role}/{args.name}/SKILL.md",
                                 "managed_by": "scripts/deploy_role_skills.py"})),
        ("files", (zip_path.name, zip_path.read_bytes(), "application/zip")),
    ]
    post_multipart("/skills", parts, args.apply)


def cmd_attach(args) -> None:
    tid = TEMPLATES[args.role]
    current = forward.req("GET", f"/templates/{tid}")
    skills = list(current.get("skills") or [])
    entry = {"type": "custom", "skill_id": args.skill_id, "version": args.version, "enabled": True}
    before_ids = [s.get("skill_id") for s in skills]
    skills = [s for s in skills if s.get("skill_id") != args.skill_id] + [entry]
    print(f"template {tid} ({current.get('name')})")
    print(f"  skills before: {before_ids}")
    print(f"  skills after : {[s.get('skill_id') for s in skills]}")
    print(f"  new entry    : {json.dumps(entry)}")
    print("  body sent    : {name, skills} only; tools/vaults/env/model/multiagent are not sent")
    if not args.apply:
        print("  dry run: nothing sent (add --apply)")
        return
    forward.req("POST", f"/templates/{tid}", {"name": current["name"], "skills": skills})
    print("  written; run verify next")


def _names(value) -> list:
    """Names of a list-or-dict field, tolerating both shapes (repositories/vaults differ per field).

    A baseline row stores repositories and vaults as name lists while a live template returns
    objects, so the two sides must fold to the same representation: dict -> sorted keys, list of
    objects -> sorted canonical JSON, list of names -> the names themselves.
    """
    if isinstance(value, dict):
        return sorted(value.keys())
    if isinstance(value, list):
        return sorted(item if isinstance(item, str) else json.dumps(item, sort_keys=True)
                      for item in value)
    return []


def _view(obj: dict) -> dict:
    """The compared fields of a template, or of a stored baseline row, in one shared shape.

    A live template carries `system` and `environment_variables`; the baseline row already holds the
    reduced `system_chars`/`system_sha256`/`env_keys`. Reducing rather than reading values is the
    point: the API returns environment values in plaintext and they must not be echoed or persisted
    (L-038).
    """
    if "system" not in obj:  # a baseline row
        return {key: obj[key] for key in (
            "status", "environment_id", "managed_tool_config", "model", "multiagent",
            "system_chars", "system_sha256")} | {
            "tools": _names(obj["tools"]), "mcp_servers": _names(obj["mcp_servers"]),
            "vaults": _names(obj["vaults"]), "github_repositories": _names(obj["github_repositories"]),
            "env_keys": sorted(obj["env_keys"])}
    env = obj.get("environment_variables")
    return {
        "status": obj.get("status"),
        "environment_id": obj.get("environment_id"),
        "tools": _names(obj.get("tools")),
        "mcp_servers": _names(obj.get("mcp_servers")),
        "vaults": _names(obj.get("vaults")),
        "managed_tool_config": obj.get("managed_tool_config") or {},
        "env_keys": sorted(env.keys()) if isinstance(env, dict) else _names(env),
        "github_repositories": _names(obj.get("github_repositories")),
        "model": obj.get("model"),
        "multiagent": obj.get("multiagent"),
        "system_chars": len(obj.get("system") or ""),
        "system_sha256": hashlib.sha256((obj.get("system") or "").encode()).hexdigest(),
    }


def cmd_verify(args) -> None:
    tid = TEMPLATES[args.role]
    live = forward.req("GET", f"/templates/{tid}")
    baseline = next(r for r in json.loads(BASELINE.read_text(encoding="utf-8")) if r["id"] == tid)
    now, was = _view(live), _view(baseline)
    print(f"template {tid} ({args.role}) against {BASELINE.name}")
    drift = [key for key in was if now[key] != was[key]]
    for key in sorted(was):
        if key in ("system_sha256", "system_chars"):
            continue
        print(f"  {key:21} {'same' if key not in drift else 'CHANGED'}  {json.dumps(now[key])[:110]}")
    same_prompt = now["system_sha256"] == was["system_sha256"]
    print(f"  {'system (sha256)':21} {'same' if same_prompt else 'CHANGED'}  {now['system_chars']} chars")
    if drift or not same_prompt:
        print(f"  DRIFT in: {sorted(drift) + ([] if same_prompt else ['system'])}")
        print("  revert with the recorded prior payload and report; a skills write must not move these")
    print(f"  {'skills':21} {[s.get('skill_id') for s in (live.get('skills') or [])]}")
    if args.agent:
        agent = cloud_api.req("GET", f"/agents/{args.agent}")
        print(f"agent {args.agent} version {agent.get('version')}")
        print(f"  {'skills':21} {[s.get('skill_id') for s in (agent.get('skills') or [])]}")
        grants = sorted(
            str(pol.get("name") or pol.get("tool") or pol)
            for pol in (agent.get("permission_policies") or agent.get("policies") or [])
            if pol.get("type") == "always_allow"
        )
        print(f"  {'always_allow':21} {grants}")


CHILD_AGENTS = {
    "researcher": "agent_00vs9v3dg0rnkr4740x3",
    "auditor": "agent_00vtx8g7k1534t7w9eve",
    "executor": "agent_00vtx8mfbxerk6vxmny5",
}


def cmd_roster(args) -> None:
    """Re-pin the desk roster to each child's current compiled-agent version.

    The forward template API exposes no version field; the number the roster pins is the child's
    compiled agent version, so it is read from /agents (L-021: the pin, not `latest`, is what a
    session actually snapshots).
    """
    tid = TEMPLATES["coordinator"]
    desk = forward.req("GET", f"/templates/{tid}")
    wanted = {role: cloud_api.req("GET", f"/agents/{agent}").get("version")
              for role, agent in CHILD_AGENTS.items()}
    roster = json.loads(json.dumps(desk.get("multiagent") or {}))
    before = [(a.get("template_id"), a.get("version")) for a in roster.get("agents", [])]
    for entry in roster.get("agents", []):
        for role, template_id in TEMPLATES.items():
            if role != "coordinator" and entry.get("template_id") == template_id:
                entry["version"] = wanted[role]
    print(f"template {tid} ({desk.get('name')}) multiagent")
    print(f"  before: {before}")
    print(f"  after : {[(a.get('template_id'), a.get('version')) for a in roster.get('agents', [])]}")
    print(f"  child agent versions: {wanted}")
    print("  body sent: {name, multiagent} only; entries keep their template_id/type, advisor keeps its model")
    if not args.apply:
        print("  dry run: nothing sent (add --apply)")
        return
    forward.req("POST", f"/templates/{tid}", {"name": desk["name"], "multiagent": roster})
    print("  written; run verify next")


def _env_fingerprint(obj: dict) -> str:
    """A comparable, value-free fingerprint of a deployment's environment payload.

    The cloud returns it either as a mapping or as an already-joined string, and either way it holds
    plaintext secrets, so nothing here echoes or stores it - the hash proves immutability only.
    """
    raw = obj.get("environment_variables")
    if isinstance(raw, dict):
        return "keys:" + ",".join(sorted(raw.keys()))
    return "hash:" + hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:12]


def cmd_cards(args) -> None:
    """Move the two scheduled desk cards onto the desk agent's current compiled version.

    A card pins an exact build, so the skills are not live until the pin moves. The body is the pin
    and nothing else (no schedule, no brief, no environment): a configuration update to an existing
    deployment, not a schedule change. Anything other than an older integer pin is left alone.
    """
    desk = cloud_api.req("GET", f"/agents/{DESK_AGENT}")
    target = desk.get("version")
    if not isinstance(target, int):
        raise SystemExit("desk compiled agent version unavailable; refusing to pin a card by name")
    cards = cloud_api.req("GET", "/deployments").get("data") or []
    if not cards:
        raise SystemExit("no deployment cards came back - refusing to call that all clear")
    for card in cards:
        agent = card.get("agent") or {}
        did = card.get("id")
        if agent.get("id") != DESK_AGENT or not str(card.get("name", "")).startswith("Tyche desk"):
            print(f"deployment {did}: not a Tyche desk card - left alone")
            continue
        before = cloud_api.req("GET", f"/deployments/{did}")
        pinned = (before.get("agent") or {}).get("version")
        events = json.dumps(before.get("initial_events") or "")
        schedule = before.get("schedule") or {}
        print(f"deployment {did} ({before.get('name')})")
        print(f"  pin            v{pinned} -> v{target}")
        print(f"  brief          sha {hashlib.sha256(events.encode()).hexdigest()[:16]} "
              f"{len(events)} chars (not sent, must be byte-identical after)")
        print(f"  cron           {schedule.get('expression')} {schedule.get('timezone')} (not sent)")
        print("  body           {'agent': {id, type, version}} only")
        if pinned == target:
            print("  already pins this version - nothing to write")
            continue
        if not isinstance(pinned, int) or pinned > target:
            print(f"  pins {pinned!r}, not an older build than v{target} - left alone")
            continue
        if not args.apply:
            print("  dry run: nothing sent (add --apply)")
            continue
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        snap = PLANS_DIR / f"cloud-deployment-{did}-pre-skills-repin.json"
        # Secret-free snapshot: the API hands back environment_variables in plaintext, so only the
        # key names are persisted; a re-pin must not move them, and the keys are enough to prove it.
        safe = {k: v for k, v in before.items() if k != "environment_variables"} | {
            "env_fingerprint": _env_fingerprint(before)}
        snap.write_text(json.dumps(safe, indent=2, sort_keys=True), encoding="utf-8")
        cloud_api.req("POST", f"/deployments/{did}",
                      {"agent": {"id": DESK_AGENT, "type": "agent", "version": target}})
        after = cloud_api.req("GET", f"/deployments/{did}")
        if (after.get("agent") or {}).get("version") != target:
            raise SystemExit(f"{did}: pin did not move; restore from {snap}")
        keep = ("name", "description", "status", "environment_id", "vault_ids", "metadata",
                "resources", "schedule", "initial_events")
        drift = [k for k in keep if json.dumps(before.get(k), sort_keys=True)
                 != json.dumps(after.get(k), sort_keys=True)]
        if _env_fingerprint(after) != _env_fingerprint(before):
            drift.append("environment_variables")
        if drift:
            raise SystemExit(f"{did}: fields {drift} changed - only the pin may move. Restore from "
                             f"{snap} and inspect before the next fire")
        print(f"  written; only the pin moved (pre-write state in {snap.name}, env values not stored)")


def cmd_grant(args) -> None:
    """Add one named MCP tool to a role's toolset: a tools-only write, arrays resent whole.

    Tool lists are a floor, not a ceiling (L-017: the researcher had no order book, so it could not
    verify the two-sided quote the auditor's checklist depends on). Everything the template already
    carries is re-read from the live record and sent back unchanged except the added entry.
    """
    tid = TEMPLATES[args.role]
    live = forward.req("GET", f"/templates/{tid}")
    original = live.get("tools") or []
    index = next((i for i, entry in enumerate(original)
                  if entry.get("type") == "mcp_toolset"
                  and entry.get("mcp_server_name") == args.server), None)
    if index is None:
        raise SystemExit(f"{args.role}: no {args.server} mcp_toolset in this template - nothing to grant")
    tools = json.loads(json.dumps(original))
    target = tools[index]
    configs = target.setdefault("configs", [])
    if any(c.get("name") == args.tool for c in configs):
        print(f"{args.role}: {args.tool} already listed; no write needed")
        return
    configs.append({"name": args.tool, "enabled": True})
    configs.sort(key=lambda c: c["name"])
    before = sorted(c["name"] for c in original[index].get("configs") or [] if c.get("enabled"))
    print(f"template {tid} ({live.get('name')}) tools")
    print(f"  server   : {args.server} (permission_policy {json.dumps(target.get('permission_policy'), sort_keys=True)})")
    print(f"  before   : {len(before)} enabled")
    print(f"  after    : {len(before) + 1} enabled, +{args.tool}")
    print("  body sent: {name, tools} only; skills/vaults/env/model/multiagent are not sent")
    if not args.apply:
        print("  dry run: nothing sent (add --apply)")
        return
    forward.req("POST", f"/templates/{tid}", {"name": live["name"], "tools": tools})
    print("  written; run verify next")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pack").set_defaults(func=cmd_pack)
    create = sub.add_parser("create")
    create.add_argument("name", choices=sorted(SKILL_ROLE))
    create.add_argument("--apply", action="store_true")
    create.set_defaults(func=cmd_create)
    attach = sub.add_parser("attach")
    attach.add_argument("role", choices=sorted(TEMPLATES))
    attach.add_argument("--skill-id", required=True)
    attach.add_argument("--version", required=True)
    attach.add_argument("--apply", action="store_true")
    attach.set_defaults(func=cmd_attach)
    roster = sub.add_parser("roster")
    roster.add_argument("--apply", action="store_true")
    roster.set_defaults(func=cmd_roster)
    cards = sub.add_parser("cards")
    cards.add_argument("--apply", action="store_true")
    cards.set_defaults(func=cmd_cards)
    grant = sub.add_parser("grant")
    grant.add_argument("role", choices=sorted(TEMPLATES))
    grant.add_argument("tool")
    grant.add_argument("--server", default="moomoo")
    grant.add_argument("--apply", action="store_true")
    grant.set_defaults(func=cmd_grant)
    verify = sub.add_parser("verify")
    verify.add_argument("role", choices=sorted(TEMPLATES))
    verify.add_argument("--agent")
    verify.set_defaults(func=cmd_verify)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
