from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from tyche.config import RiskPolicy, Sleeve
from tyche.models import AccountSnapshot, OrderIntent, RiskBreach, RiskVerdict, Side


class RiskState(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    nav: float
    prior_close_nav: float | None = None
    high_water_nav: float | None = None
    orders_today: int = 0
    traded_notional_today: float = 0.0
    halted: bool = False
    pending_orders: list[OrderIntent] = Field(default_factory=list)

    @property
    def drawdown(self) -> float | None:
        reference = self.high_water_nav or self.prior_close_nav
        return max(0.0, 1.0 - self.nav / reference) if reference and reference > 0 else None

    @property
    def daily_return(self) -> float | None:
        return self.nav / self.prior_close_nav - 1.0 if self.prior_close_nav and self.prior_close_nav > 0 else None


def evaluate_intent(
    intent: OrderIntent,
    snapshot: AccountSnapshot,
    policy: RiskPolicy,
    state: RiskState,
    last_price: float,
    universe_symbols: set[str],
    sleeve_by_symbol: dict[str, Sleeve],
    sleeve_caps: dict[str, float] | None = None,
    underlying_price: float | None = None,
) -> RiskVerdict:
    breaches: list[RiskBreach] = []
    notes: list[str] = []
    adjusted = intent.quantity
    buy = intent.side == Side.BUY
    held = snapshot.position(intent.symbol)
    held_qty = held.quantity if held else 0
    nav = snapshot.nav
    multiplier = intent.multiplier
    notional = intent.notional

    def breach(rule: str, detail: str) -> None:
        breaches.append(RiskBreach(rule=rule, detail=detail))

    if snapshot.env != "paper" or snapshot.account_id not in policy.account_allowlist:
        breach("account.paper_only", "account must be explicitly allowlisted paper")
    if snapshot.source != "demo" and (
        snapshot.account_type not in policy.sim_account_types or snapshot.market_id != policy.sim_market_id
    ):
        breach("account.sim_verified", "broker must verify US paper account type and market")
    if nav <= 0:
        breach("account.nav", "positive NAV required")
    # A NAV that does not reconcile stops new risk, never an exit: a sell only reduces exposure, and
    # before 2026-11-25 a few dollars of drift between two reads could hold a stop back.
    if (buy and snapshot.broker_nav is not None and abs(snapshot.broker_nav - nav)
            > max(1.0, snapshot.broker_nav * policy.nav_reconcile_tolerance_pct)):
        breach("account.reconcile", "computed NAV differs from broker NAV; reconcile cash/frozen/positions")
    if intent.symbol.split(".")[0] not in policy.allowed_markets:
        breach("market.allowed", "market is not allowed")
    if buy and intent.underlying not in universe_symbols:
        breach("universe.membership", f"{intent.underlying} is outside the strategy universe")
    if not math.isfinite(last_price) or last_price <= 0:
        breach("price.available", f"no usable price for {intent.symbol}")
    if buy and intent.option is None and last_price < policy.min_price:
        breach("price.minimum", f"underlying price below {policy.min_price:.2f}")
    if last_price > 0 and abs(intent.limit_price / last_price - 1.0) > policy.max_limit_deviation_pct:
        breach("price.limit_deviation", "limit too far from current price")
    if buy and notional > policy.max_order_notional_pct * nav:
        breach("order.max_notional", "order exceeds per-order NAV budget")
    if any(order.symbol == intent.symbol for order in state.pending_orders):
        breach("order.pending", "same instrument has an unresolved/resting order; reconcile first")
    if held is not None and held.option != intent.option:
        breach("instrument.contract", "order contract differs from held contract")
    if not buy and (held is None or intent.quantity > held.sellable):
        breach("position.no_short", "sell exceeds available long position; no naked shorts")
    if buy and held is None and len(snapshot.positions) >= policy.max_positions:
        breach("position.count", "position limit reached")
    if intent.option is None and notional < policy.min_order_notional and (buy or intent.quantity != held_qty):
        breach("order.min_notional", "order below minimum notional")

    pending_buys = [order for order in state.pending_orders if order.side == Side.BUY]
    if buy and intent.option:
        if underlying_price is None or not math.isfinite(underlying_price) or underlying_price < policy.min_price:
            breach("option.underlying_price", "fresh underlying price required")
        # Premium at risk, not a hypothetical stop fill: long options can expire worthless.
        if notional > policy.option_risk_per_trade_pct * nav:
            breach("trade.risk_budget", "full option debit exceeds per-trade premium risk budget")
        option_gross = sum(p.market_value for p in snapshot.positions if p.option)
        option_pending = sum(o.notional for o in pending_buys if o.option)
        if option_gross + option_pending + notional > policy.max_option_premium_pct * nav:
            breach("option.premium_cap", "total held and pending option premium exceeds allocation")
    elif buy and intent.stop_price is not None:
        if intent.stop_price >= intent.limit_price:
            breach("trade.stop", "long-stock stop must be below entry")
        elif intent.quantity * (intent.limit_price - intent.stop_price) > policy.risk_per_trade_pct * nav:
            breach("trade.risk_budget", "planned stop risk exceeds per-trade NAV budget")

    if buy:
        if state.halted:
            breach("halt.active", "halt active; only de-risking sells allowed")
        drawdown = state.drawdown
        if drawdown is not None and drawdown >= policy.hard_drawdown_pct:
            breach("drawdown.hard", "hard drawdown limit reached")
        elif drawdown is not None and drawdown >= policy.soft_drawdown_pct:
            adjusted //= 2
            notes.append("soft drawdown: quantity halved")
        if state.daily_return is not None and state.daily_return <= -policy.daily_loss_limit_pct:
            breach("loss.daily_limit", "daily loss limit reached")

    post_qty = held_qty + (intent.quantity if buy else -intent.quantity)
    post_value = max(0, post_qty) * last_price * multiplier
    same_pending = sum(o.notional for o in pending_buys if o.underlying == intent.underlying)
    same_held = sum(p.market_value for p in snapshot.positions if p.underlying == intent.underlying)
    combined_name = same_held + same_pending + (notional if buy else -notional)
    # Standard options: conservative full-share equivalent, not premium-only exposure.
    if underlying_price is not None and (intent.option or any(p.option and p.underlying == intent.underlying for p in snapshot.positions)):
        units = sum(p.quantity * p.multiplier for p in snapshot.positions if p.underlying == intent.underlying)
        units += sum(o.quantity * o.multiplier for o in pending_buys if o.underlying == intent.underlying)
        units += intent.quantity * multiplier if buy else -intent.quantity * multiplier
        combined_name = max(combined_name, units * underlying_price)
    if buy and combined_name > (policy.max_position_weight + policy.cap_tolerance_pct) * nav:
        breach("position.max_weight", "combined underlying exposure exceeds name cap")
    pending_gross = sum(o.notional for o in pending_buys)
    post_gross = snapshot.gross_exposure - (held.market_value if held else 0) + post_value + pending_gross
    if buy and post_gross > (policy.max_gross_exposure + policy.cap_tolerance_pct) * nav:
        breach("portfolio.gross", "held plus pending gross exposure exceeds cap")
    # cash is already net of broker freezes: do not subtract pending buys twice.
    post_cash = snapshot.cash - (notional if buy else -notional)
    if buy and post_cash < policy.min_cash_weight * nav:
        breach("portfolio.min_cash", "insufficient available cash after required reserve")
    if buy and sleeve_caps and sleeve_by_symbol:
        sleeve = sleeve_by_symbol.get(intent.underlying)
        if sleeve is not None:
            exposure = sum(p.market_value for p in snapshot.positions if sleeve_by_symbol.get(p.underlying) == sleeve)
            exposure += sum(o.notional for o in pending_buys if sleeve_by_symbol.get(o.underlying) == sleeve)
            cap = sleeve_caps.get(sleeve)
            if cap is not None and exposure + notional > (cap + policy.cap_tolerance_pct) * nav:
                breach("sleeve.max_weight", f"{sleeve} exposure exceeds allocation")
    if state.orders_today >= policy.competition_order_cap:
        breach("orders.competition_count", "competition daily order ceiling reached")
    elif buy and state.orders_today >= policy.max_orders_per_day:
        breach("orders.daily_count", "daily entry budget exhausted; exits retain capacity")
    if buy and state.traded_notional_today + notional > policy.max_daily_turnover_pct * nav:
        breach("turnover.daily", "cumulative daily buy notional exceeds budget")
    return RiskVerdict(allowed=not breaches and adjusted > 0, breaches=breaches,
                       adjusted_quantity=max(0, adjusted), notes=notes)
