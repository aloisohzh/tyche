"""The laptop runner: the moomoo CLI's answers in, the cycle's list out, exactly that list sent."""
from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from test_cycle import NOW, ROOT, Desk, by_symbol, ko_entry

from tyche.broker.moomoo_cli import MoomooCliError
from tyche.broker.opend import OpenDClient, OpenDError
from tyche.laptop import (
    Broker,
    as_bars,
    as_orders,
    as_quotes,
    find_cli,
    next_slot,
    pick_road,
    send_listed,
    slots,
)
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

    def kline_1m(self, symbol, num=12):
        return self._json(["kline", symbol, "--ktype", "1", "--num", str(num), "--format", "json"])

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
    result = CliRunner().invoke(app, ["laptop", "--help"], env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)   # CI renders help in colour; options split by codes
    assert result.exit_code == 0 and "--check" in text and "--once" in text and "--broker" in text
    assert Path(ROOT / "scripts" / "cloud_api.py").read_text(encoding="utf-8").count("pause-all") >= 2


# --- the OpenD road: the moomoo Python SDK's answers (pandas frames) in, the same shapes out -------------

def _et(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).astimezone(ET).strftime("%Y-%m-%d %H:%M:%S.000")


SDK_STATES = {2: "SUBMITTED", 4: "FILLED_ALL", 5: "CANCELLED_ALL"}


