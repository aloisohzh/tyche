"""Managed-mode authoring driver for the tyche desk: one field group per write, verified the same way.

The desk is authored on the Managed agents themselves (`/api/v1/cloud/agents/{id}`), which are the
objects the cards pin, the roster delegates to and the sessions run. Forward templates used to sit in
front of them as an authoring layer; that layer is gone, so this script is the only place a prompt, a
skill pin or a roster is written, and every write here is the whole story of the change.

Discipline carried over from the lessons it was written against:

- One field group per write. A write body carries `version` plus exactly one of `system`, `skills` or
  `multiagent`, so a prompt edit cannot move a tool matrix (L-023) and a re-pin cannot edit prose.
- Read before write. The live object is fetched again at apply time; arrays are replaced wholesale by
  the API, so `attach` and `roster` deep-copy the current array and change only the named rows (L-045).
- Before and after go through one projection (`_view`), never two reducers (L-047).
- Optimistic concurrency: the body carries the version that was just read, so a concurrent edit fails
  with 409 instead of being silently overwritten.
- Nothing here sends tools, mcp_servers, model, metadata or anything environment/vault shaped. `verify`
  proves those did not move.
- Reads never print prompt bodies, only char counts and a sha prefix.

    python scripts/deploy_managed_agents.py status
    python scripts/deploy_managed_agents.py export
    python scripts/deploy_managed_agents.py diff coordinator --file plans/managed-migration/desk-new.md
    python scripts/deploy_managed_agents.py apply-system coordinator --file ... --apply
    python scripts/deploy_managed_agents.py create-skill midday-watch --apply
    python scripts/deploy_managed_agents.py publish-skill exact-order-audit
    python scripts/deploy_managed_agents.py ship-skill scout-data-suite --apply
    python scripts/deploy_managed_agents.py pin-card dep_00vzb9h4ezawwl4thnva --apply
    python scripts/deploy_managed_agents.py attach auditor --skill-id skill_x --version 179... --apply
    python scripts/deploy_managed_agents.py roster --pin auditor 9 --apply
    python scripts/deploy_managed_agents.py verify coordinator
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import math
import re
import sys
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_api  # reads the PAT from the gitignored .env; no credential lives in here

ROOT = Path(__file__).resolve().parents[1]
LIVE_PROMPTS = ROOT / "templates" / "prompts" / "live"
EXPORT_DIR = ROOT / "plans" / "managed-migration"
BASELINE = EXPORT_DIR / "agents-live.json"
SKILLS_DIR = ROOT / "skills"
PACK_DIR = EXPORT_DIR / "packed"

# role -> the Managed agent that runs it. "coordinator" is the desk head itself.
ROLE_AGENTS = {
    "coordinator": "agent_00w96vnmjp81t0rfdqun",
    "researcher": "agent_00w940w68fw1saabz6oz",
    "auditor": "agent_00w96t16mwxkx3l9vi9i",
    "executor": "agent_00w96uc82lhxc3n8xzvv",
}
# skill directory name -> the Managed skill object that holds its versions, the folder under skills/
# it lives in, and the roles that pin it. A skill under skills/shared/ is pinned on several agents from
# ONE cloud object, so the body never forks (L-033). `id` None means the cloud object does not exist yet:
# run `create-skill <name> --apply`, paste the returned id here, then `publish-skill` / `attach`.
# A new version here moves nothing: an agent keeps running the version it pins until `attach` re-pins it.
SKILLS = {
    "sentinel-digest": {"id": "skill_00w5eiyk0bl6o8wz2yd8", "dir": "coordinator", "roles": ["coordinator"]},
    "exact-order-audit": {"id": "skill_00w5ej0prnz0h36xnfvm", "dir": "auditor", "roles": ["auditor"]},
    "paper-submit-protocol": {"id": "skill_00w5ej2wczbb5vfl1bq9", "dir": "executor", "roles": ["executor"]},
    # PR A (2026-11-22): written in the repo, not yet created on the platform.
    "lifecycle-contract": {"id": "skill_00wa7k0k032m9t7igh4k", "dir": "shared", "roles": ["coordinator", "executor"]},
    "midday-watch": {"id": "skill_00wa7ko2m74ea4q72wbr", "dir": "coordinator", "roles": ["coordinator"]},
    "proposal-approval": {"id": "skill_00wa7ksz0j8xsovikb89", "dir": "coordinator", "roles": ["coordinator"]},
    "scout-data-suite": {"id": "skill_00wa7lk0ugfep820a6ob", "dir": "researcher", "roles": ["researcher"]},
    "event-discovery": {"id": "skill_00wa7lp0fmnlsrqgkji2", "dir": "researcher", "roles": ["researcher"]},
    "youtube-inbox": {"id": "skill_00wa7luywxbepm4mfguu", "dir": "researcher", "roles": ["researcher"]},
    "lifecycle-review": {"id": "skill_00wa7m04tdsshgvcupta", "dir": "auditor", "roles": ["auditor"]},
    "broker-capture": {"id": "skill_00wa7m5vsymtchhxtajd", "dir": "executor", "roles": ["executor"]},
}


def _skill_path(name: str) -> Path:
    return SKILLS_DIR / SKILLS[name]["dir"] / name / "SKILL.md"


def _skill_id(name: str) -> str:
    skill_id = SKILLS[name]["id"]
    if not skill_id:
        raise SystemExit(f"{name}: no cloud skill object yet; run `create-skill {name} --apply` and record its id")
    return skill_id


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# the file stem each role's prompt export keeps, for compatibility with tests/test_skills.py
EXPORT_STEM = {"coordinator": "desk", "researcher": "researcher", "auditor": "auditor",
               "executor": "executor"}
# the permanent weekday desk card (the monthly cards were archived 2026-11-22)
CARD_IDS = ("dep_00w9n1b9mkb9cjkalhcv", "dep_00wf6hsffery89aucq7x")  # desk card, scalp card (both pin the desk)



HEADER_RE = re.compile(r"^<!--.*?-->\s*", re.DOTALL)


def _prompt_text(path: str) -> str:
    """The prompt a templates/prompts/live file proposes: its leading HTML comment is the export
    header (retrieved-at or PROPOSED), never part of the system prompt, so diff and apply drop it
    exactly as tests/test_skills.py does."""
    return HEADER_RE.sub("", Path(path).read_text(encoding="utf-8"), count=1)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()


def _agent(role: str) -> dict:
    if role not in ROLE_AGENTS:
        raise SystemExit(f"unknown role {role!r}; expected one of {sorted(ROLE_AGENTS)}")
    return cloud_api.req("GET", f"/agents/{ROLE_AGENTS[role]}")


def _names(value) -> list[str]:
    """Tool / skill / server rows as sorted names, so a reorder is not read as a change."""
    out = []
    for item in value or []:
        if isinstance(item, dict):
            if "enabled_tools" in item:
                out.extend(sorted(item["enabled_tools"]))
            else:
                out.append(str(item.get("name") or item.get("skill_id") or item.get("url") or item))
        else:
            out.append(str(item))
    return sorted(out)


def _skill_rows(value) -> list[str]:
    """Skill pins as `id@version`, because a re-pin is precisely the change a guard must see (L-047).

    Projecting skills by id alone made `attach` report "changed fields: (none reported)" while the pin
    had in fact moved, which is the failure mode L-047 warns about in the other direction: an alarm that
    cannot fire is as trained-away as one that fires wrongly.
    """
    return sorted(f"{s.get('skill_id')}@{s.get('version')}" for s in (value or []) if isinstance(s, dict))


def _view(obj: dict) -> dict:
    """The compared surface of a live agent, or of a stored baseline row, in one shared shape.

    Baseline rows are already reduced, so both sides of a before/after guard land here. A write is
    only trusted when every field it was not supposed to touch still matches.
    """
    if "system" not in obj:  # a baseline row
        return {key: obj[key] for key in ("name", "archived_at", "model", "multiagent", "tools",
                                          "mcp_servers", "skills", "system_chars", "system_sha256")}
    return {
        "name": obj.get("name"),
        "archived_at": bool(obj.get("archived_at")),
        "model": obj.get("model"),
        "tools": _names(obj.get("tools")),
        "mcp_servers": _names(obj.get("mcp_servers")),
        "skills": _skill_rows(obj.get("skills")),
        "multiagent": obj.get("multiagent"),
        "system_chars": len(obj.get("system") or ""),
        "system_sha256": _sha(obj.get("system") or ""),
    }


def _tokens(text: str) -> int:
    """Static estimate only: ~4 characters per token, floored at 1.35 tokens per whitespace word.

    The char count is the measurement; this line exists so the size change of a prompt is quotable in
    the same unit the console uses. It is not a tokenizer and is never a gate.
    """
    if not text:
        return 0
    words = len(text.split())
    return max(math.ceil(len(text) / 4), math.ceil(words * 1.35))


def _print_view(view: dict, label: str) -> None:
    for key in ("name", "archived_at", "model", "mcp_servers", "multiagent"):
        print(f"  {label} {key:14} {json.dumps(view[key], default=str)[:120]}")
    print(f"  {label} skills{'':9} {view['skills']}")
    print(f"  {label} tools{'':8} {len(view['tools'])} enabled: {json.dumps(view['tools'])[:200]}")
    print(f"  {label} system{'':6} {view['system_chars']} chars ~{_tokens('x' * view['system_chars'])}"
          f" tokens sha {view['system_sha256'][:12]}")


# --------------------------------------------------------------------------- read side


def cmd_status(args) -> None:
    print(f"Managed agents at {_now()}")
    for role in ROLE_AGENTS:
        a = _agent(role)
        view = _view(a)
        roster = (a.get("multiagent") or {}).get("agents") or []
        pins = ", ".join(f"{r.get('id') or r.get('model')}@{r.get('version', '-')}" for r in roster)
        print(f"  {role:12} {a['id']} v{a['version']:>3} {view['system_chars']:>6} chars "
              f"sha {view['system_sha256'][:12]} skills {len(view['skills'])} "
              f"mcp {len(view['mcp_servers'])} roster {len(roster)} [{pins}]")
    for did in CARD_IDS:
        d = cloud_api.req("GET", f"/deployments/{did}")
        ag = d.get("agent") or {}
        print(f"  card {did} {d.get('status')} agent {ag.get('id')} v{ag.get('version')} "
              f"cron {(d.get('schedule') or {}).get('expression')}")
        print(f"       card prompt {len(json.dumps(d.get('initial_events')))} chars json "
              f"sha {_sha(json.dumps(d.get('initial_events'), sort_keys=True))[:12]}")


def cmd_export(args) -> None:
    """Full agent objects to the gitignored tree, plus the as-retrieved prompt exports."""
    agents = {role: _agent(role) for role in ROLE_AGENTS}
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    path = EXPORT_DIR / f"agents-{stamp}.json"
    path.write_text(json.dumps(agents, indent=1, sort_keys=True), encoding="utf-8")
    BASELINE.write_text(json.dumps({role: _view(a) | {"id": a["id"], "version": a["version"]}
                                    for role, a in agents.items()}, indent=1,
                                   sort_keys=True), encoding="utf-8")
    print(f"exported {path}")
    print(f"baseline {BASELINE}")
    if args.prompts:
        for role, a in agents.items():
            out = LIVE_PROMPTS / f"{EXPORT_STEM[role]}.md"
            header = (f"<!-- retrieved-at {_now()} | managed agent {a['id']} version v{a['version']} "
                      f"(exported by scripts/deploy_managed_agents.py)\n"
                      f"     Verbatim snapshot of the live system prompt, kept for diffing and for\n"
                      f"     tests/test_skills.py hard-rule checks. Not the policy authority: the platform\n"
                      f"     holds the running pin and docs/risk-card.md + config/ hold the rules. -->\n\n")
            previous = out.read_text(encoding="utf-8") if out.exists() else ""
            new = header + a["system"]
            if new == previous:
                print(f"  {out.name}: unchanged")
                continue
            changed = [l for l in difflib.unified_diff(previous.splitlines(), new.splitlines(),
                                                       lineterm="")
                       if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            out.write_text(new, encoding="utf-8")
            print(f"  {out.name}: rewritten ({len(a['system'])} chars, {len(changed)} changed "
                  f"lines vs the previous export)")
    else:
        print("  (prompt exports untouched; pass --prompts to refresh templates/prompts/live/)")


def cmd_diff(args) -> None:
    a = _agent(args.role)
    proposed = _prompt_text(args.file)
    print(f"target: managed agent {a['id']} ({args.role}) v{a['version']} "
          f"sha {_sha(a['system'])[:12]}")
    print(f"file  : {args.file} ({len(proposed)} chars)")
    print(f"size  : {len(a['system'])} -> {len(proposed)} chars ({len(proposed) - len(a['system']):+d}), "
          f"~{_tokens(a['system'])} -> ~{_tokens(proposed)} tokens "
          f"({_tokens(proposed) - _tokens(a['system']):+d} est.)")
    if proposed == a["system"]:
        print("IDENTICAL - there is nothing to write.")
        return
    lines = list(difflib.unified_diff(a["system"].splitlines(), proposed.splitlines(),
                                      fromfile=f"live v{a['version']}", tofile=args.file,
                                      lineterm="", n=2))
    body = [l for l in lines if l.startswith("@@") or l[:1] in "+- " or l[:3] in ("---", "+++")]
    if args.compact and len(body) > 40:
        body = body[:6] + [f"... {len(body) - 12} more diff lines (drop --compact for all of them) ..."]
    print("\n".join(body))


# --------------------------------------------------------------------------- write side


def _write(role: str, body: dict, expect: str) -> dict:
    """Apply one field group to one agent and prove nothing else moved."""
    a = _agent(role)
    if a.get("archived_at"):
        raise SystemExit(f"{role} is archived; refusing to write")
    if set(body) - {"version", expect}:
        raise SystemExit(f"internal error: body carried {sorted(body)}")
    before = _view(a)
    body = {"version": a["version"], **body}
    print(f"WRITE {a['id']} ({role}) body keys {sorted(body)}")
    result = cloud_api.req("POST", f"/agents/{a['id']}", body)
    item = result.get("item", result) if isinstance(result, dict) else {}
    after_obj = _agent(role)
    after = _view(after_obj)
    moved = [k for k in before if before[k] != after[k]]
    print(f"  ack version v{item.get('version', '?')}; re-read v{a['version']} -> "
          f"v{after_obj.get('version')}")
    print(f"  changed fields: {moved or '(none reported)'}")
    for key in ("tools", "mcp_servers", "skills", "multiagent", "model", "name", "archived_at"):
        if key in moved:
            print(f"  !! {key} moved: {json.dumps(before[key])[:100]} -> {json.dumps(after[key])[:100]}")
    if {"system_chars", "system_sha256"} & set(moved):
        print(f"  system {before['system_chars']} -> {after['system_chars']} chars "
              f"sha {before['system_sha256'][:12]} -> {after['system_sha256'][:12]}")
    rows = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    rows[role] = dict(after, id=after_obj["id"], version=after_obj["version"])
    BASELINE.write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")
    print(f"  baseline row for {role} refreshed in {BASELINE.name}")
    return after_obj


def cmd_apply_system(args) -> None:
    a = _agent(args.role)
    proposed = _prompt_text(args.file)
    if not proposed.strip():
        raise SystemExit("refusing to write an empty prompt")
    if proposed == a["system"]:
        print("live prompt already matches the file; no write needed")
        return
    if not args.apply:
        print("DRY RUN - re-run with --apply to write. Exact diff:")
        args.compact = False
        return cmd_diff(args)
    _write(args.role, {"system": proposed}, "system")


def cmd_attach(args) -> None:
    """Re-pin one skill on one agent; every other binding is carried forward unchanged."""
    a = _agent(args.role)
    current = list(a.get("skills") or [])
    wanted = {"type": "custom", "skill_id": args.skill_id, "version": args.version}
    rows = [dict(s) for s in current if s.get("skill_id") != args.skill_id]
    hit = next((s for s in current if s.get("skill_id") == args.skill_id), None)
    if hit and hit.get("version") == args.version and not args.add:
        print(f"{args.role} already pins {args.skill_id} at {args.version}; no write needed")
        return
    if not hit:
        rows.append(wanted)
    else:
        rows = [wanted if s.get("skill_id") == args.skill_id else dict(s) for s in current]
    body_skills = sorted(rows, key=lambda s: str(s.get("skill_id")))
    if not args.apply:
        print(f"DRY RUN attach {args.role} ({a['id']})")
        print(f"  skills before: {[ (s.get('skill_id'), s.get('version')) for s in current ]}")
        print(f"  skills after : {[ (s.get('skill_id'), s.get('version')) for s in body_skills ]}")
        print("  body sent    : {version, skills} only; system/tools/mcp/model/multiagent are not sent")
        return
    _write(args.role, {"skills": body_skills}, "skills")


def cmd_roster(args) -> None:
    """Re-pin the coordinator's child pins. The advisor row is carried verbatim (L-045)."""
    a = _agent("coordinator")
    roster = json.loads(json.dumps(a.get("multiagent") or {}))
    agents = roster.get("agents") or []
    children = [r for r in agents if r.get("type") != "advisor"]
    if len(children) != len(ROLE_AGENTS) - 1:
        raise SystemExit(f"unexpected roster shape: {json.dumps(agents)[:200]}")
    for pair in args.pin or []:
        role, _, version = pair.partition("=")
        role, version = role.strip(), version.strip()
        if role == "coordinator" or role not in ROLE_AGENTS:
            raise SystemExit(f"{role!r} is not a child role of the coordinator")
        aid = ROLE_AGENTS[role]
        child = next((r for r in children if r.get("id") == aid), None)
        if child is None:
            raise SystemExit(f"roster has no row for {role} ({aid}); refusing to invent one")
        if not version.isdigit() and version != "latest":
            raise SystemExit(f"version {version!r} must be numeric or 'latest'")
        child["version"] = int(version) if version.isdigit() else version
    print(f"roster {a['id']} v{a['version']} ({'APPLY' if args.apply else 'DRY RUN'})")
    for row in agents:
        print(f"  {json.dumps(row)}")
    if not args.apply:
        print("  body sent: {version, multiagent} only; system/tools/skills/model are not sent")
        return
    _write("coordinator", {"multiagent": roster}, "multiagent")


