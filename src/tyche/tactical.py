"""Fast deterministic paper-stock/long-option lane, separate from ETF rotation.

No broker writes. Every order still needs an exact auditor verdict, bounded
operator authorization, and an atomic pre-submit reservation.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from tyche.approvals import OPTION_LIVE_SLACK
from tyche.config import AppConfig
from tyche.execution_state import combined_usage, day_requests, dead_request_ids, in_flight_symbols
from tyche.fees import estimate_fees
from tyche.market_calendar import ET, SessionPhase, phase_at, regular_close
from tyche.models import AccountSnapshot, OptionContract, OrderIntent, Side, apply_fill
from tyche.risk import RiskState, evaluate_intent
from tyche.watchlist import Watchlist, WatchlistEntry

RTH = {SessionPhase.OPENING_DRIVE, SessionPhase.MIDDAY, SessionPhase.CLOSING_DRIVE}
# Exit triggers the kernel raises on its own. A sell carrying one of these reasons is a protective exit:
# it only removes risk, so the reserve step authorizes it even when no operator line covers it today.
PROTECTIVE_EXIT_REASONS = frozenset({
    "underlying stop breached", "underlying target reached", "thesis invalidated",
    "option premium drawdown reached 40%", "time exit before next scheduled check",
    "close before option expiry/exercise",
})
TAKE_PROFIT_REASON = "resting take-profit at target"


class MarketQuote(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    symbol: str
    at: AwareDatetime
    book_at: AwareDatetime
    last: float = Field(gt=0)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    tradable: bool
    option: OptionContract | None = None
    open_interest: int = Field(default=0, ge=0)
    volume: int = Field(default=0, ge=0)
    delta: float | None = Field(default=None, ge=-1, le=1)
    implied_volatility: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def contract_identity(self):
        if self.option and (not self.option.matches(self.symbol) or (
            self.delta is not None and (self.delta < 0 if self.option.right == "call" else self.delta > 0)
        )):
            raise ValueError("quote contract or delta sign mismatch")
        return self

    def fresh(self, now: datetime, seconds: int) -> bool:
        """A tradable two-sided market whose order book is recent.

        The book's own time decides. The last-trade time (`at`) no longer does: before the open it is
        yesterday's close and for a thin option it can be hours old while the quoted market is live,
        which made every premarket and option quote "stale" (2026-11-24). `price` handles an old print.
        """
        return (self.tradable and self.ask >= self.bid
                and 0 <= (now - self.book_at).total_seconds() <= seconds)

    def price(self, now: datetime, seconds: int) -> float:
        """The reference price: the last trade when it is recent, else the live book's midpoint."""
        if 0 <= (now - self.at).total_seconds() <= seconds:
            return self.last
        return round((self.bid + self.ask) / 2, 4)

    @property
    def spread_pct(self) -> float:
        return (self.ask - self.bid) / ((self.ask + self.bid) / 2)


class MonitorState(BaseModel):
    last_tick: AwareDatetime | None = None
    observations: dict[str, list[dict]] = Field(default_factory=dict)
    observation_hashes: dict[str, str] = Field(default_factory=dict)
    protected: dict[str, WatchlistEntry] = Field(default_factory=dict)
    latched_exits: dict[str, str] = Field(default_factory=dict)
    # ET date each latch was set. A latch stops re-entry for the rest of that session only: kept forever
    # it barred the symbol on every later day once the monitor state was recorded (2026-11-25 review).
    latched_on: dict[str, str] = Field(default_factory=dict)


