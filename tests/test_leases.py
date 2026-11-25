"""Shared tickers: the PB-004 scalp and the PB-002 stock lane never hold one ticker in the same run."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tyche.config import load_config
from tyche.leases import FREE, SCALP, STOCK, shared_symbols, ticker_leases
from tyche.models import AccountSnapshot, Position

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 25, 15, 10, tzinfo=UTC)  # Wednesday 10:10 ET
TODAY = date(2026, 11, 25)
CHIPS = ["US.NVDA", "US.AMD", "US.AVGO", "US.MU", "US.SMH"]


def snapshot(**held: int) -> AccountSnapshot:
    positions = [Position(symbol=f"US.{name}", quantity=qty, avg_cost=100.0, last_price=100.0)
                 for name, qty in held.items()]
    return AccountSnapshot(account_id="SIM-TEST", cash=100000.0, captured_at=NOW, env="paper",
                           source="demo", positions=positions)


def requested(request_id: str, symbol: str, strategy: str, *, at: datetime = NOW) -> dict:
    return {"type": "order.requested", "ts": at.isoformat(),
            "payload": {"request_id": request_id, "symbol": symbol, "strategy_id": strategy, "side": "buy",
                        "submit_before": (at + timedelta(minutes=10)).isoformat()}}


def filled(request_id: str, symbol: str, quantity: int, *, side: str = "buy", at: datetime = NOW) -> dict:
    return {"type": "order.filled", "ts": at.isoformat(),
            "payload": {"request_id": request_id, "symbol": symbol, "side": side, "quantity": quantity,
                        "filled_at": at.isoformat()}}


def working(remark: str, symbol: str, side: int = 1) -> dict:
    return {"order_id": "9001", "symbol": symbol.removeprefix("US."), "side": side, "qty": "10", "cum_qty": "0",
            "price": "100", "status": 2, "create_time": str(int(NOW.timestamp() * 1_000_000)), "text": remark}


def leases(*, events=(), rows=(), snap=None, lots=(), setups=()):
    return ticker_leases(CHIPS, events=list(events), rows=list(rows), snapshot=snap or snapshot(),
                         scalp_lots=set(lots), stock_setups=set(setups), today=TODAY, now=NOW)


def test_the_five_chips_are_the_shared_tickers():
    config = load_config(ROOT)
    assert shared_symbols(config) == CHIPS
    config.scalp.enabled = False
    assert shared_symbols(config) == []


def test_a_ticker_nobody_holds_is_free_and_says_nothing():
    owners, alerts = leases()
    assert set(owners.values()) == {FREE} and alerts == []


def test_an_open_scalp_lot_holds_its_ticker_for_the_scalp():
    owners, alerts = leases(snap=snapshot(NVDA=40), lots={"US.NVDA"})
    assert owners["US.NVDA"] == SCALP and alerts == []


def test_shares_the_stock_lane_bought_today_hold_the_ticker_for_the_stock_lane():
    events = [requested("tyche-tac-1", "US.AMD", "PB-002"), filled("tyche-tac-1", "US.AMD", 24)]
    owners, alerts = leases(events=events, snap=snapshot(AMD=24))
    assert owners["US.AMD"] == STOCK and alerts == []


def test_a_scalp_fill_does_not_count_as_the_stock_lanes_shares():
    events = [requested("tyche-scl-1", "US.MU", "PB-004"), filled("tyche-scl-1", "US.MU", 10)]
    owners, _ = leases(events=events, snap=snapshot(MU=10), lots={"US.MU"})
    assert owners["US.MU"] == SCALP


def test_a_working_order_holds_the_ticker_for_the_lane_its_remark_names():
    rows = [working("tyche-tac-20261125-avgo", "US.AVGO"), working("tyche-scl-20261125-smh", "US.SMH"),
            working("tyche-exit-20261125-mu", "US.MU", side=2)]
    owners, _ = leases(rows=rows)
    assert (owners["US.AVGO"], owners["US.SMH"], owners["US.MU"]) == (STOCK, SCALP, STOCK)


def test_a_reservation_on_its_way_holds_the_ticker_until_its_window_closes():
    events = [requested("tyche-scl-2", "US.NVDA", "PB-004", at=NOW - timedelta(minutes=3))]
    owners, _ = leases(events=events)
    assert owners["US.NVDA"] == SCALP
    stale = [requested("tyche-scl-3", "US.NVDA", "PB-004", at=NOW - timedelta(minutes=30))]
    owners, _ = leases(events=stale)
    assert owners["US.NVDA"] == FREE


def test_when_both_lanes_claim_a_ticker_the_stock_lane_manages_it_and_says_so_loudly():
    events = [requested("tyche-tac-4", "US.NVDA", "PB-002"), filled("tyche-tac-4", "US.NVDA", 30)]
    owners, alerts = leases(events=events, snap=snapshot(NVDA=70), lots={"US.NVDA"})
    assert owners["US.NVDA"] == STOCK
    assert alerts and alerts[0].startswith("URGENT: US.NVDA: both the scalp and the stock lane")


def test_shares_no_journal_explains_go_to_todays_stock_setup_or_else_to_the_scalp():
    owners, alerts = leases(snap=snapshot(NVDA=15, AMD=15), setups={"US.NVDA"})
    assert owners["US.NVDA"] == STOCK and owners["US.AMD"] == SCALP
    assert alerts == ["US.NVDA: 15 shares no lane's journal explains; today's stock setup manages them"]


def test_yesterdays_stock_fills_do_not_hold_a_ticker_today():
    yesterday = NOW - timedelta(days=1)
    events = [requested("tyche-tac-5", "US.MU", "PB-002", at=yesterday),
              filled("tyche-tac-5", "US.MU", 12, at=yesterday)]
    owners, _ = leases(events=events, snap=snapshot(MU=12))
    assert owners["US.MU"] == SCALP  # held overnight and unexplained today: the scalp sells it, as before
