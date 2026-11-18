"""Deploy the daily alert-only NYSE calendar check into the tyche-hourly playbook.

Adds a CALENDAR CHECK clause to the schedule initial_events (pre-market, once per
day): the desk WebFetches nyse.com/trade/hours-calendars, saves the readable
output, and runs `tyche calendar-check --json`. A non-zero exit (drift or uncertain
parse) ALERTS the operator with the diff and proposes a reviewed re-pin — it never
auto-applies or alters the pinned calendar. Schedule-events edit only: no template
change, so the coordinator compile and member roster pins are untouched.

Exact single-occurrence insertion on the LIVE content, pre-change snapshot under
gitignored plans/, GET-after verification. Push the code (tyche calendar-check)
BEFORE running this so the next mount has the CLI.

Run: MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe scripts/deploy_calendar_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import forward

SCHEDULE = "sched_2dc7702e4f005d04235c078a"
SNAP_DIR = ROOT / "plans"

CALENDAR_CHECK = (
    "CALENDAR CHECK (pre-market, once per day, alert-only): at the first pre_market run of "
    "the day, WebFetch https://www.nyse.com/trade/hours-calendars and save the readable output "
    "to <run-dir>/nyse-calendar.txt, then run `tyche calendar-check --source "
    "<run-dir>/nyse-calendar.txt --json`. Exit 0 = the pinned NYSE calendar (2026-2028) is in "
    "sync; proceed. Non-zero exit (changed or uncertain) = the source drifted or the parse was "
    "incomplete: ALERT the operator in the digest (a Calendar line listing new_years and any "
    "added/removed closure dates, or the parse warnings) and propose a reviewed re-pin via "
    "scripts/refresh_calendar.py. NEVER auto-apply, edit config/, or alter the calendar "
    "yourself; the pinned tables still govern every trading decision this run. Skip on "
    "intraday/after_hours runs and if today's journal already records a calendar.check; journal "
    "the outcome as calendar.check (payload: changed, uncertain, new_years). "
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 occurrence, found {count} — aborting, nothing written")
    return text.replace(old, new)


def main() -> None:
    sched = forward.req("GET", f"/schedules/{SCHEDULE}")
    SNAP_DIR.mkdir(exist_ok=True)
    snap = SNAP_DIR / "cloud-schedule-pre-calcheck.json"
    snap.write_text(json.dumps(sched, indent=2), encoding="utf-8")
    print("snapshot:", snap.name)

    content = sched["initial_events"][0]["content"]
    if "CALENDAR CHECK" in content:
        print("schedule already carries the calendar check — skipping")
        return
    content = replace_once(
        content,
        "PHASE PLAYBOOK (follow the gate's live phase):",
        CALENDAR_CHECK + "PHASE PLAYBOOK (follow the gate's live phase):",
        "schedule calendar check insert",
    )
    forward.req("POST", f"/schedules/{SCHEDULE}", {
        "initial_events": [{"type": "user.message", "content": content}],
    })
    check = forward.req("GET", f"/schedules/{SCHEDULE}")
    live = check["initial_events"][0]["content"]
    for marker in ("CALENDAR CHECK", "tyche calendar-check", "scripts/refresh_calendar.py"):
        if marker not in live:
            raise SystemExit(f"schedule update missing marker: {marker}")
    if "APPROVALS CONTRACT" not in live or "<HH:MM> UTC / <HH:MM> SGT" not in live:
        raise SystemExit("schedule update clobbered the envelope/SGT clauses")
    print("schedule updated: calendar check inserted, version", check.get("initial_events_version"))


if __name__ == "__main__":
    main()