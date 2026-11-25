"""The laptop runner: the moomoo CLI's answers in, the cycle's list out, exactly that list sent."""
from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from test_cycle import NOW, ROOT, Desk, by_symbol, ko_entry

from tyche.broker.moomoo_cli import MoomooCliError
from tyche.laptop import Broker, as_bars, as_orders, as_quotes, next_slot, send_listed, slots
from tyche.market_calendar import ET


@pytest.fixture
def desk(tmp_path, monkeypatch) -> Desk:
    """test_cycle's fake Drive and broker, on the same fixed clock."""
    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.current
    monkeypatch.setattr("tyche.journal.datetime", Clock)
    return Desk(tmp_path, Clock)


class FakeCli:
    """Answers the way the paper API does; remembers every call so a test can see what was sent."""

    def __init__(self, desk: Desk) -> None:
        self.desk = desk
        self.calls: list[tuple] = []
        self.fail_cancel: set[str] = set()

    def _record(self, *call):
        self.calls.append(call)

    def sim_accounts(self):
        self._record("sim_accounts")
        return {"ret_code": 0, "data": {"accounts": [
            {"account_id": "LIVE-9", "account_type": 0, "market_id": 100},
            {"account_id": "SIM-TEST", "account_type": 2, "market_id": 100}]}}

    def sim_funds(self, account):
        self._record("sim_funds", account)
        gross = sum(float(p["qty"]) * float(p["cur_price"]) for p in self.desk.positions)
        return {"ret_code": 0, "data": {"balance": str(self.desk.cash), "hold": "0",
                                        "total_asset": str(self.desk.cash + gross)}}

    def sim_positions(self, account, market="US"):
        self._record("sim_positions", account, market)
        return {"ret_code": 0, "data": {"positions": self.desk.positions}}

    def sim_order_list(self, account, market="US"):
        self._record("sim_order_list", account, market)
        return {"ret_code": 0, "data": {"orders": [o for o in self.desk.orders if o["status"] == 2]}}

    def sim_order_history(self, account, market="US"):
        self._record("sim_order_history", account, market)
        return {"ret_code": 0, "data": {"orders": self.desk.orders}, "pagination": {"has_more": False}}

    def quote(self, symbols):
        self._record("quote", tuple(symbols))
        ms = int((self.desk.clock.current - timedelta(seconds=60)).timestamp() * 1000)
        return {"ret_code": 0, "data": {"quote_list": [
            {"code": s, "data_time": ms, "last_price": self.desk.quotes[s], "volume": 100000,
             "sec_status": "NORMAL", "suspension": False} for s in symbols if s in self.desk.quotes]}}

    def _json(self, args):
        self._record("kline", tuple(args))
        rows = self.desk.bars.get(args[1], [])
        return {"ret_code": 0, "data": {"kline_list": [
            {"time_key": t, "open_price": o, "high_price": h, "low_price": lo, "close_price": c}
            for t, o, h, lo, c in rows]}}

    def sim_order_cancel(self, order_id, account, market="US"):
        self._record("sim_order_cancel", order_id, account)
        if order_id in self.fail_cancel:
            raise MoomooCliError("order not found")
        return {"ret_code": 0, "data": {"order_id": order_id}}

    def sim_order_buy(self, symbol, quantity, account, limit_price, market="US", remark=""):
        self._record("sim_order_buy", symbol, quantity, account, limit_price, remark)
        return {"ret_code": 0, "data": {"order_id": "8001"}}

    def sim_order_sell(self, symbol, quantity, account, limit_price, market="US", remark=""):
        self._record("sim_order_sell", symbol, quantity, account, limit_price, remark)
        return {"ret_code": 0, "data": {"order_id": "8002"}}


def test_the_laptop_keeps_the_15_minute_cards_clock():
    day = date(2026, 11, 25)
    times = slots(day)
    assert (times[0].strftime("%H:%M"), times[-1].strftime("%H:%M"), len(times)) == ("09:07", "15:52", 28)
    assert slots(day, premarket=True)[0].strftime("%H:%M") == "08:05"
    after_close = datetime(2026, 11, 25, 21, 0, tzinfo=UTC)   # 16:00 ET Wednesday
    assert next_slot(after_close) == datetime(2026, 11, 26, 9, 7, tzinfo=ET)  # the cycle itself skips the holiday
    assert next_slot(NOW).astimezone(ET).strftime("%H:%M") == "10:22"


def test_the_clis_reads_are_saved_in_the_shapes_the_cycle_reads_and_it_trades_on_them(desk, tmp_path):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    desk.breakout("US.NVDA", NOW)
    cli = FakeCli(desk)
    run = desk.drive / "2026-11-25-laptop-1510"
    notes = Broker(cli, "SIM-TEST").save_reads(run, {"quotes": ["US.KO", "US.NVDA"], "bars": ["US.NVDA"],
                                                     "books": []})
    assert notes == []
    assert {p.name for p in run.iterdir()} >= {"accounts.json", "cash.json", "positions.json", "orders.json",
                                               "quotes.json", "bars-US.NVDA.json"}
    for path in run.iterdir():   # written "90 seconds ago" on the test's clock, as a real run's files are
        os.utime(path, ((NOW - timedelta(seconds=90)).timestamp(),) * 2)
    report = desk.run(NOW, directory=run)
    assert report["status"] == "ok", report
    sent = by_symbol(report)
    assert (sent["US.KO"]["side"], sent["US.KO"]["quantity"]) == ("buy", 51)
    assert sent["US.NVDA"]["lane"] == "PB-004"
    # Only reads were made: no order command ran while reading.
    assert {call[0] for call in cli.calls} <= {"sim_accounts", "sim_funds", "sim_positions", "sim_order_list",
                                               "sim_order_history", "quote", "kline"}


