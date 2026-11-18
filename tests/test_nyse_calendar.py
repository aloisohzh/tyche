from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from tyche.cli import app
from tyche.market_calendar import HALF_DAYS, HOLIDAYS
from tyche.nyse_calendar import diff_calendar, parse_nyse_page, render_tables

FIXTURE = Path(__file__).parent / "fixtures" / "nyse_hours_calendars.txt"


def _parsed():
    return parse_nyse_page(FIXTURE.read_text(encoding="utf-8"))


def test_parse_fixture_reproduces_pinned_tables():
    parsed = _parsed()
    assert parsed.years == [2026, 2027, 2028]
    assert parsed.confident and not parsed.warnings
    for year in (2026, 2027, 2028):
        assert set(parsed.holidays[year]) == set(HOLIDAYS[year])
        assert set(parsed.half_days[year]) == set(HALF_DAYS[year])


def test_parse_observed_and_non_observed_dates():
    parsed = _parsed()
    # 2028 New Year falls on Saturday and is NOT observed; Jul 4 IS a closure.
    assert date(2028, 1, 1) not in parsed.holidays[2028]
    assert date(2028, 7, 4) in parsed.holidays[2028]
    assert len(parsed.holidays[2028]) == 9
    # Observed shifts land on the weekday closure, not the calendar holiday.
    assert date(2027, 6, 18) in parsed.holidays[2027]
    assert date(2027, 7, 5) in parsed.holidays[2027]
    assert date(2027, 12, 24) in parsed.holidays[2027]
    # Early closes come from the footnotes, including the multi-date *** note.
    assert set(parsed.half_days[2028]) == {date(2028, 7, 3), date(2028, 11, 24)}


def test_diff_in_sync():
    report = diff_calendar(_parsed())
    assert report["changed"] is False
    assert report["uncertain"] is False
    assert report["new_years"] == [] and report["changes"] == []


def test_diff_flags_added_and_removed_closure():
    parsed = _parsed()
    parsed.holidays[2026][date(2026, 1, 2)] = "Day of mourning"
    del parsed.holidays[2027][date(2027, 11, 25)]
    report = diff_calendar(parsed)
    assert report["changed"] is True
    actions = {(c["kind"], c["date"], c["action"]) for c in report["changes"]}
    assert ("holiday", "2026-01-02", "added") in actions
    assert ("holiday", "2027-11-25", "removed") in actions


def test_pinned_year_absent_from_source_is_not_a_removal():
    parsed = _parsed()
    parsed.years = [2026]
    parsed.holidays = {2026: parsed.holidays[2026]}
    parsed.half_days = {2026: parsed.half_days[2026]}
    report = diff_calendar(parsed)
    assert report["changed"] is False  # 2027/2028 pinned but uncovered -> no claim
    assert report["new_years"] == []


def test_new_published_year_detected():
    parsed = _parsed()
    parsed.years.append(2029)
    parsed.holidays[2029] = {date(2029, 1, 1): "New Year's Day"}
    report = diff_calendar(parsed)
    assert 2029 in report["new_years"] and report["changed"] is True


def test_parse_uncertain_on_garbage():
    parsed = parse_nyse_page("no table here\njust some text")
    assert not parsed.confident and parsed.warnings
    assert diff_calendar(parsed)["uncertain"] is True


def test_render_tables_literals():
    out = render_tables(_parsed())
    assert "HOLIDAYS: dict[int, dict[date, str]] = {" in out
    assert "HALF_DAYS: dict[int, dict[date, str]] = {" in out
    assert "date(2028, 7, 4)" in out and "date(2028, 11, 24)" in out


def test_cli_calendar_check_in_sync():
    result = CliRunner().invoke(app, ["calendar-check", "--source", str(FIXTURE), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["changed"] is False and payload["uncertain"] is False


def test_cli_calendar_check_missing(tmp_path):
    result = CliRunner().invoke(app, ["calendar-check", "--source", str(tmp_path / "nope.txt")])
    assert result.exit_code == 1


def test_cli_calendar_check_changed(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8").replace("Friday, April 3", "Friday, April 10")
    src = tmp_path / "nyse.txt"
    src.write_text(text, encoding="utf-8")
    result = CliRunner().invoke(app, ["calendar-check", "--source", str(src), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    dates = {c["date"] for c in payload["changes"]}
    assert {"2026-04-03", "2026-04-10"} <= dates