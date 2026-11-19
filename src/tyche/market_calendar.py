"""US market calendar + session-phase strategy routing for Qoder automation.

The scheduler is Qoder Forward (cloud cron); this module is the deterministic
intelligence behind it. Schedules fire on computed trading days only, and a
calendar gate (``evaluate``) decides run/skip plus which strategy sleeve runs in
each session phase. Intraday edge is concentrated in the opening and closing
drives; midday is ballast monitoring; macro/earnings events modulate risk.

All times are America/New_York (DST-aware); cron output is UTC.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import AwareDatetime, BaseModel, Field, model_validator

ET = ZoneInfo("America/New_York")
SGT = ZoneInfo("Asia/Singapore")  # operator's home clock; display-only, cron stays UTC

# Hourly desk cadence: one cron, gate-routed by live session phase. :05 aligns
# 09:05 pre-market plan (after 08:30 macro data), 10:05 opening drive, 12:05
# midday, 15:05 closing drive, 17:05 EOD reconcile.
HOURLY_FIRST = time(8, 5)
HOURLY_LAST = time(17, 5)

PRE_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
HALF_CLOSE = time(13, 0)
AFTER_CLOSE = time(20, 0)
OPENING_DRIVE_END = time(10, 30)
CLOSING_DRIVE_START = time(15, 0)
HALF_CLOSING_DRIVE_START = time(12, 0)

# NYSE full-day closures, pinned from nyse.com/trade/hours-calendars (2026-2028).
# Refresh via scripts/refresh_calendar.py; the daily `tyche calendar-check` gate
# alerts on any drift. Extend per year as NYSE publishes new years.
HOLIDAYS: dict[int, dict[date, str]] = {
    2026: {
        date(2026, 1, 1): "New Year's Day",
        date(2026, 1, 19): "MLK Jr. Day",
        date(2026, 2, 16): "Washington's Birthday",
        date(2026, 4, 3): "Good Friday",
        date(2026, 5, 25): "Memorial Day",
        date(2026, 6, 19): "Juneteenth",
        date(2026, 7, 3): "Independence Day (observed)",
        date(2026, 9, 7): "Labor Day",
        date(2026, 11, 26): "Thanksgiving",
        date(2026, 12, 25): "Christmas",
    },
    2027: {
        date(2027, 1, 1): "New Year's Day",
        date(2027, 1, 18): "MLK Jr. Day",
        date(2027, 2, 15): "Washington's Birthday",
        date(2027, 3, 26): "Good Friday",
        date(2027, 5, 31): "Memorial Day",
        date(2027, 6, 18): "Juneteenth (observed)",
        date(2027, 7, 5): "Independence Day (observed)",
        date(2027, 9, 6): "Labor Day",
        date(2027, 11, 25): "Thanksgiving",
        date(2027, 12, 24): "Christmas (observed)",
    },
    2028: {
        # New Year's Day falls on Saturday Jan 1 2028; NYSE does NOT observe it.
        date(2028, 1, 17): "MLK Jr. Day",
        date(2028, 2, 21): "Washington's Birthday",
        date(2028, 4, 14): "Good Friday",
        date(2028, 5, 29): "Memorial Day",
        date(2028, 6, 19): "Juneteenth",
        date(2028, 7, 4): "Independence Day",
        date(2028, 9, 4): "Labor Day",
        date(2028, 11, 23): "Thanksgiving",
        date(2028, 12, 25): "Christmas",
    },
}
# NYSE early closes (13:00 ET), pinned from the same source.
HALF_DAYS: dict[int, dict[date, str]] = {
    2026: {
        date(2026, 11, 27): "Day after Thanksgiving",
        date(2026, 12, 24): "Christmas Eve",
    },
    2027: {
        date(2027, 11, 26): "Day after Thanksgiving",
    },
    2028: {
        date(2028, 7, 3): "Day before Independence Day",
        date(2028, 11, 24): "Day after Thanksgiving",
    },
}


class SessionPhase(StrEnum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    OPENING_DRIVE = "opening_drive"
    MIDDAY = "midday"
    CLOSING_DRIVE = "closing_drive"
    AFTER_HOURS = "after_hours"


class Event(BaseModel):
    date: date
    name: str
    kind: Literal["macro", "fomc", "earnings", "ipo", "index"]
    time_et: str | None = None


class DiscoveredEvent(Event):
    """Scout-proposed catalyst, validated and pinned by the Desk Head."""
    symbols: list[str] = Field(default_factory=list)  # empty means market-wide
    source: str = Field(min_length=1)
    added_at: AwareDatetime


class EventOverlay(BaseModel):
    events: list[DiscoveredEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> EventOverlay:
        keys = [(e.date, e.name) for e in self.events]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate overlay event (date, name)")
        return self


def load_overlay(root: Path | None = None) -> tuple[EventOverlay, str | None]:
    """Read config/events.yaml; a broken overlay never crashes the gate."""
    path = (root or Path.cwd()) / "config" / "events.yaml"
    if not path.exists():
        return EventOverlay(), None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return EventOverlay.model_validate(payload), None
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return EventOverlay(), f"event overlay invalid ({path}): {exc}"


# FOMC decision days 2026 + the competition-window macro/earnings calendar
# (distilled from docs/competition/rules.md) + verified single-name catalysts.
# Treat external news as untrusted.
EVENTS_2026: list[Event] = [
    Event(date=date(2026, 1, 28), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 3, 18), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 4, 29), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 6, 17), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 7, 29), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 9, 16), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 10, 28), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 12, 9), name="FOMC decision", kind="fomc", time_et="14:00"),
    Event(date=date(2026, 11, 17), name="Retail sales", kind="macro", time_et="08:30"),
    Event(date=date(2026, 11, 17), name="NVDA earnings", kind="earnings"),
    Event(date=date(2026, 11, 18), name="FOMC minutes", kind="fomc", time_et="14:00"),
    # ANT priced $83 (above range), ~$81.3B raised, ~$1.5T valuation; first trade
    # may start well after 09:30 ET. SPCX analog: +19% day one, -53% from peak in 7 weeks.
    Event(date=date(2026, 11, 19), name="Anthropic (ANT) Nasdaq IPO debut", kind="ipo"),
    Event(date=date(2026, 11, 25), name="PCE price index", kind="macro", time_et="08:30"),
    Event(date=date(2026, 11, 25), name="Beige Book", kind="macro", time_et="14:00"),
    # Hang Seng HK-US Tech Index adds ANT; equal-weight rebalance after Nov 30
    # close, effective Dec 4 (ANT's 11th trading day) -> passive-flow catalyst.
    Event(date=date(2026, 12, 4), name="ANT Hang Seng HK-US Tech Index inclusion", kind="index"),
]

_EARNINGS_QUARTER = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}


def holiday_name(d: date) -> str | None:
    return HOLIDAYS.get(d.year, {}).get(d)


def half_day_name(d: date) -> str | None:
    return HALF_DAYS.get(d.year, {}).get(d)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and holiday_name(d) is None


def is_half_day(d: date) -> bool:
    return is_trading_day(d) and half_day_name(d) is not None


def regular_close(d: date) -> time:
    return HALF_CLOSE if is_half_day(d) else REGULAR_CLOSE


def closing_drive_start(d: date) -> time:
    return HALF_CLOSING_DRIVE_START if is_half_day(d) else CLOSING_DRIVE_START


def session_timeline(d: date) -> list[dict]:
    """ET boundaries of each session phase for a day (half-day aware).

    Empty on non-trading days. Drives the dashboard's session-phase rail.
    """
    if not is_trading_day(d):
        return []
    close = regular_close(d)
    cd_start = closing_drive_start(d)
    segments = [
        (SessionPhase.PRE_MARKET, PRE_OPEN, REGULAR_OPEN),
        (SessionPhase.OPENING_DRIVE, REGULAR_OPEN, OPENING_DRIVE_END),
        (SessionPhase.MIDDAY, OPENING_DRIVE_END, cd_start),
        (SessionPhase.CLOSING_DRIVE, cd_start, close),
        (SessionPhase.AFTER_HOURS, close, AFTER_CLOSE),
    ]
    return [
        {"phase": phase.value, "start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")}
        for phase, start, end in segments
    ]


def _et(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(ET)


def phase_at(now: datetime) -> SessionPhase:
    local = _et(now)
    d = local.date()
    if not is_trading_day(d):
        return SessionPhase.CLOSED
    t = local.time()
    close = regular_close(d)
    if t < PRE_OPEN or t >= AFTER_CLOSE:
        return SessionPhase.CLOSED
    if t < REGULAR_OPEN:
        return SessionPhase.PRE_MARKET
    if t < OPENING_DRIVE_END:
        return SessionPhase.OPENING_DRIVE
    if t < closing_drive_start(d):
        return SessionPhase.MIDDAY
    if t < close:
        return SessionPhase.CLOSING_DRIVE
    return SessionPhase.AFTER_HOURS


def earnings_season(d: date) -> str | None:
    quarter = _EARNINGS_QUARTER.get(d.month)
    if quarter and 10 <= d.day <= 31:
        return f"{quarter} earnings season"
    return None


def events_on(d: date, overlay: EventOverlay | None = None) -> list[Event]:
    if overlay is None:
        overlay, _ = load_overlay()
    events = [e for e in EVENTS_2026 if e.date == d]
    events += [e for e in overlay.events if e.date == d]
    season = earnings_season(d)
    if season and not any(e.kind == "earnings" for e in events):
        events.append(Event(date=d, name=season, kind="earnings"))
    return events


def is_event_day(d: date) -> bool:
    return bool(events_on(d))


class StrategyDirective(BaseModel):
    phase: SessionPhase
    activity: Literal["plan", "active", "monitor", "reconcile", "noop"]
    sleeves: list[str] = Field(default_factory=list)
    new_entries: bool = False
    max_orders: int = 0
    event_caution: bool = False
    risk_note: str = ""


_BASE_DIRECTIVES: dict[SessionPhase, StrategyDirective] = {
    SessionPhase.PRE_MARKET: StrategyDirective(
        phase=SessionPhase.PRE_MARKET, activity="plan",
        sleeves=["equity", "defensive", "real_asset", "credit"],
        risk_note="research + plan + auditor critique; no orders without per-order approval",
    ),
    SessionPhase.OPENING_DRIVE: StrategyDirective(
        phase=SessionPhase.OPENING_DRIVE, activity="active",
        sleeves=["equity", "real_asset", "credit"], new_entries=True, max_orders=2,
        risk_note="opening-drive intraday edge; first-hour liquidity and price discovery",
    ),
    SessionPhase.MIDDAY: StrategyDirective(
        phase=SessionPhase.MIDDAY, activity="monitor",
        sleeves=["defensive", "equity"], max_orders=1,
        risk_note="midday lull: ballast monitor; act only on drift breach or risk halt",
    ),
    SessionPhase.CLOSING_DRIVE: StrategyDirective(
        phase=SessionPhase.CLOSING_DRIVE, activity="active",
        sleeves=["equity", "defensive", "real_asset", "credit"], new_entries=True, max_orders=3,
        risk_note="closing-drive intraday edge + rebalance to target; last-hour liquidity",
    ),
    SessionPhase.AFTER_HOURS: StrategyDirective(
        phase=SessionPhase.AFTER_HOURS, activity="reconcile",
        risk_note="EOD reconcile + modeled fees + persist; no new orders (after-hours excluded on final day)",
    ),
    SessionPhase.CLOSED: StrategyDirective(
        phase=SessionPhase.CLOSED, activity="noop", risk_note="market closed",
    ),
}


def strategy_for(phase: SessionPhase, event_day: bool = False) -> StrategyDirective:
    base = _BASE_DIRECTIVES[phase]
    if event_day and base.activity == "active":
        return base.model_copy(update={
            "max_orders": max(1, base.max_orders // 2),
            "event_caution": True,
            "risk_note": base.risk_note + " · event caution: halve order count and size",
        })
    return base


class NextRun(BaseModel):
    name: str
    phase: SessionPhase
    utc: datetime
    et: datetime
    in_seconds: int


class GateResult(BaseModel):
    now_utc: datetime
    now_et: datetime
    trading_day: bool
    half_day: bool
    holiday: str | None = None
    phase: SessionPhase
    run: bool
    reason: str
    strategy: StrategyDirective
    events: list[Event] = Field(default_factory=list)
    overlay_error: str | None = None
    next_run: NextRun | None = None


# Phase-anchored alternative (one schedule per session phase). The live desk
# runs the hourly cadence below; these templates remain for rollback/hybrid.
# name, ET fire time, intended phase, day applicability
_SCHEDULE_TEMPLATES: list[tuple[str, time, SessionPhase, Literal["all", "regular", "half"]]] = [
    ("tyche-premarket", time(8, 45), SessionPhase.PRE_MARKET, "all"),
    ("tyche-opening-drive", time(9, 35), SessionPhase.OPENING_DRIVE, "all"),
    ("tyche-midday-monitor", time(12, 0), SessionPhase.MIDDAY, "all"),
    ("tyche-closing-drive", time(15, 5), SessionPhase.CLOSING_DRIVE, "regular"),
    ("tyche-closing-drive-halfday", time(12, 5), SessionPhase.CLOSING_DRIVE, "half"),
    ("tyche-eod", time(17, 15), SessionPhase.AFTER_HOURS, "regular"),
    ("tyche-eod-halfday", time(13, 15), SessionPhase.AFTER_HOURS, "half"),
]


def _applies(d: date, scope: str) -> bool:
    if not is_trading_day(d):
        return False
    if scope == "all":
        return True
    if scope == "half":
        return is_half_day(d)
    return not is_half_day(d)


class ScheduleDef(BaseModel):
    name: str
    cron: str
    timezone: str = "UTC"
    phase: SessionPhase | None = None
    et_time: str
    sgt_time: str
    scope: Literal["all", "regular", "half"]
    activity: str
    days: int
    note: str


def _sgt_span(first_utc: datetime, last_utc: datetime) -> str:
    a, b = first_utc.astimezone(SGT), last_utc.astimezone(SGT)
    span = f"{a:%H:%M}" if a == b else f"{a:%H:%M}-{b:%H:%M}"
    if b.date() > a.date():
        span += " (+1d)"
    return span


def _cron_days(days: list[int]) -> str:
    """Compress a sorted day list into cron ranges (1-5,9,12-14)."""
    parts: list[str] = []
    start = prev = days[0]
    for d in days[1:]:
        if d == prev + 1:
            prev = d
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = d
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def generate_schedules(start: date, end: date) -> list[ScheduleDef]:
    """Emit Qoder Forward cron defs (UTC) that fire only on applicable trading days.

    Day-of-month lists are computed from the calendar, so holidays and weekends
    are skipped precisely and the result generalizes to any month/year. ET fire
    times are converted to UTC per day, so DST transitions split cleanly.
    """
    if end < start:
        raise ValueError("end must be on or after start")
    grouped: dict[tuple[str, int, int, int], list[int]] = {}
    meta: dict[tuple[str, int, int, int], tuple[time, SessionPhase, str, str]] = {}
    day = start
    while day <= end:
        for name, et_time, phase, scope in _SCHEDULE_TEMPLATES:
            if not _applies(day, scope):
                continue
            fire_et = datetime.combine(day, et_time, tzinfo=ET)
            fire_utc = fire_et.astimezone(UTC)
            key = (name, fire_utc.month, fire_utc.hour, fire_utc.minute)
            grouped.setdefault(key, []).append(fire_utc.day)
            meta[key] = (et_time, phase, scope, _sgt_span(fire_utc, fire_utc))
        day += timedelta(days=1)
    schedules: list[ScheduleDef] = []
    for (name, month, hour, minute), days in sorted(grouped.items()):
        et_time, phase, scope, sgt = meta[(name, month, hour, minute)]
        directive = strategy_for(phase)
        cron = f"{minute} {hour} {_cron_days(sorted(days))} {month} *"
        schedules.append(ScheduleDef(
            name=name, cron=cron, phase=phase, et_time=et_time.strftime("%H:%M"),
            sgt_time=sgt, scope=scope, activity=directive.activity, days=len(days),
            note=directive.risk_note,
        ))
    return schedules


def generate_hourly_schedules(start: date, end: date) -> list[ScheduleDef]:
    """Emit the hourly desk cron (UTC) firing only on trading days.

    One schedule, 08:05-17:05 ET at :05; the evaluate() gate routes each run by
    live phase (plan / active / monitor / reconcile), half days included. Days
    sharing the same UTC hour set are grouped, so DST transitions split cleanly.
    """
    if end < start:
        raise ValueError("end must be on or after start")
    grouped: dict[tuple[int, tuple[int, ...]], list[int]] = {}
    spans: dict[tuple[int, tuple[int, ...]], tuple[datetime, datetime]] = {}
    day = start
    while day <= end:
        if is_trading_day(day):
            fires = [
                datetime.combine(day, time(h, HOURLY_FIRST.minute), tzinfo=ET).astimezone(UTC)
                for h in range(HOURLY_FIRST.hour, HOURLY_LAST.hour + 1)
            ]
            key = (fires[0].month, tuple(sorted(f.hour for f in fires)))
            grouped.setdefault(key, []).append(day.day)
            spans[key] = (fires[0], fires[-1])
        day += timedelta(days=1)
    schedules: list[ScheduleDef] = []
    for (month, hours), days in sorted(grouped.items()):
        cron = f"{HOURLY_FIRST.minute} {_cron_days(list(hours))} {_cron_days(sorted(days))} {month} *"
        schedules.append(ScheduleDef(
            name="tyche-hourly", cron=cron, phase=None,
            et_time=f"{HOURLY_FIRST:%H:%M}-{HOURLY_LAST:%H:%M}",
            sgt_time=_sgt_span(*spans[(month, hours)]),
            scope="all", activity="gate-routed", days=len(days),
            note="hourly gate-routed: plan pre-market, active drives, monitor midday, reconcile after close",
        ))
    return schedules


def next_run(now: datetime) -> NextRun | None:
    local = _et(now)
    for offset in range(12):
        d = local.date() + timedelta(days=offset)
        if not is_trading_day(d):
            continue
        for h in range(HOURLY_FIRST.hour, HOURLY_LAST.hour + 1):
            fire_et = datetime.combine(d, time(h, HOURLY_FIRST.minute), tzinfo=ET)
            fire_utc = fire_et.astimezone(UTC)
            if fire_utc <= now.astimezone(UTC):
                continue
            return NextRun(
                name="tyche-hourly", phase=phase_at(fire_utc), utc=fire_utc, et=fire_et,
                in_seconds=int((fire_utc - now.astimezone(UTC)).total_seconds()),
            )
    return None


def evaluate(now: datetime, intended_phase: SessionPhase | None = None,
             root: Path | None = None) -> GateResult:
    """Calendar gate: decide whether a scheduled run should act, and how.

    Called first inside every Qoder automation run. Returns run=False on
    weekends/holidays/outside-session, or when the live phase does not match the
    schedule's intended phase (e.g. a regular-close cron firing on a half day).
    """
    local = _et(now)
    d = local.date()
    trading = is_trading_day(d)
    half = is_half_day(d)
    holiday = holiday_name(d)
    phase = phase_at(now)
    overlay, overlay_error = load_overlay(root)
    events = events_on(d, overlay)
    strategy = strategy_for(phase, bool(events))
    if not trading:
        run, reason = False, f"market closed: {holiday or 'weekend'}"
    elif phase is SessionPhase.CLOSED:
        run, reason = False, "outside trading session (04:00-20:00 ET)"
    elif intended_phase is not None and phase is not intended_phase:
        run, reason = False, f"phase mismatch: schedule wants {intended_phase}, now {phase}"
    else:
        run, reason = True, f"{phase} active"
    return GateResult(
        now_utc=now.astimezone(UTC), now_et=local, trading_day=trading, half_day=half,
        holiday=holiday, phase=phase, run=run, reason=reason, strategy=strategy,
        events=events, overlay_error=overlay_error, next_run=next_run(now),
    )