from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from tyche.market_calendar import (
    ET,
    SessionPhase,
    _cron_days,
    closing_drive_start,
    earnings_season,
    evaluate,
    events_on,
    generate_schedules,
    half_day_name,
    holiday_name,
    is_half_day,
    is_trading_day,
    next_run,
    phase_at,
    regular_close,
    session_timeline,
    strategy_for,
)


def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_trading_days_and_holidays():
    assert is_trading_day(date(2026, 11, 18))  # Wednesday
    assert not is_trading_day(date(2026, 11, 26))  # Thanksgiving
    assert not is_trading_day(date(2026, 11, 21))  # Saturday
    assert not is_trading_day(date(2026, 11, 22))  # Sunday
    assert is_trading_day(date(2026, 11, 27))  # half day is still a trading day
    assert holiday_name(date(2026, 11, 26)) == "Thanksgiving"
    assert holiday_name(date(2026, 7, 3)) == "Independence Day (observed)"
    assert holiday_name(date(2026, 11, 18)) is None


def test_half_days():
    assert is_half_day(date(2026, 11, 27))
    assert is_half_day(date(2026, 12, 24))
    assert not is_half_day(date(2026, 11, 18))
    assert not is_half_day(date(2026, 11, 26))  # holiday, not a half day
    assert half_day_name(date(2026, 11, 27)) == "Day after Thanksgiving"
    assert regular_close(date(2026, 11, 27)) == time(13, 0)
    assert regular_close(date(2026, 11, 18)) == time(16, 0)
    assert closing_drive_start(date(2026, 11, 27)) == time(12, 0)
    assert closing_drive_start(date(2026, 11, 18)) == time(15, 0)


def test_phase_boundaries_est():
    # November = EST (UTC-5). 09:30 ET = 14:30 UTC.
    assert phase_at(utc(2026, 11, 18, 13, 0)) is SessionPhase.PRE_MARKET  # 08:00 ET
    assert phase_at(utc(2026, 11, 18, 14, 30)) is SessionPhase.OPENING_DRIVE  # 09:30 ET
    assert phase_at(utc(2026, 11, 18, 15, 29)) is SessionPhase.OPENING_DRIVE  # 10:29 ET
    assert phase_at(utc(2026, 11, 18, 15, 30)) is SessionPhase.MIDDAY  # 10:30 ET
    assert phase_at(utc(2026, 11, 18, 20, 0)) is SessionPhase.CLOSING_DRIVE  # 15:00 ET
    assert phase_at(utc(2026, 11, 18, 21, 0)) is SessionPhase.AFTER_HOURS  # 16:00 ET
    assert phase_at(utc(2026, 11, 18, 1, 0)) is SessionPhase.CLOSED  # 20:00 ET prior day
    assert phase_at(utc(2026, 11, 26, 15, 0)) is SessionPhase.CLOSED  # holiday


def test_phase_boundaries_half_day():
    # Nov 27 half day: close 13:00 ET = 18:00 UTC, closing drive 12:00 ET = 17:00 UTC.
    assert phase_at(utc(2026, 11, 27, 17, 0)) is SessionPhase.CLOSING_DRIVE  # 12:00 ET
    assert phase_at(utc(2026, 11, 27, 18, 0)) is SessionPhase.AFTER_HOURS  # 13:00 ET
    assert phase_at(utc(2026, 11, 27, 20, 0)) is SessionPhase.AFTER_HOURS  # 15:00 ET


def test_dst_awareness():
    # July = EDT (UTC-4). 09:30 ET = 13:30 UTC, not 14:30.
    assert phase_at(utc(2026, 7, 15, 13, 30)) is SessionPhase.OPENING_DRIVE
    assert phase_at(utc(2026, 7, 15, 14, 30)) is SessionPhase.MIDDAY  # 10:30 EDT
    # Same wall-clock UTC lands in different phases across DST.
    assert phase_at(utc(2026, 11, 18, 14, 30)) is SessionPhase.OPENING_DRIVE
    assert utc(2026, 7, 15, 13, 30).astimezone(ET).hour == 9


def test_strategy_routing():
    opening = strategy_for(SessionPhase.OPENING_DRIVE)
    assert opening.activity == "active" and opening.new_entries
    assert opening.max_orders == 2
    midday = strategy_for(SessionPhase.MIDDAY)
    assert midday.activity == "monitor" and not midday.new_entries
    closing = strategy_for(SessionPhase.CLOSING_DRIVE)
    assert closing.activity == "active" and closing.max_orders == 3
    assert strategy_for(SessionPhase.AFTER_HOURS).activity == "reconcile"
    assert strategy_for(SessionPhase.PRE_MARKET).activity == "plan"
    assert strategy_for(SessionPhase.CLOSED).activity == "noop"


