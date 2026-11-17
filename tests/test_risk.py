from __future__ import annotations

from tyche.config import RiskPolicy, Sleeve
from tyche.models import AccountSnapshot, OrderIntent, Position, Side, apply_fill
from tyche.risk import RiskState, evaluate_intent

POLICY = RiskPolicy()
UNIVERSE = {"US.SPY", "US.QQQ", "US.TLT", "US.GLD"}
SLEEVES: dict[str, Sleeve] = {
    "US.SPY": "equity",
    "US.QQQ": "equity",
    "US.TLT": "defensive",
    "US.GLD": "real_asset",
}


def make_intent(
    quantity: int = 10,
    price: float = 600.0,
    side: Side = Side.BUY,
    symbol: str = "US.SPY",
) -> OrderIntent:
    return OrderIntent(
        symbol=symbol,
        side=side,
        quantity=quantity,
        limit_price=price,
        reason="test",
    )


def make_snapshot(
    cash: float = 100_000.0,
    positions: list[Position] | None = None,
    account_id: str = "SIM-DEMO-US",
) -> AccountSnapshot:
    return AccountSnapshot(account_id=account_id, cash=cash, positions=positions or [])


def evaluate(
    intent: OrderIntent,
    snapshot: AccountSnapshot | None = None,
    state: RiskState | None = None,
    last_price: float = 600.0,
    sleeve_caps: dict[str, float] | None = None,
    policy: RiskPolicy | None = None,
):
    snapshot = snapshot or make_snapshot()
    state = state or RiskState(nav=snapshot.nav, prior_close_nav=snapshot.nav)
    return evaluate_intent(
        intent=intent,
        snapshot=snapshot,
        policy=policy or POLICY,
        state=state,
        last_price=last_price,
        universe_symbols=UNIVERSE,
        sleeve_by_symbol=SLEEVES,
        sleeve_caps=sleeve_caps,
    )


def test_valid_buy_is_allowed() -> None:
    verdict = evaluate(make_intent())
    assert verdict.allowed
    assert verdict.adjusted_quantity == 10
    assert not verdict.breaches


def test_live_account_is_blocked() -> None:
    verdict = evaluate(make_intent(), snapshot=make_snapshot(account_id="LIVE-01"))
    assert not verdict.allowed
    assert any(breach.rule == "account.paper_only" for breach in verdict.breaches)


def test_sell_beyond_holding_is_blocked() -> None:
    snapshot = make_snapshot(
        cash=94_000.0,
        positions=[Position(symbol="US.SPY", quantity=5, avg_cost=500, last_price=600)],
    )
    verdict = evaluate(make_intent(quantity=10, side=Side.SELL), snapshot)
    assert not verdict.allowed
    assert any(breach.rule == "position.no_short" for breach in verdict.breaches)


def test_limit_price_deviation_is_blocked() -> None:
    verdict = evaluate(make_intent(price=660.0))
    assert not verdict.allowed
    assert any(breach.rule == "price.limit_deviation" for breach in verdict.breaches)


def test_order_notional_cap() -> None:
    verdict = evaluate(make_intent(quantity=40, price=600.0))
    assert not verdict.allowed
    assert any(breach.rule == "order.max_notional" for breach in verdict.breaches)


def test_soft_drawdown_halves_buy_quantity() -> None:
    state = RiskState(nav=96_000.0, prior_close_nav=96_000.0, high_water_nav=100_000.0)
    verdict = evaluate(make_intent(quantity=10), state=state)
    assert verdict.allowed
    assert verdict.adjusted_quantity == 5
    assert verdict.notes


def test_hard_drawdown_blocks_buys() -> None:
    state = RiskState(nav=93_000.0, prior_close_nav=93_000.0, high_water_nav=100_000.0)
    verdict = evaluate(make_intent(), state=state)
    assert not verdict.allowed
    assert any(breach.rule == "drawdown.hard" for breach in verdict.breaches)


def test_daily_loss_limit_blocks_buys() -> None:
    state = RiskState(nav=97_000.0, prior_close_nav=100_000.0, high_water_nav=100_000.0)
    verdict = evaluate(make_intent(), state=state)
    assert not verdict.allowed
    assert any(breach.rule == "loss.daily_limit" for breach in verdict.breaches)


