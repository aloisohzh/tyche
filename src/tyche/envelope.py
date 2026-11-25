"""Draft the operator's exit note from records the kernel already trusts.

This module proposes; it never approves. It writes only `data/approvals.proposed.json`,
and `data/approvals.json` stays the exclusive property of `arm_envelope` (dashboard) or a
human who read the draft. ADR 0013's protection design needs the operator to sign a bounded
exit while calm, so the desk has to be able to produce that bound without asking them to
invent numbers they do not have.

Every field of a proposed sell line has a source that is not an opinion:

* symbol and quantity - the broker snapshot the desk is already showing;
* the floor - the stop the plan journaled when it entered, widened by one operator-set
  collar percentage (`risk.exit_collar_pct`); for a contract that stop has to be a premium
  (`premium_stop` in the journal), because an underlying price is not a price a contract
  can be sold at, and a floor invented by converting one would be an opinion;
* `setup_hash` - copied verbatim from the journal, never recomputed. It folds in the
  account id and the whole loaded config (`tactical.py:72`), so recomputation on another
  machine or after a config edit yields a different string, and `tactical_cli.py:265`
  refuses an envelope whose hash does not match. A draft that could not be bound is
  reported as such rather than silently unbound.

An exit-only envelope deliberately carries no `max_notional`. Quantity and the per-name
floor already bound an exit, and an exit that fills *above* its floor would consume budget
the envelope was never measuring; a notional cap earns its place on entries, where it
limits what can be spent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import ValidationError

from tyche.approvals import ApprovalBatch, ApprovalLine
from tyche.models import AccountSnapshot, looks_like_option
from tyche.tactical import PREMIUM_DRAWDOWN_FLOOR
from tyche.watchlist import Watchlist, WatchlistEntry

StopSource = Literal["journal_contract", "journal_order", "watchlist"]

# Where the number came from, in the words an operator reads on the card.
SOURCE_LABEL = {
    "journal_contract": "protected setup (journal)",
    "journal_order": "journaled stop price",
    "watchlist": "watchlist level (no journal contract)",
}


@dataclass(frozen=True)
class ExitLevel:
    """The protective level an open position is supposed to have, and its provenance.

    `entry` is the validated plan the level came from, carried so a consumer can resolve
    what the level is *stated against* (an option's stop is an underlying price) without
    re-deriving it. Drafting never reads it; the Level 0 monitor does.
    """

    symbol: str
    stop: float
    source: StopSource
    setup_id: str | None = None
    setup_hash: str | None = None
    strategy_id: str | None = None
    direction: str = "bullish"
    entry: WatchlistEntry | None = None
    # A contract stop recorded in premium, when somebody wrote one down. The plan's `stop` on an
    # option is stated against the underlying, so it is not a price a contract can be sold at.
    premium_stop: float | None = None


@dataclass
class Proposal:
    """A draft envelope plus everything it refused to draft, with reasons."""

    batch: ApprovalBatch | None
    lines: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    collar_pct: float = 0.0
    positions_seen: int = 0

    @property
    def armable(self) -> bool:
        return self.batch is not None and bool(self.batch.orders)

    def as_payload(self, *, generated_at: datetime | None = None) -> dict:
        """JSON for the draft file and the desk card. Carries display metadata the
        envelope itself must not hold."""
        return {
            "draft": True,
            "armed": False,
            "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
            "collar_pct": self.collar_pct,
            "positions_seen": self.positions_seen,
            "proposed": len(self.lines),
            "refused": len(self.skipped),
            "lines": self.lines,
            "skipped": self.skipped,
            "problems": self.problems,
            "envelope": self.batch.model_dump(mode="json") if self.batch else None,
        }


def exit_levels(events: list[dict]) -> tuple[dict[str, ExitLevel], list[str]]:
    """Latest journaled protective level per symbol, plus unreadable events counted as problems.

    A later request wins over an earlier one: positions get re-planned, and the newest
    contract is the one the executor would honour (`tactical_cli.monitor_state` keeps the
    same last-write-wins rule).
    """
    levels: dict[str, ExitLevel] = {}
    problems: list[str] = []
    for event in events:
        if event.get("type") != "order.requested":
            continue
        payload = event.get("payload") or {}
        symbol = payload.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            problems.append(f"{event.get('type')} event without a symbol was ignored")
            continue
        premium = payload.get("premium_stop")
        premium_stop = float(premium) if isinstance(premium, int | float) and premium > 0 else None
        setup = payload.get("protected_setup")
        if setup:
            try:
                entry = WatchlistEntry.model_validate(setup)
            except ValidationError:
                problems.append(f"{symbol}: journaled protected setup no longer parses; "
                                "that position gets no proposed exit")
                continue
            levels[symbol] = ExitLevel(
                symbol=symbol, stop=entry.stop, source="journal_contract",
                setup_id=payload.get("setup_id") or entry.setup_id or None,
                setup_hash=payload.get("setup_hash"), strategy_id=payload.get("strategy_id"),
                direction=entry.direction, entry=entry, premium_stop=premium_stop,
            )
            continue
        stop = payload.get("stop_price", payload.get("stop"))
        if isinstance(stop, int | float) and stop > 0:
            premium_stop = premium_stop or (float(stop) if looks_like_option(symbol) else None)
            levels[symbol] = ExitLevel(
                symbol=symbol, stop=float(stop), source="journal_order",
                setup_id=payload.get("setup_id"), setup_hash=payload.get("setup_hash"),
                strategy_id=payload.get("strategy_id"), premium_stop=premium_stop,
            )
    return levels, problems


def _watchlist_levels(watchlist: Watchlist | None) -> dict[str, ExitLevel]:
    """Fallback levels for positions entered before the contract was journaled.

    Expiry is not a filter: a position still open past its setup's expiry is the case
    where an exit bound matters most, and the stop is the only level that survives it.
    """
    if watchlist is None:
        return {}
    out: dict[str, ExitLevel] = {}
    for entry in watchlist.entries:
        if entry.status in ("exited", "dropped") or entry.invalidated:
            continue
        out.setdefault(entry.symbol, ExitLevel(
            symbol=entry.symbol, stop=entry.stop, source="watchlist",
            setup_id=entry.setup_id or None, direction=entry.direction, entry=entry,
        ))
    return out


def propose_exit_envelope(
    snapshot: AccountSnapshot,
    events: list[dict],
    *,
    today: date,
    collar_pct: float,
    max_orders_per_day: int,
    watchlist: Watchlist | None = None,
    options_enabled: bool = False,
    now: datetime | None = None,
) -> Proposal:
    """Build the draft: one bounded sell per open paper position that has a level to protect."""
    if not 0.0 < collar_pct <= 0.20:
        raise ValueError("collar_pct must be in (0, 0.20]")
    if snapshot.env != "paper":
        raise ValueError("proposals cover paper positions only")
    now = now or datetime.now(UTC)
    levels, problems = exit_levels(events)
    for symbol, level in _watchlist_levels(watchlist).items():
        levels.setdefault(symbol, level)

    proposal = Proposal(batch=None, collar_pct=collar_pct, positions_seen=len(snapshot.positions),
                        problems=problems)
    built: list[ApprovalLine] = []
    for position in snapshot.positions:
        symbol = position.symbol
        if position.option and not options_enabled:
            proposal.skipped.append({"symbol": symbol, "why": "options are not enabled on this desk"})
            continue
        qty = position.sellable
        if qty < 1:
            proposal.skipped.append({"symbol": symbol,
                                     "why": "nothing sellable today (unsettled or zero quantity)"})
            continue
        level = levels.get(symbol)
        if level is None:
            proposal.skipped.append({"symbol": symbol,
                                     "why": "no journaled stop or watchlist level to protect; "
                                            "rebalance-protected ballast exits at the next "
                                            "rebalance, so nothing is proposed"})
            continue
        if level.direction != "bullish":
            proposal.skipped.append({"symbol": symbol,
                                     "why": "bearish expression exits by buying back; a sell floor "
                                            "would not protect it"})
            continue
        stop, stop_basis = level.stop, "underlying"
        if position.option:
            # A plan's stop on a contract is a price on its underlying, and an underlying price is not a
            # price a contract can be sold at. The premium numbers the kernel trusts are the one the
            # journal was given (`premium_stop`) and the lane's own 40% premium drawdown measured on the
            # cost basis the broker reports, so the floor comes from those and says which it used.
            if level.premium_stop is not None:
                stop, stop_basis = level.premium_stop, "journaled premium stop"
            elif position.avg_cost > 0:
                stop, stop_basis = position.avg_cost * PREMIUM_DRAWDOWN_FLOOR, "premium drawdown floor"
            else:
                proposal.skipped.append({"symbol": symbol,
                                         "why": "no premium to floor a contract on: the broker reports no "
                                                "cost basis and the journal holds no premium stop"})
                continue
        floor = round(stop * (1.0 - collar_pct), 4)
        if floor <= 0:
            proposal.skipped.append({"symbol": symbol, "why": f"floor from stop {stop} is not positive"})
            continue
        try:
            line = ApprovalLine(symbol=symbol, side="sell", max_qty=qty, max_total_qty=qty,
                                limit_min=floor, multiplier=position.multiplier,
                                setup_hash=level.setup_hash)
        except ValidationError as exc:
            proposal.skipped.append({"symbol": symbol, "why": f"proposed line rejected: {exc.errors()[:1]}"})
            continue
        proposal.lines.append({
            "symbol": symbol, "side": "sell", "max_qty": qty, "limit_min": line.limit_min,
            "multiplier": position.multiplier, "source": level.source,
            "source_label": SOURCE_LABEL[level.source], "stop": stop,
            "stop_basis": stop_basis,
            "setup_id": level.setup_id, "setup_hash": level.setup_hash,
            "strategy_id": level.strategy_id,
            "bound": bool(level.setup_hash),
            "warn": None if level.setup_hash else
            "no setup hash in the journal: the tactical lane refuses an unbound line",
        })
        built.append(line)

    if not built:
        proposal.batch = None
        return proposal

    # Three attempts per line: a rejected or partially filled submit must not force a
    # re-approval, and the daily cap remains the hard stop either way.
    max_orders = min(3 * len(built), max_orders_per_day)
    proposal.batch = ApprovalBatch(
        as_of=today, approved_at=now, approved_by="kernel draft (not an operator approval)",
        max_orders=max_orders, orders=built, max_notional=None,
        note=("DRAFT ONLY - not armed. Exit floors = journaled stop widened by "
              f"{collar_pct:.1%}; the operator sets the collar, the plan sets the stop. "
              "Arming requires the operator's click; copy to data/approvals.json only via "
              "the desk Arm control."),
    )
    return proposal
