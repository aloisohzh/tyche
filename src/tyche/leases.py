"""Shared tickers: one lane at a time (2026-11-25).

A ticker listed in both config/scalp.yaml and config/tactical.yaml may be traded by the PB-004 scalp
and by the PB-002 stock lane, never by both at once. Each run of `tyche cycle` decides, before either
lane plans, which lane holds each shared ticker for that run:

- a lane holds a ticker while it has shares in it (the scalp's open lots, the stock lane's own fills
  today) that the broker still shows, an order for it working at the broker (told apart by the
  order's remark), or a reservation for it still on its way to the broker;
- a ticker no lane holds is free: either lane may enter it, and the scalp, which plans first, takes it
  for the run when it enters (the cycle then keeps the stock lane off it);
- shares that no lane's journal explains go to the stock lane when today's watchlist has a stock
  setup for the ticker (its exits manage them), otherwise to the scalp, which sells them as before;
- if both lanes claim one ticker, the stock lane manages it for the run and the run says so loudly.
  Its exit sells every share the broker shows, so nothing is sold twice.

Options never collide: the scalp trades shares only, and an option is its own contract. The stock
lane's combined-name cap still counts every share and option on an underlying, whichever lane holds
it, so sharing a ticker never lets the account hold more of a name than one lane could.
"""
from __future__ import annotations

from datetime import date, datetime

from tyche.execution_state import (
    EXIT_PREFIX,
    SCALP_PREFIX,
    TACTICAL_PREFIX,
    _request_rows,
    _window_open,
    closed_request_ids,
    order_finished,
    order_symbol,
)
from tyche.market_calendar import ET

SCALP, STOCK, FREE = "scalp", "stock", "free"


def shared_symbols(config) -> list[str]:
    """Tickers both the scalp and the stock lane may trade (empty unless both lanes are on)."""
    if not (config.scalp.enabled and config.tactical.enabled and config.strategy_enabled("PB-004")):
        return []
    return [symbol for symbol in config.scalp.symbols if symbol in config.tactical.symbols]


def _lane_of_remark(text: str) -> str | None:
    if text.startswith(SCALP_PREFIX):
        return SCALP
    if text.startswith((TACTICAL_PREFIX, EXIT_PREFIX)):
        return STOCK
    return None


def _lane_of_strategy(strategy_id: str) -> str:
    return SCALP if strategy_id.startswith("PB-004") else STOCK


def _fill_day(payload: dict, event: dict) -> date | None:
    for stamp in (payload.get("filled_at"), event.get("ts")):
        try:
            moment = datetime.fromisoformat(str(stamp))
        except (TypeError, ValueError):
            continue
        if moment.tzinfo is not None:
            return moment.astimezone(ET).date()
    return None


def ticker_leases(shared: list[str], *, events: list[dict], rows: list[dict], snapshot, scalp_lots: set[str],
                  stock_setups: set[str], today: date, now: datetime) -> tuple[dict[str, str], list[str]]:
    """Which lane holds each shared ticker this run: {symbol: "scalp" | "stock" | "free"}, plus alerts."""
    owners: dict[str, str] = {}
    alerts: list[str] = []
    if not shared:
        return owners, alerts
    wanted = set(shared)
    claims: dict[str, set[str]] = {symbol: set() for symbol in shared}
    # 1. Orders working at the broker, told apart by their remark.
    for row in rows:
        symbol = order_symbol(row)
        if symbol in wanted and not order_finished(row, today):
            lane = _lane_of_remark(str(row.get("text") or ""))
            if lane:
                claims[symbol].add(lane)
    # 2. Reservations still on their way: no broker order yet, submit window open.
    closed = closed_request_ids(events)
    for event, payload, matches in _request_rows(events, rows):
        symbol = payload.get("symbol")
        if (symbol in wanted and not matches and payload["request_id"] not in closed
                and _window_open(event, payload, now)):
            claims[symbol].add(_lane_of_strategy(str(payload.get("strategy_id") or "")))
    # 3. Shares at the broker: the scalp's open lots, the stock lane's own fills today.
    strategy_of = {str((e.get("payload") or {}).get("request_id")): str((e.get("payload") or {}).get("strategy_id") or "")
                   for e in events if e.get("type") == "order.requested"}
    stock_net = {symbol: 0 for symbol in shared}
    for event in events:
        payload = event.get("payload") or {}
        symbol = payload.get("symbol")
        if event.get("type") != "order.filled" or symbol not in wanted:
            continue
        strategy = str(payload.get("strategy_id") or strategy_of.get(str(payload.get("request_id")), ""))
        if strategy.startswith("PB-004") or _fill_day(payload, event) != today:
            continue
        quantity = int(float(payload.get("quantity") or 0))
        stock_net[symbol] += quantity if payload.get("side") == "buy" else -quantity
    for symbol in shared:
        position = snapshot.position(symbol)
        held = position is not None and position.quantity > 0
        if held and symbol in scalp_lots:
            claims[symbol].add(SCALP)
        if held and stock_net[symbol] > 0:
            claims[symbol].add(STOCK)
        lanes = claims[symbol]
        if lanes == {SCALP, STOCK}:
            owners[symbol] = STOCK
            alerts.append(f"URGENT: {symbol}: both the scalp and the stock lane claim this ticker; the stock lane "
                          "manages it this run and the scalp leaves it alone")
        elif lanes:
            owners[symbol] = next(iter(lanes))
        elif held and symbol in stock_setups:
            owners[symbol] = STOCK
            alerts.append(f"{symbol}: {position.quantity:g} shares no lane's journal explains; today's stock setup "
                          "manages them")
        elif held:
            owners[symbol] = SCALP  # the scalp sells shares nobody explains, as it always has
        else:
            owners[symbol] = FREE
    return owners, alerts
