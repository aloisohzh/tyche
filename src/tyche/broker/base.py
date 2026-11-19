from __future__ import annotations

from typing import Protocol

from tyche.models import AccountSnapshot, OrderAck, OrderIntent, apply_fill


class Broker(Protocol):
    def snapshot(self) -> AccountSnapshot: ...

    def submit(self, intent: OrderIntent) -> OrderAck: ...


class PaperBroker:
    """In-memory fill simulator; not evidence of a Moomoo broker fill."""

    def __init__(self, snapshot: AccountSnapshot) -> None:
        self._snapshot = snapshot.model_copy(deep=True)
        self._orders: list[OrderAck] = []

    def snapshot(self) -> AccountSnapshot:
        return self._snapshot.model_copy(deep=True)

    def submit(self, intent: OrderIntent) -> OrderAck:
        if self._snapshot.env != "paper":
            raise ValueError("paper broker refuses live account")
        self._snapshot = apply_fill(self._snapshot, intent, intent.quantity)
        ack = OrderAck(
            order_id=f"PAPER-{len(self._orders) + 1:04d}",
            status="filled",
            raw={"fill_price": intent.limit_price, "multiplier": intent.multiplier},
        )
        self._orders.append(ack)
        return ack
