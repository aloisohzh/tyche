"""PB-004 intraday momentum scalp: one strategy, many small trades, flat by close.

Signal is deterministic, never an LLM call: enter long when the latest 1-minute
close prints above the highest high of the prior N bars and the current bar is
up. Stop is a fixed percentage under the limit, target a fixed R multiple,
timeout and session flatten are hard. Sizing uses fixed fractional risk of NAV
to the stop, capped by notional per trade. All state is rebuilt from the journal
(plan stops, fills, requests), so a restart cannot invent or lose positions.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel

from tyche.config import AppConfig, ScalpConfig
from tyche.fees import estimate_fees
from tyche.market_calendar import ET, SessionPhase, phase_at, regular_close
from tyche.models import AccountSnapshot, OrderIntent, Side
from tyche.risk import RiskState, evaluate_intent
from tyche.tactical import MarketQuote, order_hash

RTH = {SessionPhase.OPENING_DRIVE, SessionPhase.MIDDAY, SessionPhase.CLOSING_DRIVE}
# The newest 1-minute bar may trail the quote by this much before the series counts as stale: a bar
# is stamped when its minute opens or closes, and a thin minute prints no bar at all.
BAR_LAG_SECONDS = 180


class Bar(BaseModel):
    at: datetime
    open: float
    high: float
    low: float
    close: float


class ScalpLot(BaseModel):
    symbol: str
    quantity: int
    entry: float
    stop: float
    target: float
    opened_at: datetime
    deadline: datetime


class ScalpState(BaseModel):
    lots: dict[str, ScalpLot] = {}
    last_request: dict[str, datetime] = {}
    round_trips_today: int = 0


def bars_from_kline(payload: dict, limit: int = 60) -> list[Bar]:
    if payload.get("ret_code") != 0 or "data" not in payload:
        raise ValueError("successful kline payload required")
    rows = payload["data"].get("kline_list")
    if not isinstance(rows, list) or not rows:
        raise ValueError("kline_list missing")
    bars = [Bar(at=datetime.fromtimestamp(int(r["time_key"]) / 1000, UTC),
                open=float(r["open_price"]), high=float(r["high_price"]),
                low=float(r["low_price"]), close=float(r["close_price"])) for r in rows]
    return sorted(bars, key=lambda b: b.at)[-limit:]


def breakout(bars: list[Bar], lookback: int, window: int = 1) -> bool:
    """An up bar that closed above the highest high of the `lookback` bars before it.

    `window` is how many of the latest bars may be that breakout bar. The latest close must still hold
    above the level that was broken, so a breakout that already failed is not bought. With window 1
    this is the original rule: only the latest bar counts. A run that looks once every 15 minutes
    almost never lands on the exact breakout minute, which is why the live lane widens the window.
    """
    for back in range(max(1, window)):
        end = len(bars) - back
        if end - 1 - lookback < 0:
            break
        bar, prior = bars[end - 1], bars[end - 1 - lookback:end - 1]
        level = max(item.high for item in prior)
        if bar.close > level and bar.close > bar.open and bars[-1].close > level:
            return True
    return False


def scalp_state(events: list[dict], today: date, timeout_minutes: int, *,
                stop_pct: float = 0.0025, target_r: float = 2.0,
                never_sent: set[str] | None = None) -> ScalpState:
    """Rebuild open lots, cooldown and the day's round trips from the journal.

    A fill's own time (`filled_at`, from the broker's order list) dates the lot when the journal row
    carries it; the row's write time is only the fallback. `never_sent` names reservations that never
    reached the broker: they start no cooldown, because nothing was traded.
    """
    state = ScalpState()
    never_sent = never_sent or set()
    fifo: dict[str, list[ScalpLot]] = {}
    request_strategy = {
        str(e.get("payload", {}).get("request_id")): str(e.get("payload", {}).get("strategy_id", ""))
        for e in events
        if e.get("type") == "order.requested" and e.get("payload", {}).get("request_id")
    }
    for event in sorted(events, key=lambda e: e.get("ts", "")):
        payload = event.get("payload", {})
        ts = event.get("ts", "")
        strategy_id = str(
            payload.get("strategy_id")
            or request_strategy.get(str(payload.get("request_id")), "")
        )
        if not strategy_id.startswith("PB-004"):
            continue
        if event.get("type") != "order.filled":
            continue
        symbol = str(payload.get("symbol"))
        qty = int(float(payload.get("quantity") or 0))
        price = float(payload.get("price") or 0)
        when = datetime.fromisoformat(ts)
        try:
            when = datetime.fromisoformat(str(payload["filled_at"]))
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
        except (KeyError, ValueError):
            pass
        if payload.get("side") == "buy":
            stop = price * (1 - stop_pct)
            target = price * (1 + target_r * stop_pct)
            fifo.setdefault(symbol, []).append(ScalpLot(
                symbol=symbol, quantity=qty, entry=price, stop=stop, target=target,
                opened_at=when, deadline=when + timedelta(minutes=timeout_minutes)))
        elif payload.get("side") == "sell":
            queue = fifo.get(symbol, [])
            while qty > 0 and queue:
                lot = queue[0]
                taken = min(qty, lot.quantity)
                lot.quantity -= taken
                qty -= taken
                if lot.quantity == 0:
                    queue.pop(0)
            if when.astimezone(ET).date() == today:
                state.round_trips_today += 1
    state.lots = {symbol: lots[0] for symbol, lots in fifo.items() if lots}
    for event in events:
        payload = event.get("payload", {})
        if (event.get("type") == "order.requested" and payload.get("strategy_id") == "PB-004"
                and payload.get("request_id") not in never_sent):
            when = datetime.fromisoformat(event["ts"])
            if when.astimezone(ET).date() == today:
                state.last_request[str(payload["symbol"])] = when
    return state


def plan_scalp(
    quotes: dict[str, MarketQuote], bars: dict[str, list[Bar]], state: ScalpState,
    snapshot: AccountSnapshot, config: AppConfig, now: datetime, *,
    orders_today: int = 0, traded_notional_today: float = 0.0, halted: bool = False,
    skip: set[str] | frozenset[str] = frozenset(),
) -> dict:
    """Exit open lots first, then one entry per eligible symbol. Never submits.

    `skip` names shared tickers the PB-002 stock lane holds this run (tyche.leases): no entry there.
    """
    cfg = config.scalp
    today = now.astimezone(ET).date()
    report = {"as_of": now.isoformat(), "strategy": "PB-004", "orders": [], "decisions": [],
              "alerts": [], "submitted": False}
    if not cfg.enabled or phase_at(now) not in RTH:
        report["alerts"].append("scalp disabled or outside regular session")
        return report
    if snapshot.captured_at is None or not (
            0 <= (now - snapshot.captured_at).total_seconds() <= cfg.max_snapshot_age_seconds):
        report["alerts"].append("stale/missing account snapshot; no orders")
        return report
    if snapshot.env != "paper" or snapshot.account_id not in config.risk.account_allowlist:
        report["alerts"].append("paper account verification failed")
        return report
    close = datetime.combine(today, regular_close(today), ET)
    flatten = close - timedelta(minutes=cfg.flatten_minutes_before_close)
    max_age = cfg.max_quote_age_seconds

    for lot in sorted(state.lots.values(), key=lambda item: item.symbol):
        q = quotes.get(lot.symbol)
        decision = {"symbol": lot.symbol, "action": "hold", "reason": ""}
        report["decisions"].append(decision)
        overdue = now >= flatten or now >= lot.deadline
        fresh = q is not None and q.fresh(now, max_age)
        # A lot past its timeout or the flatten line is sold on the last quote the run has, however old:
        # a stale price is a reason to price the exit wider, never a reason to keep the lot.
        if q is None or not q.tradable or q.bid <= 0 or not (fresh or overdue):
            decision["reason"] = "exit quote stale; protection incomplete"
            report["alerts"].append(f"{lot.symbol}: scalp exit quote unavailable")
            continue
        price = q.price(now, max_age) if fresh else min(q.last, q.bid)
        if overdue:
            reason = "scalp flatten/timeout"
        elif price <= lot.stop:
            reason = "scalp stop"
        elif price >= lot.target:
            reason = "scalp target"
        else:
            decision["reason"] = "hold within stop/target/timeout"
            continue
        # The collar puts the limit under the bid so an exit priced from a minutes-old quote still
        # trades; a marketable limit fills at the market's price, not at the limit.
        limit = max(0.01, round(q.bid * (1 - cfg.exit_collar_pct), 2))
        report["orders"].append({**_proposal(OrderIntent(
            symbol=lot.symbol, side=Side.SELL, quantity=lot.quantity, limit_price=limit,
            strategy_id="PB-004", reason=reason)),
            "submit_before": min(now + timedelta(seconds=cfg.exit_submit_window_seconds),
                                 close).isoformat()})
        decision.update(action="sell", reason=reason)

    risk_state = RiskState(nav=snapshot.nav, prior_close_nav=snapshot.prior_close_nav,
                           high_water_nav=snapshot.high_water_nav, orders_today=orders_today,
                           traded_notional_today=traded_notional_today, halted=halted)
    opening = 0
    for symbol in cfg.symbols:
        decision = {"symbol": symbol, "action": "wait", "reason": ""}
        report["decisions"].append(decision)
        if symbol in state.lots:
            continue
        if symbol in skip:
            decision["reason"] = "shared ticker held or worked by the PB-002 stock lane this run"
            continue
        q = quotes.get(symbol)
        if q is None or not q.fresh(now, max_age):
            decision["reason"] = "entry quote missing/stale"
            continue
        last_request = state.last_request.get(symbol)
        if last_request and (now - last_request).total_seconds() < cfg.cooldown_seconds:
            decision["reason"] = "cooldown after last request"
            continue
        series = bars.get(symbol, [])
        if not series or not 0 <= (now - series[-1].at).total_seconds() <= max_age + BAR_LAG_SECONDS:
            decision["reason"] = "1-minute bars missing/stale"
            continue
        if not breakout(series, cfg.breakout_bars, cfg.breakout_window_bars):
            decision["reason"] = f"no {cfg.breakout_bars}-bar breakout"
            continue
        if now >= flatten:
            decision["reason"] = "flatten window"
            continue
        if halted:
            decision["reason"] = "kill-switch engaged; buys blocked"
            continue
        if len(state.lots) + opening >= cfg.max_open:  # lots held plus entries already planned this pass
            decision["reason"] = "max open positions"
            continue
        if state.round_trips_today >= cfg.max_round_trips_per_day:
            decision["reason"] = "daily round-trip budget exhausted"
            continue
        if q.spread_pct > cfg.max_spread_pct:
            decision["reason"] = "spread too wide"
            continue
        # The buffer keeps the limit marketable when the saved ask is a few minutes old.
        limit = round(q.ask * (1 + cfg.entry_buffer_pct), 2)
        stop = round(limit * (1 - cfg.stop_pct), 2)
        target = round(limit * (1 + cfg.target_r * cfg.stop_pct), 2)
        quantity = int(cfg.risk_per_trade_pct * snapshot.nav / (limit - stop)) if limit > stop else 0
        quantity = min(quantity, int(cfg.max_notional_pct * snapshot.nav / limit))
        while quantity > 0:
            fee = estimate_fees(symbol, "buy", quantity, limit, "stock").total
            if quantity * (limit - stop) + fee <= cfg.risk_per_trade_pct * snapshot.nav:
                break
            quantity -= 1
        if quantity <= 0:
            decision["reason"] = "one unit exceeds scalp risk budget"
            continue
        intent = OrderIntent(symbol=symbol, side=Side.BUY, quantity=quantity, limit_price=limit,
                             stop_price=stop, strategy_id="PB-004",
                             reason=f"{cfg.breakout_bars}-bar breakout, stop {stop}, target {target}")
        verdict = evaluate_intent(intent, snapshot, config.risk, risk_state, q.price(now, max_age),
                                  set(cfg.symbols), {s: "equity" for s in cfg.symbols})
        if not verdict.allowed:
            decision["reason"] = "; ".join(f"{b.rule}: {b.detail}" for b in verdict.breaches)
            continue
        intent = intent.model_copy(update={"quantity": min(quantity, verdict.adjusted_quantity)})
        proposal = _proposal(intent)
        proposal["plan"] = {"symbol": symbol, "stop": stop, "target": target}
        proposal["thesis"] = scalp_thesis(symbol=symbol, limit=limit, stop=stop, target=target,
                                          spread_pct=q.spread_pct, cfg=cfg)
        report["orders"].append(proposal)
        decision.update(action="buy", reason=intent.reason)
        opening += 1
        risk_state.orders_today += 1
        risk_state.traded_notional_today += intent.notional
    return report


def _proposal(intent: OrderIntent) -> dict:
    return {"order_hash": order_hash(intent, "PB-004"), "intent": intent.model_dump(mode="json")}


def scalp_thesis(*, symbol: str, limit: float, stop: float, target: float,
                 spread_pct: float, cfg: ScalpConfig) -> dict:
    """Deterministic thesis for a PB-004 entry, with missing axes marked unknown."""
    ticker = symbol.removeprefix("US.")
    return {
        "thesis": f"{ticker} printed a {cfg.breakout_bars}-bar high breakout with the current bar up",
        "synthesis": (f"Long {ticker} on a deterministic breakout, {cfg.target_r:g}R target, "
                      f"hard {cfg.timeout_minutes}-minute timeout and a flat close."),
        "edge": f"target {target} is {cfg.target_r:g}R from {limit} against stop {stop}",
        "bear_case": f"a close back below {stop} invalidates the breakout",
        "invalidation": f"stop {stop}, {cfg.timeout_minutes}-minute timeout, or session flatten",
        "horizon": "intraday; flat before the close",
        "direction": "bullish",
        "factors": [
            {"name": f"{cfg.breakout_bars}-bar high breakout", "axis": "technical", "state": "pass",
             "why": "latest 1-minute close is above the prior highs and the bar is up", "detail": ""},
            {"name": "reward:risk", "axis": "technical", "state": "pass",
             "why": f"target is set at {cfg.target_r:g}R against a {cfg.stop_pct:.2%} stop", "detail": ""},
            {"name": "spread", "axis": "liquidity",
             "state": "pass" if spread_pct <= cfg.max_spread_pct else "fail",
             "why": f"quoted spread {spread_pct:.2%} versus the {cfg.max_spread_pct:.2%} cap",
             "detail": ""},
            {"name": "macro / sentiment / seasonality", "axis": "macro", "state": "unknown",
             "why": "this lane is price-action native and carries no macro or sentiment input",
             "detail": ""},
        ],
        "outlook": {"regime": "", "conviction": "low",
                    "alignment": {"technical": "bull", "liquidity": "neutral"}},
        "thesis_ref": None,
        "source": "deterministic",
    }
