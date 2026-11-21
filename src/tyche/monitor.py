"""Level 0 protection monitor: deterministic breach detection, no orders, no submissions.

ADR 0013's detector, built to the contract in
[docs/runbooks/intraday-protection-monitor.md](../../docs/runbooks/intraday-protection-monitor.md) §2.
The blind window on an open lot is the distance between checks, and the desk fires three
times a day, so "we noticed at 15:05" is not protection. This module is the piece that runs
every few minutes in plain Python: it reads a book, a quote file and the journal, decides
whether a journaled level has been breached, and emits `monitor.*` events.

What it can do: evaluate, journal `monitor.heartbeat` / `monitor.breach` / `monitor.clear` /
`monitor.gap` / `monitor.error`, and shout by exiting non-zero when it could not judge.

What it can never do, at this level or any other in this file: size an order, submit one,
authorize one, widen a level, or make an entry more urgent. A detected breach is an alert;
what makes it *actionable* while the operator is away is the pre-armed bounded exit in
[envelope.py](envelope.py) (rung 1.5), which the operator signed in advance.

The judgment is a pure function of its inputs - `--at` replay reproduces exactly the same
breach set - which is the whole reason a breach decision is reviewable without an LLM in the
loop (§8.3).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from tyche.envelope import ExitLevel, exit_levels
from tyche.market_calendar import ET, SessionPhase, is_trading_day, phase_at
from tyche.tactical import RTH, MarketQuote
from tyche.watchlist import Watchlist

# The build starts at the 5-minute tier (§3): while `options_enabled` is false the 1-2 minute
# tiers buy nothing, and a cadence the desk cannot afford is a cadence that gets switched off.
# Cadence is deliberately a runner argument, not a config field: `config_hash` folds the whole
# loaded AppConfig into every `setup_hash` (`tactical.py:67-75`), so adding a knob here would
# re-bind every open plan and `tactical_cli.py:269` would refuse its envelope as "setup changed".
DEFAULT_CADENCE_SECONDS = 300

LevelKind = Literal["synthetic_stop", "defined_risk", "rebalance"]


@dataclass(frozen=True)
class WatchTarget:
    """One held instrument, the level that protects it, and what price the level is stated against."""

    symbol: str
    quote_symbol: str
    level: float
    direction: Literal["bullish", "bearish"]
    strategy_id: str | None
    protection_type: LevelKind
    source: str
    setup_id: str | None

    def is_breached(self, price: float) -> bool:
        """Bullish levels sit below the market; a bearish put's stop sits above its underlying."""
        return price <= self.level if self.direction == "bullish" else price >= self.level

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "quote_symbol": self.quote_symbol, "level": self.level,
            "direction": self.direction, "strategy_id": self.strategy_id,
            "protection_type": self.protection_type, "level_source": self.source,
            "setup_id": self.setup_id,
        }


def episode_id(symbol: str, started_at: datetime) -> str:
    """Stable per (symbol, first breach tick), so a replay reproduces the same ids."""
    seed = f"{symbol}|{started_at.isoformat()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def protection_type(level: ExitLevel) -> LevelKind:
    """Which row of the cadence table a level belongs to, from the plan that wrote it."""
    entry = level.entry
    if entry is not None and entry.option:
        return "defined_risk"
    if (level.strategy_id or "").upper() == "PB-001":
        # Ballast is alert-only by design: it exits at the next rebalance, never at a stop.
        return "rebalance"
    return "synthetic_stop"


def watch_targets(book: Watchlist | None, events: list[dict],
                  held: set[str] | None = None) -> tuple[list[WatchTarget], list[str], list[str]]:
    """Levels worth watching, the reasons anything was left out, and journal problems.

    Journal levels win over watchlist levels because the journal holds the contract the
    executor would actually honour. A watchlist row only counts when it says the plan was
    entered: watching an unexecuted idea would turn the monitor into a price alert service.
    """
    levels, problems = exit_levels(events)
    for entry in (book.entries if book else []):
        if entry.status != "entered" or entry.invalidated or entry.symbol in levels:
            continue
        levels[entry.symbol] = ExitLevel(
            symbol=entry.symbol, stop=entry.stop, source="watchlist",
            setup_id=entry.setup_id or None, direction=entry.direction, entry=entry,
        )

    targets: list[WatchTarget] = []
    skipped: list[str] = []
    for symbol, level in sorted(levels.items()):
        entry = level.entry
        if entry is not None and entry.status in ("exited", "dropped"):
            skipped.append(f"{symbol}: plan says {entry.status}, so nothing is being protected")
            continue
        quote_symbol = entry.underlying if entry is not None else symbol
        if quote_symbol != symbol and entry is not None and entry.option is None:
            skipped.append(f"{symbol}: level is stated against {quote_symbol}, which is not held")
            continue
        if held is not None and symbol not in held:
            skipped.append(f"{symbol}: journaled level exists but the book holds nothing")
            continue
        targets.append(WatchTarget(
            symbol=symbol, quote_symbol=quote_symbol, level=float(level.stop),
            direction=level.direction, strategy_id=level.strategy_id,
            protection_type=protection_type(level), source=level.source,
            setup_id=level.setup_id,
        ))
    return targets, skipped, problems