def config_hash(config: AppConfig) -> str:
    data = config.model_dump(mode="json", exclude={"root"})
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def setup_hash(entry: WatchlistEntry, config: AppConfig, account_id: str) -> str:
    payload = {"entry": entry.model_dump(mode="json", exclude={"reviewed_at", "status", "invalidated"}),
               "config": config_hash(config), "account": hashlib.sha256(account_id.encode()).hexdigest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def order_hash(intent: OrderIntent, contract_hash: str) -> str:
    payload = {"intent": intent.model_dump(mode="json"), "setup_hash": contract_hash}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def setup_key(book: Watchlist, entry: WatchlistEntry) -> str:
    return entry.setup_id or f"{book.as_of}:{entry.symbol}:{entry.strategy}"


def thesis_block(entry: WatchlistEntry) -> dict:
    """Per-trade thesis carried from the scout record into the plan and desk."""
    return {
        "thesis": entry.thesis or None,
        "synthesis": entry.synthesis or None,
        "edge": entry.edge or None,
        "bear_case": entry.bear_case or None,
        "invalidation": entry.invalidation or None,
        "horizon": entry.horizon or None,
        "direction": entry.direction,
        "factors": [factor.model_dump(mode="json") for factor in entry.factors],
        "outlook": entry.outlook.model_dump(mode="json") if entry.outlook else None,
        "thesis_ref": entry.thesis_ref or None,
        "source": "scout",
    }


def order_reasons(entry: WatchlistEntry, trigger: str | None = None) -> dict:
    """The written technical and fundamental reason an order carries (operator rule 2026-11-24).

    Entries take them from the thesis factors that passed. An exit's technical reason is its trigger;
    its fundamental reason is the thesis invalidation when the thesis broke, else the entry's own
    fundamental case (the exit closes the trade the fundamental case opened). A missing reason is
    None, never a made-up sentence; the kernel refuses an entry that lacks either.
    """
    def passing(axis: str) -> str | None:
        for factor in entry.factors:
            if factor.axis == axis and factor.state == "pass":
                text = factor.why or factor.detail or factor.name
                return f"{factor.name}: {text}" if text != factor.name else text
        return None
    technical, fundamental = passing("technical"), passing("fundamental")
    if trigger is not None:
        technical = trigger
        if trigger == "thesis invalidated":
            fundamental = entry.invalidation or "thesis invalidated by the researcher"
        elif trigger == TAKE_PROFIT_REASON:
            technical = f"target {entry.target} is the thesis's priced-in upside"
    return {"technical": technical, "fundamental": fundamental}


def open_orders_for(raw_orders: list[dict], symbol: str, today) -> list[str]:
    """Broker order ids still working for one symbol (the desk's own resting orders to cancel first)."""
    from tyche.execution_state import order_finished, order_symbol
    return [str(r.get("order_id")) for r in raw_orders
            if order_symbol(r) == symbol and not order_finished(r, today)]


def risk_preview(intent: OrderIntent, entry: WatchlistEntry, nav: float, etf: bool) -> dict:
    fees = estimate_fees(intent.symbol, intent.side.value, intent.quantity, intent.limit_price,
                         "option" if intent.option else "stock").total
    if intent.option:
        worst = intent.notional + fees
        planned = worst
    else:
        worst = intent.notional + fees
        planned = intent.quantity * max(0, intent.limit_price - entry.stop) + fees
    return {
        "product": f"long {intent.option.right}" if intent.option else ("ETF" if etf else "stock"),
        "strategy": intent.strategy_id, "nav_pct": intent.notional / nav if nav > 0 else 0,
        "notional_usd": round(intent.notional, 2), "modeled_entry_fees_usd": fees,
        "worst_case_capital_loss_usd": round(worst, 2),
        "planned_stop_risk_usd": round(planned, 2),
        "exit": f"underlying stop {entry.stop}, target {entry.target}, deadline {entry.exit_at}; synthetic limit exit",
        "halt": "halts block new buys, not exits; an exit is not guaranteed to fill",
        "ladder": "one entry, full-position exit; no scaling or automatic re-entry",
        "limitations": "Options may lose the full debit. Stops can gap; fees/slippage reduce returns. Close before expiry/exercise.",
        "expected_edge": "unvalidated; measure fee-net forward results, not guaranteed profit",
    }


def plan_tick(
    book: Watchlist, snapshot: AccountSnapshot, quotes: list[MarketQuote],
    pending: list[OrderIntent], raw_orders: list[dict], events: list[dict],
    state: MonitorState, config: AppConfig, now: datetime, *, halted: bool = False,
    skip: dict[str, str] | None = None,
) -> dict:
    """One pass of the PB-002 stock and PB-003 option lanes. Never submits.

    `skip` maps shared tickers the PB-004 scalp holds this run (tyche.leases) to the reason: their
    shares are not this lane's, so it neither manages nor buys them, and they do not use up its
    stock allocation. Options on those tickers are still this lane's own.
    """
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    skip = skip or {}
    cfg = config.tactical
    today = now.astimezone(ET).date()
    phase = phase_at(now)
    report = {"as_of": now.isoformat(), "phase": phase.value, "config_hash": config_hash(config),
              "orders": [], "decisions": [], "alerts": [], "submitted": False}
    premarket = phase == SessionPhase.PRE_MARKET and cfg.resting_entries
    if not cfg.enabled or (phase not in RTH and not premarket):
        report["alerts"].append("tactical lane disabled or outside regular session")
        return report
    if premarket:
        report["alerts"].append("premarket: resting DAY entries only; protection runs in the regular session")
    if len({q.symbol for q in quotes}) != len(quotes):
        raise ValueError("duplicate quote symbols")
    if snapshot.captured_at is None or snapshot.captured_at.tzinfo is None or not (
        0 <= (now - snapshot.captured_at).total_seconds() <= cfg.max_snapshot_age_seconds
    ):
        report["alerts"].append("stale/missing account snapshot; no orders")
        return report
    if snapshot.env != "paper" or snapshot.account_id not in config.risk.account_allowlist:
        report["alerts"].append("paper account verification failed")
        return report
    if state.last_tick and state.last_tick > now:
        raise ValueError("monitor clock moved backwards")
    gap = state.last_tick is None or (now - state.last_tick).total_seconds() > cfg.monitor_interval_seconds * 2
    if gap:
        state.observations.clear()
        report["alerts"].append("monitor starting or heartbeat gap; rebuild entry confirmations")
    state.last_tick = now
    for symbol in [s for s in state.latched_exits
                   if snapshot.position(s) is None and state.latched_on.get(s) != today.isoformat()]:
        state.latched_exits.pop(symbol)
        state.latched_on.pop(symbol, None)
    contracts = {q.symbol: q.option for q in quotes if q.option}
    count, turnover = combined_usage(events, raw_orders, today, contracts)
    risk_state = RiskState(nav=snapshot.nav, prior_close_nav=snapshot.prior_close_nav,
                           high_water_nav=snapshot.high_water_nav, orders_today=count,
                           traded_notional_today=turnover, halted=halted, pending_orders=pending)
    in_flight = in_flight_symbols(events, raw_orders, now)
    never_sent = dead_request_ids(events, raw_orders, now)
    quote_map = {q.symbol: q for q in quotes}
    entries = {e.symbol: e for e in book.entries}
    for symbol, protected in state.protected.items():
        if snapshot.position(symbol):
            if symbol in entries and entries[symbol] != protected:
                report["alerts"].append(f"{symbol}: using reserved exit contract, not edited watchlist levels")
            # Fresh explicit invalidation can only tighten protection, never move stops.
            protected = protected.model_copy(update={"invalidated": protected.invalidated or bool(
                symbol in entries and entries[symbol].invalidated
            )})
            entries[symbol] = protected
    uncovered = [p.symbol for p in snapshot.positions
                 if p.underlying in cfg.symbols and p.symbol not in entries and p.symbol not in skip]
    if uncovered:
        # An alert, not a brake: a lot with no plan on file is a problem to fix, and holding every other
        # setup back until it is fixed only adds a second problem (MSFT on 2026-11-23).
        report["alerts"].append(f"unprotected tactical positions: {', '.join(uncovered)}; no exit plan on file")
    projected = snapshot.model_copy(deep=True)
    close = datetime.combine(today, regular_close(today), ET)
    session_end = close - timedelta(minutes=cfg.session_exit_minutes_before_close)
    new_orders = 0
    for entry in sorted(entries.values(), key=lambda e: snapshot.position(e.symbol) is None):
        key = setup_key(book, entry)
        fingerprint = setup_hash(entry, config, snapshot.account_id)
        if state.observation_hashes.get(key) != fingerprint:
            state.observations.pop(key, None)
            state.observation_hashes[key] = fingerprint
        held = snapshot.position(entry.symbol)
        q = quote_map.get(entry.symbol)
        uq = quote_map.get(entry.underlying)
        decision = {"setup_id": key, "symbol": entry.symbol, "action": "wait", "reason": ""}
        report["decisions"].append(decision)

        def reject(reason, decision=decision, key=key):
            decision["reason"] = reason
            state.observations.pop(key, None)

        if entry.option is None and entry.symbol in skip:
            reject(skip[entry.symbol])
            continue
        if entry.underlying not in cfg.symbols:
            reject("outside tactical universe; ETF ballast has its own planner")
            continue
        if q is None or not q.fresh(now, cfg.max_quote_age_seconds):
            reject("missing/stale/non-tradable quote or order book")
            if held:
                report["alerts"].append(f"{entry.symbol}: protection quote unavailable")
            continue
        if q.option != entry.option or (held and held.option != entry.option):
            reject("contract metadata mismatch")
            continue
        underlying_fresh = uq is not None and uq.fresh(now, cfg.max_quote_age_seconds)
        last = uq.price(now, cfg.max_quote_age_seconds) if underlying_fresh else None
        exit_reason = state.latched_exits.get(entry.symbol)
        resting_row = None
        cancel_first: list[str] = []
        if held:
            if premarket:
                reject("premarket; protection and take-profit orders are placed in the regular session")
                continue
            if entry.invalidated:
                exit_reason = "thesis invalidated"
            if last is not None:
                stop_hit = last <= entry.stop if entry.direction == "bullish" else last >= entry.stop
                target_hit = last >= entry.target if entry.direction == "bullish" else last <= entry.target
                if stop_hit:
                    exit_reason = "underlying stop breached"
                elif target_hit:
                    exit_reason = "underlying target reached"
            if entry.option and q.bid <= held.avg_cost * 0.60:
                exit_reason = "option premium drawdown reached 40%"
            deadline = entry.exit_at or session_end
            if entry.option is None:
                deadline = min(deadline, session_end)  # stock lots are same-session: out before the close
            next_check = now + timedelta(seconds=cfg.monitor_interval_seconds)
            if next_check >= deadline or today > entry.expiry:
                exit_reason = "time exit before next scheduled check"
            if entry.option and entry.option.expiry <= today and next_check >= close - timedelta(minutes=cfg.option_exit_minutes_before_close):
                exit_reason = "close before option expiry/exercise"
            resting_sells = [o for o in pending if o.symbol == entry.symbol and o.side == Side.SELL]
            if not exit_reason:
                if not underlying_fresh:
                    reject("underlying feed stale; protection incomplete")
                    continue
                if resting_sells:
                    reject(f"hold; take-profit sell resting at the broker ({resting_sells[0].limit_price})")
                    continue
                if (not cfg.resting_take_profit or entry.option or entry.direction != "bullish"
                        or now >= close - timedelta(minutes=cfg.session_exit_minutes_before_close)):
                    reject("hold; no exit trigger")
                    continue
                if held.available_quantity is None or held.sellable <= 0:
                    reject("hold; no available quantity for a take-profit order")
                    continue
                # Rest the exit at the target so the win is taken without waiting for a run.
                intent = OrderIntent(symbol=entry.symbol, option=None, side=Side.SELL,
                                     quantity=held.sellable, limit_price=entry.target, reason=TAKE_PROFIT_REASON,
                                     strategy_id="PB-002", setup_id=key)
                resting_row = {"kind": "take_profit", "time_in_force": "day",
                               "limit_basis": f"target {entry.target} from the approved setup",
                               "expires": close.isoformat(),
                               "note": "re-placed each session until filled, stopped or the deadline passes"}
            else:
                state.latched_exits[entry.symbol] = exit_reason
                state.latched_on.setdefault(entry.symbol, today.isoformat())
                cancel_first = open_orders_for(raw_orders, entry.symbol, today)
                if held.available_quantity is None:
                    reject("broker available quantity required for close")
                    continue
                # A resting take-profit locks the shares at the broker; cancelling it first frees them.
                quantity = held.quantity if cancel_first else held.sellable
                if quantity <= 0:
                    reject("no available quantity to close")
                    continue
                # A stock exit is priced a collar under the bid so it still trades when the quote is a
                # few minutes old. An option keeps the quoted bid: its tick size is not ours to guess.
                exit_limit = q.bid if entry.option else max(0.01, round(q.bid * (1 - cfg.exit_collar_pct), 2))
                intent = OrderIntent(symbol=entry.symbol, option=entry.option, side=Side.SELL,
                                     quantity=quantity, limit_price=exit_limit, reason=exit_reason,
                                     strategy_id="PB-003" if entry.option else "PB-002", setup_id=key)
        else:
            if entry.symbol in state.latched_exits:
                reject("closed/triggered setup; no automatic re-entry")
                continue
            if not underlying_fresh:
                reject("fresh underlying quote required")
                continue
            if book.stale(today) or entry.expiry < today or entry.status != "watch" or entry.invalidated:
                reject("watchlist stale/inactive/invalidated")
                continue
            if snapshot.prior_close_nav is None or snapshot.high_water_nav is None:
                reject("prior-close and high-water NAV references required")
                continue
            if not entry.catalyst or not entry.sources or not entry.thesis or not entry.setup_id:
                reject("actionable setup needs id, thesis, catalyst and cited evidence")
                continue
            if entry.reviewed_at is None or not 0 <= (now - entry.reviewed_at).total_seconds() <= cfg.max_review_age_seconds:
                reject(f"research review missing, future-dated or older than {cfg.max_review_age_seconds // 60} "
                       "minutes; refresh only this setup")
                continue
            if entry.underlying not in cfg.etf_symbols and (entry.market_cap_usd or 0) < config.universe.min_market_cap_usd:
                reject("verified underlying market cap required")
                continue
            if entry.exit_at is None:
                reject("explicit exit deadline required")
                continue
            entry_deadline = entry.exit_at
            if entry.option is not None:
                # PB-003 holds overnight by design: its deadline is the next fire's start (operator
                # ruling 2026-11-24). It must still fall before the contract can expire or be exercised.
                if entry.exit_at.astimezone(ET).date() >= entry.option.expiry:
                    reject("option exit deadline must fall before the contract's expiry")
                    continue
            else:
                # A stock deadline past the session's exit time is cut back to it, not refused: a plan
                # written for a normal day (15:50 ET) still trades on a half day and leaves by 12:50.
                entry_deadline = min(entry.exit_at, session_end)
            if now >= entry_deadline - timedelta(seconds=max(600, cfg.monitor_interval_seconds)):
                reject("too close to exit deadline for the next scheduled check")
                continue
            # One entry per setup per session. A reservation that never reached the broker is not an
            # attempt (the next run may send it); one from an earlier day is not today's attempt.
            attempts = sum(1 for row in day_requests(events, today)
                           if row.get("setup_id") == key and row.get("side") == "buy"
                           and row.get("request_id") not in never_sent)
            if attempts >= cfg.max_entries_per_setup:
                reject("setup entry already attempted; no automatic re-entry")
                continue
            reasons = order_reasons(entry)
            if not reasons["technical"] or not reasons["fundamental"]:
                reject("entry needs a passing technical and a passing fundamental factor in the thesis")
                continue
            # Option entries buy at the live price once approved (operator ruling 2026-11-24, PB-003
            # test): the underlying's zone still sets stop/target, but no pullback is awaited.
            in_zone = entry.option is not None or entry.entry_low <= last <= entry.entry_high
            resting_ok = (cfg.resting_entries and entry.option is None and entry.direction == "bullish"
                          and now < close - timedelta(minutes=cfg.resting_cutoff_minutes))
            within_reach = entry.entry_low <= last <= entry.entry_high * (1 + cfg.resting_reach_pct)
            # In the session an in-zone price is bought at the ask now. A price up to the reach above
            # the zone, or any premarket price inside the reach, is a DAY limit resting at the zone top.
            resting_entry = resting_ok and within_reach and (premarket or not in_zone)
            if not resting_entry and (premarket or not in_zone):
                reject("outside entry zone; do not chase" if not premarket
                       else "premarket price outside the resting reach of the entry zone")
                continue
            distance = abs((entry.entry_high if entry.direction == "bullish" else entry.entry_low) - entry.stop)
            reward = abs(entry.target - (entry.entry_high if entry.direction == "bullish" else entry.entry_low))
            if reward / distance < cfg.min_reward_risk - 1e-9:  # 2.7/1.8 is 1.4999... in floating point
                reject("underlying reward/risk below threshold (not an option return forecast)")
                continue
            ticks = min(entry.confirmation_ticks, cfg.max_confirmation_ticks)
            stamp = max(uq.at, uq.book_at).isoformat()  # one sample per distinct quote, print or book
            observations = state.observations.setdefault(key, [])
            if not observations or observations[-1]["at"] != stamp:
                observations.append({"at": stamp, "price": last})
            observations[:] = [o for o in observations if 0 <= (now - datetime.fromisoformat(o["at"])).total_seconds() <= cfg.monitor_interval_seconds * (ticks + 1)][-ticks:]
            if len(observations) < ticks:
                decision["reason"] = "awaiting distinct fresh quote confirmations"
                continue
            if new_orders >= cfg.max_new_orders_per_tick:
                reject("per-tick entry budget exhausted")
                continue
            spread_cap = cfg.option_spread_pct if entry.option else cfg.stock_spread_pct
            if q.spread_pct > spread_cap and not resting_entry:
                reject("bid/ask spread too wide")
                continue
            if entry.option:
                dte = (entry.option.expiry - today).days
                if not config.options_live or not cfg.min_option_dte <= dte <= cfg.max_option_dte:
                    reject("option disabled or outside DTE limits; no 0DTE entries")
                    continue
                if q.open_interest < cfg.min_option_open_interest or q.volume < cfg.min_option_volume:
                    reject("option liquidity below threshold")
                    continue
                if q.delta is None or q.implied_volatility is None or not 0.45 <= abs(q.delta) <= 0.80:
                    reject("option Greeks missing or delta outside directional range")
                    continue
                if q.ask > round(entry.premium_limit * (1 + OPTION_LIVE_SLACK), 2):
                    reject("option ask exceeds approved research debit limit")
                    continue
                budget = config.risk.option_risk_per_trade_pct * projected.nav
                quantity = math.floor(budget / (q.ask * 100))
                limit = q.ask
            else:
                if not resting_entry and q.ask > entry.entry_high:
                    if not resting_ok:
                        reject("ask outside entry zone")
                        continue
                    resting_entry = True
                if resting_entry:
                    # Fair-value price: the top of the researcher's pullback zone. The order rests for
                    # the day; a fill means the market came to the plan's price, not that the desk chased.
                    limit = entry.entry_high
                    resting_row = {"kind": "entry", "time_in_force": "day",
                                   "limit_basis": f"entry zone top {entry.entry_high} (fair value); last {last}, ask {q.ask}",
                                   "expires": close.isoformat(),
                                   "note": "unfilled at the close it expires with the day; never re-placed from stale quotes"}
                else:
                    limit = q.ask
                distance = limit - entry.stop
                quantity = math.floor(config.risk.risk_per_trade_pct * projected.nav / distance)
                quantity = min(quantity, math.floor(cfg.max_name_weight * projected.nav / limit))
            same_units = sum(p.quantity * p.multiplier for p in projected.positions if p.underlying == entry.underlying)
            same_units += sum(o.quantity * o.multiplier for o in pending if o.side == Side.BUY and o.underlying == entry.underlying)
            name_room = cfg.max_name_weight * projected.nav - same_units * last
            quantity = min(quantity, math.floor(name_room / (last * (100 if entry.option else 1))))
            if entry.max_quantity is not None:
                quantity = min(quantity, entry.max_quantity)
            # Include modeled fees in the full-premium/stop risk budget.
            while quantity > 0:
                fee = estimate_fees(entry.symbol, "buy", quantity, limit, "option" if entry.option else "stock").total
                risk_per_unit = limit * 100 if entry.option else limit - entry.stop
                budget = (config.risk.option_risk_per_trade_pct if entry.option else config.risk.risk_per_trade_pct) * projected.nav
                if quantity * risk_per_unit + fee <= budget:
                    break
                quantity -= 1
            if quantity <= 0:
                reject("one unit exceeds risk budget")
                continue
            intent = OrderIntent(symbol=entry.symbol, option=entry.option, side=Side.BUY,
                                 quantity=quantity, limit_price=limit,
                                 stop_price=None if entry.option else entry.stop,
                                 strategy_id="PB-003" if entry.option else "PB-002", setup_id=key,
                                 reason=entry.thesis)
            # Shares the scalp holds in a shared ticker are its own lane's, not this lane's allocation.
            tactical_stock = sum(p.market_value for p in projected.positions
                                 if not p.option and p.symbol in cfg.symbols and p.symbol not in skip)
            tactical_stock += sum(o.notional for o in pending if o.side == Side.BUY and not o.option
                                  and o.symbol in cfg.symbols and o.symbol not in skip)
            if not entry.option and tactical_stock + intent.notional > cfg.stock_allocation_cap * projected.nav:
                reject("tactical-stock allocation exhausted")
                continue
        if entry.symbol in in_flight:
            reject("an order for this symbol is on its way to the broker; wait for its receipt")
            continue
        if any(o.symbol == entry.symbol for o in pending) and not cancel_first:
            reject("resting entry already working at the broker; no second buy" if intent.side == Side.BUY
                   else "unresolved/resting order; reconcile before any further write")
            continue
        if intent.side == Side.BUY:
            units = sum(p.quantity * p.multiplier for p in projected.positions if p.underlying == entry.underlying)
            units += sum(o.quantity * o.multiplier for o in pending if o.side == Side.BUY and o.underlying == entry.underlying)
            if (units + intent.quantity * intent.multiplier) * last > cfg.max_name_weight * projected.nav:
                reject("tactical combined-underlying name cap exceeded")
                continue
        risk_pending = [o for o in pending if not (cancel_first and o.symbol == entry.symbol)]
        risk_book = projected
        if cancel_first and held:
            # Cancelling the desk's own resting order frees the locked shares before the exit is sent.
            risk_book = projected.model_copy(update={"positions": [
                p.model_copy(update={"available_quantity": p.quantity}) if p.symbol == entry.symbol else p
                for p in projected.positions]})
        verdict = evaluate_intent(intent, risk_book, config.risk,
                                  risk_state.model_copy(update={"pending_orders": risk_pending}),
                                  q.price(now, cfg.max_quote_age_seconds),
                                  set(cfg.symbols), {s: "equity" for s in cfg.symbols},
                                  underlying_price=last)
        breaches = [b for b in verdict.breaches
                    if not (b.rule == "price.limit_deviation" and intent.reason == TAKE_PROFIT_REASON)]
        if breaches:
            reject("; ".join(f"{b.rule}: {b.detail}" for b in breaches))
            continue
        intent = intent.model_copy(update={"quantity": min(intent.quantity, verdict.adjusted_quantity)})
        preview = risk_preview(intent, entry, snapshot.nav, entry.underlying in cfg.etf_symbols)
        contract_hash = setup_hash(entry, config, snapshot.account_id)
        trigger = intent.reason if intent.side == Side.SELL else None
        report["orders"].append({"setup_hash": contract_hash, "order_hash": order_hash(intent, contract_hash),
                                 "intent": intent.model_dump(mode="json"),
                                 "thesis": thesis_block(entry),
                                 "reasons": order_reasons(entry, trigger),
                                 "resting": resting_row,
                                 "cancel_first": cancel_first,
                                 "protective": intent.reason in PROTECTIVE_EXIT_REASONS,
                                 "risk": preview, "verdict": verdict.model_dump(mode="json"),
                                 "authorization": ("not granted; protective exit - reserve authorizes it"
                                                   if intent.reason in PROTECTIVE_EXIT_REASONS
                                                   else "not granted; auditor + operator envelope required")})
        decision.update(action=intent.side.value, reason=intent.reason)
        risk_state.orders_today += 1
        if intent.side == Side.BUY:
            projected = apply_fill(projected, intent, intent.quantity)
            risk_state.traded_notional_today += intent.notional
            new_orders += 1
        # Never finance buys with proceeds from merely PLANNED sells.
    return report
