"""Apply the operator-approved stale-caps re-pin (L-033; docs/reviews/2026-11-21-prompt-repin-proposal.md).

Templates are the editable source, agents are compiled artifacts, and the desk roster plus the scheduled
deployment cards each pin an exact compiled version - so a re-pin that stops at the template changes
nothing the next run actually sees. This walks the whole chain: the auditor and researcher templates, then
the desk template *and* its roster pins in one write (one desk version, not two), then - only under
`--apply-deployments` - the scheduled desk cards.

Every edit is a byte-exact replacement asserted to match exactly once, so a pin that drifted since the
proposal was reviewed aborts instead of shipping a prompt nobody read. Pre-change state is snapshotted to
gitignored plans/, and each write is followed by an invariance check on model, tools, MCP servers, vaults,
env *keys* and the repo mount (L-023: a recompile has silently dropped a needed tool before). Secret
values are never read out or printed.

Usage: python scripts/repin_stale_caps.py [--check] [--apply-deployments]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward

CLOUD = "https://api.qoder.com/api/v1/cloud"
PLANS = ROOT / "plans"
CHECK = "--check" in sys.argv

DESK = "tmpl_004fa008901a6c256bd0ed3f"
DESK_AGENT = "agent_00vtt1wjgm22o20s8ykz"
# The pin the operator reviewed in the proposal (data/capture-2026-11-21-repin). A card holding any
# other version was moved by someone else and is left alone rather than overwritten.
REVIEWED_PIN = 28
# The advisor row exactly as it read on the desk template immediately before the 2026-11-21 re-pin
# dropped it (L-045). Recorded here so the restore is reviewable rather than improvised.
ADVISOR = {"model": "qmodel_38max", "type": "advisor"}
EXECUTOR = "tmpl_bc25a5c313827d53894fd7ff"

# No child of the desk may reach an order write. A substring rule is the wrong shape here - it fires on
# read-only tools like quote_insider_trade_list - so the grant is stated positively (every MCP tool a child
# may reach starts with a market-data prefix) and negatively (none of the known order verbs).
READ_ONLY_PREFIXES = ("quote_", "news_")
ORDER_WRITE_NAMES = {"sim_trade_input_order", "trading_order_place", "trading_order_cancel",
                     "trading_order_modify", "sim_trade_place_order", "trading_approve"}

AUDITOR_OLD = ("Enforce current exact YAML/kernel limits including pending buys and held positions, "
               "40 daily entry orders, 200 competition total orders, 150% buy turnover and <=100 positions.")
AUDITOR_NEW = ("Enforce the current exact YAML/kernel limits including pending buys and held positions, "
               "read from config/risk.yaml on this run - the daily order budget, competition order ceiling, "
               "turnover cap and position count are configured there, never recited from memory. Those "
               "values have already been raised twice as lanes landed, and a stale number in this prompt "
               "reads as authority while the kernel's verdict is the real one (L-033).")

DESK_OLD = ("5%, soft/hard DD 4%/6%, <=40 entry orders/day, <=200 total competition orders/day, turnover "
            "and underlying concentration per exact config.")
DESK_NEW = ("5%, soft/hard DD 4%/6%. The daily order budget, competition order ceiling, turnover and "
            "underlying concentration come from config/risk.yaml and the kernel's verdict on this run, "
            "never from a number quoted here: the caps move when a lane lands, and a stale figure in a "
            "prompt is a second, wrong authority (L-033).")

RESEARCHER_OLD = ("ARSENAL: keep PB-001 ETF rotation as ballast (25% ceiling); add catalyst-driven long "
                  "stocks (45% ceiling) and standard single-leg long calls/long puts (25% premium ceiling), "
                  "cash >=5%. These are maximum allocations, never mandatory investment targets.")
RESEARCHER_NEW = (RESEARCHER_OLD + " Which lanes are actually mounted is not stated here: the run brief "
                  "names the live playbook ids and it wins - propose only inside the ids the brief reports, "
                  "and treat a lane missing from it as research, not as a proposal. A switched-off lane "
                  "still runs its exits, stops and targets, so its holdings stay relevant even though its "
                  "entries are not.")

CHILDREN = [
    {"name": "tyche-risk-auditor", "template": "tmpl_ae317cc0626a4fcc8fa8fad6",
     "agent": "agent_00vtx8g7k1534t7w9eve", "old": AUDITOR_OLD, "new": AUDITOR_NEW,
     "marker": "never recited from memory"},
    {"name": "tyche-researcher", "template": "tmpl_875834770244a9e35c7f6499",
     "agent": "agent_00vs9v3dg0rnkr4740x3", "old": RESEARCHER_OLD, "new": RESEARCHER_NEW,
     "marker": "the run brief names the live playbook ids"},
]
DESK_EDIT = {"name": "tyche-desk", "template": DESK, "agent": DESK_AGENT,
             "old": DESK_OLD, "new": DESK_NEW, "marker": "a second, wrong authority (L-033)"}

STALE_AFTER = ("40 daily entry orders", "<=40 entry orders/day", "<=200 total competition orders",
               "150% buy turnover", "<=100 positions", "200 competition total orders")

ALLOWLISTS = {
    "tyche-risk-auditor": {"builtins": ["Read", "Glob", "Grep", "Write"], "mcp_servers": [], "mcp_tools": 0},
    "tyche-desk": {"builtins": ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch",
                                "DeliverArtifacts"], "mcp_servers": [], "mcp_tools": 0},
    "tyche-researcher": {"builtins": ["Read", "Write", "Glob", "Grep", "WebSearch", "WebFetch"],
                         "mcp_servers": ["moomoo"], "mcp_tools": 24},
}


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def cloud(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        CLOUD + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {forward.pat()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        raise SystemExit(f"HTTP {error.code} on cloud {method} {path}: {error.read().decode()[:600]}")


def snapshot(name: str, obj: Any) -> Path:
    PLANS.mkdir(exist_ok=True)
    out = PLANS / name
    out.write_text(json.dumps({"retrieved_at": stamp(), "data": obj}, indent=2), encoding="utf-8")
    return out


def version_of(cfg: dict, label: str) -> int:
    version = cfg.get("version", (cfg.get("item") or {}).get("version"))
    if not isinstance(version, int):
        raise SystemExit(f"{label}: compiled agent version is {version!r}, not an int")
    return version


def grants(cfg: dict) -> dict:
    """The capability surface a template or compiled agent actually carries."""
    toolsets = [t for t in cfg.get("tools") or [] if str(t.get("type", "")).startswith("agent_toolset")]
    configs = [c for t in cfg.get("tools") or [] for c in (t.get("configs") or [])]
    return {
        "builtins": list((toolsets[0].get("enabled_tools") or []) if toolsets else []),
        "mcp_servers": [m.get("name") for m in cfg.get("mcp_servers") or []],
        "mcp_enabled": sorted(c["name"] for c in configs if c.get("enabled") is True),
        "mcp_disabled": sorted(c["name"] for c in configs if c.get("enabled") is False),
    }


def assert_allowlist(name: str, cfg: dict, where: str) -> str:
    """L-023: a recompile can silently drop or widen a grant, so the reviewed shape is re-asserted."""
    want, got = ALLOWLISTS[name], grants(cfg)
    if sorted(got["builtins"]) != sorted(want["builtins"]):
        raise SystemExit(f"{name} ({where}): built-in tools are {got['builtins']}, expected {want['builtins']}")
    if got["mcp_servers"] != want["mcp_servers"]:
        raise SystemExit(f"{name} ({where}): MCP servers are {got['mcp_servers']}, expected {want['mcp_servers']}")
    if len(got["mcp_enabled"]) != want["mcp_tools"] or got["mcp_disabled"]:
        raise SystemExit(f"{name} ({where}): MCP grants drifted - {len(got['mcp_enabled'])} enabled, "
                         f"{got['mcp_disabled']} disabled")
    not_read_only = [t for t in got["mcp_enabled"] if not t.startswith(READ_ONLY_PREFIXES)]
    if not_read_only:
        raise SystemExit(f"{name} ({where}): MCP tools outside the read-only prefixes "
                         f"{READ_ONLY_PREFIXES}: {not_read_only}")
    blocked = sorted(set(got["mcp_enabled"]) & ORDER_WRITE_NAMES)
    if blocked:
        raise SystemExit(f"{name} ({where}): order-write tool reachable: {blocked}")
    return (f"{len(got['builtins'])} built-ins, MCP {got['mcp_servers']} with {len(got['mcp_enabled'])} "
            f"read-only tools, no order-write")


def invariants(cfg: dict) -> dict:
    """Everything a prompt edit must not move. Env values reduce to their key names only."""
    return {
        "name": cfg.get("name"),
        "model": cfg.get("model"),
        "tools": cfg.get("tools"),
        "mcp_servers": cfg.get("mcp_servers"),
        "skills": cfg.get("skills"),
        "vaults": cfg.get("vaults"),
        "github_repositories": cfg.get("github_repositories"),
        "environment_id": cfg.get("environment_id"),
        "environment_keys": sorted((cfg.get("environment_variables") or {}).keys()),
    }


def roster(template: dict) -> dict:
    return template.get("multiagent") or {}


def roster_entries(template: dict) -> list[dict]:
    """The child-agent rows of the roster - for *reading* pins, never for rebuilding the roster."""
    return [e for e in roster(template).get("agents") or [] if e.get("type") == "agent"]


def non_agent_entries(multiagent: dict) -> list[dict]:
    """The model-only roster rows, e.g. the advisor (ADR 0011: three roles + coordinator + advisor)."""
    return [e for e in multiagent.get("agents") or [] if e.get("type") != "agent"]


def replace_once(system: str, edit: dict) -> str:
    hits = system.count(edit["old"])
    if hits != 1:
        raise SystemExit(f"{edit['name']}: the reviewed OLD text occurs {hits} times, not exactly once - "
                         "the pin has drifted since the proposal was written, so nothing was sent")
    return system.replace(edit["old"], edit["new"])


def wait_for_recompile(edit: dict, previous: int) -> int:
    """A template write recompiles its agent; the roster must pin the new version, never the old one."""
    deadline = time.time() + 90
    while time.time() < deadline:
        version = version_of(cloud("GET", f"/agents/{edit['agent']}"), edit["name"])
        if version != previous:
            print(f"{edit['name']}: compiled agent v{previous} -> v{version}")
            return version
        time.sleep(3)
    raise SystemExit(f"{edit['name']}: compiled agent is still v{previous} 90s after the write; "
                     "nothing downstream was pinned")


def apply_template(edit: dict, *, pin: dict[str, int] | None = None) -> int:
    """One byte-exact prompt edit (plus, for the desk, its roster pins) and the checks that prove it."""
    name, tid = edit["name"], edit["template"]
    before = forward.req("GET", f"/templates/{tid}")
    system = before.get("system") or ""
    previous = version_of(cloud("GET", f"/agents/{edit['agent']}"), name)
    if edit["marker"] in system:
        print(f"{name}: clause already present at v{previous} - no prompt change to send")
        wrote, new_system = False, system
    else:
        new_system = replace_once(system, edit)
        wrote = True
    body: dict[str, Any] = {"name": before["name"], "system": new_system}
    if pin:
        if pin_moved(before, pin):
            print(f"{name}: roster pins already current")
        body["multiagent"] = renumber(roster(before), pin, name)
    # A pin move recompiles on its own, so "changed" is the prompt or the roster, not just the prompt.
    changed = wrote or (pin is not None and not pin_moved(before, pin))
    snap = snapshot(f"cloud-{name}-pre-repin.json", before)
    if CHECK:
        print(f"{name}: CHECK only - would send {len(system)} -> {len(new_system)} chars, "
              f"pins {pin or {}}, agent v{previous} -> v{previous + 1 if changed else previous} "
              f"(snapshot {snap.name})")
        return previous + 1 if changed else previous
    if not changed:
        return previous
    forward.req("POST", f"/templates/{tid}", body)
    print(f"{name}: template written ({len(system)} -> {len(new_system)} chars, system sha "
          f"{sha(new_system)[:12]}, snapshot {snap.name})")

    after = forward.req("GET", f"/templates/{tid}")
    if after.get("system") != new_system:
        raise SystemExit(f"{name}: the stored system differs from the reviewed text")
    if after.get("system", "").count(edit["marker"]) != 1:
        raise SystemExit(f"{name}: the clause is not present exactly once after the write")
    stale = [s for s in STALE_AFTER if s in after.get("system", "")]
    if stale:
        raise SystemExit(f"{name}: stale cap text survived the write: {stale}")
    if invariants(after) != invariants(before):
        raise SystemExit(f"{name}: model/tools/MCP/vaults/env-keys/mount drifted across the write")
    if pin:
        got = {e.get("template_id"): e.get("version") for e in roster_entries(after)}
        if {k: v for k, v in got.items() if k in pin} != pin:
            raise SystemExit(f"{name}: roster did not land - {got} vs {pin}")
        if non_agent_entries(roster(after)) != non_agent_entries(roster(before)):
            raise SystemExit(f"{name}: the model-only roster rows changed - "
                             f"{non_agent_entries(roster(before))} -> {non_agent_entries(roster(after))}")
        print(f"{name}: roster pins {got}, model-only rows {non_agent_entries(roster(after))} preserved")
    print(f"{name}: verify: clause exact, no stale caps, grants+vaults+env-keys+mount unchanged, "
          f"allowlist - {assert_allowlist(name, after, 'template')}")
    return wait_for_recompile(edit, previous) if changed else previous


def strip_desk_managed_grant(desk_version: int) -> int:
    """Remove the platform's drive/schedule tool group from the desk, the operator's reviewed choice.

    The desk template carried `managed_tool_config: {"enabled_tools": ["drive", "schedule"]}`, which v28
    never materialized and v29 did: ten always-allow tools that let an unattended run reshape its own
    Forward schedules and delete Drive entries. v28 ran the documented Drive persistence through the mount
    with Bash/Write and zero MCP servers, so the empty grant is the surface that was actually reviewed
    (L-023), and the card's own "the paused Forward schedule must remain paused, never two writers" line
    stops being the only thing enforcing it.
    """
    before = forward.req("GET", f"/templates/{DESK}")
    groups = (before.get("managed_tool_config") or {}).get("enabled_tools") or []
    if not groups:
        print("desk: managed platform grant is already empty")
        return desk_version
    snap = snapshot("cloud-tyche-desk-pre-ungrant.json", before)
    if CHECK:
        print(f"desk: CHECK only - would clear managed_tool_config {groups} (snapshot {snap.name})")
        return desk_version + 1
    forward.req("POST", f"/templates/{DESK}", {"managed_tool_config": {"enabled_tools": []}})
    after = forward.req("GET", f"/templates/{DESK}")
    left = (after.get("managed_tool_config") or {}).get("enabled_tools")
    if left:
        raise SystemExit(f"desk: managed grant still holds {left} after the write; restore from "
                         f"plans/{snap.name}")
    if after.get("system") != before.get("system"):
        raise SystemExit("desk: the prompt moved under a grant-only write - inspect before pinning anything")
    if roster_entries(after) != roster_entries(before):
        raise SystemExit("desk: the roster moved under a grant-only write")
    if invariants(after) != invariants(before):
        raise SystemExit("desk: tools/vaults/env-keys/mount drifted under the grant write")
    print(f"desk: managed grant {groups} -> [] (snapshot {snap.name}); prompt and roster byte-identical")
    edit = {**DESK_EDIT, "marker": "unused - no prompt write here"}
    return wait_for_recompile(edit, desk_version)


def pin_moved(template: dict, pin: dict[str, int]) -> bool:
    if not pin:
        return False
    got = {e.get("template_id"): e.get("version") for e in roster_entries(template)}
    return all(got.get(k) == v for k, v in pin.items())


def restore_desk_advisor(desk_version: int) -> int:
    """Put back what a filtered roster rebuild dropped: the desk's model-only advisor row (L-045).

    The 2026-11-21 re-pin rebuilt `multiagent` from the rows that carry a `template_id`, which silently
    deleted the advisor - a topology member ADR 0011 names deliberately ("Advisor - model-only critique,
    advisory; its failure does not block"). If the roster already holds any non-agent row nothing is
    touched, so this is a repair, not a standing preference for one model id.
    """
    before = forward.req("GET", f"/templates/{DESK}")
    if non_agent_entries(roster(before)):
        print(f"desk: roster keeps its model-only rows - {non_agent_entries(roster(before))}")
        return desk_version
    snap = snapshot("cloud-tyche-desk-pre-advisor-restore.json", roster(before))
    fixed = json.loads(json.dumps(roster(before)))
    fixed["agents"] = list(fixed.get("agents") or []) + [dict(ADVISOR)]
    if CHECK:
        print(f"desk: CHECK only - would restore the advisor row {ADVISOR} (snapshot {snap.name})")
        return desk_version + 1
    forward.req("POST", f"/templates/{DESK}", {"multiagent": fixed})
    after = forward.req("GET", f"/templates/{DESK}")
    if non_agent_entries(roster(after)) != [dict(ADVISOR)]:
        raise SystemExit(f"desk: advisor row did not land - {non_agent_entries(roster(after))}")
    if roster_entries(after) != roster_entries(before):
        raise SystemExit("desk: the child pins moved while restoring the advisor")
    if after.get("system") != before.get("system") or invariants(after) != invariants(before):
        raise SystemExit("desk: prompt or grants changed under a roster-only write")
    print(f"desk: advisor row restored (snapshot {snap.name}); children and prompt byte-identical")
    return wait_for_recompile(DESK_EDIT, desk_version)


def renumber(multiagent: dict, pin: dict[str, int], name: str) -> dict:
    """Move only the listed child pins; every other roster row is carried through byte-identically.

    Rebuilding the roster from a filtered view is how the advisor got dropped once (L-045), so this takes
    the whole object, touches nothing it was not told to touch, and the caller diffs the rest afterwards.
    """
    out = json.loads(json.dumps(multiagent))
    seen = set()
    for entry in out.get("agents") or []:
        tid = entry.get("template_id")
        if tid in pin:
            print(f"{name}: roster {tid} {entry.get('version')} -> {pin[tid]}")
            entry["version"] = pin[tid]
            seen.add(tid)
    missing = set(pin) - seen
    if missing:
        raise SystemExit(f"{name}: {sorted(missing)} not on the desk roster - a blind pin would "
                         "leave the edited child unpinned")
    return out


def move_deployments(desk_version: int) -> None:
    """The scheduled cards pin an exact desk version, so the re-pin is not live until they move."""
    listing = cloud("GET", "/deployments")
    cards = listing.get("data") or listing.get("items") or []
    if not cards:
        raise SystemExit("no deployment cards came back from the cloud API - refusing to call that all clear")
    for card in cards:
        agent = card.get("agent") or {}
        did = card.get("id")
        if agent.get("id") != DESK_AGENT or not str(card.get("name", "")).startswith("Tyche desk"):
            print(f"deployment {did}: not a Tyche desk card - left alone")
            continue
        before = cloud("GET", f"/deployments/{did}")
        pinned = (before.get("agent") or {}).get("version")
        if pinned == desk_version:
            print(f"deployment {did} ({before.get('name')}): already pins v{desk_version}")
            continue
        if not isinstance(pinned, int) or pinned >= desk_version:
            print(f"deployment {did}: pins {pinned!r}, which is not an older build than "
                  f"v{desk_version} - left alone, re-pin by hand")
            continue
        snap = snapshot(f"cloud-deployment-{did}-pre-repin.json", before)
        if CHECK:
            print(f"deployment {did}: CHECK only - would move agent v{pinned} -> v{desk_version} "
                  f"(snapshot {snap.name})")
            continue
        cloud("POST", f"/deployments/{did}",
              {"agent": {"id": DESK_AGENT, "type": "agent", "version": desk_version}})
        after = cloud("GET", f"/deployments/{did}")
        if (after.get("agent") or {}).get("version") != desk_version:
            raise SystemExit(f"deployment {did}: the pin did not move to v{desk_version}; restore from "
                             f"plans/cloud-deployment-{did}-pre-repin.json")
        keep = ("name", "description", "status", "environment_id", "vault_ids", "metadata", "resources",
                "schedule", "initial_events")
        drift = [k for k in keep if json.dumps(before.get(k), sort_keys=True)
                 != json.dumps(after.get(k), sort_keys=True)]
        if drift:
            raise SystemExit(f"deployment {did}: fields {drift} changed - only the pin may move. Restore "
                             f"from plans/cloud-deployment-{did}-pre-repin.json and inspect")
        events = json.dumps(after.get("initial_events") or "")
        sched = after.get("schedule") or {}
        print(f"deployment {did} ({after.get('name')}): agent v{pinned} -> v{desk_version}; "
              f"card prompt {sha(events)[:12]} ({len(events)} chars), cron "
              f"{sched.get('expression')} {sched.get('timezone')} and env keys unchanged")


def main() -> None:
    # The executor pin is carried through untouched; reading it before any write is what lets the desk
    # write assert that the one child nobody edited stayed where it was.
    executor_pin = next(e["version"] for e in roster_entries(forward.req("GET", f"/templates/{DESK}"))
                        if e.get("template_id") == EXECUTOR)
    desk_previous = version_of(cloud("GET", f"/agents/{DESK_AGENT}"), "tyche-desk")
    versions: dict[str, int] = {}
    for edit in CHILDREN:
        versions[edit["template"]] = apply_template(edit)
    desk_version = apply_template(DESK_EDIT, pin={**versions, EXECUTOR: executor_pin})
    desk_version = strip_desk_managed_grant(desk_version)
    desk_version = restore_desk_advisor(desk_version)
    desk_agent = cloud("GET", f"/agents/{DESK_AGENT}")
    if version_of(desk_agent, "desk") != desk_version:
        raise SystemExit(f"desk: the card would be pinned to v{desk_version} but the agent reads "
                         f"v{desk_agent.get('version')}")
    print(f"desk compiled agent is v{version_of(desk_agent, 'desk')}: "
          f"allowlist - {assert_allowlist('tyche-desk', desk_agent, 'compiled agent')}")
    for edit in CHILDREN:
        agent = cloud("GET", f"/agents/{edit['agent']}")
        print(f"{edit['name']} compiled agent is v{version_of(agent, edit['name'])}: "
              f"allowlist - {assert_allowlist(edit['name'], agent, 'compiled agent')}")
    if "--apply-deployments" in sys.argv:
        move_deployments(desk_version)
    else:
        print(f"deployments untouched - the cards still pin v{desk_previous}; re-run with "
              "--apply-deployments to move them onto the verified pin")
    print("DONE: stale caps are out of the three prompts and every pin downstream of them moved; "
          "only new sessions pick up a new pin (L-021)")
    print(json.dumps({"auditor": versions[CHILDREN[0]["template"]],
                      "researcher": versions[CHILDREN[1]["template"]],
                      "desk": desk_version}, indent=2))


if __name__ == "__main__":
    main()