def open_episodes(events: list[dict]) -> dict[str, dict[str, Any]]:
    """Unresolved breaches keyed by symbol, read back out of the journal.

    State lives in the chain rather than in a side file, because that is what makes a replay
    reproduce yesterday's verdicts: the journal already says what was breached when.
    """
    open_by_symbol: dict[str, dict[str, Any]] = {}
    for event in events:
        payload = event.get("payload") or {}
        symbol = payload.get("symbol")
        if not isinstance(symbol, str):
            continue
        if event.get("type") == "monitor.breach":
            open_by_symbol[symbol] = {
                "episode_id": payload.get("episode_id"),
                # The market time the level was printed through, not the append stamp: an event
                # journaled late (or replayed days later) must not stretch an episode that was
                # already over. `ts` only answers "when did the writer get to it".
                "started_at": payload.get("observed_at") or event.get("ts"),
                "level": payload.get("level"),
            }
        elif event.get("type") == "monitor.clear":
            open_by_symbol.pop(symbol, None)
    return open_by_symbol


def last_heartbeat_at(events: list[dict]) -> str | None:
    """The last tick the chain records, on the clock that tick judged against.

    Same rule as an episode's start: the payload's own `tick_at` is the coverage statement, and
    the append stamp is only the fallback for a heartbeat written before the field existed.
    """
    for event in reversed(events):
        if event.get("type") == "monitor.heartbeat":
            payload = event.get("payload") or {}
            return payload.get("tick_at") or event.get("ts")
    return None


def session_gate(now: datetime) -> tuple[bool, str]:
    """Whether the tick should run at all. False is a cheap no-op, not a clean bill of health."""
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    today = now.astimezone(ET).date()
    if not is_trading_day(today):
        return False, f"{today.isoformat()} is not a trading day"
    phase = phase_at(now)
    if phase not in RTH:
        return False, f"outside the regular session ({phase.value})"
    return True, phase.value