def test_daily_order_count() -> None:
    state = RiskState(nav=100_000.0, prior_close_nav=100_000.0, orders_today=6)
    verdict = evaluate(make_intent(), state=state)
    assert not verdict.allowed
    assert any(breach.rule == "orders.daily_count" for breach in verdict.breaches)


def test_turnover_cap() -> None:
    state = RiskState(nav=100_000.0, prior_close_nav=100_000.0, traded_notional_today=20_000.0)
    verdict = evaluate(make_intent(), state=state)
    assert not verdict.allowed
    assert any(breach.rule == "turnover.daily" for breach in verdict.breaches)


def test_turnover_exemption_for_de_risking_sells() -> None:
    snapshot = make_snapshot(
        cash=94_000.0,
        positions=[Position(symbol="US.SPY", quantity=10, avg_cost=500, last_price=600)],
    )
    state = RiskState(nav=100_000.0, prior_close_nav=100_000.0, traded_notional_today=25_000.0)
    verdict = evaluate(make_intent(quantity=5, side=Side.SELL), snapshot, state)
    assert verdict.allowed


def test_minimum_cash_floor() -> None:
    snapshot = make_snapshot(
        cash=6_000.0,
        positions=[Position(symbol="US.TLT", quantity=188, avg_cost=500, last_price=500)],
    )
    verdict = evaluate(make_intent(), snapshot)
    assert not verdict.allowed
    assert any(breach.rule == "portfolio.min_cash" for breach in verdict.breaches)


def test_halt_blocks_buys_but_allows_sells() -> None:
    snapshot = make_snapshot(
        cash=94_000.0,
        positions=[Position(symbol="US.SPY", quantity=10, avg_cost=500, last_price=600)],
    )
    state = RiskState(nav=100_000.0, prior_close_nav=100_000.0, halted=True)

    buy = evaluate(make_intent(quantity=2), snapshot, state)
    assert not buy.allowed
    assert any(breach.rule == "halt.active" for breach in buy.breaches)

    sell = evaluate(make_intent(quantity=5, side=Side.SELL), snapshot, state)
    assert sell.allowed


def test_sleeve_cap_is_enforced() -> None:
    verdict = evaluate(
        make_intent(),
        sleeve_caps={"equity": 0.0, "defensive": 1.0, "real_asset": 1.0, "credit": 1.0},
    )
    assert not verdict.allowed
    assert any(breach.rule == "sleeve.max_weight" for breach in verdict.breaches)


def test_projected_sell_frees_capacity_for_later_buy() -> None:
    caps = {"equity": 0.80, "defensive": 0.40, "real_asset": 0.25, "credit": 0.15}
    snapshot = make_snapshot(
        cash=20_000.0,
        positions=[Position(symbol="US.SPY", quantity=800, avg_cost=100, last_price=100)],
    )
    state = RiskState(nav=100_000.0, prior_close_nav=100_000.0, high_water_nav=100_000.0)
    sell = make_intent(quantity=100, price=100.0, side=Side.SELL)
    buy = make_intent(quantity=200, price=100.0, side=Side.BUY, symbol="US.GLD")

    stale = evaluate(buy, snapshot, state, last_price=100.0, sleeve_caps=caps)
    assert not stale.allowed
    assert any(
        breach.rule in {"portfolio.min_cash", "portfolio.gross"} for breach in stale.breaches
    )

    assert evaluate(sell, snapshot, state, last_price=100.0, sleeve_caps=caps).allowed
    projected = apply_fill(snapshot, sell, sell.quantity)
    verdict = evaluate(buy, projected, state, last_price=100.0, sleeve_caps=caps)
    assert verdict.allowed, verdict.breaches


def test_live_env_is_blocked_even_for_allowlisted_id() -> None:
    snapshot = AccountSnapshot(account_id="SIM-DEMO-US", cash=100_000.0, env="live")
    verdict = evaluate(make_intent(), snapshot=snapshot)
    assert not verdict.allowed
    assert any(b.rule == "account.paper_only" for b in verdict.breaches)


