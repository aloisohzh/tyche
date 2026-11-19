from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request

import forward

TEMPLATES = {
    "desk": "tmpl_004fa008901a6c256bd0ed3f",
    "researcher": "tmpl_875834770244a9e35c7f6499",
    "auditor": "tmpl_ae317cc0626a4fcc8fa8fad6",
    "executor": "tmpl_bc25a5c313827d53894fd7ff",
}
SCHEDULE = "sched_2dc7702e4f005d04235c078a"
PROTECTED = (
    "tools", "mcp_servers", "vaults", "environment_variables", "github_repositories",
    "environment_id", "model", "skills", "files", "tunnel_id", "managed_tool_config", "name",
)
MODE = (
    "HOURLY VALIDATION MODE (2026-11-19): the operator approved hourly-first deployment and "
    "controlled paper validation in the existing Qoder session. Scheduled screening and position "
    "review use tyche-hourly; no two-minute worker, new schedule or duplicate authentication is "
    "required. Production orders remain NOT RELEASED until actual operational validation and "
    "an operator-reviewed activation. Deployment permission is not an exact setup approval, "
    "auditor evidence or a broker fill. Do not change execution gates or manufacture grants. "
    "A separately supplied complete, previewed and operator-approved validation contract may "
    "authorize a bounded regular-session paper drill only after the existing reserve/audit/state "
    "checks pass. Without that exact contract, do not submit. Options require their own real "
    "entry/exit validation before production release. Live trading is forbidden. Cancel/modify "
    "require separate per-action confirmation."
)
CADENCE = (
    "HOURLY TIMING: monitor_interval_seconds=3600, but account capture remains <=120s, tactical "
    "quote/book age <=60s and exact-order audit validity <=120s. Hourly samples can confirm an "
    "unchanged setup only after fresh targeted research; old quotes never become executable. "
    "Tactical exits anticipate the next hourly check; no entry when its exit deadline arrives "
    "before that check. Tactical plans remain same-session, not multi-day options. Stock/ETF "
    "lifecycle deadlines must fall by a scheduled RTH check with processing margin, including "
    "the Nov27 early close. Hourly synthetic exits are not resting broker stops or guaranteed "
    "fills; gaps, halts, delayed runs and nonfills can exceed planned stop loss. On-demand Qoder "
    "monitoring is read-only unless explicitly assigned the sole execution-owner role."
)
STATE = (
    "STATE AND SINGLE WRITER: the existing tyche-hourly schedule is the only scheduled execution "
    "owner, with max_concurrent_runs=1 and max_attempts=1. The other desk schedules must remain "
    "paused. Only its one executor may perform execution-state writes after release; researcher, "
    "auditor, ad-hoc monitoring and parallel sessions never independently submit. Verify schedule "
    "provenance and absence of another active writer; if ownership cannot be verified, block. "
    "A controlled operator-assigned validation owner must finish and relinquish ownership before "
    "the scheduled owner takes over. Restore the verified existing Drive journal lineage and "
    "retain all unknown reservations. The known EOD lineage is "
    "/data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl; verify later descendants first. "
    "Production lifecycle state belongs under /data/drive/tyche-raw/lifecycle. Missing state is "
    "a bootstrap/reconciliation task, not proof there were no holdings or prior orders. "
    "Initialize it only in an explicit operator-controlled bootstrap after complete broker/history "
    "reconciliation and verifying no prior ledger exists; never turn missing history into an empty "
    "journal. Do not create adoption grants from current holdings alone. Keep unowned holdings "
    "visible as protection gaps. Drive replica visibility, mkdir, flock and fsync are NOT "
    "distributed locks. Do not break locks, overwrite authority or copy it to concurrent writers."
)
CONTRACT = (
    "RESERVATION CONTRACT: only the executor uses the existing authenticated Moomoo MCP for "
    "all lifecycle and tactical submissions; the local direct-HTTP exit adapter has been "
    "removed. Do not provision another broker token or extract connector credentials. "
    "Tactical orders need a "
    "same-ET-day exact setup/config/account-bound entry AND exit envelope, fresh independent "
    "exact-order Audit and successful live-clock tyche tactical reserve. Stock/ETF orders need "
    "the exact immutable lifecycle grant and tyche lifecycle reserve. Config/rules changes require "
    "reviewed new hashes, not rewriting old grants. Reservation and journal must persist before "
    "one exact paper RTH limit order with request_id as text, strictly before submit_before. "
    "Record the receipt, then reconcile orders/positions. Receipt is not fill. Timeouts, partial "
    "fills, uncertain statuses and unmatched requests block retry. Only full status4 with exact "
    "cumulative quantity is currently verified terminal; status5 remains unresolved. No legacy "
    "authorize/execute bypass, automatic re-entry, scaling, shorts, spreads or naked options. "
    "Never invent operator or auditor references. Validation mode alone does not authorize a write."
)


