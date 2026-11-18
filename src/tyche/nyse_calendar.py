"""Parse the NYSE holidays & trading-hours page into a forward-looking calendar.

Source of truth: https://www.nyse.com/trade/hours-calendars (NYSE publishes 2-3
years ahead). The cloud kernel cannot fetch, so the desk agent saves the WebFetch
readable output to a file and this module parses + diffs it against the pinned
HOLIDAYS / HALF_DAYS tables.

Read-only by contract: it NEVER mutates the calendar. A detected change is an
operator alert; re-pinning is a reviewed commit (scripts/refresh_calendar.py).
The parser is conservative — if it cannot confidently read the table it reports
uncertain rather than silently claiming "no change", so a fragile scrape can
never quietly flip a trading day.
"""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from tyche.market_calendar import HALF_DAYS, HOLIDAYS

_MONTHS = {
    name: index
    for index, name in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], 1,
    )
}
_MONTH_ALT = "|".join(_MONTHS)
# A date cell: "Friday, June 18 (observed)" / "Tuesday, July 4**".
_CELL = re.compile(r"^[A-Z][a-z]+,\s+(?P<mon>[A-Z][a-z]+)\s+(?P<day>\d{1,2})")
_YEAR = re.compile(r"^20\d{2}$")
_EARLY = re.compile(r"close early at 1:00")
# Early-close footnote dates: "... on Friday, November 27, 2026, ...".
_MD_DATE = re.compile(rf"(?P<mon>{_MONTH_ALT})\s+(?P<day>\d{{1,2}}),\s+(?P<y>20\d{{2}})")
_NOISE = (".lexical", "data-is-button", "[Trading Days]", "[Trading Hours]", "* * *")


class NyseCalendar(BaseModel):
    years: list[int] = Field(default_factory=list)
    holidays: dict[int, dict[date, str]] = Field(default_factory=dict)
    half_days: dict[int, dict[date, str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @property
    def confident(self) -> bool:
        if self.warnings or not self.years:
            return False
        if any(len(self.holidays.get(y, {})) < 9 for y in self.years):
            return False
        return sum(len(v) for v in self.half_days.values()) >= 1


def _unescape(text: str) -> str:
    return re.sub(r"\\([*_\[\]#.`~()\-])", r"\1", text)


def _cell_date(cell: str, year: int) -> date | None:
    if cell.startswith(("—", "-", "–")) or cell.lower().startswith("n/a"):
        return None
    match = _CELL.match(cell)
    if not match:
        return None
    month = _MONTHS.get(match.group("mon"))
    if month is None:
        return None
    try:
        return date(year, month, int(match.group("day")))
    except ValueError:
        return None


def parse_nyse_page(text: str) -> NyseCalendar:
    lines = [ln.strip() for ln in _unescape(text).splitlines()]
    lines = [ln for ln in lines if ln and not any(n in ln for n in _NOISE)]

    years: list[int] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if line == "Holiday":
            cursor = index + 1
            while cursor < len(lines) and _YEAR.match(lines[cursor]):
                years.append(int(lines[cursor]))
                cursor += 1
            start = cursor
            break
    if start is None or not years:
        return NyseCalendar(warnings=["holiday table header ('Holiday' + year columns) not found"])

    holidays: dict[int, dict[date, str]] = {y: {} for y in years}
    warnings: list[str] = []
    name: str | None = None
    cells: list[str] = []

    def flush() -> None:
        nonlocal name, cells
        if name is not None:
            if len(cells) == len(years):
                for year, cell in zip(years, cells, strict=True):
                    day = _cell_date(cell, year)
                    if day is not None:
                        holidays[year][day] = name
            else:
                warnings.append(f"row '{name}' has {len(cells)} cells, expected {len(years)}")
        name, cells = None, []

    for line in lines[start:]:
        if line.startswith("*") or line == "Trading Hours" or _EARLY.search(line):
            break
        if _CELL.match(line) or line.startswith(("—", "-", "–")):
            cells.append(line)
        else:
            flush()
            name = line
    flush()

    half_days: dict[int, dict[date, str]] = {y: {} for y in years}
    for line in lines:
        if not _EARLY.search(line):
            continue
        for match in _MD_DATE.finditer(line):
            year = int(match.group("y"))
            if year in half_days:
                half_days[year][date(year, _MONTHS[match.group("mon")], int(match.group("day")))] = (
                    "Early close (13:00 ET)"
                )

    for year in years:
        if len(holidays[year]) < 9:
            warnings.append(f"year {year}: only {len(holidays[year])} closures parsed (<9)")
    if not any(half_days.values()):
        warnings.append("no early-close footnotes parsed")
    return NyseCalendar(years=years, holidays=holidays, half_days=half_days, warnings=warnings)


def _changes(
    parsed: dict[int, dict[date, str]], pinned: dict[int, dict[date, str]], kind: str, years: list[int],
) -> list[dict]:
    out: list[dict] = []
    for year in years:
        src, pin = parsed.get(year, {}), pinned.get(year, {})
        for day in sorted(set(src) - set(pin)):
            out.append({"kind": kind, "year": year, "date": day.isoformat(),
                        "action": "added", "name": src[day]})
        for day in sorted(set(pin) - set(src)):
            out.append({"kind": kind, "year": year, "date": day.isoformat(),
                        "action": "removed", "name": pin[day]})
    return out


def diff_calendar(parsed: NyseCalendar) -> dict:
    """Date-based diff of parsed NYSE calendar vs the pinned tables (JSON-ready).

    Names are cosmetic (the gate only uses dates), so only added/removed closure
    dates count as a change. Years present in the source but not pinned are
    reported as new_years. Pinned years absent from the source are not treated as
    removals (the source may simply not cover them).
    """
    overlap = sorted(set(parsed.years) & set(HOLIDAYS))
    changes = _changes(parsed.holidays, HOLIDAYS, "holiday", overlap)
    changes += _changes(parsed.half_days, HALF_DAYS, "half_day", overlap)
    new_years = sorted(set(parsed.years) - set(HOLIDAYS))
    uncertain = not parsed.confident
    return {
        "changed": bool(changes) or bool(new_years),
        "uncertain": uncertain,
        "years_source": parsed.years,
        "years_pinned": sorted(HOLIDAYS),
        "new_years": new_years,
        "changes": changes,
        "warnings": parsed.warnings,
        "source": "https://www.nyse.com/trade/hours-calendars",
    }


def render_tables(parsed: NyseCalendar) -> str:
    """Emit ready-to-review HOLIDAYS / HALF_DAYS Python literals from parsed data."""
    def block(var: str, data: dict[int, dict[date, str]]) -> str:
        rows = [f"{var}: dict[int, dict[date, str]] = {{"]
        for year in sorted(data):
            rows.append(f"    {year}: {{")
            for day in sorted(data[year]):
                name = data[year][day].replace('"', '\\"')
                rows.append(f"        date({day.year}, {day.month}, {day.day}): \"{name}\",")
            rows.append("    },")
        rows.append("}")
        return "\n".join(rows)

    return block("HOLIDAYS", parsed.holidays) + "\n\n" + block("HALF_DAYS", parsed.half_days)