def test_numeric_account_outside_allowlist_is_blocked() -> None:
    snapshot = AccountSnapshot(
        account_id="9000002", cash=100_000.0, source="sim_list", account_type=2, market_id=100
    )
    verdict = evaluate(make_intent(), snapshot=snapshot)
    assert not verdict.allowed
    assert any(b.rule == "account.paper_only" for b in verdict.breaches)


def test_allowlisted_competition_account_is_allowed() -> None:
    policy = RiskPolicy(account_allowlist=["9000001"])
    snapshot = AccountSnapshot(
        account_id="9000001", cash=100_000.0, source="sim_list", account_type=2, market_id=100
    )
    verdict = evaluate(make_intent(), snapshot=snapshot, policy=policy)
    assert verdict.allowed, verdict.breaches


def test_sim_source_requires_us_paper_market() -> None:
    policy = RiskPolicy(account_allowlist=["9000001"])
    snapshot = AccountSnapshot(
        account_id="9000001", cash=100_000.0, source="sim_list", account_type=1, market_id=1
    )
    verdict = evaluate(make_intent(), snapshot=snapshot, policy=policy)
    assert not verdict.allowed
    assert any(b.rule == "account.sim_verified" for b in verdict.breaches)


def test_sim_source_rejects_unknown_account_type() -> None:
    policy = RiskPolicy(account_allowlist=["9000001"])
    snapshot = AccountSnapshot(
        account_id="9000001", cash=100_000.0, source="sim_list", account_type=9, market_id=100
    )
    verdict = evaluate(make_intent(), snapshot=snapshot, policy=policy)
    assert not verdict.allowed
    assert any(b.rule == "account.sim_verified" for b in verdict.breaches)


def test_personal_paper_type_one_is_allowed() -> None:
    policy = RiskPolicy(account_allowlist=["9000001"])
    snapshot = AccountSnapshot(
        account_id="9000001", cash=100_000.0, source="sim_list", account_type=1, market_id=100
    )
    verdict = evaluate(make_intent(), snapshot=snapshot, policy=policy)
    assert verdict.allowed, verdict.breaches


def test_competition_min_price_is_one_dollar() -> None:
    verdict = evaluate(make_intent(quantity=10, price=0.75), last_price=0.75)
    assert not verdict.allowed
    assert any(b.rule == "price.minimum" for b in verdict.breaches)


def test_max_positions_blocks_new_symbol() -> None:
    policy = RiskPolicy(max_positions=1)
    snapshot = make_snapshot(
        cash=94_000.0,
        positions=[Position(symbol="US.TLT", quantity=10, avg_cost=500, last_price=500)],
    )
    verdict = evaluate(make_intent(symbol="US.SPY"), snapshot=snapshot, policy=policy)
    assert not verdict.allowed
    assert any(b.rule == "position.count" for b in verdict.breaches)


def test_disallowed_market_is_blocked() -> None:
    verdict = evaluate(make_intent(symbol="HK.0700"))
    assert not verdict.allowed
    assert any(b.rule == "market.allowed" for b in verdict.breaches)


def test_outside_universe_is_blocked() -> None:
    verdict = evaluate(make_intent(symbol="US.AAPL"))
    assert not verdict.allowed
    assert any(b.rule == "universe.membership" for b in verdict.breaches)


def test_missing_price_is_blocked() -> None:
    verdict = evaluate(make_intent(), last_price=0.0)
    assert not verdict.allowed
    assert any(b.rule == "price.available" for b in verdict.breaches)


def test_below_min_notional_is_blocked() -> None:
    verdict = evaluate(make_intent(quantity=1, price=100.0), last_price=100.0)
    assert not verdict.allowed
    assert any(b.rule == "order.min_notional" for b in verdict.breaches)


def test_single_asset_weight_cap() -> None:
    snapshot = make_snapshot(
        cash=64_000.0,
        positions=[Position(symbol="US.SPY", quantity=60, avg_cost=600, last_price=600)],
    )
    verdict = evaluate(make_intent(quantity=10, price=600.0), snapshot=snapshot)
    assert not verdict.allowed
    assert any(b.rule == "position.max_weight" for b in verdict.breaches)