def paragraph(text: str, prefix: str, replacement: str) -> str:
    pattern = re.compile(r"(?m)^" + re.escape(prefix) + r"[^\n]*(?:\n(?!\n)[^\n]+)*")
    if len(pattern.findall(text)) != 1:
        raise ValueError(f"expected exactly one policy paragraph: {prefix}")
    return pattern.sub(lambda _: replacement, text)


def engine(release: str) -> str:
    return (
        f"PINNED ENGINE: use reviewed release {release} for BOTH lifecycle and tactical code "
        "and the operator-approved 25% ETF /45% tactical stocks /25% aggregate option premium "
        "ceilings, >=5% cash and <=95% gross. Preserve the mounted repo and current reporting "
        "helpers. If its clean HEAD contains the release, use it as LC_ROOT; otherwise use a "
        "unique isolated clone of the configured authorized repository at that exact commit, "
        "never reset or overwrite concurrent work. Verify imports and pass the same absolute "
        "LC_ROOT/config-root to both lanes. Do not use old lifecycle-hourly-release 1e902cf. "
        "The MCP lifecycle capture now accepts verified standard metadata in contracts.json "
        "for ALL option holdings and history, and counts option premium with multiplier100. "
        "Missing or inconsistent metadata blocks capture; never omit options or infer metadata "
        "from premium. The lifecycle order lane itself remains stock/ETF-only. Existing per-trade, "
        "loss, allocation, liquidity, calendar and ownership controls remain unchanged."
    )


def transform(text: str, role: str, release: str) -> str:
    if "HOURLY VALIDATION MODE (2026-11-19)" in text:
        if release not in text:
            raise ValueError("already migrated against a different release")
        return text
    text = paragraph(text, "SCOPE AND ROLLOUT:", MODE + "\n\n" + CADENCE)
    text = paragraph(text, "PINNED ENGINE:", engine(release))
    text = paragraph(text, "STATE:", STATE)
    if role != "schedule":
        text = paragraph(text, "ROLLOUT HOLD", MODE)
    if role == "desk":
        text = paragraph(text, "AUTHORIZATION AFTER A FUTURE RELEASE ONLY:", CONTRACT)
        text = paragraph(text, "PHASE FLOW:",
                         "PHASE FLOW: use the existing hourly calendar-gated schedule. Reconcile "
                         "holdings, pending orders and retained protection first. Pre-market "
                         "produces source-backed approval-ready proposals; intraday checks refresh "
                         "targeted theses, events, quotes and audits, not mandatory broad re-scouts. "
                         "After-hours never submit; reconcile fills, completed closes and coverage. "
                         "An earlier EOD report must not suppress new risk findings. " + CADENCE)
    if role == "executor":
        text = paragraph(text, "STATE SAFETY:", STATE)
        text = paragraph(text, "POST-RELEASE CONTRACT", CONTRACT)
        text = paragraph(text, "FUTURE RESERVATION CONTRACT", CONTRACT)
    if role == "auditor":
        text = text.replace("reliable 120-second cloud monitoring", "configured hourly monitoring")
        text = text.replace("Keep tactical 120-second validation requirements specific to that separate lane; this task does not enable it.",
                            "Check hourly timing and early-close exit feasibility in both lanes; options still require their own broker validation.")
    if role == "schedule":
        text = paragraph(text, "TYCHE HOURLY DESK RUN", "TYCHE HOURLY DESK RUN - VALIDATION MODE. " + MODE)
        text = text.replace("This is NOT the proposed 120-second tactical monitor.", CADENCE)
    text = text.replace("HOURLY STOCK/ETF LIFECYCLE ADDENDUM V1", "HOURLY INTEGRATED WORKFLOW V2")
    text = text.replace("This is distinct from the proposed 120-second tactical lane;", "Both lanes use hourly checks;")
    text = text.replace("Stock-only lifecycle capture of an option-containing account is an unresolved blocker, not permission to omit options.",
                        "Mixed-account capture requires verified contracts.json for every option holding and order; never omit exposure.")
    text = text.replace("Never feed an option-containing account through a stock-only lifecycle capture and assume safety; report and block until compatibility is validated.",
                        "Include verified contracts.json for option-containing accounts and all option history; absent metadata blocks capture.")
    text = text.replace("No option-containing account through a stock-only parser.",
                        "Mixed accounts require verified contracts.json; never omit option exposure.")
    return text