def _frontmatter(path: Path) -> dict[str, str]:
    """Top-level key/value pairs of a SKILL.md frontmatter block, the way the platform parses them."""
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


def _pack(name: str) -> Path:
    """Build the one top-level directory the platform demands, named exactly like the frontmatter name."""
    path = _skill_path(name)
    fields = _frontmatter(path)
    fm_name, desc = fields.get("name", ""), fields.get("description", "")
    problems = []
    if not NAME_RE.match(fm_name) or len(fm_name) > 64:
        problems.append(f"name {fm_name!r} violates ^[a-z0-9][a-z0-9_-]*$ (max 64)")
    if path.parent.name != fm_name:
        problems.append(f"directory {path.parent.name!r} must equal frontmatter name {fm_name!r}")
    if not desc or len(desc) > 5120:
        problems.append(f"description length {len(desc)} is outside 1..5120")
    for key, value in fields.items():
        if ": " in value:
            problems.append(f"{key}: contains ': ' and must be quoted or reworded")
    if problems:
        raise SystemExit(f"{path}: " + "; ".join(problems))
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = PACK_DIR / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(path, f"{fm_name}/SKILL.md", compress_type=zipfile.ZIP_DEFLATED)
    return zip_path


def _post_multipart(path: str, parts: list, apply: bool) -> dict:
    """One multipart POST. `parts` are (field, value) or (field, (filename, bytes, content-type))."""
    boundary = "tycheManagedSkillBoundary7c1f"
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
    body = b"".join(out)
    print(f"POST {cloud_api.BASE}{path}  ({len(body)} bytes, {len(parts)} part(s))")
    for part in parts:
        if isinstance(part[1], tuple):
            print(f"  file field {part[0]!r}: {part[1][0]} sha256 "
                  f"{hashlib.sha256(part[1][1]).hexdigest()[:16]}")
        else:
            print(f"  field {part[0]!r}: {part[1]}")
    if not apply:
        print("  DRY RUN - nothing sent; re-run with --apply")
        return {}
    request = urllib.request.Request(
        cloud_api.BASE + path, data=body, method="POST",
        headers={"Authorization": f"Bearer {cloud_api._pat()}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def cmd_publish_skill(args) -> str | None:
    """Add an immutable version to an existing Managed skill; pins are a separate, deliberate step."""
    name = args.skill
    skill_id = _skill_id(name)
    roles = SKILLS[name]["roles"]
    rel = _skill_path(name).relative_to(ROOT).as_posix()
    zip_path = _pack(name)
    before = cloud_api.req("GET", f"/skills/{skill_id}")
    pins = {r: next((s.get("version") for s in (_agent(r).get("skills") or [])
                     if s.get("skill_id") == skill_id), None) for r in roles}
    print(f"skill {name} ({skill_id}) roles {roles}")
    print(f"  latest_version now {before.get('latest_version')}; pins {pins}")
    print(f"  package {zip_path.name} {zip_path.stat().st_size} bytes from {rel}")
    if not args.apply:
        print("  body sent: the zip only. display_title and metadata are immutable and are not re-sent.")
        return
    item = _post_multipart(f"/skills/{skill_id}/versions",
                           [("files", (zip_path.name, zip_path.read_bytes(), "application/zip"))], True)
    version = item.get("version") or item.get("item", {}).get("version")
    after = cloud_api.req("GET", f"/skills/{skill_id}")
    rows = cloud_api.req("GET", f"/skills/{skill_id}/versions").get("data") or []
    print(f"  ack version {version}; skill latest_version {after.get('latest_version')}; "
          f"{len(rows)} version(s) on record: {[r.get('version') for r in rows]}")
    body = _version_content(skill_id, version or after.get("latest_version"))
    local = _skill_path(name).read_text(encoding="utf-8")
    if body is None:
        print("  content round-trip: shape unknown, not claimed. Keys seen printed above.")
    elif body.splitlines() == local.splitlines():
        note = " (line endings normalised in transit; the text is the same)" if body != local else ""
        print(f"  content round-trip: MATCHES {rel} {len(body)} chars{note}")
    else:
        diff = [l for l in difflib.unified_diff(local.splitlines(), body.splitlines(),
                                                fromfile="local", tofile="cloud", lineterm="")][:20]
        print(f"  content round-trip: DIFFERS from {rel} {len(body)} chars vs {len(local)}")
        print("\n".join(diff))
    new_version = version or after.get("latest_version")
    for r in roles:
        print(f"  nothing re-pinned: {r} still runs {pins[r]} until "
              f"`attach {r} --skill-id {skill_id} --version {new_version} --apply`")
    return new_version


def cmd_ship_skill(args) -> None:
    """One paste for an edited repo skill: publish a version, re-pin it on every role that carries it,
    re-pin those children in the desk roster, then move the desk card to the new desk version.

    Each write is the same single-field-group write the separate subcommands make (and prints the same
    before/after proof); this only saves copying opaque version strings between them by hand.
    """
    name = args.skill
    skill_id = _skill_id(name)
    roles = SKILLS[name]["roles"]
    if not args.apply:
        print(f"DRY RUN ship-skill {name} ({skill_id}) for roles {roles}:")
        print("  1. publish-skill (new immutable version)")
        print(f"  2. attach {', '.join(roles)} to that version")
        children = [r for r in roles if r != "coordinator"]
        if children:
            print(f"  3. roster re-pin {', '.join(children)} on the desk")
        print(f"  4. pin-card {', '.join(CARD_IDS)} to the new desk version")
        print("  nothing sent; re-run with --apply")
        return
    version = cmd_publish_skill(argparse.Namespace(skill=name, apply=True))
    if not version:
        raise SystemExit("publish returned no version; nothing re-pinned")
    pins = []
    for role in roles:
        print(f"-- attach {role}")
        cmd_attach(argparse.Namespace(role=role, skill_id=skill_id, version=version, add=False, apply=True))
        if role != "coordinator":
            pins.append(f"{role}={_agent(role)['version']}")
    if pins:
        print(f"-- roster {pins}")
        cmd_roster(argparse.Namespace(pin=pins, apply=True))
    for card in CARD_IDS:
        print(f"-- pin-card {card}")
        cmd_pin_card(argparse.Namespace(card=card, version=None, apply=True))
    print(f"shipped {name} {version}; run `verify` to see every agent against the baseline")


def cmd_create_skill(args) -> None:
    """Create the Managed skill object for a repo skill that has none yet (first version included).

    One multipart POST to /skills, the same shape the retired deploy_role_skills.py used on 2026-11-21.
    The platform answers with the skill id and its first latest_version: record the id in SKILLS, then
    `attach <role> --skill-id <id> --version <latest_version> --add --apply` for each role, and finish
    with `pin-card`, because a skills write bumps the agent version the card pins.
    """
    name = args.skill
    if SKILLS[name]["id"]:
        raise SystemExit(f"{name} already exists as {SKILLS[name]['id']}; use publish-skill for a new version")
    zip_path = _pack(name)
    rel = _skill_path(name).relative_to(ROOT).as_posix()
    roles = SKILLS[name]["roles"]
    # metadata values must be strings (the platform answers 400 to a list), so the roles join on "/"
    parts = [
        ("display_title", f"tyche {'/'.join(roles)} {name}"),
        ("metadata", json.dumps({"roles": "/".join(roles), "source_path": rel,
                                 "managed_by": "scripts/deploy_managed_agents.py"})),
        ("files", (zip_path.name, zip_path.read_bytes(), "application/zip")),
    ]
    print(f"create skill {name} for roles {roles} from {rel} ({zip_path.stat().st_size} bytes)")
    item = _post_multipart("/skills", parts, args.apply)
    if not args.apply:
        return
    skill_id = item.get("id") or item.get("item", {}).get("id")
    latest = item.get("latest_version") or item.get("item", {}).get("latest_version")
    print(f"  created {skill_id} latest_version {latest}")
    print(f"  next: set SKILLS[{name!r}]['id'] = {skill_id!r} in this file, then for each role:")
    for r in roles:
        print(f"    attach {r} --skill-id {skill_id} --version {latest} --add --apply")
    print("  then pin-card for the live desk card.")


def _version_content(skill_id: str, version: str) -> str | None:
    """Fetch a version's package back and return the SKILL.md text, or None if the shape is unfamiliar.

    The route answers with the bytes of the upload, not JSON, so it is read raw; cloud_api.req would try
    to decode it as text and fail on the zip.
    """
    request = urllib.request.Request(
        f"{cloud_api.BASE}/skills/{skill_id}/versions/{version}/content",
        headers={"Authorization": f"Bearer {cloud_api._pat()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            blob = response.read()
            ctype = response.headers.get_content_type()
    except OSError as exc:
        print(f"  content round-trip unavailable: {exc}")
        return None
    print(f"  content response: {len(blob)} bytes, {ctype}")
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = [n for n in archive.namelist() if n.endswith("SKILL.md")]
            if not names:
                print(f"  package members: {archive.namelist()}")
                return None
            return archive.read(names[0]).decode()
    return blob.decode("utf-8", errors="replace")


CARD_FIELDS = ("name", "description", "status", "environment_id", "vault_ids", "metadata", "resources",
               "schedule", "agent")


def _env_keys(raw) -> list[str]:
    """Key names from a card's environment_variables, never its values.

    The API hands that field back in plaintext - the Telegram bot token and the account allowlist among
    them - so no projection, snapshot or log line may carry it. `initial_events` is hashed instead of
    stored, for the same reason: the card brief is prose, but the blob is where a hand-edit would appear.
    """
    if isinstance(raw, str):
        return sorted(l.split("=", 1)[0] for l in raw.splitlines() if "=" in l)
    if isinstance(raw, dict):
        return sorted(raw)
    return []


def _card_view(card: dict) -> dict:
    view = {key: card.get(key) for key in CARD_FIELDS}
    events = json.dumps(card.get("initial_events") or "")
    view["initial_events_chars"] = len(events)
    view["initial_events_sha256"] = _sha(events)
    view["env_keys"] = _env_keys(card.get("environment_variables"))
    return view


def cmd_pin_card(args) -> None:
    """Move a scheduled card's desk pin, which is the only thing that decides what actually fires."""
    card = cloud_api.req("GET", f"/deployments/{args.card}")
    agent = card.get("agent") or {}
    head = _agent("coordinator")
    if agent.get("id") != head["id"]:
        raise SystemExit(f"{args.card} pins {agent.get('id')}, not the desk coordinator; refusing")
    target = args.version or head["version"]
    if target != head["version"]:
        raise SystemExit(f"the live coordinator is v{head['version']}; v{target} is not what is authored - "
                         "pin the current version or author it first")
    before = _card_view(card)
    body = {"agent": {"id": agent["id"], "type": agent.get("type") or "agent", "version": target}}
    print(f"card {args.card} ({card.get('name')}) status {card.get('status')}")
    print(f"  pin before v{agent.get('version')} -> v{target}; body sent {json.dumps(body)}")
    print(f"  compared fields: {sorted(CARD_FIELDS)} + initial_events + env_keys")
    print(f"  cron {(card.get('schedule') or {}).get('expression')} "
          f"{(card.get('schedule') or {}).get('timezone')}; env keys {before['env_keys']} "
          f"(values never read or stored)")
    if not args.apply:
        print("  DRY RUN - nothing sent; re-run with --apply")
        return
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    snap = EXPORT_DIR / f"card-{args.card}-pre-pin.json"
    snap.write_text(json.dumps(before, indent=1, sort_keys=True, default=str), encoding="utf-8")
    cloud_api.req("POST", f"/deployments/{args.card}", body)
    after = _card_view(cloud_api.req("GET", f"/deployments/{args.card}"))
    if (after.get("agent") or {}).get("version") != target:
        raise SystemExit(f"the pin did not move to v{target}; restore from {snap.name}")
    drift = sorted(k for k in before if before[k] != after[k] and k != "agent")
    print(f"  pin now v{after['agent'].get('version')}; fields that moved beyond the agent block: "
          f"{drift or '(none)'}")
    if drift:
        raise SystemExit(f"{drift} changed under a pin-only write - restore from {snap.name} and inspect")
    print(f"  prompt {after['initial_events_chars']} chars sha "
          f"{after['initial_events_sha256'][:12]}; cron {after['schedule'].get('expression')}; "
          f"status {after['status']} (redacted before-state in {snap.name})")


def cmd_verify(args) -> None:
    roles = [args.role] if args.role else list(ROLE_AGENTS)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    print(f"verify at {_now()} against {BASELINE.name if baseline else 'no baseline'}")
    for role in roles:
        a = _agent(role)
        now = _view(a)
        _print_view(now, "live")
        was = baseline.get(role)
        if not was:
            print("  (no baseline row; run export first)")
            continue
        drift = [k for k in now if now[k] != was.get(k, now[k])]
        print(f"  vs baseline v{was.get('version')}: "
              f"{'no drift' if not drift else 'DRIFT in ' + str(sorted(drift))}")
        for key in sorted(drift):
            print(f"    {key}: {json.dumps(was.get(key), default=str)[:90]} -> "
                  f"{json.dumps(now[key], default=str)[:90]}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    x = sub.add_parser("export")
    x.add_argument("--prompts", action="store_true",
                   help="also refresh templates/prompts/live/*.md from the live agents")
    x.set_defaults(func=cmd_export)

    d = sub.add_parser("diff")
    d.add_argument("role", choices=sorted(ROLE_AGENTS))
    d.add_argument("--file", required=True)
    d.add_argument("--compact", action="store_true")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("apply-system")
    s.add_argument("role", choices=sorted(ROLE_AGENTS))
    s.add_argument("--file", required=True)
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_apply_system)

    t = sub.add_parser("attach")
    t.add_argument("role", choices=sorted(ROLE_AGENTS))
    t.add_argument("--skill-id", required=True)
    t.add_argument("--version", required=True, help="the opaque latest_version string, verbatim")
    t.add_argument("--add", action="store_true", help="bind a skill the role does not carry yet")
    t.add_argument("--apply", action="store_true")
    t.set_defaults(func=cmd_attach)

    k = sub.add_parser("publish-skill")
    k.add_argument("skill", choices=sorted(SKILLS))
    k.add_argument("--apply", action="store_true")
    k.set_defaults(func=cmd_publish_skill)

    h = sub.add_parser("ship-skill", help="publish an edited skill and re-pin it all the way to the desk card")
    h.add_argument("skill", choices=sorted(n for n, s in SKILLS.items() if s["id"]))
    h.add_argument("--apply", action="store_true")
    h.set_defaults(func=cmd_ship_skill)

    n = sub.add_parser("create-skill", help="create the cloud object for a repo skill that has none yet")
    n.add_argument("skill", choices=sorted(n for n, s in SKILLS.items() if not s["id"]))
    n.add_argument("--apply", action="store_true")
    n.set_defaults(func=cmd_create_skill)

    c = sub.add_parser("pin-card")
    c.add_argument("card", choices=sorted(CARD_IDS))
    c.add_argument("--version", type=int, help="defaults to the live coordinator version")
    c.add_argument("--apply", action="store_true")
    c.set_defaults(func=cmd_pin_card)

    r = sub.add_parser("roster")
    r.add_argument("--pin", action="append", metavar="ROLE=VERSION",
                   help="one child pin to change, repeatable; numeric or 'latest'")
    r.add_argument("--apply", action="store_true")
    r.set_defaults(func=cmd_roster)

    v = sub.add_parser("verify")
    v.add_argument("role", nargs="?", choices=sorted(ROLE_AGENTS))
    v.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
