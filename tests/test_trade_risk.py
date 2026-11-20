from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tyche.config import (
    AppConfig,
    Asset,
    RiskPolicy,
    SleeveCaps,
    StrategyConfig,
    UniverseConfig,
)
from tyche.fees import estimate_fees
from tyche.models import AccountSnapshot, OrderIntent, Side
from tyche.risk import RiskState, evaluate_intent
from tyche.strategies import build_intents
from tyche.trade_risk import compute_expectancy

SLEEVES = {"US.SPY": "equity", "US.TLT": "defensive"}
PLAN_TS = "2026-11-18T13:00:00+00:00"


def plan_event(nav: float = 10_000.0, stop: float | None = 92.0) -> dict:
    intent = {
        "symbol": "US.SPY",
        "side": "buy",
        "quantity": 100,
        "limit_price": 100.0,
    }
    if stop is not None:
        intent["stop_price"] = stop
    return {
        "ts": PLAN_TS,
        "type": "plan.created",
        "payload": {"plan": {"nav": nav, "orders": [{"intent": intent}]}},
    }


def fill(ts: str, side: str | None, qty: int, price: float, symbol: str = "US.SPY") -> dict:
    payload = {"symbol": symbol, "quantity": qty, "price": price}
    if side is not None:
        payload["side"] = side
    return {"ts": ts, "type": "order.filled", "payload": payload}


def test_partial_close_realizes_pro_rata_r_fee_net() -> None:
    events = [
        plan_event(),
        fill("2026-11-18T14:00:00+00:00", "buy", 100, 100.0),
        fill("2026-11-18T15:00:00+00:00", "sell", 50, 110.0),
    ]
    report = compute_expectancy(events, SLEEVES)
    assert report.closed_n == 1
    trade = report.sleeves[0]
    assert trade.closed_n == 1
    closed = report.open_lots
    assert len(closed) == 1 and closed[0].quantity == 50
    assert closed[0].initial_risk_usd == pytest.approx(400.0)
    buy_fee = estimate_fees("US.SPY", "buy", 100, 100.0).total
    sell_fee = estimate_fees("US.SPY", "sell", 50, 110.0).total
    expected_net = 500.0 - buy_fee * 0.5 - sell_fee
    assert report.pnl_net == pytest.approx(expected_net, abs=1e-3)
    assert report.expectancy_r is None or report.r_n == 1
    win_r = expected_net / 400.0
    assert report.avg_win_r == pytest.approx(win_r, abs=1e-3)


def test_win_and_loss_produce_negative_expectancy_when_symmetric_fees() -> None:
    events = [
        plan_event(),
        fill("2026-11-18T14:00:00+00:00", "buy", 100, 100.0),
        fill("2026-11-18T15:00:00+00:00", "sell", 100, 110.0),
        fill("2026-11-18T16:00:00+00:00", "buy", 100, 100.0),
        fill("2026-11-18T17:00:00+00:00", "sell", 100, 90.0),
    ]
    report = compute_expectancy(events, SLEEVES)
    assert report.closed_n == 2
    assert report.r_n == 2
    assert report.wins == 1 and report.losses == 1
    assert report.win_rate == pytest.approx(0.5)
    assert report.expectancy_r is not None and report.expectancy_r < 0
    assert report.provisional is True
    assert report.open_lots == []


def test_fill_without_side_is_unattributed_not_guessed() -> None:
    events = [
        plan_event(),
        fill("2026-11-18T14:00:00+00:00", "buy", 100, 100.0),
        fill("2026-11-18T15:00:00+00:00", None, 100, 110.0),
    ]
    report = compute_expectancy(events, SLEEVES)
    assert report.closed_n == 0
    assert report.unattributed_fills == 1
    assert report.open_lots[0].quantity == 100


def test_sell_without_entry_lot_is_unattributed() -> None:
    events = [fill("2026-11-18T15:00:00+00:00", "sell", 10, 110.0)]
    report = compute_expectancy(events, SLEEVES)
    assert report.closed_n == 0
    assert report.unattributed_fills == 1


def test_fill_below_stop_falls_back_to_planned_distance() -> None:
    events = [
        plan_event(),
        fill("2026-11-18T14:00:00+00:00", "buy", 100, 90.0),
        fill("2026-11-18T15:00:00+00:00", "sell", 100, 95.0),
    ]
    report = compute_expectancy(events, SLEEVES)
    assert report.closed_n == 1
    assert report.r_n == 1
    assert report.avg_win_r is not None


def test_no_plan_stop_yields_pct_but_no_r() -> None:
    events = [
        plan_event(stop=None),
        fill("2026-11-18T14:00:00+00:00", "buy", 100, 100.0),
        fill("2026-11-18T15:00:00+00:00", "sell", 100, 110.0),
    ]
    report = compute_expectancy(events, SLEEVES)
    assert report.closed_n == 1
    assert report.r_n == 0
    assert report.expectancy_r is None
    assert report.closed_trades[0].realized_pct_nav is not None
    assert report.closed_trades[0].realized_pct_nav > 0


def make_config() -> AppConfig:
    caps = SleeveCaps(equity=0.8, defensive=0.4, real_asset=0.25, credit=0.15)
    return AppConfig(
        universe=UniverseConfig(
            assets=[Asset(symbol="US.SPY", name="SPY", sleeve="equity", max_weight=0.4)]
        ),
        strategies=[
            StrategyConfig(
                id="PB-001",
                sleeve_caps={"risk_on": caps, "neutral": caps, "risk_off": caps},
            )
        ],
        risk=RiskPolicy(),
        root=Path("."),
    )


def test_kernel_blocks_initial_risk_above_budget() -> None:
    config = make_config()
    snapshot = AccountSnapshot(account_id="SIM-DEMO-US", cash=100_000.0, positions=[])
    state = RiskState(nav=snapshot.nav, prior_close_nav=snapshot.nav)
    intent = OrderIntent(
        symbol="US.SPY",
        side=Side.BUY,
        quantity=200,
        limit_price=100.0,
        stop_price=92.0,
        reason="test",
    )
    verdict = evaluate_intent(
        intent=intent,
        snapshot=snapshot,
        policy=config.risk,
        state=state,
        last_price=100.0,
        universe_symbols={"US.SPY"},
        sleeve_by_symbol=SLEEVES,
    )
    assert not verdict.allowed
    assert any(b.rule == "trade.risk_budget" for b in verdict.breaches)
    intent.quantity = 100
    verdict = evaluate_intent(
        intent=intent,
        snapshot=snapshot,
        policy=config.risk,
        state=state,
        last_price=100.0,
        universe_symbols={"US.SPY"},
        sleeve_by_symbol=SLEEVES,
    )
    assert verdict.allowed


def test_sizing_clamps_quantity_to_risk_budget() -> None:
    config = make_config()
    strategy = config.strategies[0]
    snapshot = AccountSnapshot(account_id="SIM-DEMO-US", cash=100_000.0, positions=[])
    result = SimpleNamespace(targets={"US.SPY": 0.30}, regime=SimpleNamespace(value="neutral"))
    intents = build_intents(result, snapshot, {"US.SPY": 100.0}, config, strategy)
    assert len(intents) == 1
    intent = intents[0]
    assert intent.stop_price == pytest.approx(92.09)
    budget = config.risk.risk_per_trade_pct * snapshot.nav
    assert intent.quantity == int(budget / (intent.limit_price - intent.stop_price))
    assert intent.quantity * (intent.limit_price - intent.stop_price) <= budget