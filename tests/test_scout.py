"""Continuous scout loop: feed freshness, deterministic cadence floor, confirmations."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from tyche.config import TacticalConfig, load_config
from tyche.journal import append_event, read_events
from tyche.tactical_cli import scout_cycle
from tyche.watchlist import Factor, Watchlist, WatchlistEntry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 19, 15, 5, tzinfo=UTC)

ACCOUNTS = {"ret_code": 0, "data": {"accounts": [
    {"account_id": "SIM-TEST", "account_title": "Challenge", "account_type": 2, "market_id": 100}]}}
CASH = {"ret_code": 0, "data": {"balance": "100000.0", "hold": "0", "total_asset": "100000.0"}}
POSITIONS = {"ret_code": 0, "data": {"positions": []}}


def write_feed(directory: Path, stamp: datetime, *, last=150.0, bid=149.95, ask=150.05) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ms = int(stamp.timestamp() * 1000)
    payloads = {
        "accounts.json": ACCOUNTS,
        "cash.json": CASH,
        "positions.json": POSITIONS,
        "quotes.json": {"ret_code": 0, "data": {"quote_list": [
            {"code": "US.NVDA", "data_time": ms, "last_price": last, "volume": 1000,
             "sec_status": "NORMAL", "suspension": False}]}},
        "book-US.NVDA.json": {"ret_code": 0, "data": [{"code": "US.NVDA", "books": [
            {"exchange": "NASDAQ", "exchange_data_time_ms": ms,
             "bid_list": [{"price": bid, "volume": 100}], "ask_list": [{"price": ask, "volume": 100}]}]}]},
    }
    for name, payload in payloads.items():
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")
    for path in directory.glob("*.json"):
        os.utime(path, (stamp.timestamp(), stamp.timestamp()))
    return directory


def write_book(tmp_path: Path) -> Path:
    entry = WatchlistEntry(symbol="US.NVDA", sleeve="equity", strategy="catalyst reclaim",
                           setup_id="scout-1", entry_low=149, entry_high=151, stop=145, target=165,
                           expiry=NOW.date(), thesis="Synthetic catalyst thesis",
                           catalyst="synthetic earnings surprise", sources=["https://example.test/earnings"],
                           reviewed_at=NOW, market_cap_usd=1e12,
                           exit_at=NOW.replace(hour=20, minute=45),
                           factors=[Factor(name="reclaim", axis="technical", state="pass", why="held 150"),
                                    Factor(name="guide", axis="fundamental", state="pass", why="raised")])
    book = Watchlist(as_of=NOW.date(), entries=[entry])
    path = tmp_path / "book.json"
    path.write_text(book.model_dump_json(), encoding="utf-8")
    return path


def run_cycle(tmp_path, monkeypatch, now, *, feed_stamp=None, journal, book, config):
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda _: config)
    feed = write_feed(tmp_path / "feed", feed_stamp or now)
    orders = tmp_path / "orders.json"
    orders.write_text(json.dumps({"ret_code": 0, "data": {"orders": []}}), encoding="utf-8")
    return scout_cycle(feed, feed, book, orders, journal, ROOT, "SIM-TEST",
                       100000.0, 100000.0, now)


def test_cadence_floor_allows_five_seconds():
    assert TacticalConfig(monitor_interval_seconds=5).monitor_interval_seconds == 5
    with pytest.raises(ValidationError):
        TacticalConfig(monitor_interval_seconds=4)


def test_scout_cycle_skips_stale_feed_and_leaves_no_state(tmp_path, monkeypatch):
    journal = tmp_path / "events.jsonl"
    config = load_config(ROOT)
    config.tactical.max_snapshot_age_seconds = 120  # the daemon's own clock, not the agent runs'
    line = run_cycle(tmp_path, monkeypatch, NOW, feed_stamp=NOW - timedelta(minutes=10),
                     journal=journal, book=write_book(tmp_path), config=config)
    assert "stale" in line["skipped"]
    assert line["interval_seconds"] == config.tactical.monitor_interval_seconds
    assert not journal.exists()


def test_scout_cycle_confirms_across_feed_refreshes_then_freezes_order(tmp_path, monkeypatch):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    book = write_book(tmp_path)
    config = load_config(ROOT)
    config.tactical.enabled = True
    # Pin the lane universe to the fixture symbol so tests do not track live config.
    config.tactical.symbols = ["US.NVDA"]
    config.tactical.etf_symbols = []
    config.tactical.monitor_interval_seconds = 30
    config.tactical.max_confirmation_ticks = 5  # this drill is about the two-quote confirmation

    first = run_cycle(tmp_path, monkeypatch, NOW, journal=journal, book=book, config=config)
    assert not first["orders"], first
    assert first["decisions"][0]["reason"] == "awaiting distinct fresh quote confirmations"

    later = NOW + timedelta(seconds=30)
    second = run_cycle(tmp_path, monkeypatch, later, journal=journal, book=book, config=config)
    assert len(second["orders"]) == 1, second
    order = second["orders"][0]
    assert order["intent"]["side"] == "buy"
    assert order["intent"]["limit_price"] == 150.05
    assert order["setup_hash"] and order["order_hash"]
    assert not second["submitted"]
    events = read_events(journal)
    assert [e["type"] for e in events].count("tactical.monitor") == 2
