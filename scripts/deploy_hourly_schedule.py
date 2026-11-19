"""Deploy the hourly gate-routed desk schedule and retire the phase anchors.

Creates tyche-hourly (six fires at :05 ET, 08:05-16:05, computed trading days, DST-safe)
with a unified phase playbook + watchlist monitor contract, pauses the seven
phase schedules (reversible: POST /schedules/{id}/resume), and updates the desk
template's DAILY FLOW to the hourly cadence. The Telegram delivery contract is
copied verbatim from the live pre-market schedule. PAT stays in the gitignored
.env (server-side only); nothing secret is printed or committed.

Run: MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe scripts/deploy_hourly_schedule.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import forward

from tyche.market_calendar import generate_hourly_schedules

TEMPLATE_ID = "tmpl_004fa008901a6c256bd0ed3f"
ENVIRONMENT_ID = "env_00vtsfiylf7czjlt4b82"
IDENTITY_ID = "idn_1d7b9ab60a1bcc934d4a1d8f"
WINDOW = (date(2026, 11, 18), date(2026, 11, 28))
WATCHLIST_MARKER = "hourly cadence, gate-routed"

PHASE_SCHEDULES = [
    "tyche-premarket", "tyche-opening-drive", "tyche-midday-monitor",
    "tyche-closing-drive", "tyche-closing-drive-halfday",
    "tyche-eod", "tyche-eod-halfday",
]

GATE_AND_WORK = (
    "MARKET GATE (run first): bootstrap mount-first (clone fallback), `pip install -e . -c "
    "constraints.txt` if tyche is missing, then `tyche journal-verify` and `tyche halt-status "
    "--json` (halted=true blocks buys; approved de-risking sells may still run). Run `tyche "
    "calendar --json` (no --phase: hourly cadence, the live phase decides) — exit 0 means run, "
    "exit 1 means skip. If it skips "
    "(run=false): journal a run.skip with the returned reason, send a one-line Telegram skip "
    "notice (TYCHE HOURLY SKIP — <date>, <reason>), and STOP: no research, no plan, no orders. "
    "If run=true: follow the playbook for the returned phase and honor the strategy directive "
    "(activity, sleeves, new_entries, max_orders; on event days event_caution halves the order "
    "count and size). "
    "SCHEDULED HOURLY DESK RUN (six fires at :05 ET, 08:05-16:05, trading days only). "
    "Run `date -u` yourself for today's UTC date and clock; paste HH:MM UTC into every "
    "delegation message (members have no clock tool). "
    "WATCHLIST CONTRACT: the scout's shortlist persists at /data/drive/tyche-raw/watchlist.json "
    "(Drive survives sessions; the repo mount does not). Load and validate it with `tyche "
    "watchlist --path /data/drive/tyche-raw/watchlist.json --json` (exit 1 = missing/invalid). "
    "Schema: {as_of, entries:[{symbol, sleeve, strategy, entry_low, entry_high, stop, target, "
    "expiry, status(watch|entered|exited|dropped), thesis}]}. ONLY the pre-market scout writes "
    "or refreshes it (as_of=today); intraday runs NEVER re-run discovery — they monitor the "
    "existing entries and held positions against the crafted entry/exit plans. After any fill "
    "or invalidation, update the entry status (entered/exited/dropped) in the Drive copy and "
    "mirror a sanitized snapshot to data/watchlist.json for the PERSIST step. If the watchlist "
    "is missing or stale during an intraday phase: no new entries this run; monitor held "
    "positions only and note the gap in the digest. "
    "PHASE PLAYBOOK (follow the gate's live phase): "
    "pre_market (plan): delegate research (multifactor inputs -> thesis -> outlook -> vehicle & "
    "edge) with the kline handoff; the scout shortlists counters and writes the watchlist with "
    "a crafted strategy and entry/exit plan per name (entry zone, stop, target, expiry); "
    "executor snapshot fetch; build the day plan with the deterministic kernel; auditor "
    "review. A second pre-market run refreshes quotes and refines entry zones — not a full "
    "re-scout unless an invalidation hit. No order submissions without per-order operator "
    "confirmation. "
    "opening_drive / closing_drive (active): read the watchlist (no re-scout); researcher "
    "checks entry zones, stops, targets and invalidation on watchlist names plus held "
    "positions; refresh the rotation plan toward target; auditor review; executor submits "
    "ONLY via MCP sim_trade_input_order with per-order operator confirmation (always_ask). "
    "Honor the gate's max_orders and new_entries; closing drive also rebalances to target. "
    "midday (monitor): watchlist + positions drift/stop/target check; act ONLY on a drift "
    "breach or risk halt, with per-order operator confirmation; otherwise submit no orders. "
    "after_hours (reconcile): ONCE per day — if the journal already carries today's EOD "
    "reconcile, journal a run.skip (reason: eod already reconciled) and stop. Otherwise EOD "
    "reconcile (fills + modeled fees), update watchlist statuses, write reports/<date>-eod.md, "
    "then PERSIST + DeliverArtifacts per your DAILY FLOW. No new orders. "
    "HARD: no live/crypto tools ever; challenge allowlisted paper account only; a submit is "
    "not a fill; never expose credentials, tokens, or full account ids. Persist per the "
    "PERSIST step (raw to /data/drive/tyche-raw, sanitized to git only if the sanitize gate "
    "passes). "
)

NEW_DAILY_FLOW = (
    "DAILY FLOW (hourly cadence, gate-routed): the tyche-hourly schedule fires six times at :05 ET "
    "at :05 on computed trading days; 'tyche calendar --json' returns the live phase and "
    "strategy directive — obey it (activity, sleeves, new_entries, max_orders, event_caution). "
    "(1) pre_market (plan): delegate research (report + data/prices.csv kline handoff) and the "
    "executor snapshot fetch; the scout shortlists counters into the WATCHLIST, then build the "
    "plan with 'tyche plan --prices data/prices.csv --account <run-dir>/snapshot.json' "
    "(deterministic kernel; never invent trades or alter quantities). (2) Delegate the audit; "
    "REJECT means no trade today or re-plan. (3) opening_drive/closing_drive (active): monitor "
    "the watchlist's entry/exit plans — never re-scout intraday; execution only when the "
    "operator confirms each order (executor sim writes are always_ask). (4) midday (monitor): "
    "drift/stop/target checks on watchlist names + positions; act only on a breach or risk "
    "halt. (5) after_hours (reconcile, once per day — skip if the journal already carries "
    "today's EOD): fills + fees via tyche.fees.reconcile_cash, update watchlist statuses, write "
    "reports/<date>-eod.md, then PERSIST: 'tyche persist' raw to the Drive locker "
    "(/data/drive/tyche-raw) and sanitized summaries to git, then DeliverArtifacts the raw run "
    "bundle and the EOD report so the operator can download them from console Files. The "
    "sandbox is ephemeral; a run without persistence is a failed run. WATCHLIST: "
    "/data/drive/tyche-raw/watchlist.json is the persistent working copy (validate: 'tyche "
    "watchlist --path /data/drive/tyche-raw/watchlist.json --json'); the scout writes it at "
    "pre-market only; intraday runs monitor it; mirror the sanitized snapshot to "
    "data/watchlist.json for PERSIST. "
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report planned changes without mutating.")
    args = parser.parse_args()
    check = args.check

    live = forward.req("GET", "/schedules?limit=50").get("data") or []
    by_name = {s["name"]: s for s in live}

    premarket = by_name.get("tyche-premarket")
    if not premarket:
        raise SystemExit("tyche-premarket not found — cannot copy the Telegram contract")
    base_content = premarket["initial_events"][0]["content"]
    idx = base_content.find("TELEGRAM DELIVERY")
    if idx < 0:
        raise SystemExit("Telegram delivery contract not found in pre-market run instruction")
    telegram = base_content[idx:]

    specs = generate_hourly_schedules(*WINDOW)
    if len(specs) != 1:
        raise SystemExit(f"expected one hourly cron for the window, got {len(specs)}")
    spec = specs[0]

    if "tyche-hourly" in by_name:
        existing = by_name["tyche-hourly"]
        live_cron = (existing.get("trigger_policy") or {}).get("expression")
        if live_cron == spec.cron:
            print("tyche-hourly cron already current:", spec.cron)
        elif check:
            print(f"would update tyche-hourly cron: {live_cron} -> {spec.cron}")
        else:
            policy = dict(existing.get("trigger_policy") or {})
            policy["expression"] = spec.cron
            forward.req("POST", f"/schedules/{existing['id']}", {"trigger_policy": policy})
            check_policy = (forward.req("GET", f"/schedules/{existing['id']}").get("trigger_policy") or {})
            if check_policy.get("expression") != spec.cron:
                raise SystemExit("cron update did not take effect")
            print("updated tyche-hourly cron:", spec.cron)
        if existing.get("status") == "paused":
            print("note: tyche-hourly is paused; the cadence applies when the operator resumes it")
    elif check:
        print("would create tyche-hourly with cron:", spec.cron)
    else:
        body = {
            "name": "tyche-hourly",
            "description": (
                "Tyche hourly desk run (six fires at :05 ET, 08:05-16:05, trading days only). "
                "Gate-routed by live session phase: plan pre-market, active drives, monitor "
                "midday, reconcile after close (once/day). Watchlist monitored intraday; "
                "orders require per-order operator confirmation via executor always_ask."
            ),
            "template_id": TEMPLATE_ID,
            "environment_id": ENVIRONMENT_ID,
            "identity_id": IDENTITY_ID,
            "initial_events": [{"type": "user.message", "content": GATE_AND_WORK + telegram}],
            "execution": {
                "session_mode": "new_session",
                "max_concurrent_runs": 1,
                "max_attempts": 1,
                "timeout_ms": 3600000,
            },
            "trigger_policy": {
                "type": "cron",
                "expression": spec.cron,
                "timezone": "UTC",
                "start_at": "2026-11-18T00:00:00Z",
                "stop_at": "2026-11-28T00:00:00Z",
            },
            "sinks": [],
            "metadata": {},
        }
        result = forward.req("POST", "/schedules", body)
        print("created tyche-hourly:", result.get("id"), "cron:", spec.cron)

    paused, already, would_pause = [], [], []
    for name in PHASE_SCHEDULES:
        sched = by_name.get(name)
        if not sched:
            continue
        if sched.get("status") == "paused":
            already.append(name)
            continue
        if check:
            would_pause.append(name)
            continue
        forward.req("POST", f"/schedules/{sched['id']}/pause", {})
        verified = forward.req("GET", f"/schedules/{sched['id']}")
        if verified.get("status") != "paused":
            raise SystemExit(f"pause did not take effect for {name} — stopping")
        paused.append(name)
    print("paused:", paused)
    print("would pause:", would_pause)
    print("already paused:", already)

    template = forward.req("GET", f"/templates/{TEMPLATE_ID}")
    system = template.get("system") or ""
    if WATCHLIST_MARKER in system:
        print("desk template DAILY FLOW already updated — skipping")
    elif check:
        print("would update desk template DAILY FLOW to hourly cadence + watchlist contract")
    else:
        start = system.find("DAILY FLOW")
        end = system.find("HARD RULES:")
        if start < 0 or end < 0 or end <= start:
            raise SystemExit("DAILY FLOW / HARD RULES markers not found in desk template")
        new_system = system[:start] + NEW_DAILY_FLOW + system[end:]
        forward.req("POST", f"/templates/{TEMPLATE_ID}", {"system": new_system})
        verified = forward.req("GET", f"/templates/{TEMPLATE_ID}")
        if WATCHLIST_MARKER not in (verified.get("system") or ""):
            raise SystemExit("template update did not take effect")
        print("desk template DAILY FLOW updated to hourly cadence + watchlist contract")

    final = forward.req("GET", "/schedules?limit=50").get("data") or []
    for s in final:
        tp = s.get("trigger_policy") or {}
        print(f"  {s['name']}: {s.get('status')} · {tp.get('expression')}")


if __name__ == "__main__":
    main()