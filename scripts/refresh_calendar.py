"""Operator-side NYSE calendar refresh (reviewed re-pin, never auto-applied).

Workflow:
  1. Fetch https://www.nyse.com/trade/hours-calendars via WebFetch and save the
     readable output to a file (e.g. plans/nyse-calendar.txt, gitignored).
  2. python scripts/refresh_calendar.py --source plans/nyse-calendar.txt --emit-tables
     -> prints the drift vs the pinned tables and proposed HOLIDAYS/HALF_DAYS literals.
  3. Apply the reviewed change to src/tyche/market_calendar.py, update tests,
     commit + push. The cloud mount syncs it; the daily `tyche calendar-check`
     gate then reports IN SYNC.

Reads + prints only. It does not fetch (the cloud kernel has no network) and does
not write the calendar — re-pinning is always a reviewed operator commit.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tyche.nyse_calendar import diff_calendar, parse_nyse_page, render_tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Saved WebFetch readable output of the NYSE page.")
    parser.add_argument("--emit-tables", action="store_true", help="Print proposed HOLIDAYS/HALF_DAYS literals.")
    args = parser.parse_args()

    path = Path(args.source)
    if not path.is_file():
        raise SystemExit(f"source not found: {path}")
    parsed = parse_nyse_page(path.read_text(encoding="utf-8"))
    report = diff_calendar(parsed)

    print(f"source years: {report['years_source']}  pinned years: {report['years_pinned']}")
    if report["uncertain"]:
        print("UNCERTAIN — parse incomplete; review manually:")
        for warning in report["warnings"]:
            print(f"  · {warning}")
    if report["new_years"]:
        print(f"new years published: {report['new_years']}")
    if report["changes"]:
        print(f"{len(report['changes'])} drift(s) vs pinned tables:")
        for change in report["changes"]:
            print(f"  · {change['action']:7} {change['kind']:8} {change['date']}  {change['name']}")
    elif not report["uncertain"]:
        print("IN SYNC — no drift; nothing to re-pin.")
    if args.emit_tables:
        print("\n# --- proposed literals (review before applying) ---")
        print(render_tables(parsed))


if __name__ == "__main__":
    main()