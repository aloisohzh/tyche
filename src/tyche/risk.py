from __future__ import annotations

from pydantic import BaseModel

from tyche.config import RiskPolicy, Sleeve
from tyche.models import (
    AccountSnapshot,
    OrderIntent,
    RiskBreach,
    RiskVerdict,
    Side,
)


class RiskState(BaseModel):
    nav: float
    prior_close_nav: float | None = None
    high_water_nav: float | None = None
    orders_today: int = 0
    traded_notional_today: float = 0.0
    halted: bool = False

    @property
    def drawdown(self) -> float | None:
        reference = self.high_water_nav or self.prior_close_nav
        if not reference or reference <= 0:
            return None
        return max(0.0, 1.0 - self.nav / reference)

    @property
    def daily_return(self) -> float | None:
        if not self.prior_close_nav or self.prior_close_nav <= 0:
            return None
        return self.nav / self.prior_close_nav - 1.0


def evaluate_intent(
    intent: OrderIntent,
    snapshot: AccountSnapshot,
    policy: RiskPolicy,
    state: RiskState,
    last_price: float,
    universe_symbols: set[str],
    sleeve_by_symbol: dict[str, Sleeve],
    sleeve_caps: dict[str, float] | None = None,
) -> RiskVerdict:
    breaches: list[RiskBreach] = []
    notes: list[str] = []
    adjusted = intent.quantity

    def breach(rule: str, detail: str) -> None:
        breaches.append(RiskBreach(rule=rule, detail=detail))

    if snapshot.env != "paper":
        breach("account.paper_only", f"env '{snapshot.env}' is not paper")
    elif snapshot.account_id not in policy.account_allowlist:
        breach("account.paper_only", f"{snapshot.account_id} is not in the account allowlist")
    if snapshot.source != "demo" and (
        snapshot.account_type not in policy.sim_account_types
        or snapshot.market_id != policy.sim_market_id
    ):
        breach(
            "account.sim_verified",
            f"account_type={snapshot.account_type} market_id={snapshot.market_id}; "
            f"require type in {policy.sim_account_types} and market {policy.sim_market_id}",
        )
    market = intent.symbol.split(".")[0]
    if market not in policy.allowed_markets:
        breach("market.allowed", f"market {market} is not allowed")
    if intent.symbol not in universe_symbols:
        breach("universe.membership", f"{intent.symbol} is outside the configured universe")
    if last_price <= 0:
        breach("price.available", f"no usable last price for {intent.symbol}")
    if last_price < policy.min_price:
        breach("price.minimum", f"last price {last_price:.2f} below minimum {policy.min_price:.2f}")
    if last_price > 0:
        deviation = abs(intent.limit_price / last_price - 1.0)
        if deviation > policy.max_limit_deviation_pct:
            breach(
                "price.limit_deviation",
                f"limit {intent.limit_price:.2f} is {deviation:.1%} away from last {last_price:.2f}",
            )

    notional = intent.quantity * intent.limit_price
    nav = snapshot.nav
    if notional > policy.max_order_notional_pct * nav:
        breach(
            "order.max_notional",
            f"order notional {notional:,.0f} exceeds {policy.max_order_notional_pct:.0%} of NAV",
        )

    held = snapshot.position(intent.symbol)
    held_qty = held.quantity if held else 0
    if intent.side == Side.BUY and held is None and len(snapshot.positions) >= policy.max_positions:
        breach("position.count", f"already holding {policy.max_positions} positions")
    closes_position = intent.side == Side.SELL and intent.quantity == held_qty
    if intent.side == Side.SELL and intent.quantity > held_qty:
        breach("position.no_short", f"sell {intent.quantity} exceeds held {held_qty}")
    if notional < policy.min_order_notional and not closes_position:
        breach(
            "order.min_notional",
            f"order notional {notional:,.0f} below minimum {policy.min_order_notional:,.0f}",
        )

    if state.halted and intent.side == Side.BUY:
        breach("halt.active", "agent is halted; de-risking sells remain allowed")
    if intent.side == Side.BUY:
        drawdown = state.drawdown
        if drawdown is not None and drawdown >= policy.hard_drawdown_pct:
            breach(
                "drawdown.hard",
                f"drawdown {drawdown:.1%} at or beyond hard limit {policy.hard_drawdown_pct:.0%}",
            )
        elif drawdown is not None and drawdown >= policy.soft_drawdown_pct:
            adjusted = intent.quantity // 2
            notes.append(
                f"soft drawdown {drawdown:.1%}; quantity halved from {intent.quantity} to {adjusted}"
            )
        daily_return = state.daily_return
        if daily_return is not None and daily_return <= -policy.daily_loss_limit_pct:
            breach(
                "loss.daily_limit",
                f"daily return {daily_return:.1%} at or beyond {policy.daily_loss_limit_pct:.0%} limit",
            )

    signed_qty = intent.quantity if intent.side == Side.BUY else -intent.quantity
    post_qty = held_qty + signed_qty
    post_value = post_qty * last_price
    if (
        intent.side == Side.BUY
        and post_value > (policy.max_position_weight + policy.cap_tolerance_pct) * nav
    ):
        breach(
            "position.max_weight",
            f"post-trade weight {post_value / nav:.1%} exceeds {policy.max_position_weight:.0%}",
        )

    post_gross = snapshot.gross_exposure - held_qty * last_price + post_value
    if (
        intent.side == Side.BUY
        and post_gross > (policy.max_gross_exposure + policy.cap_tolerance_pct) * nav
    ):
        breach(
            "portfolio.gross",
            f"post-trade gross {post_gross / nav:.1%} exceeds {policy.max_gross_exposure:.0%}",
        )

    post_cash = snapshot.cash - signed_qty * intent.limit_price
    if post_cash < policy.min_cash_weight * nav:
        breach(
            "portfolio.min_cash",
            f"post-trade cash {post_cash / nav:.1%} below {policy.min_cash_weight:.0%}",
        )

    if intent.side == Side.BUY and sleeve_caps and sleeve_by_symbol:
        sleeve = sleeve_by_symbol.get(intent.symbol)
        if sleeve is not None:
            sleeve_exposure = sum(
                position.market_value
                for position in snapshot.positions
                if sleeve_by_symbol.get(position.symbol) == sleeve
            )
            post_sleeve = sleeve_exposure - held_qty * last_price + post_value
            cap = sleeve_caps.get(sleeve)
            if cap is not None and post_sleeve > (cap + policy.cap_tolerance_pct) * nav:
                breach(
                    "sleeve.max_weight",
                    f"{sleeve} exposure {post_sleeve / nav:.1%} exceeds cap {cap:.0%}",
                )

    if state.orders_today >= policy.max_orders_per_day:
        breach(
            "orders.daily_count",
            f"{state.orders_today} orders already planned against {policy.max_orders_per_day}",
        )
    if intent.side == Side.BUY and (
        state.traded_notional_today + notional > policy.max_daily_turnover_pct * nav
    ):
        breach(
            "turnover.daily",
            f"new exposure {state.traded_notional_today + notional:,.0f} exceeds "
            f"{policy.max_daily_turnover_pct:.0%} of NAV; de-risking sells are exempt",
        )

    if adjusted <= 0:
        notes.append("quantity adjusted to zero")

    return RiskVerdict(
        allowed=not breaches and adjusted > 0,
        breaches=breaches,
        adjusted_quantity=max(0, adjusted),
        notes=notes,
    )
