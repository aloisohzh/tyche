"""Deploy the session-phase schedules and wire the market gate into every run.

Creates the four new phase schedules (opening-drive, midday-monitor,
closing-drive, closing-drive-halfday) from market_calendar.generate_schedules,
and prepends a MARKET GATE step to every desk schedule's run instruction so each
run calls `tyche calendar --phase <intended> --json` first and skips on exit 1.

The Telegram delivery contract is copied verbatim from the live pre-market
schedule so new runs stay consistent with the existing ones. PAT stays in the
gitignored .env (server-side only); nothing secret is printed or committed.

Run: MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe scripts/deploy_phase_schedules.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import forward  # noqa: E402

from tyche.market_calendar import generate_schedules  # noqa: E402

TEMPLATE_ID = "tmpl_004fa008901a6c256bd0ed3f"
ENVIRONMENT_ID = "env_00vtsfiylf7czjlt4b82"
IDENTITY_ID = "idn_1d7b9ab60a1bcc934d4a1d8f"
WINDOW = (date(2026, 11, 18), date(2026, 11, 28))
GATE_MARKER = "MARKET GATE (run first)"

# Intended phase for the three pre-existing schedules (gate --phase argument).
EXISTING_PHASE = {
    "tyche-premarket": "pre_market",
    "tyche-eod": "after_hours",
    "tyche-eod-halfday": "after_hours",
}

PHASE_WORK = {
    "tyche-opening-drive": (
        "SCHEDULED OPENING-DRIVE RUN (challenge window, first-hour liquidity 09:30-10:30 ET). "
        "Run `date -u` yourself for today's UTC date and clock; paste HH:MM UTC into every "
        "delegation message (members have no clock tool). Follow the ACTIVE intraday phase of "
        "your DAILY FLOW: executor reads broker cash/positions/order state for the allowlisted "
        "challenge paper account (read-only), researcher refreshes intraday signals, refresh the "
        "rotation plan toward target, auditor review, then executor submits ONLY via MCP "
        "sim_trade_input_order with per-order operator confirmation (always_ask). Honor the gate's "
        "max_orders and new_entries; no live/crypto tools ever; challenge allowlisted paper account "
        "only; a submit is not a fill. Persist per the PERSIST step (raw to /data/drive/tyche-raw, "
        "sanitized to git only if the sanitize gate passes). "
    ),
    "tyche-midday-monitor": (
        "SCHEDULED MIDDAY MONITOR RUN (challenge window, 10:30-15:00 ET lull). Run `date -u` "
        "yourself for today's UTC date and clock; paste HH:MM UTC into every delegation message. "
        "Follow the MONITOR phase of your DAILY FLOW: executor reads broker state for the "
        "allowlisted challenge paper account (read-only), check drift vs target and risk caps / "
        "kill-switch; act ONLY on a drift breach or risk halt, with per-order operator confirmation "
        "(always_ask); otherwise submit no orders. Honor the gate's max_orders (ballast sleeves). "
        "No live/crypto tools ever; challenge allowlisted paper account only; a submit is not a "
        "fill. Persist per the PERSIST step. "
    ),
    "tyche-closing-drive": (
        "SCHEDULED CLOSING-DRIVE RUN (challenge window, last-hour liquidity 15:00-16:00 ET). "
        "Run `date -u` yourself for today's UTC date and clock; paste HH:MM UTC into every "
        "delegation message. Follow the ACTIVE intraday phase of your DAILY FLOW: rebalance to "
        "target plus last-hour edge, executor reads broker state (read-only), auditor review, then "
        "executor submits ONLY via MCP sim_trade_input_order with per-order operator confirmation "
        "(always_ask). Honor the gate's max_orders and new_entries; no live/crypto tools ever; "
        "challenge allowlisted paper account only; a submit is not a fill. Persist per the PERSIST "
        "step. "
    ),
    "tyche-closing-drive-halfday": (
        "SCHEDULED CLOSING-DRIVE RUN (challenge window, 27 Nov HALF-DAY session: last-hour "
        "liquidity 12:00-13:00 ET, market closes 18:00 UTC). Run `date -u` yourself for today's UTC "
        "date and clock; paste HH:MM UTC into every delegation message. Follow the ACTIVE intraday "
        "phase of your DAILY FLOW: rebalance to target plus last-hour edge, executor reads broker "
        "state (read-only), auditor review, then executor submits ONLY via MCP sim_trade_input_order "
        "with per-order operator confirmation (always_ask). Honor the gate's max_orders and "
        "new_entries; no live/crypto tools ever; challenge allowlisted paper account only; a submit "
        "is not a fill. Persist per the PERSIST step. "
    ),
}


def gate_prefix(phase: str, label: str) -> str:
    return (
        f"{GATE_MARKER}: bootstrap mount-first (clone fallback), `pip install -e . --no-deps` if "
        f"tyche is missing, then `tyche journal-verify`. Run `tyche calendar --phase {phase} --json` "
        f"— exit 0 means run, exit 1 means skip. If it skips (run=false): journal a run.skip with "
        f"the returned reason, send a one-line Telegram skip notice (TYCHE {label} SKIP — <date>, "
        f"<reason>), and STOP: no research, no plan, no orders. If run=true: proceed with the phase "
        f"below and honor the returned strategy directive (activity, sleeves, new_entries, "
        f"max_orders; on event days event_caution halves the order count and size). "
    )


def main() -> None:
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

    generated = {d.name: d for d in generate_schedules(*WINDOW)}
    created, updated, skipped = [], [], []

    for name, work in PHASE_WORK.items():
        if name in by_name:
            skipped.append(name)
            continue
        spec = generated[name]
        label = name.removeprefix("tyche-").replace("-", " ").upper()
        content = gate_prefix(spec.phase, label) + work + telegram
        body = {
            "name": name,
            "description": (
                f"Tyche {spec.phase.replace('_', ' ')} run ({spec.scope} session days), "
                f"{spec.et_time} ET fire. {spec.note}. Market-gated; orders require per-order "
                f"operator confirmation via executor always_ask."
            ),
            "template_id": TEMPLATE_ID,
            "environment_id": ENVIRONMENT_ID,
            "identity_id": IDENTITY_ID,
            "initial_events": [{"type": "user.message", "content": content}],
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
        created.append({"name": name, "id": result.get("id"), "cron": spec.cron})

    # Wire the gate into the three pre-existing schedules (prepend, keep verbatim).
    for name, phase in EXISTING_PHASE.items():
        sched = by_name.get(name)
        if not sched:
            continue
        content = sched["initial_events"][0]["content"]
        if GATE_MARKER in content:
            skipped.append(name + " (gate already present)")
            continue
        label = name.removeprefix("tyche-").replace("-", " ").upper()
        new_content = gate_prefix(phase, label) + content
        forward.req(
            "POST",
            f"/schedules/{sched['id']}",
            {"initial_events": [{"type": "user.message", "content": new_content}]},
        )
        updated.append(name)

    print("created:", created)
    print("gate wired into existing:", updated)
    print("skipped:", skipped)


if __name__ == "__main__":
    main()