def evaluate(
    *, book: Watchlist | None, quotes: list[MarketQuote], events: list[dict], now: datetime,
    cadence_seconds: int = DEFAULT_CADENCE_SECONDS, max_quote_age_seconds: int = 120,
    held: set[str] | None = None,
) -> dict[str, Any]:
    """One tick, as a pure function of its inputs.

    `status` is the field a runner must read before saying anything about breaches:
    "evaluated" means every watched level had a fresh quote; "no-go" means the tick judged
    nothing and must be reported as a failure, never as "no breaches".
    """
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    problems: list[dict[str, str]] = []
    phase = phase_at(now)
    targets, skipped, journal_problems = watch_targets(book, events, held)
    problems.extend({"reason": text, "input_path": "journal"} for text in journal_problems)

    if not targets:
        # Nothing to protect: no heartbeat, no verdict. An empty watch is not an all-clear,
        # so this stays loud in the report even though the exit code is 0.
        return {"status": "empty", "at": now.isoformat(), "phase": phase.value,
                "cadence_seconds": cadence_seconds, "watched": [], "skipped": skipped,
                "breaches": [], "clears": [], "gap": None, "problems": problems,
                "heartbeat": None}

    by_symbol: dict[str, MarketQuote] = {}
    for quote in quotes:
        by_symbol.setdefault(quote.symbol, quote)

    priced: list[tuple[WatchTarget, MarketQuote, float]] = []
    for target in targets:
        quote = by_symbol.get(target.quote_symbol)
        if quote is None:
            problems.append({"reason": f"no quote for {target.quote_symbol} (watching {target.symbol})",
                             "input_path": "quotes"})
            continue
        if not quote.fresh(now, max_quote_age_seconds):
            problems.append({"reason": f"quote for {quote.symbol} is stale or untradable",
                             "input_path": "quotes"})
            continue
        priced.append((target, quote, quote.last))

    if problems:
        # Fail closed and shout: a partial quote set cannot produce a "no breaches" sentence.
        return {"status": "no-go", "at": now.isoformat(), "phase": phase.value,
                "cadence_seconds": cadence_seconds, "watched": [t.as_dict() for t in targets],
                "skipped": skipped, "breaches": [], "clears": [], "gap": None,
                "problems": problems, "heartbeat": None}

    ages = [(now - q.at).total_seconds() for _, q, _ in priced]
    open_before = open_episodes(events)
    breaches: list[dict[str, Any]] = []
    clears: list[dict[str, Any]] = []
    for target, quote, price in priced:
        episode = open_before.get(target.symbol)
        if target.is_breached(price):
            if episode is None:
                breaches.append({
                    "symbol": target.symbol, "strategy_id": target.strategy_id,
                    "protection_type": target.protection_type, "level": target.level,
                    "observed_price": price, "observed_at": quote.at.isoformat(),
                    "episode_id": episode_id(target.symbol, now),
                    "exit_ref": target.setup_id or f"watch:{target.symbol}",
                    "level_source": target.source, "quote_symbol": target.quote_symbol,
                    "direction": target.direction,
                })
            # else: already alerting. De-duplication is by transition, not by tick, so a
            # volatile afternoon cannot bury the operator in repeats of the same episode.
        elif episode is not None:
            started = episode.get("started_at")
            duration = None
            if isinstance(started, str):
                try:
                    duration = round((now - datetime.fromisoformat(started)).total_seconds(), 1)
                except ValueError:
                    duration = None
            clears.append({
                "symbol": target.symbol, "strategy_id": target.strategy_id,
                "protection_type": target.protection_type, "level": target.level,
                "observed_price": price, "observed_at": quote.at.isoformat(),
                "episode_id": episode.get("episode_id"), "duration_seconds": duration,
                "exit_ref": target.setup_id or f"watch:{target.symbol}",
            })

    gap = None
    previous = last_heartbeat_at(events)
    if previous:
        try:
            missed = round((now - datetime.fromisoformat(previous)).total_seconds(), 1)
        except ValueError:
            missed = None
        if missed is not None and missed > cadence_seconds * 2:
            gap = {"last_heartbeat_at": previous, "missed_seconds": missed,
                   "cadence_seconds": cadence_seconds}

    breaching = sum(1 for target, _, price in priced if target.is_breached(price))
    heartbeat = {
        "tick_at": now.isoformat(), "cadence_seconds": cadence_seconds,
        "watched": len(targets), "breached": breaching,
        "new_breaches": len(breaches), "cleared": len(clears), "coverage_ok": gap is None,
        "quote_age_seconds": round(max(ages), 1), "phase": phase.value,
        "skipped_levels": len(skipped),
    }
    return {"status": "evaluated", "at": now.isoformat(), "phase": phase.value,
            "cadence_seconds": cadence_seconds, "watched": [t.as_dict() for t in targets],
            "skipped": skipped, "breaches": breaches, "clears": clears, "gap": gap,
            "problems": problems, "heartbeat": heartbeat}


def journal_events(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The chain entries one tick produces, in the order they must be appended.

    Gap first, then transitions, then the heartbeat: a reader walking the chain sees the
    coverage statement last, so the newest heartbeat always describes the state it follows.
    """
    events: list[tuple[str, dict[str, Any]]] = []
    if report.get("gap"):
        events.append(("monitor.gap", dict(report["gap"])))
    for breach in report.get("breaches", []):
        events.append(("monitor.breach", dict(breach)))
    for clear in report.get("clears", []):
        events.append(("monitor.clear", dict(clear)))
    if report.get("heartbeat"):
        events.append(("monitor.heartbeat", dict(report["heartbeat"])))
    return events


def error_event(reason: str, input_path: str = "") -> tuple[str, dict[str, Any]]:
    """The one event a tick emits when it could not judge anything."""
    return "monitor.error", {"reason": reason or "unreadable input", "input_path": input_path}


__all__ = [
    "DEFAULT_CADENCE_SECONDS", "SessionPhase", "WatchTarget", "episode_id", "error_event",
    "evaluate", "journal_events", "last_heartbeat_at", "open_episodes",
    "protection_type", "session_gate", "watch_targets",
]
