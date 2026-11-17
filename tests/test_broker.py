from __future__ import annotations

import pytest

from tyche.broker import PaperBroker
from tyche.models import AccountSnapshot, OrderIntent, Side


def make_intent(side: Side, quantity: int, price: float) -> OrderIntent:
    return OrderIntent(
        symbol="US.SPY",
        side=side,
        quantity=quantity,
        limit_price=price,
        reason="test",
    )


def test_paper_broker_round_trip() -> None:
    broker = PaperBroker(AccountSnapshot(account_id="SIM-DEMO-US", cash=100_000.0))

    buy_ack = broker.submit(make_intent(Side.BUY, 10, 100.0))
    assert buy_ack.status == "filled"
    after_buy = broker.snapshot()
    assert after_buy.cash == pytest.approx(99_000.0)
    assert after_buy.position("US.SPY").quantity == 10
    assert after_buy.nav == pytest.approx(100_000.0)

    sell_ack = broker.submit(make_intent(Side.SELL, 4, 110.0))
    assert sell_ack.status == "filled"
    after_sell = broker.snapshot()
    assert after_sell.cash == pytest.approx(99_440.0)
    assert after_sell.position("US.SPY").quantity == 6
    assert after_sell.nav == pytest.approx(100_100.0)


def test_paper_broker_rejects_oversell() -> None:
    broker = PaperBroker(AccountSnapshot(account_id="SIM-DEMO-US", cash=10_000.0))
    with pytest.raises(ValueError):
        broker.submit(make_intent(Side.SELL, 1, 100.0))
