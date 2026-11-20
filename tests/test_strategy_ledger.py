"""Strategy mount/retire ledger: provisional hold, mount on proven edge, retire on decay."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tyche.strategy_ledger import StrategyPolicy, score, status_from_journal

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)
SLEEVES = {"US.NVDA": "equity", "US.AMD": "equity"}


def round_trips(n: int, *, entry: float = 100.0, exit_price: float, stop: float = 95.0,
                qty: int = 10, symbol: str = "US.NVDA",
                strategy_id: str = "PB-004") -> list[dict]:
    events = [{"ts": (NOW - timedelta(hours=1)).isoformat(), "type": "plan.created", "payload": {
        "plan": {"nav": 100000.0, "orders": [{"intent": {
            "strategy_id": strategy_id, "symbol": symbol, "side": "buy",
            "stop_price": stop, "limit_price": entry}}]}}}]
    for index in range(n):
        opened = NOW + timedelta(minutes=2 * index)
        events.append({"ts": opened.isoformat(), "type": "order.filled", "payload": {
            "strategy_id": strategy_id, "symbol": symbol, "side": "buy",
            "quantity": qty, "price": entry}})
        events.append({"ts": (opened + timedelta(minutes=1)).isoformat(), "type": "order.filled",
                       "payload": {"strategy_id": strategy_id, "symbol": symbol, "side": "sell",
                                   "quantity": qty, "price": exit_price}})
    return events


def mixed(wins: int, losses: int, **kwargs) -> list[dict]:
    return (round_trips(wins, exit_price=101.0, **kwargs)
            + round_trips(losses, exit_price=99.0, **kwargs))


def test_few_trades_hold_as_provisional():
    decision = score(mixed(2, 1), "PB-004", "equity", SLEEVES, at=NOW)
    assert decision.action == "hold"
    assert decision.scorecard.provisional
    assert decision.scorecard.closed_n == 3
    assert "provisional" in decision.rule


def test_winners_mount_only_after_minimum_sample():
    decision = score(mixed(29, 1), "PB-004", "equity", SLEEVES, at=NOW)
    assert decision.action == "mount", decision.rule
    card = decision.scorecard
    assert card.closed_n == 30 and card.expectancy_r and card.expectancy_r > 0
    assert card.profit_factor and card.profit_factor > 1.2
    assert card.fees_total > 0


def test_mounted_strategy_retires_when_expectancy_decays():
    events = mixed(5, 25)
    assert score(events, "PB-004", "equity", SLEEVES, at=NOW).action == "hold"
    events.append({"ts": NOW.isoformat(), "type": "strategy.decision",
                   "payload": {"strategy_id": "PB-004", "action": "mount"}})
    assert status_from_journal(events, "PB-004") == "mounted"
    retired = score(events, "PB-004", "equity", SLEEVES, at=NOW)
    assert retired.action == "retire", retired.rule
    assert "decay" in retired.rule


def test_drawdown_breach_retires_a_mounted_strategy():
    events = mixed(29, 1)
    events.append({"ts": NOW.isoformat(), "type": "strategy.decision",
                   "payload": {"strategy_id": "PB-004", "action": "mount"}})
    decision = score(events, "PB-004", "equity", SLEEVES,
                     StrategyPolicy(max_drawdown_pct=0.000001), at=NOW)
    assert decision.action == "retire"
    assert "drawdown" in decision.rule


def test_other_strategy_fills_are_not_scored():
    events = mixed(29, 1)
    events += round_trips(30, exit_price=90.0, symbol="US.AMD", strategy_id="PB-001")
    decision = score(events, "PB-004", "equity", SLEEVES, at=NOW)
    assert decision.scorecard.closed_n == 30
    assert decision.action == "mount"
