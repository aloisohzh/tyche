"""Per-trade risk budget and R-multiple expectancy accounting (ADR 0016).

Initial R is fixed at plan time by the protective stop: R = entry - stop.
Realized R is computed fee-net from FIFO round trips over ``order.filled``
journal events. Fills that cannot be attributed (missing side, no matching
entry lot, no plan stop) are counted and surfaced, never guessed.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel, Field

from tyche.fees import estimate_fees

FORMULA = "(Win% × AvgWin) − (Loss% × AvgLoss)"
PROVISIONAL_BELOW_N = 30


class ClosedTrade(BaseModel):
    symbol: str
    sleeve: str
    quantity: int
    entry_price: float
    exit_price: float
    stop_price: float | None = None
    initial_risk_usd: float | None = None
    pnl_gross: float
    fees: float
    pnl_net: float
    realized_r: float | None = None
    realized_pct_nav: float | None = None
    entry_ts: str
    exit_ts: str


class SleeveExpectancy(BaseModel):
    sleeve: str
    closed_n: int = 0
    r_n: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None
    avg_win_r: float | None = None
    avg_loss_r: float | None = None
    expectancy_r: float | None = None
    expectancy_pct: float | None = None
    pnl_net: float = 0.0


class OpenLot(BaseModel):
    symbol: str
    sleeve: str
    quantity: int
    entry_price: float
    stop_price: float | None = None
    initial_risk_usd: float | None = None
    risk_pct_nav: float | None = None


class ExpectancyReport(BaseModel):
    formula: str = FORMULA
    closed_n: int = 0
    r_n: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None
    avg_win_r: float | None = None
    avg_loss_r: float | None = None
    expectancy_r: float | None = None
    expectancy_pct: float | None = None
    pnl_net: float = 0.0
    fees_total: float = 0.0
    sleeves: list[SleeveExpectancy] = Field(default_factory=list)
    closed_trades: list[ClosedTrade] = Field(default_factory=list)
    open_lots: list[OpenLot] = Field(default_factory=list)
    unattributed_fills: int = 0
    provisional: bool = True


class _Lot:
    def __init__(self, qty: int, price: float, stop: float | None, planned_distance: float | None,
                 nav: float | None, ts: str, fee: float) -> None:
        self.qty = qty
        self.price = price
        self.stop = stop
        self.fee = fee
        self.nav = nav
        self.ts = ts
        distance = price - stop if stop is not None and price > stop else planned_distance
        self.initial_risk = qty * distance if distance else None


def _normalize(symbol: str, sleeves: dict[str, str]) -> str:
    if symbol in sleeves:
        return symbol
    for key in sleeves:
        if key.split(".")[-1] == symbol:
            return key
    return symbol


def _plan_stops(events: list[dict[str, Any]]) -> list[tuple[str, float | None, dict[str, dict[str, float]]]]:
    """(ts, nav, symbol -> {stop, planned distance}) per plan.created event."""
    plans = []
    for event in events:
        if event.get("type") != "plan.created":
            continue
        plan = event.get("payload", {}).get("plan", {})
        stops: dict[str, dict[str, float]] = {}
        for order in plan.get("orders", []):
            intent = order.get("intent", {})
            stop = intent.get("stop_price")
            if intent.get("side") == "buy" and stop:
                stops[intent["symbol"]] = {
                    "stop": float(stop),
                    "distance": float(intent["limit_price"]) - float(stop),
                }
        plans.append((event.get("ts", ""), plan.get("nav"), stops))
    return plans


def _stop_for(symbol: str, ts: str, plans: list) -> tuple[float | None, float | None, float | None]:
    stop = distance = nav = None
    for plan_ts, plan_nav, stops in plans:
        if plan_ts > ts:
            break
        nav = plan_nav
        if symbol in stops:
            stop = stops[symbol]["stop"]
            distance = stops[symbol]["distance"]
    return stop, distance, nav


def _aggregate(trades: list[ClosedTrade], sleeve: str) -> SleeveExpectancy:
    out = SleeveExpectancy(sleeve=sleeve)
    out.closed_n = len(trades)
    out.pnl_net = round(sum(t.pnl_net for t in trades), 4)
    wins = [t for t in trades if t.pnl_net > 0]
    losses = [t for t in trades if t.pnl_net < 0]
    out.wins, out.losses = len(wins), len(losses)
    decided = out.wins + out.losses
    out.win_rate = out.wins / decided if decided else None
    win_r = [t.realized_r for t in wins if t.realized_r is not None]
    loss_r = [abs(t.realized_r) for t in losses if t.realized_r is not None]
    out.r_n = len(win_r) + len(loss_r)
    out.avg_win_r = sum(win_r) / len(win_r) if win_r else None
    out.avg_loss_r = sum(loss_r) / len(loss_r) if loss_r else None
    if out.win_rate is not None and out.avg_win_r is not None and out.avg_loss_r is not None:
        out.expectancy_r = round(out.win_rate * out.avg_win_r - (1 - out.win_rate) * out.avg_loss_r, 4)
    win_pct = [t.realized_pct_nav for t in wins if t.realized_pct_nav is not None]
    loss_pct = [abs(t.realized_pct_nav) for t in losses if t.realized_pct_nav is not None]
    if out.win_rate is not None and win_pct and loss_pct:
        out.expectancy_pct = round(
            out.win_rate * (sum(win_pct) / len(win_pct))
            - (1 - out.win_rate) * (sum(loss_pct) / len(loss_pct)),
            6,
        )
    return out


def compute_expectancy(
    events: list[dict[str, Any]],
    sleeve_by_symbol: dict[str, str],
) -> ExpectancyReport:
    plans = _plan_stops(events)
    lots: dict[str, deque[_Lot]] = {}
    closed: list[ClosedTrade] = []
    unattributed = 0

    for event in sorted(events, key=lambda e: e.get("ts", "")):
        if event.get("type") != "order.filled":
            continue
        payload = event.get("payload", {})
        ts = event.get("ts", "")
        symbol = _normalize(str(payload.get("symbol", "")), sleeve_by_symbol)
        side = payload.get("side")
        qty = int(payload.get("quantity") or 0)
        price = float(payload.get("price") or payload.get("avg_fill_price") or 0.0)
        if side not in ("buy", "sell") or qty <= 0 or price <= 0 or not symbol:
            unattributed += 1
            continue
        sleeve = sleeve_by_symbol.get(symbol, "other")
        if side == "buy":
            stop, distance, nav = _stop_for(symbol, ts, plans)
            fee = estimate_fees(symbol, "buy", qty, price).total
            lots.setdefault(symbol, deque()).append(
                _Lot(qty, price, stop, distance, nav, ts, fee)
            )
            continue
        fee_sell = estimate_fees(symbol, "sell", qty, price).total
        remaining = qty
        queue = lots.get(symbol)
        while remaining > 0 and queue:
            lot = queue[0]
            taken = min(remaining, lot.qty)
            fraction = taken / lot.qty
            pnl_gross = (price - lot.price) * taken
            fees = lot.fee * fraction + fee_sell * (taken / qty)
            pnl_net = pnl_gross - fees
            initial_risk = lot.initial_risk * fraction if lot.initial_risk else None
            closed.append(
                ClosedTrade(
                    symbol=symbol,
                    sleeve=sleeve,
                    quantity=taken,
                    entry_price=lot.price,
                    exit_price=price,
                    stop_price=lot.stop,
                    initial_risk_usd=round(initial_risk, 4) if initial_risk else None,
                    pnl_gross=round(pnl_gross, 4),
                    fees=round(fees, 4),
                    pnl_net=round(pnl_net, 4),
                    realized_r=round(pnl_net / initial_risk, 4) if initial_risk else None,
                    realized_pct_nav=round(pnl_net / lot.nav, 6) if lot.nav else None,
                    entry_ts=lot.ts,
                    exit_ts=ts,
                )
            )
            lot.qty -= taken
            lot.fee -= lot.fee * fraction
            if lot.initial_risk:
                lot.initial_risk -= lot.initial_risk * fraction
            remaining -= taken
            if lot.qty == 0:
                queue.popleft()
        if remaining > 0:
            unattributed += 1

    report = ExpectancyReport()
    report.closed_n = len(closed)
    report.unattributed_fills = unattributed
    report.pnl_net = round(sum(t.pnl_net for t in closed), 4)
    report.fees_total = round(sum(t.fees for t in closed), 4)
    overall = _aggregate(closed, "all")
    report.wins, report.losses = overall.wins, overall.losses
    report.win_rate = overall.win_rate
    report.r_n = overall.r_n
    report.avg_win_r = overall.avg_win_r
    report.avg_loss_r = overall.avg_loss_r
    report.expectancy_r = overall.expectancy_r
    report.expectancy_pct = overall.expectancy_pct
    report.provisional = report.closed_n < PROVISIONAL_BELOW_N
    by_sleeve: dict[str, list[ClosedTrade]] = {}
    for trade in closed:
        by_sleeve.setdefault(trade.sleeve, []).append(trade)
    report.sleeves = [_aggregate(trades, sleeve) for sleeve, trades in sorted(by_sleeve.items())]
    report.closed_trades = closed
    for symbol, queue in sorted(lots.items()):
        for lot in queue:
            if lot.qty <= 0:
                continue
            report.open_lots.append(
                OpenLot(
                    symbol=symbol,
                    sleeve=sleeve_by_symbol.get(symbol, "other"),
                    quantity=lot.qty,
                    entry_price=lot.price,
                    stop_price=lot.stop,
                    initial_risk_usd=round(lot.initial_risk, 4) if lot.initial_risk else None,
                    risk_pct_nav=round(lot.initial_risk / lot.nav, 6)
                    if lot.initial_risk and lot.nav
                    else None,
                )
            )
    return report