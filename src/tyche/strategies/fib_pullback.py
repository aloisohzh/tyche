"""PB-007 fib 50% pullback: a deterministic swing signal on completed daily bars (ADR 0017).

The signal never calls an LLM and never touches a broker. It reads daily OHLC bars, finds the
last impulse leg (swing low -> swing high), checks a moving-average regime filter and emits a
complete ``LifecyclePlan`` for the lifecycle lane: entry zone between the 61.8% and 50%
retracements, stop under the 78.6% level, target at the swing high, time exit after a fixed
number of sessions. Sizing is fixed-fractional risk to the stop, capped by notional. Everything
the plan claims is reproducible from the bars it was built from, and the thesis block says so.

Vocabulary: a ratio ``r`` means "r of the leg retraced from the swing high", so
``level(r) = high - r * (high - low)``; 0.5 is halfway back down, 0.786 deeper.
"""
from __future__ import annotations

import csv
import hashlib
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tyche.config import FibPullbackConfig
from tyche.lifecycle import LifecyclePlan, Trigger
from tyche.market_calendar import ET, is_trading_day, regular_close

ENTRY_EXPIRES_BEFORE_CLOSE = timedelta(minutes=10)
DEADLINE_BEFORE_CLOSE = timedelta(minutes=30)


class Bar(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(default=0.0, ge=0)


class Factor(BaseModel):
    name: str
    axis: str = "technical"
    state: str  # pass | fail | unknown
    why: str = ""
    detail: str = ""


class FibSignal(BaseModel):
    """Everything the plan is derived from, so a reviewer can recompute each number."""
    model_config = ConfigDict(allow_inf_nan=False)
    symbol: str
    as_of: date
    swing_low: float
    swing_low_date: date
    swing_high: float
    swing_high_date: date
    high_age: int
    atr: float
    sma_fast: float
    sma_slow: float
    sma_fast_prev: float
    last_close: float
    last_low: float
    levels: dict[str, float]
    entry_low: float
    entry_high: float
    stop: float
    target: float
    reward_risk: float
    confluence: list[str] = Field(default_factory=list)
    factors: list[Factor] = Field(default_factory=list)


class ScanResult(BaseModel):
    as_of: date | None
    strategy_id: str
    rules_hash: str
    nav: float
    plans: list[LifecyclePlan] = Field(default_factory=list)
    signals: list[FibSignal] = Field(default_factory=list)
    rejected: dict[str, str] = Field(default_factory=dict)
    bars_sha256: str = ""


# ---------------------------------------------------------------- indicators

def sma(values: list[float], n: int) -> float:
    if len(values) < n or n <= 0:
        raise ValueError("not enough values for the moving average")
    return sum(values[-n:]) / n


def atr(bars: list[Bar], n: int) -> float:
    """Simple mean of the true range over the last n bars (stated, not Wilder-smoothed)."""
    if len(bars) < n + 1:
        raise ValueError("not enough bars for ATR")
    ranges = []
    for prev, cur in zip(bars[-(n + 1):-1], bars[-n:], strict=True):
        ranges.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(ranges) / n


def level(low: float, high: float, ratio: float) -> float:
    return round(high - ratio * (high - low), 2)


def impulse_leg(bars: list[Bar], cfg: FibPullbackConfig) -> tuple[int, int] | None:
    """(index of swing low, index of swing high) inside the lookback, or None when there is no leg.

    The swing high is the highest high of the lookback; the swing low is the lowest low from the
    start of the lookback up to that high. Ties resolve to the most recent high and the earliest low,
    so the same bars always give the same leg.
    """
    window = bars[-cfg.leg.lookback:]
    if len(window) < cfg.leg.lookback:
        return None
    offset = len(bars) - len(window)
    i_high = max(range(len(window)), key=lambda i: (window[i].high, i))
    if i_high == 0:
        return None
    i_low = min(range(i_high + 1), key=lambda i: (window[i].low, i))
    if i_low >= i_high:
        return None
    return offset + i_low, offset + i_high


def confluence_notes(bars: list[Bar], sig_entry: float, lo: float, hi: float,
                     sma_fast: float, atr_value: float, i_low: int,
                     cfg: FibPullbackConfig) -> list[str]:
    notes = []
    zone_bottom, zone_top = level(lo, hi, cfg.fib.stop_level), level(lo, hi, cfg.fib.zone_top)
    if zone_bottom <= sma_fast <= zone_top:
        notes.append(f"SMA{cfg.regime.sma_fast} {sma_fast:.2f} sits inside the retracement zone")
    prior = bars[max(0, i_low - cfg.leg.lookback):i_low]
    near = [b for b in prior if abs(b.high - sig_entry) <= 0.5 * atr_value]
    if near:
        notes.append(f"prior swing high {max(b.high for b in near):.2f} within 0.5 ATR of the 50% level")
    return notes


# ---------------------------------------------------------------- the signal

def signal(symbol: str, bars: list[Bar], cfg: FibPullbackConfig) -> tuple[FibSignal | None, str]:
    """(signal, reason). A None signal always comes with the gate that rejected it."""
    bars = sorted(bars, key=lambda b: b.date)
    if len({b.date for b in bars}) != len(bars):
        return None, "data.duplicate_dates"
    if len(bars) < cfg.min_bars:
        return None, f"data.insufficient: {len(bars)} bars < {cfg.min_bars}"
    closes = [b.close for b in bars]
    last = bars[-1]
    reg = cfg.regime
    fast, slow = sma(closes, reg.sma_fast), sma(closes, reg.sma_slow)
    fast_prev = sma(closes[:-reg.slope_bars], reg.sma_fast)
    factors = [
        Factor(name="close above slow SMA", state="pass" if last.close > slow else "fail",
               why=f"close {last.close:.2f} vs SMA{reg.sma_slow} {slow:.2f}"),
        Factor(name="fast SMA above slow and rising",
               state="pass" if fast > slow and fast > fast_prev else "fail",
               why=f"SMA{reg.sma_fast} {fast:.2f} vs SMA{reg.sma_slow} {slow:.2f}, "
                   f"{reg.slope_bars} bars ago {fast_prev:.2f}"),
    ]
    if any(f.state != "pass" for f in factors):
        return None, "regime.off: " + "; ".join(f.why for f in factors if f.state != "pass")
    leg = impulse_leg(bars, cfg)
    if leg is None:
        return None, "leg.none: no swing low before the lookback high"
    i_low, i_high = leg
    lo, hi = bars[i_low].low, bars[i_high].high
    high_age = len(bars) - 1 - i_high
    if not cfg.leg.min_high_age <= high_age <= cfg.leg.max_high_age:
        return None, f"leg.stale_or_fresh: swing high {high_age} bars ago"
    atr_value = atr(bars, cfg.leg.atr_period)
    if hi - lo < cfg.leg.min_leg_atr * atr_value:
        return None, f"leg.small: {hi - lo:.2f} < {cfg.leg.min_leg_atr} x ATR {atr_value:.2f}"
    fib = cfg.fib
    levels = {f"fib{r:g}": level(lo, hi, r) for r in sorted({fib.zone_top, fib.entry, fib.zone_bottom, fib.stop_level})}
    zone_top, entry, zone_bottom = level(lo, hi, fib.zone_top), level(lo, hi, fib.entry), level(lo, hi, fib.zone_bottom)
    if any(b.close < zone_bottom for b in bars[i_high + 1:]):
        return None, f"zone.failed: a close since the swing high fell below {zone_bottom:.2f}"
    if last.low > zone_top:
        return None, f"zone.untouched: yesterday's low {last.low:.2f} above {zone_top:.2f}"
    stop = round(level(lo, hi, fib.stop_level) - fib.stop_atr_buffer * atr_value, 2)
    target = round(hi, 2)
    if not stop < zone_bottom <= entry < target:
        return None, "levels.inconsistent"
    reward_risk = (target - entry) / (entry - stop)
    if reward_risk < cfg.min_reward_risk:
        return None, f"reward_risk.low: {reward_risk:.2f} < {cfg.min_reward_risk}"
    notes = confluence_notes(bars, entry, lo, hi, fast, atr_value, i_low, cfg)
    factors += [
        Factor(name="impulse leg size", state="pass",
               why=f"{lo:.2f} ({bars[i_low].date}) -> {hi:.2f} ({bars[i_high].date}) = "
                   f"{(hi - lo) / atr_value:.1f} ATR"),
        Factor(name="pullback inside zone, zone holding", state="pass",
               why=f"low {last.low:.2f} <= {zone_top:.2f}; every close since the high >= {zone_bottom:.2f}"),
        Factor(name="reward to risk at the limit", state="pass", why=f"{reward_risk:.2f}R"),
        Factor(name="confluence", state="pass" if notes else "unknown",
               why="; ".join(notes) or "no S/R or moving-average confluence found; ranking tiebreaker only"),
    ]
    return FibSignal(
        symbol=symbol, as_of=last.date, swing_low=lo, swing_low_date=bars[i_low].date,
        swing_high=hi, swing_high_date=bars[i_high].date, high_age=high_age, atr=round(atr_value, 4),
        sma_fast=round(fast, 4), sma_slow=round(slow, 4), sma_fast_prev=round(fast_prev, 4),
        last_close=last.close, last_low=last.low, levels=levels, entry_low=zone_bottom,
        entry_high=entry, stop=stop, target=target, reward_risk=round(reward_risk, 4),
        confluence=notes, factors=factors,
    ), "ok"


# ---------------------------------------------------------------- sizing and the plan

def size(sig: FibSignal, nav: float, cfg: FibPullbackConfig) -> int:
    """Fixed-fractional risk to the stop, capped by notional; R is measured from the limit price."""
    if nav <= 0:
        return 0
    per_share_risk = sig.entry_high - sig.stop
    by_risk = math.floor(cfg.risk_per_trade_pct * nav / per_share_risk)
    by_notional = math.floor(cfg.max_notional_pct * nav / sig.entry_high)
    return max(0, min(by_risk, by_notional))


def _next_trading_day(d: date) -> date:
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def _sessions_ahead(d: date, n: int) -> date:
    out = d
    for _ in range(n):
        out = _next_trading_day(out + timedelta(days=1))
    return out


def thesis_text(sig: FibSignal, cfg: FibPullbackConfig) -> str:
    return (
        f"Rule-generated (PB fib pullback, no scout): {sig.symbol} rallied {sig.swing_low:.2f} "
        f"({sig.swing_low_date}) to {sig.swing_high:.2f} ({sig.swing_high_date}), "
        f"{(sig.swing_high - sig.swing_low) / sig.atr:.1f} ATR, with close above SMA{cfg.regime.sma_slow} "
        f"and a rising SMA{cfg.regime.sma_fast}. Price has pulled back into the "
        f"{cfg.fib.zone_top:.1%}-{cfg.fib.zone_bottom:.1%} retracement zone and every close since the high "
        f"held above {sig.entry_low:.2f}. Buy between {sig.entry_low:.2f} and {sig.entry_high:.2f}, stop "
        f"{sig.stop:.2f} (under the {cfg.fib.stop_level:.1%} level), target {sig.target:.2f} (swing high), "
        f"{sig.reward_risk:.2f}R at the limit. Confluence: {'; '.join(sig.confluence) or 'none'}."
    )


def thesis_block(sig: FibSignal, cfg: FibPullbackConfig, bars_sha256: str) -> dict:
    """Same shape the tactical planner carries for scout theses, labelled as rule output."""
    return {
        "thesis": thesis_text(sig, cfg),
        "synthesis": "deterministic daily-bar signal; the regime filter and the leg geometry are the whole case",
        "edge": "asymmetric geometry (stop under 78.6%, target at the swing high) in a confirmed uptrend; unvalidated",
        "bear_case": "pullbacks keep going at trend tops and in chop; the 50% level breaks and the stop is paid",
        "invalidation": f"daily close below {sig.entry_low:.2f} before fill cancels; after fill the stop {sig.stop:.2f}, "
                        f"a close below SMA{cfg.regime.sma_slow}, or {cfg.max_hold_sessions} sessions ends it",
        "horizon": f"{cfg.max_hold_sessions} sessions",
        "direction": "bullish",
        "factors": [f.model_dump() for f in sig.factors],
        "outlook": {"regime": "uptrend by SMA filter", "conviction": "medium" if sig.confluence else "low",
                    "alignment": {"technical": "bull"}},
        "thesis_ref": f"bars sha256 {bars_sha256[:12]} as of {sig.as_of.isoformat()}",
        "source": "rules",
    }


def build_plan(sig: FibSignal, nav: float, cfg: FibPullbackConfig, rules_hash: str,
               now: datetime, bars_sha256: str = "", latest_deadline: date | None = None) -> LifecyclePlan | None:
    """A complete lifecycle contract, or None when no share fits the budget or the window is over.

    `latest_deadline` clamps the holding deadline (the competition's last session, for example);
    an entry whose deadline would land on or before its own entry day is not worth opening.
    """
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    quantity = size(sig, nav, cfg)
    if quantity <= 0:
        return None
    today_et = now.astimezone(ET).date()
    entry_day = _next_trading_day(today_et)
    expires = datetime.combine(entry_day, regular_close(entry_day), ET) - ENTRY_EXPIRES_BEFORE_CLOSE
    if expires <= now:
        entry_day = _next_trading_day(today_et + timedelta(days=1))
        expires = datetime.combine(entry_day, regular_close(entry_day), ET) - ENTRY_EXPIRES_BEFORE_CLOSE
    deadline_day = _sessions_ahead(entry_day, cfg.max_hold_sessions)
    if latest_deadline is not None and deadline_day > latest_deadline:
        deadline_day = latest_deadline
        while not is_trading_day(deadline_day):
            deadline_day -= timedelta(days=1)
        if deadline_day <= entry_day:
            return None
    deadline = datetime.combine(deadline_day, regular_close(deadline_day), ET) - DEADLINE_BEFORE_CLOSE
    return LifecyclePlan(
        plan_id=f"{cfg.id}-{sig.as_of.strftime('%Y%m%d')}-{sig.symbol.split('.')[-1]}",
        revision=1, symbol=sig.symbol, strategy_id=cfg.id, rules_hash=rules_hash,
        thesis=thesis_text(sig, cfg),
        invalidation_rules=[
            f"before fill: a daily close below {sig.entry_low:.2f} (the {cfg.fib.zone_bottom:.1%} level) cancels the entry",
            f"after fill: last price at or below the stop {sig.stop:.2f}",
            f"after fill: a daily close below SMA{cfg.regime.sma_slow} (regime lost) exits at the next session",
            f"time: flat by the exit deadline, {cfg.max_hold_sessions} sessions after entry",
            "sourced material adverse event on the issuer or sector marks the review invalidated",
        ],
        created_at=now, mode="new_entry", quantity=quantity,
        entry_low=sig.entry_low, entry_high=sig.entry_high,
        stop=Trigger(price=sig.stop, basis="last"),
        take_profit=Trigger(price=sig.target, basis="last"),
        entry_expires_at=expires, exit_deadline=deadline,
        review_max_age_minutes=60,
    )


# ---------------------------------------------------------------- data and the scan

def load_ohlc(path: Path, as_of: date | None = None) -> dict[str, list[Bar]]:
    """Long CSV `date,symbol,open,high,low,close[,volume]` -> symbol -> bars sorted by date."""
    out: dict[str, dict[date, Bar]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "open", "high", "low", "close"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise ValueError(f"OHLC file needs columns {sorted(required)}")
        for row in reader:
            day = date.fromisoformat(row["date"])
            if as_of is not None and day > as_of:
                continue
            bar = Bar(date=day, open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                      close=float(row["close"]), volume=float(row.get("volume") or 0))
            out.setdefault(row["symbol"], {})[day] = bar
    return {symbol: [bars[d] for d in sorted(bars)] for symbol, bars in sorted(out.items())}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scan(bars_by_symbol: dict[str, list[Bar]], cfg: FibPullbackConfig, nav: float, rules_hash: str,
         now: datetime, *, open_symbols: set[str] | None = None, event_names: list[str] | None = None,
         bars_sha256: str = "", latest_deadline: date | None = None) -> ScanResult:
    """Run the signal over the lane's scope and keep the best plans up to the open-slot budget.

    Ranking: more confluence first, then higher reward/risk. Symbols already held or planned are
    skipped (one lifecycle per symbol). A blackout event today empties the plan list but keeps the
    signals, so the report still shows what fired.
    """
    open_symbols = open_symbols or set()
    as_of_dates = {bars[-1].date for bars in bars_by_symbol.values() if bars}
    result = ScanResult(as_of=max(as_of_dates) if as_of_dates else None, strategy_id=cfg.id,
                        rules_hash=rules_hash, nav=nav, bars_sha256=bars_sha256)
    blackout = [name for name in (event_names or [])
                if any(kind.lower() in name.lower() for kind in cfg.no_entry_event_kinds)]
    for symbol in cfg.symbols:
        if symbol in open_symbols:
            result.rejected[symbol] = "held or already planned; one lifecycle per symbol"
            continue
        bars = bars_by_symbol.get(symbol)
        if not bars:
            result.rejected[symbol] = "data.missing"
            continue
        if result.as_of and bars[-1].date != result.as_of:
            result.rejected[symbol] = f"data.stale: last bar {bars[-1].date} != {result.as_of}"
            continue
        sig, reason = signal(symbol, bars, cfg)
        if sig is None:
            result.rejected[symbol] = reason
            continue
        result.signals.append(sig)
    result.signals.sort(key=lambda s: (-len(s.confluence), -s.reward_risk, s.symbol))
    slots = max(0, cfg.max_open - len(open_symbols))
    if blackout:
        result.rejected["*"] = "event blackout today: " + "; ".join(blackout)
        return result
    for sig in result.signals:
        if len(result.plans) >= slots:
            result.rejected[sig.symbol] = "ranked below the open-slot budget"
            continue
        plan = build_plan(sig, nav, cfg, rules_hash, now, bars_sha256, latest_deadline)
        if plan is None:
            result.rejected[sig.symbol] = "no room: one share exceeds the budget, or the window ends before a deadline fits"
            continue
        result.plans.append(plan)
    return result
