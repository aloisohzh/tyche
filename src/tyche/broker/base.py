from __future__ import annotations

from typing import Protocol

from tyche.models import AccountSnapshot, OrderAck, OrderIntent, Position, Side


class Broker(Protocol):
    def snapshot(self) -> AccountSnapshot: ...

    def submit(self, intent: OrderIntent) -> OrderAck: ...


class PaperBroker:
    def __init__(self, snapshot: AccountSnapshot) -> None:
        self._snapshot = snapshot.model_copy(deep=True)
        self._orders: list[OrderAck] = []

    def snapshot(self) -> AccountSnapshot:
        return self._snapshot.model_copy(deep=True)

    def submit(self, intent: OrderIntent) -> OrderAck:
        price = intent.limit_price
        notional = intent.quantity * price
        if intent.side == Side.BUY:
            if notional > self._snapshot.cash:
                raise ValueError("insufficient paper cash for order")
            self._snapshot.cash -= notional
            self._apply_buy(intent.symbol, intent.quantity, price)
        else:
            position = self._snapshot.position(intent.symbol)
            if position is None or position.quantity < intent.quantity:
                raise ValueError("insufficient paper position for order")
            self._snapshot.cash += notional
            position.quantity -= intent.quantity
            position.last_price = price
            if position.quantity == 0:
                self._snapshot.positions.remove(position)

        ack = OrderAck(
            order_id=f"PAPER-{len(self._orders) + 1:04d}",
            status="filled",
            raw={"fill_price": price},
        )
        self._orders.append(ack)
        return ack

    def _apply_buy(self, symbol: str, quantity: int, price: float) -> None:
        position = self._snapshot.position(symbol)
        if position is None:
            self._snapshot.positions.append(
                Position(symbol=symbol, quantity=quantity, avg_cost=price, last_price=price)
            )
            return
        total_quantity = position.quantity + quantity
        position.avg_cost = (
            position.avg_cost * position.quantity + price * quantity
        ) / total_quantity
        position.quantity = total_quantity
        position.last_price = price