def update(path: str, before: dict, body: dict, protected: tuple[str, ...], apply: bool) -> None:
    changed = {k: v for k, v in body.items() if before.get(k) != v}
    print(json.dumps({"path": path, "fields": list(changed), "apply": apply}))
    if not changed or not apply:
        return
    current = forward.req("GET", path)
    if current != before:
        raise RuntimeError("cloud resource changed during preparation; no write sent")
    request = urllib.request.Request(
        forward.BASE + path, method="POST", data=json.dumps(changed).encode(),
        headers={"Authorization": "Bearer " + forward.pat(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except Exception as exc:
        raise RuntimeError("write outcome unknown; read actual cloud state before any retry") from exc
    after = forward.req("GET", path)
    if any(after.get(k) != v for k, v in changed.items()):
        raise RuntimeError("post-write verification differs; stop and inspect")
    if any(after.get(k) != before.get(k) for k in protected):
        raise RuntimeError("protected resource configuration changed; stop and inspect")
    print(json.dumps({"verified": path, "protected_fields_unchanged": True,
                      "policy_hash": hashlib.sha256(json.dumps(changed, sort_keys=True).encode()).hexdigest()}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--phase", choices=["members", "desk", "schedule"], required=True)
    parser.add_argument("--pins", help="Actual compiled versions keyed by researcher/auditor/executor")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{40}", args.release):
        parser.error("release must be a full verified commit SHA")
    if args.phase == "schedule":
        path = "/schedules/" + SCHEDULE
        before = forward.req("GET", path)
        events = before["initial_events"]
        if len(events) != 1 or events[0]["type"] != "user.message":
            raise ValueError("unexpected schedule event structure")
        content = transform(events[0]["content"], "schedule", args.release)
        update(path, before, {"initial_events": [{"type": "user.message", "content": content}],
                              "description": "Hourly integrated paper screening and protection; controlled validation pending exact grants, no production order release."},
               ("execution", "trigger_policy", "template_id", "identity_id", "environment_id", "sinks", "status"), args.apply)
        return
    roles = ["researcher", "auditor", "executor"] if args.phase == "members" else ["desk"]
    for role in roles:
        path = "/templates/" + TEMPLATES[role]
        before = forward.req("GET", path)
        body = {"system": transform(before["system"], role, args.release)}
        if role == "desk":
            if not args.pins:
                parser.error("desk phase requires verified compiled member versions")
            pins = json.loads(args.pins)
            roster = json.loads(json.dumps(before["multiagent"]))
            for name in ("researcher", "auditor", "executor"):
                rows = [row for row in roster["agents"] if row.get("template_id") == TEMPLATES[name]]
                if len(rows) != 1 or not isinstance(pins.get(name), int) or pins[name] < rows[0]["version"]:
                    raise ValueError("invalid compiled member version")
                rows[0]["version"] = pins[name]
            body["multiagent"] = roster
        update(path, before, body, PROTECTED + (() if role == "desk" else ("multiagent",)), args.apply)


if __name__ == "__main__":
    main()
