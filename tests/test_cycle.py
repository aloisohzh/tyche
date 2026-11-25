"""`tyche cycle`: saved broker reads in, the list of orders to send out.

These drills run the whole order path the two cards use, against a fake Drive root, a fake broker
(order rows and positions written the way the paper API returns them) and a fixed clock.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tyche.approvals import ApprovalBatch
from tyche.cli import app
from tyche.config import load_config
from tyche.cycle import (
    contract_from_symbol,
    find_ledger,
    find_nav_refs,
    find_watchlist,
    reads_needed,
    run_cycle,
)
from tyche.journal import append_event, read_events, verify_chain
from tyche.market_calendar import SessionPhase
from tyche.watchlist import Factor, Watchlist, WatchlistEntry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 25, 15, 10, tzinfo=UTC)  # Wednesday 10:10 ET, regular session
TODAY = date(2026, 11, 25)


def envelope(*lines: dict) -> dict:
    return {"as_of": TODAY.isoformat(), "valid_until": "2026-11-27", "approved_at": "2026-11-25T03:00:00+00:00",
            "approved_by": "operator (test)", "max_orders": 200, "orders": list(lines)}


STOCK_LINES = [
    {"symbol": "US.KO", "side": "buy", "max_qty": 100, "max_total_qty": 200, "limit_max": 113.0},
    {"symbol": "US.KO", "side": "sell", "max_qty": 200, "max_total_qty": 400, "limit_min": 68.0},
    {"symbol": "US.KO", "side": "buy", "multiplier": 100, "max_qty": 5, "max_total_qty": 10, "limit_max": 40.0},
    {"symbol": "US.KO", "side": "sell", "multiplier": 100, "max_qty": 10, "max_total_qty": 20, "limit_min": 0.01},
]
SCALP_LINES = [
    {"symbol": "US.NVDA", "side": "buy", "max_qty": 60, "max_total_qty": 2000, "limit_max": 1500.0},
    {"symbol": "US.NVDA", "side": "sell", "max_qty": 60, "max_total_qty": 2000, "limit_min": 50.0},
]


def ko_entry(now: datetime = NOW, **changes) -> WatchlistEntry:
    """Tuesday 24 Nov's real KO setup: zone 96.2 to 96.5, stop 95.4, target 98.3, 51 shares."""
    fields = {
        "symbol": "US.KO", "sleeve": "defensive", "strategy": "pullback to support", "setup_id": "ko-pullback",
        "entry_low": 96.2, "entry_high": 96.5, "stop": 95.4, "target": 98.3, "expiry": now.date(),
        "thesis": "Staples bid in a risk-off tape; pullback to the 20-day line", "catalyst": "defensive rotation",
        "sources": ["https://example.test/ko"], "reviewed_at": now - timedelta(hours=2), "market_cap_usd": 4.1e11,
        "max_quantity": 51, "exit_at": now.replace(hour=20, minute=50),
        "factors": [Factor(name="support", axis="technical", state="pass", why="held the 20-day line"),
                    Factor(name="earnings", axis="fundamental", state="pass", why="guidance raised")]}
    fields.update(changes)
    return WatchlistEntry(**fields)


class Desk:
    """A fake Drive root plus a fake broker the cycle reads through saved payloads."""

    def __init__(self, tmp_path: Path, clock) -> None:
        self.clock = clock
        self.drive = tmp_path / "drive"
        self.ledger = self.drive / "2026-11-25-premarket-1305" / "journal" / "events.jsonl"
        append_event(self.ledger, "run.started", {"run": "premarket"})
        (self.drive / "nav-refs.json").write_text(json.dumps(
            {"as_of": "2026-11-24", "prior_close_nav": 100000.0, "high_water_nav": 100000.0}), encoding="utf-8")
        self.stock_envelope = tmp_path / "standing-approval.json"
        self.stock_envelope.write_text(json.dumps(envelope(*STOCK_LINES)), encoding="utf-8")
        self.scalp_envelope = tmp_path / "scalp-approvals.json"
        self.scalp_envelope.write_text(json.dumps(envelope(*SCALP_LINES)), encoding="utf-8")
        self.cash = 100000.0
        self.hold = 0.0
        self.total_asset: float | None = None
        self.positions: list[dict] = []
        self.orders: list[dict] = []
        self.quotes: dict[str, float] = {}
        self.books: dict[str, tuple[float, float]] = {}
        self.bars: dict[str, list[tuple[int, float, float, float, float]]] = {}
        self.runs = 0
        self.account_type = 2

    def watch(self, *entries: WatchlistEntry, as_of: date = TODAY, where: str = "watchlist.json") -> Path:
        path = self.drive / where
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(Watchlist(as_of=as_of, entries=list(entries)).model_dump_json(), encoding="utf-8")
        return path

    def breakout(self, symbol: str, now: datetime, *, base: float = 100.0, close: float = 100.6,
                 minutes_ago: int = 1) -> None:
        """Six quiet bars, then one up bar that closes above their highs."""
        rows = [(int((now - timedelta(minutes=minutes_ago + 6 - i)).timestamp() * 1000),
                 base - 0.5, base, base - 1.0, base - 0.2) for i in range(6)]
        rows.append((int((now - timedelta(minutes=minutes_ago)).timestamp() * 1000),
                     base + 0.1, close + 0.1, base, close))
        self.bars[symbol] = rows
        self.quotes[symbol] = close

    def order(self, remark: str, symbol: str, side: int, qty: int, price: float, *, status: int = 4,
              filled: int | None = None, fill_price: float | None = None, at: datetime = NOW) -> dict:
        filled = qty if filled is None and status == 4 else (filled or 0)
        row = {"order_id": str(7000 + len(self.orders)), "symbol": symbol.removeprefix("US."), "side": side,
               "qty": str(qty), "cum_qty": str(filled), "price": str(price),
               "avg_fill_price": str(fill_price or price), "status": status,
               "create_time": str(int(at.timestamp() * 1_000_000)),
               "update_time": str(int((at + timedelta(seconds=20)).timestamp() * 1_000_000)),
               "text": remark, "time_in_force": 0}
        self.orders.append(row)
        return row

    def hold_position(self, symbol: str, qty: int, cost: float, last: float, *, available: int | None = None) -> None:
        self.positions = [p for p in self.positions if p["symbol"] != symbol.removeprefix("US.")]
        self.positions.append({"symbol": symbol.removeprefix("US."), "qty": str(qty),
                               "qty_avbl": str(qty if available is None else available),
                               "cost_price": str(cost), "cur_price": str(last), "pstn_type": 0})

    def write_reads(self, now: datetime) -> Path:
        self.runs += 1
        directory = self.drive / f"2026-11-25-cycle-{self.runs:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = now - timedelta(seconds=90)
        ms = int(stamp.timestamp() * 1000)
        gross = sum(float(p["qty"]) * float(p["cur_price"]) for p in self.positions)
        total = self.total_asset if self.total_asset is not None else self.cash + self.hold + gross
        payloads = {
            "accounts.json": {"ret_code": 0, "data": {"accounts": [
                {"account_id": "LIVE-9", "account_type": 0, "market_id": 100},
                {"account_id": "SIM-TEST", "account_type": self.account_type, "market_id": 100}]}},
            "cash.json": {"ret_code": 0, "data": {"balance": str(self.cash), "hold": str(self.hold),
                                                   "total_asset": str(total)}},
            "positions.json": {"ret_code": 0, "data": {"positions": self.positions}},
            "orders.json": {"ret_code": 0, "data": {"orders": self.orders}, "pagination": {"has_more": False}},
            "quotes.json": {"ret_code": 0, "data": {"quote_list": [
                {"code": symbol, "data_time": ms, "last_price": last, "volume": 100000,
                 "sec_status": "NORMAL", "suspension": False} for symbol, last in self.quotes.items()]}},
        }
        for symbol, (bid, ask) in self.books.items():
            payloads[f"book-{symbol}.json"] = {"ret_code": 0, "data": [{"code": symbol, "books": [
                {"exchange_data_time_ms": ms, "bid_list": [{"price": bid, "volume": 500}],
                 "ask_list": [{"price": ask, "volume": 500}]}]}]}
        for symbol, rows in self.bars.items():
            payloads[f"bars-{symbol}.json"] = {"ret_code": 0, "data": {"kline_list": [
                {"time_key": t, "open_price": o, "high_price": h, "low_price": lo, "close_price": c}
                for t, o, h, lo, c in rows]}}
        for name, payload in payloads.items():
            (directory / name).write_text(json.dumps(payload), encoding="utf-8")
            os.utime(directory / name, (stamp.timestamp(), stamp.timestamp()))
        return directory

    def run(self, now: datetime = NOW, *, record: bool = True, directory: Path | None = None, **kwargs) -> dict:
        self.clock.current = now
        directory = directory or self.write_reads(now)
        options = {"directory": directory, "record": record, "now": now, "config_root": ROOT,
                   "drive_root": self.drive, "account_id": "SIM-TEST", "stock_envelope": self.stock_envelope,
                   "scalp_envelope": self.scalp_envelope}
        options.update(kwargs)
        return run_cycle(**options)

    def events(self, kind: str | None = None) -> list[dict]:
        rows = read_events(self.ledger)
        return [e for e in rows if kind is None or e["type"] == kind]