def test_event_day_modulates_risk():
    calm = strategy_for(SessionPhase.OPENING_DRIVE, event_day=False)
    cautious = strategy_for(SessionPhase.OPENING_DRIVE, event_day=True)
    assert not calm.event_caution
    assert cautious.event_caution
    assert cautious.max_orders < calm.max_orders
    # Non-active phases are not modulated.
    assert strategy_for(SessionPhase.MIDDAY, event_day=True).max_orders == 1


def test_events_and_earnings_season():
    nov18 = events_on(date(2026, 11, 18))
    assert any(e.name == "FOMC minutes" and e.kind == "fomc" for e in nov18)
    nov25 = events_on(date(2026, 11, 25))
    assert {e.name for e in nov25} >= {"PCE price index", "Beige Book"}
    assert any(e.kind == "earnings" for e in events_on(date(2026, 11, 17)))
    assert earnings_season(date(2026, 10, 15)) == "Q3 earnings season"
    assert earnings_season(date(2026, 11, 18)) is None
    assert any(e.kind == "earnings" for e in events_on(date(2026, 10, 15)))


def test_gate_skips_holiday():
    result = evaluate(utc(2026, 11, 26, 15, 0))
    assert not result.run
    assert result.holiday == "Thanksgiving"
    assert result.phase is SessionPhase.CLOSED
    assert not result.trading_day


def test_gate_runs_matching_phase():
    result = evaluate(utc(2026, 11, 18, 14, 35), SessionPhase.OPENING_DRIVE)
    assert result.run
    assert result.phase is SessionPhase.OPENING_DRIVE
    assert result.strategy.activity == "active"


def test_gate_half_day_phase_mismatch():
    # Regular closing-drive cron (15:05 ET) firing on a half day -> after hours.
    mismatch = evaluate(utc(2026, 11, 27, 20, 5), SessionPhase.CLOSING_DRIVE)
    assert not mismatch.run
    assert "phase mismatch" in mismatch.reason
    # Half-day closing-drive cron (12:05 ET) matches.
    match = evaluate(utc(2026, 11, 27, 17, 5), SessionPhase.CLOSING_DRIVE)
    assert match.run and match.half_day


def test_cron_days_compression():
    assert _cron_days([18, 19, 20, 23, 24, 25, 27]) == "18-20,23-25,27"
    assert _cron_days([27]) == "27"
    assert _cron_days([1, 2, 3]) == "1-3"


def test_generate_schedules_match_calendar():
    schedules = generate_schedules(date(2026, 11, 18), date(2026, 11, 28))
    by_name = {s.name: s for s in schedules}
    assert by_name["tyche-premarket"].cron == "45 13 18-20,23-25,27 11 *"
    assert by_name["tyche-eod"].cron == "15 22 18-20,23-25 11 *"
    assert by_name["tyche-eod-halfday"].cron == "15 18 27 11 *"
    assert by_name["tyche-closing-drive"].cron == "5 20 18-20,23-25 11 *"
    assert by_name["tyche-closing-drive-halfday"].cron == "5 17 27 11 *"
    # Thanksgiving (26) appears in no schedule.
    assert all("26" not in s.cron.split()[2].split(",") for s in schedules)
    assert all(s.timezone == "UTC" for s in schedules)


def test_generate_schedules_rejects_bad_range():
    with pytest.raises(ValueError):
        generate_schedules(date(2026, 11, 28), date(2026, 11, 18))


def test_next_run_skips_holiday():
    # After the Nov 25 EOD, the next session is Nov 27 (Nov 26 is Thanksgiving).
    nr = next_run(utc(2026, 11, 25, 23, 0))
    assert nr is not None
    assert nr.utc.date() == date(2026, 11, 27)
    assert nr.name == "tyche-premarket"
    assert nr.in_seconds > 0


def test_next_run_intraday():
    nr = next_run(utc(2026, 11, 18, 14, 0))  # 09:00 ET, pre-market
    assert nr is not None
    assert nr.name == "tyche-opening-drive"
    assert nr.utc == utc(2026, 11, 18, 14, 35)


def test_session_timeline():
    regular = session_timeline(date(2026, 11, 18))
    assert [s["phase"] for s in regular] == [
        "pre_market", "opening_drive", "midday", "closing_drive", "after_hours",
    ]
    assert regular[0]["start"] == "04:00" and regular[-1]["end"] == "20:00"
    assert regular[3] == {"phase": "closing_drive", "start": "15:00", "end": "16:00"}
    half = session_timeline(date(2026, 11, 27))
    assert half[2]["end"] == "12:00"  # midday ends at half-day closing drive
    assert half[3] == {"phase": "closing_drive", "start": "12:00", "end": "13:00"}
    assert half[4]["start"] == "13:00"
    assert session_timeline(date(2026, 11, 26)) == []  # holiday