def test_exactly_the_listed_orders_are_sent_once_each_after_their_cancels(desk):
    cli = FakeCli(desk)
    cli.fail_cancel = {"77"}
    soon = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    report = {"cancel": [{"order_id": "70", "symbol": "US.KO", "why": "pulled"}], "submit": [
        {"n": 1, "symbol": "US.KO", "side": "sell", "quantity": 51, "limit_price": 94.98, "order_type": "LIMIT",
         "time_in_force": "DAY", "remark": "tyche-tac-a", "submit_before": soon, "cancel_first": ["71"]},
        {"n": 2, "symbol": "US.MU", "side": "sell", "quantity": 10, "limit_price": 99.0, "order_type": "LIMIT",
         "time_in_force": "DAY", "remark": "tyche-tac-b", "submit_before": soon, "cancel_first": ["77"]},
        {"n": 3, "symbol": "US.NVDA", "side": "buy", "quantity": 40, "limit_price": 100.73, "order_type": "LIMIT",
         "time_in_force": "DAY", "remark": "tyche-scl-c", "submit_before": soon, "cancel_first": []},
        {"n": 4, "symbol": "US.AMD", "side": "buy", "quantity": 5, "limit_price": 200.0, "order_type": "LIMIT",
         "time_in_force": "DAY", "remark": "tyche-scl-d",
         "submit_before": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(), "cancel_first": []}]}
    results = send_listed(Broker(cli, "SIM-TEST"), report)
    assert [c for c in cli.calls] == [
        ("sim_order_cancel", "70", "SIM-TEST"),
        ("sim_order_cancel", "71", "SIM-TEST"),
        ("sim_order_sell", "US.KO", 51, "SIM-TEST", 94.98, "tyche-tac-a"),
        ("sim_order_cancel", "77", "SIM-TEST"),            # fails: the MU sell is skipped, not sent anyway
        ("sim_order_buy", "US.NVDA", 40, "SIM-TEST", 100.73, "tyche-scl-c")]   # AMD's window had closed
    done = {(r["action"], r.get("symbol")): r for r in results}
    assert done[("submit", "US.KO")]["done"] and done[("submit", "US.KO")]["order_id"] == "8002"
    assert not done[("submit", "US.MU")]["done"] and "cancel of order 77 failed" in done[("submit", "US.MU")]["why"]
    assert not done[("submit", "US.AMD")]["done"] and "submit_before passed" in done[("submit", "US.AMD")]["why"]


def test_a_refused_order_is_reported_and_never_retried(desk):
    cli = FakeCli(desk)

    def refuse(*args, **kwargs):
        cli.calls.append(("sim_order_buy",))
        raise MoomooCliError("moomoo sim order buy failed (1): price out of band for account SIM-TEST")
    cli.sim_order_buy = refuse
    soon = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    item = {"symbol": "US.NVDA", "side": "buy", "quantity": 40, "limit_price": 100.73, "order_type": "LIMIT",
            "remark": "tyche-scl-c", "submit_before": soon, "cancel_first": []}
    results = send_listed(Broker(cli, "SIM-TEST"), {"cancel": [], "submit": [item]})
    assert cli.calls == [("sim_order_buy",)]
    assert not results[0]["done"] and "SIM-TEST" not in results[0]["why"] and "<account>" in results[0]["why"]


def test_cli_answers_in_other_spellings_still_become_the_cycles_shapes():
    orders = as_orders({"data": {"order_list": [
        {"id": "5", "code": "US.KO", "trd_side": "BUY", "qty": 10, "dealt_qty": 10, "price": 96.5,
         "order_status": 4, "create_time": "2026-11-25 09:31:05", "remark": "tyche-tac-x"}]}})
    row = orders["data"]["orders"][0]
    assert (row["order_id"], row["symbol"], row["side"], row["cum_qty"], row["text"]) == ("5", "US.KO", "BUY", 10,
                                                                                          "tyche-tac-x")
    assert row["create_time"] == int(datetime(2026, 11, 25, 9, 31, 5, tzinfo=ET).timestamp() * 1_000_000)
    quotes = as_quotes({"data": [{"code": "NVDA", "last_price": 101.2, "update_time": "2026-11-25 10:09:00"}]})
    assert quotes["data"]["quote_list"][0]["code"] == "US.NVDA"
    assert quotes["data"]["quote_list"][0]["data_time"] == int(datetime(2026, 11, 25, 10, 9, tzinfo=ET).timestamp() * 1000)
    bars = as_bars({"data": {"kline_list": [{"time_key": "2026-11-25 10:08:00", "open": 1, "high": 2, "low": 0.5,
                                             "close": 1.5}]}})
    assert bars["data"]["kline_list"][0]["close_price"] == 1.5
    assert json.dumps(bars)  # plain JSON, as the run folder needs


def test_the_laptop_command_is_wired_into_the_cli():
    from typer.testing import CliRunner

    from tyche.cli import app
    result = CliRunner().invoke(app, ["laptop", "--help"])
    assert result.exit_code == 0 and "--check" in result.output and "--once" in result.output
    assert Path(ROOT / "scripts" / "cloud_api.py").read_text(encoding="utf-8").count("pause-all") >= 2
