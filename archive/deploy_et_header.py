"""Add ET (US Eastern, the market's clock) to the sentinel digest header.

The header currently shows UTC / SGT; this inserts ET between them so the
operator can read the market's local clock directly. Two exact single-occurrence
replacements on the LIVE schedule content: the clock clause and the line-1 header
format. Schedule-events edit only — no template change, so the coordinator compile
and member roster pins are untouched. Pre-change snapshot under gitignored plans/,
GET-after verification, idempotent.

Run: MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe scripts/deploy_et_header.py
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

OLD_CLOCK = "SGT = UTC+8 (operator's home clock); show UTC and SGT in the digest header."
NEW_CLOCK = (
    "SGT = UTC+8 (operator's home clock); ET = US Eastern, the market's clock "
    "(UTC-5 EST / UTC-4 EDT); show UTC, ET and SGT in the digest header."
)
OLD_HEADER = "<HH:MM> UTC / <HH:MM> SGT; line 2 one plain-English sentence"
NEW_HEADER = "<HH:MM> UTC / <HH:MM> ET / <HH:MM> SGT; line 2 one plain-English sentence"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 occurrence, found {count} — aborting, nothing written")
    return text.replace(old, new)


def main() -> None:
    sched = forward.req("GET", f"/schedules/{SCHEDULE}")
    SNAP_DIR.mkdir(exist_ok=True)
    snap = SNAP_DIR / "cloud-schedule-pre-et.json"
    snap.write_text(json.dumps(sched, indent=2), encoding="utf-8")
    print("snapshot:", snap.name)

    content = sched["initial_events"][0]["content"]
    if "<HH:MM> ET" in content:
        print("schedule already carries the ET header — skipping")
        return
    content = replace_once(content, OLD_CLOCK, NEW_CLOCK, "schedule clock clause")
    content = replace_once(content, OLD_HEADER, NEW_HEADER, "schedule digest header")
    forward.req("POST", f"/schedules/{SCHEDULE}", {
        "initial_events": [{"type": "user.message", "content": content}],
    })
    check = forward.req("GET", f"/schedules/{SCHEDULE}")
    live = check["initial_events"][0]["content"]
    for marker in (NEW_HEADER, "show UTC, ET and SGT"):
        if marker not in live:
            raise SystemExit(f"schedule update missing marker: {marker}")
    for preserved in ("APPROVALS CONTRACT", "CALENDAR CHECK", "tyche authorize"):
        if preserved not in live:
            raise SystemExit(f"schedule update clobbered clause: {preserved}")
    print("schedule updated: ET added to digest header, version", check.get("initial_events_version"))


if __name__ == "__main__":
    main()