class FakeOpenD:
    """The moomoo SDK's contexts over test_cycle's fake broker, answering with pandas frames."""

    RET_OK = 0
    TrdMarket = SimpleNamespace(US="US")
    TrdEnv = SimpleNamespace(SIMULATE="SIMULATE", REAL="REAL")
    Currency = SimpleNamespace(USD="USD")
    KLType = SimpleNamespace(K_1M="K_1M")
    OrderType = SimpleNamespace(NORMAL="NORMAL")
    TrdSide = SimpleNamespace(BUY="BUY", SELL="SELL")
    TimeInForce = SimpleNamespace(DAY="DAY")
    ModifyOrderOp = SimpleNamespace(CANCEL="CANCEL")

    def __init__(self, desk: Desk) -> None:
        self.desk = desk
        self.calls: list[tuple] = []
        fake = self

        class Quote:
            def __init__(self, host, port):
                pass

            def get_market_snapshot(self, codes):
                fake.calls.append(("snapshot", tuple(codes)))
                at = _et(int((fake.desk.clock.current - timedelta(seconds=60)).timestamp() * 1000))
                return 0, pd.DataFrame([{"code": c, "update_time": at, "last_price": fake.desk.quotes[c],
                                         "volume": 100000, "suspension": False, "sec_status": "NORMAL"}
                                        for c in codes if c in fake.desk.quotes])

            def request_history_kline(self, code, start=None, end=None, ktype=None, max_count=1000):
                fake.calls.append(("kline", code, ktype))
                return 0, pd.DataFrame([{"time_key": _et(t), "open": o, "high": h, "low": lo, "close": c,
                                         "volume": 1000} for t, o, h, lo, c in fake.desk.bars.get(code, [])]), None

            def close(self):
                fake.calls.append(("close quote",))

        class Trade:
            def __init__(self, filter_trdmarket, host, port):
                pass

            def get_acc_list(self):
                fake.calls.append(("accounts",))
                return 0, pd.DataFrame([
                    {"acc_id": 281756455, "trd_env": "REAL", "acc_type": "MARGIN", "trdmarket_auth": ["US", "HK"]},
                    {"acc_id": "SIM-TEST", "trd_env": "SIMULATE", "acc_type": "MARGIN", "trdmarket_auth": ["US"],
                     "sim_acc_type": "STOCK", "competition_acc_name": "challenge"},
                    {"acc_id": 9003, "trd_env": "SIMULATE", "acc_type": "CASH", "trdmarket_auth": ["HK"]}])

            def accinfo_query(self, trd_env, acc_id, currency):
                fake.calls.append(("funds", trd_env, acc_id))
                gross = sum(float(p["qty"]) * float(p["cur_price"]) for p in fake.desk.positions)
                return 0, pd.DataFrame([{"cash": fake.desk.cash, "frozen_cash": fake.desk.hold,
                                         "total_assets": fake.desk.cash + gross, "market_val": gross}])

            def position_list_query(self, trd_env, acc_id):
                fake.calls.append(("positions", trd_env, acc_id))
                return 0, pd.DataFrame([{"code": f"US.{p['symbol']}", "qty": float(p["qty"]),
                                         "can_sell_qty": float(p["qty_avbl"]), "average_cost": float(p["cost_price"]),
                                         "nominal_price": float(p["cur_price"]), "position_side": "LONG"}
                                        for p in fake.desk.positions],
                                       columns=["code", "qty", "can_sell_qty", "average_cost", "nominal_price",
                                                "position_side"])

            def _orders(self):
                return pd.DataFrame([{"order_id": o["order_id"], "code": f"US.{o['symbol']}",
                                      "trd_side": {1: "BUY", 2: "SELL"}[o["side"]], "qty": float(o["qty"]),
                                      "dealt_qty": float(o["cum_qty"]), "price": float(o["price"]),
                                      "dealt_avg_price": float(o["avg_fill_price"]),
                                      "order_status": SDK_STATES[o["status"]],
                                      "create_time": _et(int(o["create_time"]) // 1000),
                                      "updated_time": _et(int(o["update_time"]) // 1000), "remark": o["text"]}
                                     for o in fake.desk.orders],
                                    columns=["order_id", "code", "trd_side", "qty", "dealt_qty", "price",
                                             "dealt_avg_price", "order_status", "create_time", "updated_time",
                                             "remark"])

            def order_list_query(self, trd_env, acc_id):
                fake.calls.append(("orders", trd_env, acc_id))
                return 0, self._orders()

            def history_order_list_query(self, trd_env, acc_id, start, end):
                fake.calls.append(("history", trd_env, acc_id))
                return 0, self._orders()

            def place_order(self, **kwargs):
                fake.calls.append(("place", kwargs))
                return 0, pd.DataFrame([{"order_id": "8001", "code": kwargs["code"]}])

            def modify_order(self, op, order_id, qty, price, trd_env, acc_id):
                fake.calls.append(("modify", op, order_id, trd_env, acc_id))
                return 0, pd.DataFrame([{"trd_env": trd_env, "order_id": order_id}])

            def close(self):
                fake.calls.append(("close trade",))

        self.OpenQuoteContext = Quote
        self.OpenSecTradeContext = Trade


def test_opends_reads_are_saved_in_the_cycles_shapes_and_it_trades_on_them(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    desk.breakout("US.NVDA", NOW)
    desk.order("tyche-tac-earlier", "US.MU", 1, 10, 99.0, status=5, filled=0)
    fake = FakeOpenD(desk)
    client = OpenDClient(module=fake)
    run = desk.drive / "2026-11-25-laptop-151000"
    notes = Broker(client, "SIM-TEST").save_reads(run, {"quotes": ["US.KO", "US.NVDA"], "bars": ["US.NVDA"],
                                                        "books": []})
    assert notes == []
    accounts = json.loads((run / "accounts.json").read_text(encoding="utf-8"))["data"]["accounts"]
    assert [a["account_id"] for a in accounts] == ["SIM-TEST"]          # the live and the HK rows never land
    assert (accounts[0]["account_type"], accounts[0]["market_id"]) == (2, 100)
    quotes = json.loads((run / "quotes.json").read_text(encoding="utf-8"))["data"]["quote_list"]
    assert quotes[0]["suspension"] is False and quotes[0]["sec_status"] == "NORMAL"
    orders = json.loads((run / "orders.json").read_text(encoding="utf-8"))["data"]["orders"]
    assert (orders[0]["status"], orders[0]["side"], orders[0]["text"]) == (5, "buy", "tyche-tac-earlier")
    for path in run.iterdir():
        os.utime(path, ((NOW - timedelta(seconds=90)).timestamp(),) * 2)
    report = desk.run(NOW, directory=run)
    assert report["status"] == "ok", report
    sent = by_symbol(report)
    assert (sent["US.KO"]["side"], sent["US.KO"]["quantity"]) == ("buy", 51)
    assert sent["US.NVDA"]["lane"] == "PB-004"
    assert all(call[0] not in ("place", "modify") for call in fake.calls)   # reading placed nothing
    assert {call[1] for call in fake.calls if call[0] in ("funds", "positions", "orders", "history")} == {"SIMULATE"}


def test_opend_sends_paper_orders_only_for_the_listed_paper_account(desk):
    fake = FakeOpenD(desk)
    client = OpenDClient(module=fake)
    soon = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    report = {"cancel": [{"order_id": "70", "symbol": "US.KO"}], "submit": [
        {"symbol": "US.NVDA", "side": "buy", "quantity": 40, "limit_price": 100.734, "order_type": "LIMIT",
         "remark": "tyche-scl-c", "submit_before": soon, "cancel_first": []}]}
    results = send_listed(Broker(client, "SIM-TEST"), report)
    assert [r["done"] for r in results] == [True, True] and results[1]["order_id"] == "8001"
    placed = next(call[1] for call in fake.calls if call[0] == "place")
    assert (placed["code"], placed["qty"], placed["price"], placed["trd_side"], placed["remark"]) == (
        "US.NVDA", 40, 100.73, "BUY", "tyche-scl-c")
    assert (placed["trd_env"], placed["acc_id"], placed["order_type"]) == ("SIMULATE", "SIM-TEST", "NORMAL")
    assert ("modify", "CANCEL", "70", "SIMULATE", "SIM-TEST") in fake.calls
    # The live account, or any id OpenD does not call a US paper account, is refused before any call.
    for account in ("281756455", "9003"):
        before = len(fake.calls)
        with pytest.raises(OpenDError):
            client.sim_order_buy("US.NVDA", 1, account, 100.0, remark="x")
        assert not [c for c in fake.calls[before:] if c[0] in ("place", "modify")]


def test_opend_order_states_and_quote_status_read_as_the_cycle_expects():
    client = OpenDClient(module=FakeOpenD.__new__(FakeOpenD))
    rows = client._orders(pd.DataFrame([
        {"order_id": 1, "code": "US.KO", "trd_side": "SELL", "qty": 10.0, "dealt_qty": 4.0, "price": 96.5,
         "order_status": "CANCELLED_PART", "create_time": "2026-11-25 09:31:05.120", "remark": "tyche-tac-x"},
        {"order_id": 2, "code": "US.KO", "trd_side": "BUY", "qty": 10.0, "dealt_qty": 0.0, "price": 96.5,
         "order_status": "SUBMIT_FAILED", "create_time": "2026-11-25 09:32:00", "remark": None},
        {"order_id": 3, "code": "US.KO", "trd_side": "BUY", "qty": 10.0, "dealt_qty": 0.0, "price": 96.5,
         "order_status": "SOMETHING_NEW", "create_time": "2026-11-25 09:33:00", "remark": ""}]))
    assert [r["status"] for r in rows] == [5, 5, 1]       # finished for good twice; unknown stays unresolved
    assert rows[0]["side"] == "sell" and rows[0]["cum_qty"] == 4.0 and rows[1]["text"] == ""
    shaped = as_orders({"data": {"orders": rows}})["data"]["orders"][0]
    assert shaped["create_time"] == int(datetime(2026, 11, 25, 9, 31, 5, 120000, tzinfo=ET).timestamp() * 1_000_000)
    assert json.loads(json.dumps(rows))  # plain JSON values, no numpy scalars
    fake = FakeOpenD.__new__(FakeOpenD)
    fake.OpenQuoteContext = lambda host, port: SimpleNamespace(get_market_snapshot=lambda codes: (0, pd.DataFrame([
        {"code": "US.KO", "update_time": "2026-11-25 10:09:00.000", "last_price": 96.4, "volume": 5,
         "suspension": False, "sec_status": "N/A"},
        {"code": "US.MU", "update_time": "2026-11-25 10:09:00.000", "last_price": 99.0, "volume": 5,
         "suspension": True, "sec_status": "N/A"}])))
    quotes = OpenDClient(module=fake).quote(["US.KO", "US.MU"])["data"]["quote_list"]
    assert [(q["sec_status"], q["suspension"]) for q in quotes] == [("NORMAL", False), ("SUSPENDED", True)]


def test_the_runner_takes_the_cli_when_the_laptop_has_it_and_opend_otherwise(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.laptop.shutil.which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("TYCHE_MOOMOO_CLI", raising=False)
    assert find_cli() is None
    assert isinstance(pick_road("auto"), OpenDClient)
    tool = tmp_path / "FutuCLI" / "bin" / "futu.exe"
    tool.parent.mkdir(parents=True)
    tool.write_text("", encoding="utf-8")
    road = pick_road("auto")
    assert not isinstance(road, OpenDClient) and road.binary == str(tool)
    assert isinstance(pick_road("opend"), OpenDClient)