@pytest.fixture
def clock(monkeypatch):
    """Journal rows are stamped by the test clock, so "today" and the submit windows are deterministic."""
    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.current
    monkeypatch.setattr("tyche.journal.datetime", Clock)
    return Clock


@pytest.fixture
def desk(tmp_path, clock) -> Desk:
    return Desk(tmp_path, clock)


def by_symbol(report: dict, key: str = "submit") -> dict[str, dict]:
    return {row["symbol"]: row for row in report[key]}


# --- the whole life of a stock trade and a scalp trade, through the one command -----------------------

def test_one_command_carries_a_stock_and_a_scalp_from_entry_to_exit(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40          # inside the plan's zone: bought at the ask now
    desk.breakout("US.NVDA", NOW)          # five-bar breakout: scalp entry

    first = desk.run(NOW)
    assert first["status"] == "ok" and first["recorded"] and first["phase"] == "opening_drive", first
    sent = by_symbol(first)
    ko, nvda = sent["US.KO"], sent["US.NVDA"]
    assert (ko["side"], ko["quantity"], ko["limit_price"], ko["lane"]) == ("buy", 51, 96.43, "PB-002")
    assert ko["remark"].startswith("tyche-tac-") and ko["order_type"] == "LIMIT" and ko["time_in_force"] == "DAY"
    assert (nvda["side"], nvda["lane"]) == ("buy", "PB-004") and nvda["remark"].startswith("tyche-scl-")
    assert nvda["limit_price"] == 100.73 and 0 < nvda["quantity"] * nvda["limit_price"] <= 5000  # 5% of NAV
    assert datetime.fromisoformat(ko["submit_before"]) == NOW + timedelta(minutes=10)
    assert [row["n"] for row in first["submit"]] == [1, 2]
    assert "2 order(s) sent" in first["telegram"] and "BUY 51 KO @ 96.43" in first["telegram"]
    assert "No record-order" not in first["instructions"] and "no record-order step" in first["instructions"]
    assert len(desk.events("order.requested")) == 2 and verify_chain(desk.ledger)[0]

    # 15 minutes later the broker shows both filled. Nobody typed a receipt: the order list is the record.
    later = NOW + timedelta(minutes=15)
    desk.order(ko["remark"], "US.KO", 1, 51, 96.43, fill_price=96.41, at=NOW + timedelta(minutes=2))
    desk.order(nvda["remark"], "US.NVDA", 1, nvda["quantity"], 100.73, fill_price=100.64, at=NOW + timedelta(minutes=2))
    desk.hold_position("US.KO", 51, 96.41, 96.60)
    desk.hold_position("US.NVDA", nvda["quantity"], 100.64, 101.30)
    desk.cash = 100000.0 - 51 * 96.41 - nvda["quantity"] * 100.64
    desk.quotes.update({"US.KO": 96.60, "US.NVDA": 101.30})   # NVDA is through its 0.5% target
    desk.bars.clear()

    second = desk.run(later)
    assert second["status"] == "ok", second
    assert sorted(second["journaled_receipts"]) == sorted([
        "order.submitted US.KO buy 51", "order.filled US.KO buy 51",
        f"order.submitted US.NVDA buy {nvda['quantity']}", f"order.filled US.NVDA buy {nvda['quantity']}"])
    sent = by_symbol(second)
    assert [row["side"] for row in second["submit"]] == ["sell", "sell"]
    assert sent["US.NVDA"]["why"] == "scalp target" and sent["US.NVDA"]["quantity"] == nvda["quantity"]
    assert sent["US.NVDA"]["limit_price"] == round(round(101.30 * 0.9997, 2) * 0.997, 2)  # bid less the collar
    assert (sent["US.KO"]["quantity"], sent["US.KO"]["limit_price"]) == (51, 98.3)  # take-profit rests at the target
    assert "take-profit" in sent["US.KO"]["why"]
    assert "FILLED buy 51 US.KO @ 96.41" in second["telegram"]
    requests = {e["payload"]["request_id"]: e["payload"] for e in desk.events("order.requested")}
    assert requests[sent["US.KO"]["remark"]]["authorization"]["kind"] == "protective"
    assert requests[sent["US.NVDA"]["remark"]]["authorization"]["kind"] == "protective"

    # Another 15 minutes: the scalp exit filled, the take-profit rests, and KO has broken its stop.
    last = later + timedelta(minutes=15)
    desk.order(sent["US.NVDA"]["remark"], "US.NVDA", 2, nvda["quantity"], sent["US.NVDA"]["limit_price"],
               fill_price=101.25, at=later + timedelta(minutes=2))
    resting = desk.order(sent["US.KO"]["remark"], "US.KO", 2, 51, 98.3, status=2, at=later + timedelta(minutes=2))
    desk.positions = []
    desk.hold_position("US.KO", 51, 96.41, 95.30, available=0)   # the resting sell locks the shares
    desk.cash = 100000.0 - 51 * 96.41 + nvda["quantity"] * (101.25 - 100.64)
    desk.quotes = {"US.KO": 95.30, "US.NVDA": 101.0}

    third = desk.run(last)
    assert third["status"] == "ok", third
    assert f"order.filled US.NVDA sell {nvda['quantity']}" in third["journaled_receipts"]
    stop = by_symbol(third)["US.KO"]
    assert (stop["side"], stop["quantity"], stop["why"]) == ("sell", 51, "underlying stop breached")
    assert stop["limit_price"] == round(round(95.30 * 0.9997, 2) * 0.997, 2)   # the bid less the 0.3% collar
    assert stop["cancel_first"] == [resting["order_id"]]          # the take-profit is pulled, then the stop goes
    assert third["cancel"] == []                                  # listed once, with the order it frees
    assert "US.NVDA" not in by_symbol(third)                      # the scalp lot is closed
    nvda = next(d for d in third["scalp"]["decisions"] if d["symbol"] == "US.NVDA")
    assert nvda["reason"] != "max open positions"
    assert verify_chain(desk.ledger)[0]


def test_a_dry_run_reserves_nothing_and_says_so(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    before = len(desk.events())
    report = desk.run(NOW, record=False)
    assert report["status"] == "ok" and not report["recorded"] and report["submit"] == []
    assert [(row["symbol"], row["side"], row["quantity"]) for row in report["preview"]] == [("US.KO", "buy", 51)]
    assert "nothing may be submitted" in report["instructions"]
    assert len(desk.events()) == before


def test_the_next_run_does_not_buy_twice_while_an_order_is_on_its_way_or_working(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    first = desk.run(NOW)
    remark = by_symbol(first)["US.KO"]["remark"]

    # Five minutes on, the order list does not show it yet: it may still be sent, so nothing new goes out.
    again = desk.run(NOW + timedelta(minutes=5))
    assert again["submit"] == [], again
    # Fifteen minutes on it rests at the broker: still one order, never a second buy.
    desk.order(remark, "US.KO", 1, 51, 96.43, status=2, at=NOW + timedelta(minutes=1))
    resting = desk.run(NOW + timedelta(minutes=15))
    assert resting["submit"] == [] and resting["journaled_receipts"] == ["order.submitted US.KO buy 51"]
    assert len(desk.events("order.requested")) == 1


def test_a_reservation_that_was_never_sent_frees_the_setup_for_the_next_run(desk):
    """24 Nov: one unsent reservation froze its symbol for the rest of the day."""
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    desk.run(NOW)
    retry = desk.run(NOW + timedelta(minutes=15))      # the window (10 minutes) closed with no broker order
    assert [(row["symbol"], row["side"]) for row in retry["submit"]] == [("US.KO", "buy")], retry
    assert len(desk.events("order.requested")) == 2
    # The operator is told, once, that a listed order was not placed: silence here is how a desk
    # that lists orders nobody sends could go unnoticed for a whole session.
    assert "1 order(s) the command listed never reached the broker: buy 51 KO (listed 10:10 ET)" in retry["telegram_urgent"]
    assert [e["payload"]["symbol"] for e in desk.events("order.unsent")] == ["US.KO"]
    desk.order(retry["submit"][0]["remark"], "US.KO", 1, 51, 96.43, status=2, filled=0,
               at=NOW + timedelta(minutes=16))
    third = desk.run(NOW + timedelta(minutes=30))      # the second listing was placed and is working
    assert "telegram_urgent" not in third and len(desk.events("order.unsent")) == 1


def test_a_price_just_above_the_zone_rests_a_day_order_at_the_plan_price(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 97.20          # 0.7% above the zone top: do not chase, rest at 96.50
    order = by_symbol(desk.run(NOW))["US.KO"]
    assert (order["side"], order["limit_price"], order["quantity"]) == ("buy", 96.5, 51)
    assert "resting buy at the plan's price" in order["why"]


def test_premarket_rests_stock_entries_from_the_live_book_and_runs_no_scalp(desk):
    early = datetime(2026, 11, 25, 13, 10, tzinfo=UTC)   # 08:10 ET
    desk.watch(ko_entry(early))
    desk.quotes["US.KO"] = 96.90
    desk.books["US.KO"] = (96.85, 96.95)
    desk.breakout("US.NVDA", early)
    report = desk.run(early)
    assert report["phase"] == "pre_market" and report["status"] == "ok", report
    assert [(r["symbol"], r["side"], r["limit_price"]) for r in report["submit"]] == [("US.KO", "buy", 96.5)]
    assert report["scalp"]["decisions"] == []


def test_a_closed_market_is_a_clean_skip(desk):
    holiday = datetime(2026, 11, 26, 15, 10, tzinfo=UTC)   # Thanksgiving
    report = desk.run(holiday)
    assert report["status"] == "skip" and "closed" in report["reason"] and report["submit"] == []


# --- the one hard rule and the reads ---------------------------------------------------------------------

def test_only_the_allowlisted_paper_account_can_ever_be_planned_for(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    live = desk.run(NOW, account_id="LIVE-9")           # a real account row: account_type 0
    assert live["status"] == "blocked" and "paper account" in live["reason"] and live["submit"] == []
    assert "LIVE-9" not in json.dumps(live)             # an account id is never echoed
    unknown = desk.run(NOW, account_id="SIM-OTHER")     # not in the broker's own list
    assert unknown["status"] == "blocked" and unknown["submit"] == []
    desk.account_type = 0                                # the broker no longer calls it a paper account
    assert desk.run(NOW)["status"] == "blocked"
    assert desk.events("order.requested") == []


def test_no_account_id_means_no_run(desk, monkeypatch):
    monkeypatch.delenv("TYCHE_ALLOWED_ACCOUNT_IDS", raising=False)
    desk.quotes["US.KO"] = 96.40
    report = desk.run(NOW, account_id=None)
    assert report["status"] == "blocked" and "TYCHE_ALLOWED_ACCOUNT_IDS" in report["reason"]


def test_missing_or_failed_reads_block_with_the_fix_in_plain_words(desk):
    desk.quotes["US.KO"] = 96.40
    directory = desk.write_reads(NOW)
    (directory / "orders.json").unlink()
    missing = desk.run(NOW, directory=directory)
    assert missing["status"] == "blocked" and "orders.json" in missing["reason"]
    (directory / "orders.json").write_text(json.dumps({"ret_code": 0, "data": {"orders": [
        {"order_id": "1", "symbol": "KO", "side": 1}]}}), encoding="utf-8")
    thin = desk.run(NOW, directory=directory)
    assert thin["status"] == "blocked" and "lacks qty" in thin["reason"]
    (directory / "cash.json").write_text(json.dumps({"ret_code": -5, "data": None}), encoding="utf-8")
    failed = desk.run(NOW, directory=directory)
    assert failed["status"] == "blocked" and "error -5" in failed["reason"] and "again" in failed["reason"]


def test_reads_lists_what_to_fetch_before_the_run(desk):
    desk.watch(ko_entry())
    report = run_cycle(directory=desk.drive / "nowhere", record=False, now=NOW, config_root=ROOT,
                       drive_root=desk.drive, reads_only=True)
    assert report["status"] == "ok" and report["watchlist"].endswith("watchlist.json")
    reads = report["reads"]
    assert reads["quotes"][0] == "US.KO" and set(load_config(ROOT).scalp.symbols) <= set(reads["quotes"])
    assert reads["books"] == [] and reads["bars"] == load_config(ROOT).scalp.symbols
    config = load_config(ROOT)
    early = reads_needed(config, Watchlist(as_of=TODAY, entries=[ko_entry()]), [], SessionPhase.PRE_MARKET, NOW)
    assert early["books"] == ["US.KO"] and early["bars"] == []   # premarket: the live book, no scalp


def test_an_option_setup_asks_for_the_contract_and_its_underlying(desk):
    call = "US.KO261218C97000"
    entry = ko_entry(symbol=call, setup_id="ko-call", premium_limit=1.8,
                     option=contract_from_symbol(call), exit_at=NOW + timedelta(days=2))
    reads = reads_needed(load_config(ROOT), Watchlist(as_of=TODAY, entries=[entry]), [], SessionPhase.MIDDAY, NOW)
    assert reads["quotes"][0] == "US.KO" and reads["quotes"][-1] == call and reads["books"] == [call]
    assert contract_from_symbol(call).strike == 97.0 and contract_from_symbol("US.KO") is None


# --- finding the ledger, the watchlist and the NAV references ---------------------------------------------

def test_the_ledger_is_the_longest_verified_journal_on_drive(tmp_path):
    drive = tmp_path / "drive"
    short, long = drive / "a" / "journal" / "events.jsonl", drive / "b" / "journal" / "events.jsonl"
    append_event(short, "x", {})
    for _ in range(3):
        append_event(long, "x", {})
    broken = drive / "c" / "journal" / "events.jsonl"
    broken.parent.mkdir(parents=True)
    broken.write_text(long.read_text(encoding="utf-8") * 2, encoding="utf-8")   # longer, but the chain is broken
    assert find_ledger(drive) == long
    assert find_ledger(tmp_path / "empty") is None


def test_orders_written_into_a_run_folder_copy_are_merged_back_into_the_ledger(desk):
    """A run that journaled into its own copy left the ledger blind to its reservation (24 Nov forks)."""
    fork = desk.drive / "2026-11-25-midday-1705" / "journal" / "events.jsonl"
    fork.parent.mkdir(parents=True)
    fork.write_text(desk.ledger.read_text(encoding="utf-8"), encoding="utf-8")
    request = {"request_id": "tyche-tac-fork1", "symbol": "US.KO", "side": "buy", "quantity": 51,
               "limit_price": 96.43, "strategy_id": "PB-002", "setup_id": "2026-11-25:ko-pullback",
               "authorization": {"kind": "envelope", "as_of": TODAY.isoformat()},
               "submit_before": (NOW + timedelta(minutes=10)).isoformat()}
    desk.clock.current = NOW - timedelta(minutes=3)
    append_event(fork, "order.requested", request)
    for _ in range(2):                    # the ledger moved on meanwhile, so it is still the longest chain
        append_event(desk.ledger, "run.started", {"run": "scalp"})
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    report = desk.run(NOW)
    assert any("merged into the ledger" in alert for alert in report["alerts"]), report
    merged = desk.events("order.requested")[0]["payload"]
    assert merged["request_id"] == "tyche-tac-fork1" and merged["merged_from"] == "2026-11-25-midday-1705"
    assert report["submit"] == []      # the fork's order is on its way: no second KO buy
    again = desk.run(NOW + timedelta(minutes=2))
    assert not any("merged into the ledger" in alert for alert in again["alerts"])   # healed once, not every run


def test_only_a_watchlist_dated_today_is_traded(desk, tmp_path):
    desk.watch(ko_entry(), as_of=TODAY - timedelta(days=1))
    desk.quotes["US.KO"] = 96.40
    stale = desk.run(NOW)
    assert stale["submit"] == [] and stale["watchlist"] is None
    assert any("no watchlist dated today" in alert for alert in stale["alerts"])
    # The newest research file a run saved today is found without anyone naming it.
    desk.watch(ko_entry(), where="2026-11-25-premarket-1305/research/watchlist.json")
    book, where, notes = find_watchlist(None, tmp_path, desk.drive, TODAY)
    assert notes == [] and where.endswith("research/watchlist.json") and book.entries[0].symbol == "US.KO"


def test_one_bad_setup_is_left_out_by_name_and_the_good_ones_still_trade(desk):
    """The file used to be all or nothing: one malformed option block silenced every stock setup."""
    good = ko_entry().model_dump(mode="json")
    no_stop = {**good, "symbol": "US.PG", "setup_id": "pg-pullback", "stop": 999.0}       # stop above the zone
    bad_option = {**good, "symbol": "US.KO261218C97000", "setup_id": "ko-call",
                  "option": {"underlying": "US.KO", "expiry": "2026-12-18", "right": "call", "strike": 97.0}}
    twin = {**good, "setup_id": "ko-second"}
    (desk.drive / "watchlist.json").write_text(json.dumps(
        {"as_of": TODAY.isoformat(), "entries": [good, no_stop, bad_option, twin]}), encoding="utf-8")
    desk.quotes["US.KO"] = 96.40
    report = desk.run(NOW)
    assert report["setups"] == ["US.KO"]
    assert [(r["symbol"], r["side"]) for r in report["submit"]] == [("US.KO", "buy")]
    left_out = [a for a in report["alerts"] if "left out" in a]
    assert len(left_out) == 3 and "US.PG" in left_out[0] and "ordering" in left_out[0]
    assert left_out[1] == "watchlist setup US.KO261218C97000 left out: option plan needs a maximum debit per share"
    assert "second setup for the same symbol" in left_out[2]
    # A file that is not a dated list at all is named with its reason, and nothing new is opened.
    (desk.drive / "watchlist.json").write_text("[]", encoding="utf-8")
    broken = desk.run(NOW + timedelta(minutes=20))
    assert broken["watchlist"] is None and any("cannot be read" in a for a in broken["alerts"])


def test_nav_references_fall_back_from_flags_to_drive_to_the_journal_to_the_start(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    events = [{"type": "nav.refs_updated", "payload": {"prior_close_nav": 98800.0, "high_water_nav": 100000.0}}]
    assert find_nav_refs(None, None, drive, events) == (98800.0, 100000.0, None)
    (drive / "nav-refs.json").write_text(json.dumps({"prior_close_nav": 99100.5, "high_water_nav": 100200.0}))
    assert find_nav_refs(None, None, drive, events) == (99100.5, 100200.0, None)
    assert find_nav_refs(98000.0, 101000.0, drive, events) == (98000.0, 101000.0, None)
    prior, high, note = find_nav_refs(None, None, tmp_path / "none", [])
    assert (prior, high) == (100000.0, 100000.0) and "nav-refs.json" in note


def test_the_cycle_keeps_the_nav_references_itself(desk):
    """Looking up yesterday's close was one of the hand steps. Now the last NAV a session saw is the
    next session's prior close, and the high-water mark only rises from such a close."""
    refs = desk.drive / "nav-refs.json"
    refs.write_text(json.dumps({"as_of": "2026-11-24", "prior_close_nav": 100000.0, "high_water_nav": 100000.0}))
    desk.cash = 98800.0                    # flat: the account is worth exactly what it closed at
    desk.quotes["US.KO"] = 96.40
    first = desk.run(NOW)
    assert (first["account"]["prior_close_nav"], first["account"]["high_water_nav"]) == (98800.0, 100000.0)
    saved = json.loads(refs.read_text())
    assert saved == {"as_of": "2026-11-25", "prior_close_nav": 98800.0, "high_water_nav": 100000.0,
                     "last_nav": 98800.0, "last_nav_at": NOW.isoformat()}
    assert [e["payload"]["prior_close_nav"] for e in desk.events("nav.refs_updated")] == [98800.0]

    desk.cash = 99900.0                    # later the same day: the references hold, only the last NAV moves
    desk.run(NOW + timedelta(hours=5))
    saved = json.loads(refs.read_text())
    assert (saved["prior_close_nav"], saved["last_nav"]) == (98800.0, 99900.0)
    assert len(desk.events("nav.refs_updated")) == 1

    friday = datetime(2026, 11, 27, 14, 37, tzinfo=UTC)
    desk.cash = 101500.0
    desk.hold_position("US.KO", 10, 96.0, 96.0)   # not flat: Wednesday's last NAV is the prior close
    desk.cash -= 960.0
    third = desk.run(friday, record=False)         # a dry run reads the same numbers and writes nothing
    assert (third["account"]["prior_close_nav"], third["account"]["high_water_nav"]) == (99900.0, 100000.0)
    assert json.loads(refs.read_text())["as_of"] == "2026-11-25"
    desk.run(friday)
    assert json.loads(refs.read_text())["prior_close_nav"] == 99900.0
    # A close above the mark raises it; the operator's flags still win over everything.
    refs.write_text(json.dumps({"as_of": "2026-11-27", "prior_close_nav": 99900.0, "high_water_nav": 100000.0,
                                "last_nav": 100700.0}))
    monday = datetime(2026, 11, 30, 15, 10, tzinfo=UTC)
    stock = json.loads(desk.stock_envelope.read_text())
    desk.stock_envelope.write_text(json.dumps({**stock, "valid_until": "2026-11-30"}))
    rolled = desk.run(monday, record=False)
    assert (rolled["account"]["prior_close_nav"], rolled["account"]["high_water_nav"]) == (100700.0, 100700.0)
    forced = desk.run(monday, record=False, prior_close_nav=99000.0, high_water_nav=102000.0)
    assert (forced["account"]["prior_close_nav"], forced["account"]["high_water_nav"]) == (99000.0, 102000.0)


# --- the scalp lane inside the cycle -----------------------------------------------------------------------

def test_the_broker_position_is_the_truth_about_scalp_lots(desk):
    # Shares of a scalp symbol nobody can explain are sold at once: the lane is flat by the close.
    desk.hold_position("US.AMD", 12, 409.0, 410.0)
    desk.cash = 100000.0 - 12 * 409.0
    desk.quotes["US.AMD"] = 410.0
    report = desk.run(NOW)
    sell = by_symbol(report)["US.AMD"]
    assert (sell["side"], sell["quantity"], sell["why"]) == ("sell", 12, "scalp flatten/timeout")
    assert any("no scalp lot explains" in alert for alert in report["alerts"])


def test_a_scalp_entry_still_unfilled_after_five_minutes_is_cancelled(desk):
    desk.quotes["US.NVDA"] = 100.0
    stale = desk.order("tyche-scl-old", "US.NVDA", 1, 40, 100.2, status=2, at=NOW - timedelta(minutes=14))
    fresh = desk.order("tyche-scl-new", "US.AMD", 1, 10, 400.0, status=2, at=NOW - timedelta(minutes=2))
    desk.quotes["US.AMD"] = 401.0
    report = desk.run(NOW)
    assert [c["order_id"] for c in report["cancel"]] == [stale["order_id"]]
    assert fresh["order_id"] not in json.dumps(report["cancel"])
    assert "Cancel every order under `cancel`" in report["instructions"]


def test_lots_still_open_at_the_flatten_time_raise_an_urgent_alert_and_a_sell(desk):
    late = datetime(2026, 11, 25, 20, 37, tzinfo=UTC)   # 15:37 ET, inside the last 25 minutes
    buy = desk.order("tyche-scl-entry", "US.NVDA", 1, 40, 100.0, fill_price=100.0, at=late - timedelta(minutes=10))
    desk.clock.current = late - timedelta(minutes=11)
    append_event(desk.ledger, "order.requested", {
        "request_id": "tyche-scl-entry", "symbol": "US.NVDA", "side": "buy", "quantity": 40, "limit_price": 100.0,
        "strategy_id": "PB-004", "authorization": {"kind": "envelope", "as_of": TODAY.isoformat()},
        "submit_before": (late - timedelta(minutes=5)).isoformat()})
    desk.hold_position("US.NVDA", 40, 100.0, 100.1)
    desk.cash = 96000.0
    desk.quotes["US.NVDA"] = 100.1
    report = desk.run(late)
    assert buy["order_id"] and by_symbol(report)["US.NVDA"]["why"] == "scalp flatten/timeout"
    assert report["telegram_urgent"].startswith("TYCHE URGENT (paper): scalp lot(s) still open")


# --- stock protection inside the cycle ----------------------------------------------------------------------

def test_a_resting_stock_buy_is_pulled_before_the_session_exit_time(desk):
    late = datetime(2026, 11, 25, 20, 37, tzinfo=UTC)   # next check 15:52 ET is past the 15:50 exit
    resting = desk.order("tyche-tac-rest", "US.KO", 1, 51, 96.5, status=2, at=late - timedelta(hours=4))
    desk.watch(ko_entry(late))
    desk.quotes["US.KO"] = 97.1
    report = desk.run(late)
    assert report["cancel"] == [{"order_id": resting["order_id"], "symbol": "US.KO",
                                 "why": "resting buy pulled before the session's exit time"}]
    assert report["submit"] == []


def test_on_the_half_day_a_stock_lot_leaves_before_the_one_oclock_close(desk):
    friday = datetime(2026, 11, 27, 17, 37, tzinfo=UTC)   # 12:37 ET; the market closes at 13:00
    stock = dict(json.loads(desk.stock_envelope.read_text()))
    desk.stock_envelope.write_text(json.dumps({**stock, "as_of": "2026-11-27"}), encoding="utf-8")
    plan = ko_entry(friday, exit_at=friday.replace(hour=20, minute=50))   # written for a normal day
    desk.watch(plan, as_of=friday.date())
    desk.clock.current = friday - timedelta(hours=3)
    append_event(desk.ledger, "order.requested", {
        "request_id": "tyche-tac-fri", "symbol": "US.KO", "side": "buy", "quantity": 51, "limit_price": 96.43,
        "strategy_id": "PB-002", "setup_id": "2026-11-27:ko-pullback",
        "protected_setup": plan.model_dump(mode="json"),
        "authorization": {"kind": "envelope", "as_of": "2026-11-27"},
        "submit_before": (friday - timedelta(hours=3) + timedelta(minutes=10)).isoformat()})
    desk.order("tyche-tac-fri", "US.KO", 1, 51, 96.43, fill_price=96.4, at=friday - timedelta(hours=3))
    desk.hold_position("US.KO", 51, 96.4, 96.9)
    desk.cash = 100000.0 - 51 * 96.4
    desk.quotes["US.KO"] = 96.9
    report = desk.run(friday)
    sell = by_symbol(report)["US.KO"]
    assert (sell["side"], sell["quantity"], sell["why"]) == ("sell", 51, "time exit before next scheduled check")


def test_cash_held_for_a_resting_buy_never_makes_the_account_look_unreconciled(desk):
    """Whether `balance` already includes the held cash is unknown; either way the next buy goes out."""
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    for cash, hold in ((100000.0, 5000.0), (95000.0, 5000.0)):   # balance includes the hold / excludes it
        desk.cash, desk.hold, desk.total_asset = cash, hold, 100000.0
        report = desk.run(NOW, record=False)
        assert [(r["symbol"], r["side"]) for r in report["preview"]] == [("US.KO", "buy")], report
        assert report["account"]["nav"] == 100000.0


def test_an_order_outside_the_standing_approval_is_named_not_sent(desk):
    desk.stock_envelope.write_text(json.dumps(envelope(*SCALP_LINES)), encoding="utf-8")   # no KO line
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    report = desk.run(NOW)
    assert report["submit"] == []
    assert any("US.KO buy 51" in alert and "no line for this order" in alert for alert in report["alerts"])


# --- the files the cards rely on ------------------------------------------------------------------------------

def test_the_standing_paper_approval_covers_every_tactical_symbol_through_friday():
    batch = ApprovalBatch.model_validate_json((ROOT / "data" / "standing-approval.json").read_text(encoding="utf-8"))
    config = load_config(ROOT)
    assert batch.valid_on(date(2026, 11, 25)) and batch.valid_on(date(2026, 11, 27))
    assert not batch.valid_on(date(2026, 11, 28)) and not batch.valid_on(date(2026, 11, 24))
    for symbol in config.tactical.symbols:
        buy, sell = batch.line_for(symbol, "buy"), batch.line_for(symbol, "sell")
        assert buy and sell and buy.setup_hash is None and sell.max_qty >= buy.max_qty, symbol
        ticker = symbol.removeprefix("US.")
        call = batch.line_for(f"US.{ticker}261218C100000", "buy", multiplier=100, underlying=symbol)
        assert call is not None and call.multiplier == 100 and call.symbol == symbol
        assert batch.line_for(f"US.{ticker}261218C100000", "sell", multiplier=100, underlying=symbol) is not None
    scalp = ApprovalBatch.model_validate_json((ROOT / "data" / "scalp-approvals.json").read_text(encoding="utf-8"))
    assert scalp.valid_on(date(2026, 11, 27))
    assert {line.symbol for line in scalp.orders} == set(config.scalp.symbols)
    # data/*.json is ignored by git unless named: a file that never reaches the cloud approves nothing.
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "!/data/standing-approval.json" in ignore and "!/data/scalp-approvals.json" in ignore


def test_the_command_line_prints_the_report_and_keeps_a_copy(desk, monkeypatch):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    directory = desk.write_reads(NOW)
    monkeypatch.setattr("tyche.cycle.now_utc", lambda: NOW)
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "SIM-TEST")
    monkeypatch.chdir(ROOT)
    runner = CliRunner()
    base = ["cycle", "--dir", str(directory), "--drive-root", str(desk.drive)]
    reads = runner.invoke(app, [*base, "--reads"])
    assert reads.exit_code == 0 and json.loads(reads.stdout)["reads"]["quotes"][0] == "US.KO"
    dry = runner.invoke(app, base)
    assert dry.exit_code == 0, dry.output
    report = json.loads(dry.stdout)
    assert report["preview"] and json.loads((directory / "cycle.json").read_text(encoding="utf-8")) == report
    assert json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))["nav"] == 100000.0   # for the desk page
    assert runner.invoke(app, [*base, "--record", "--at", NOW.isoformat()]).exit_code == 1   # a replay never records
    live = runner.invoke(app, [*base, "--record"])
    assert live.exit_code == 0 and (directory / "telegram.txt").read_text(encoding="utf-8").startswith("TYCHE 10:10 ET")
    # A blocked run says so once an hour per reason, not on every run of the night.
    empty = desk.drive / "empty"
    blocked = runner.invoke(app, ["cycle", "--dir", str(empty), "--drive-root", str(desk.drive), "--record"])
    answer = json.loads(blocked.stdout)
    assert blocked.exit_code == 1 and answer["status"] == "blocked" and "place no order" in answer["instructions"]
    assert (empty / "telegram-urgent.txt").read_text(encoding="utf-8").startswith("TYCHE BLOCKED (paper)")
    second = desk.drive / "empty-2"
    again = runner.invoke(app, ["cycle", "--dir", str(second), "--drive-root", str(desk.drive), "--record"])
    assert again.exit_code == 1 and "telegram_urgent" not in json.loads(again.stdout)
    assert not (second / "telegram-urgent.txt").exists()


def test_running_the_record_step_twice_in_one_folder_gives_the_same_list_again(desk, monkeypatch):
    """An agent that repeats the step must never be told "nothing to submit" about orders it still owes."""
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    directory = desk.write_reads(NOW)
    monkeypatch.setattr("tyche.cycle.now_utc", lambda: NOW)
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "SIM-TEST")
    monkeypatch.chdir(ROOT)
    runner = CliRunner()
    base = ["cycle", "--dir", str(directory), "--drive-root", str(desk.drive), "--record"]
    first = json.loads(runner.invoke(app, base).stdout)
    assert [row["symbol"] for row in first["submit"]] == ["US.KO"] and "already_recorded" not in first
    reserved = len(desk.events("order.requested"))
    again = runner.invoke(app, base)
    second = json.loads(again.stdout)
    assert again.exit_code == 0 and second["already_recorded"] is True
    assert second["submit"] == first["submit"] and "SAME answer" in second["instructions"]
    assert len(desk.events("order.requested")) == reserved          # nothing reserved twice
    assert (directory / "telegram.txt").is_file()


def test_a_problem_that_was_fixed_is_not_announced_afterwards(desk, monkeypatch):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    directory = desk.write_reads(NOW)
    monkeypatch.setattr("tyche.cycle.now_utc", lambda: NOW)
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "SIM-TEST")
    monkeypatch.chdir(ROOT)
    runner = CliRunner()
    base = ["cycle", "--dir", str(directory), "--drive-root", str(desk.drive), "--record"]
    cash = (directory / "cash.json").read_text(encoding="utf-8")
    (directory / "cash.json").write_text(json.dumps({"ret_code": -5, "msg": "glitch"}), encoding="utf-8")
    blocked = runner.invoke(app, base)
    assert blocked.exit_code == 1 and (directory / "telegram-urgent.txt").is_file()
    (directory / "cash.json").write_text(cash, encoding="utf-8")      # the read is taken again and saved
    read_at = (NOW - timedelta(seconds=30)).timestamp()
    os.utime(directory / "cash.json", (read_at, read_at))
    fixed = runner.invoke(app, base)
    assert fixed.exit_code == 0 and json.loads(fixed.stdout)["submit"]
    assert not (directory / "telegram-urgent.txt").exists()


def test_reads_stamped_a_little_ahead_of_this_clock_still_trade(desk):
    """Two machines, two clocks: a read 20 seconds "in the future" is a clock difference, not stale data."""
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    desk.breakout("US.NVDA", NOW + timedelta(minutes=1), minutes_ago=0)   # stamped with the minute it ends in
    directory = desk.write_reads(NOW + timedelta(seconds=110))      # files and quotes 20 s ahead of "now"
    report = desk.run(NOW, directory=directory)
    assert report["status"] == "ok" and set(by_symbol(report)) == {"US.KO", "US.NVDA"}, report
    # Further ahead than any clock difference is still refused: no entry on data from "the future".
    far = desk.write_reads(NOW + timedelta(hours=2))
    late = desk.run(NOW + timedelta(minutes=1), directory=far)
    assert late["submit"] == []


def test_a_setup_trades_without_the_bookkeeping_fields_and_with_a_time_zone_slip(desk):
    """The research gives levels and evidence; ids, dates and clock times are filled in, never a reason to sit out."""
    entry = json.loads(ko_entry().model_dump_json())
    for key in ("expiry", "exit_at", "setup_id"):
        entry.pop(key)
    entry["reviewed_at"] = (NOW + timedelta(hours=5)).isoformat()       # UTC digits typed with the New York offset
    path = desk.drive / "watchlist.json"
    path.write_text(json.dumps({"as_of": TODAY.isoformat(), "entries": [entry]}), encoding="utf-8")
    desk.quotes["US.KO"] = 96.40
    report = desk.run(NOW)
    assert [row["symbol"] for row in report["submit"]] == ["US.KO"], report
    assert any("time-zone slip" in alert for alert in report["alerts"])
    setup = desk.events("order.requested")[-1]["payload"]["protected_setup"]
    assert setup["setup_id"] == "ko-2026-11-25" and setup["expiry"] == "2026-11-25"
    assert setup["exit_at"].startswith("2026-11-25T15:50:00")           # the session's own exit time
    # The same file gives the same setup on the next run: the lot is recognised, not re-bought.
    desk.order(report["submit"][0]["remark"], "US.KO", 1, 51, 96.45)
    desk.hold_position("US.KO", 51, 96.45, 96.50)
    desk.quotes["US.KO"] = 96.50
    later = desk.run(NOW + timedelta(minutes=15))
    assert [row["side"] for row in later["submit"]] == ["sell"] and "take-profit" in later["submit"][0]["why"]
    # Evidence is never defaulted: a setup with no sources is named with its reason and not bought.
    bare = dict(entry, sources=[], symbol="US.PG")
    path.write_text(json.dumps({"as_of": TODAY.isoformat(), "entries": [bare]}), encoding="utf-8")
    desk.quotes["US.PG"] = 96.40
    third = desk.run(NOW + timedelta(minutes=30))
    verdict = next(row for row in third["stocks"]["decisions"] if row["symbol"] == "US.PG")
    assert verdict["action"] == "wait" and "cited evidence" in verdict["reason"]
    assert not [row for row in third["submit"] if row["symbol"] == "US.PG"]


def test_a_lot_is_sized_to_fit_the_approval_line_instead_of_being_refused(desk):
    """With no size from the research the kernel would ask for about 200 KO; the line allows 100 an order."""
    desk.watch(ko_entry(max_quantity=None))
    desk.quotes["US.KO"] = 96.40
    report = desk.run(NOW)
    order = by_symbol(report)["US.KO"]
    assert order["side"] == "buy" and order["quantity"] == 100, report["alerts"]
    assert not any("not sent" in alert for alert in report["alerts"])


def test_an_order_list_saved_as_pages_with_a_repeated_row_and_text_codes_is_still_read(desk):
    """How the list was saved is never a reason to sit out: pages are joined, a repeat counts once."""
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    first = desk.run(NOW)
    working = desk.order(first["submit"][0]["remark"], "US.KO", 1, 51, 96.45, status=2, filled=0)
    older = desk.order("manual", "US.PG", 1, 5, 150.0, at=NOW - timedelta(days=3))
    directory = desk.write_reads(NOW + timedelta(minutes=15))
    pages = [{"ret_code": 0, "data": {"orders": [dict(working, side="BUY", status="2")]},
              "pagination": {"has_more": True}},
             {"ret_code": 0, "data": {"orders": [working, older]}, "pagination": {"has_more": False}}]
    (directory / "orders.json").write_text(json.dumps(pages), encoding="utf-8")
    read_at = (NOW + timedelta(minutes=14)).timestamp()
    os.utime(directory / "orders.json", (read_at, read_at))
    report = desk.run(NOW + timedelta(minutes=15), directory=directory)
    assert report["status"] == "ok", report
    assert report["submit"] == []                                    # the working buy is seen, not repeated
    assert any("twice" in alert for alert in report["alerts"])
    assert report["journaled_receipts"] == ["order.submitted US.KO buy 51"]
    # A list whose last page says there is more is still refused: half an order list hides orders.
    (directory / "orders.json").write_text(json.dumps(pages[0]), encoding="utf-8")
    partial = desk.run(NOW + timedelta(minutes=16), directory=directory)
    assert partial["status"] == "blocked" and "all pages" in partial["reason"]


def test_a_run_with_nothing_to_price_is_a_quiet_ok_not_an_alarm(desk):
    """Before the open with no setups there is no quote to take: the run still journals and keeps the NAV."""
    early = datetime(2026, 11, 25, 14, 7, tzinfo=UTC)          # 09:07 New York
    directory = desk.write_reads(early)
    (directory / "quotes.json").unlink()                       # the read step had no symbol to quote
    report = desk.run(early, directory=directory)
    assert report["status"] == "ok" and report["submit"] == [] and "telegram_urgent" not in report
    assert report["account"]["nav"] == 100000.0
    # In the session the scalp symbols are expected, so a missing quote file is asked for by name.
    directory = desk.write_reads(NOW)
    (directory / "quotes.json").unlink()
    blocked = desk.run(NOW, directory=directory)
    assert blocked["status"] == "blocked" and "quotes.json" in blocked["reason"]


def test_one_unusable_quote_or_book_row_is_named_and_the_rest_still_trade(desk):
    desk.watch(ko_entry())
    desk.quotes["US.KO"] = 96.40
    desk.breakout("US.NVDA", NOW)
    directory = desk.write_reads(NOW)
    quotes = json.loads((directory / "quotes.json").read_text(encoding="utf-8"))
    quotes["data"]["quote_list"] += [{"code": "US.AMD", "data_time": None, "last_price": 541.0},
                                     {"code": "US.MU", "data_time": quotes["data"]["quote_list"][0]["data_time"],
                                      "last_price": 0}]
    (directory / "quotes.json").write_text(json.dumps(quotes), encoding="utf-8")
    (directory / "book-US.SMH.json").write_text(json.dumps(
        {"ret_code": 0, "data": {"code": "US.SMH", "books": [{"bid_list": [{"price": 350.0}]}]}}), encoding="utf-8")
    (directory / "book-US.AVGO.json").write_text(json.dumps({"ret_code": 0, "data": [{"books": []}]}), encoding="utf-8")
    read_at = (NOW - timedelta(seconds=90)).timestamp()
    for path in directory.iterdir():
        os.utime(path, (read_at, read_at))
    report = desk.run(NOW, directory=directory)
    assert report["status"] == "ok" and set(by_symbol(report)) == {"US.KO", "US.NVDA"}, report
    text = " | ".join(report["alerts"])
    assert "US.AMD: quote row unusable" in text and "US.MU: quote row unusable" in text
    assert "order-book row is unusable" in text
