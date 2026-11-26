"""Operator exit gate (`tyche exit-now`) and the 2026-11-24 rulings it relies on.

The 23 Nov close fire could not sell three approved exits: the lifecycle reserve refused on legacy
journal rows, the envelope lines had no lifecycle grant, and two zero-fill orders from 18-19 Nov
blocked their symbols forever. These tests pin the direct path that replaces that chain for exits.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

from typer.testing import CliRunner

from tyche.cli import app
from tyche.execution_state import expired_unfilled, order_finished, pending_intents
from tyche.journal import append_event, read_events
from tyche.lifecycle import LifecycleState
from tyche.lifecycle_cli import check_execution_journal
from tyche.market_calendar import ET

ACCOUNT = "PAPER-598"


def _today() -> date:
    return datetime.now(UTC).astimezone(ET).date()


def _setup(tmp_path, monkeypatch, *, env="paper", lines=None):
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", ACCOUNT)
    snap = {
        "account_id": ACCOUNT, "cash": 45680.12, "env": env, "account_type": 2, "market_id": 100,
        "source": "sim_list", "captured_at": datetime.now(UTC).isoformat(),
        "positions": [
            {"symbol": "US.SPY", "quantity": 28, "available_quantity": 28, "avg_cost": 731.54, "last_price": 724.1},
            {"symbol": "US.MSFT", "quantity": 39, "available_quantity": 39, "avg_cost": 503.33, "last_price": 497.4},
        ],
    }
    account = tmp_path / "snapshot.json"
    account.write_text(json.dumps(snap), encoding="utf-8")
    envelope = tmp_path / "approvals.json"
    envelope.write_text(json.dumps({
        "as_of": _today().isoformat(), "approved_at": datetime.now(UTC).isoformat(), "max_orders": 3,
        "orders": lines or [
            {"symbol": "US.SPY", "side": "sell", "max_qty": 28, "max_total_qty": 28, "limit_min": 690.0},
            {"symbol": "US.MSFT", "side": "sell", "max_qty": 39, "max_total_qty": 39, "limit_min": 474.0},
        ],
    }), encoding="utf-8")
    journal = tmp_path / "journal" / "events.jsonl"
    journal.parent.mkdir()
    # A legacy 18 Nov row with no request_id, exactly what blocked the lifecycle reserve.
    append_event(journal, "order.requested", {"symbol": "US.SPY", "side": "buy", "quantity": 28,
                                               "limit_price": 733.17, "remark": "tyche-2026-11-18"})
    return account, envelope, journal


def _run(account, envelope, journal, *extra, symbol="US.SPY", qty=28, limit=720.0):
    args = ["exit-now", "--account", str(account), "--symbol", symbol, "--qty", str(qty), "--limit", str(limit),
            "--path", str(envelope), "--journal", str(journal), *extra]
    result = CliRunner().invoke(app, args)
    return result.exit_code, json.loads(result.stdout)


def test_an_approved_sell_of_a_held_lot_reserves_once(tmp_path, monkeypatch):
    account, envelope, journal = _setup(tmp_path, monkeypatch)
    code, out = _run(account, envelope, journal)
    assert code == 0, out
    assert out["request_id"].startswith("tyche-exit-") and out["quantity"] == 28
    rows = [e["payload"] for e in read_events(journal) if e["type"] == "order.requested"]
    assert rows[-1]["request_id"] == out["request_id"]
    assert rows[-1]["authorization"]["kind"] == "envelope"
    # The approval is spent: a second reservation for the same lot is refused.
    code, out = _run(account, envelope, journal)
    assert code == 1 and "cumulative quantity" in out["reason"]


def test_a_live_account_is_always_refused(tmp_path, monkeypatch):
    account, envelope, journal = _setup(tmp_path, monkeypatch, env="live")
    code, out = _run(account, envelope, journal)
    assert code == 1 and "paper" in out["reason"]
    assert len(read_events(journal)) == 1


def test_more_than_held_below_floor_or_unapproved_is_refused(tmp_path, monkeypatch):
    account, envelope, journal = _setup(tmp_path, monkeypatch)
    assert _run(account, envelope, journal, qty=29)[0] == 1
    code, out = _run(account, envelope, journal, limit=680.0)
    assert code == 1 and "below approved floor" in out["reason"]
    code, out = _run(account, envelope, journal, symbol="US.EFA", qty=1, limit=99.0)
    assert code == 1
    assert len(read_events(journal)) == 1


def test_a_sell_already_working_at_the_broker_blocks_a_second(tmp_path, monkeypatch):
    account, envelope, journal = _setup(tmp_path, monkeypatch)
    now_us = int(datetime.now(UTC).timestamp() * 1_000_000)
    orders = tmp_path / "orders.json"
    orders.write_text(json.dumps({"ret_code": 0, "pagination": {"has_more": False}, "data": {"orders": [
        {"order_id": "9", "symbol": "MSFT", "side": 2, "qty": 39, "cum_qty": 0, "status": 2,
         "price": 480.0, "create_time": now_us}]}}), encoding="utf-8")
    code, out = _run(account, envelope, journal, "--orders", str(orders), symbol="US.MSFT", qty=39, limit=490.0)
    assert code == 1 and "already working" in out["reason"]
    code, _ = _run(account, envelope, journal, "--orders", str(orders))
    assert code == 0


def test_zero_fill_orders_from_a_past_session_are_finished():
    today = date(2026, 11, 24)
    nov19 = int(datetime(2026, 11, 19, 14, 0, tzinfo=UTC).timestamp() * 1_000_000)
    now = int(datetime(2026, 11, 24, 14, 0, tzinfo=UTC).timestamp() * 1_000_000)
    assert expired_unfilled(5, 83, 0, nov19, today)
    assert not expired_unfilled(2, 83, 0, nov19, today)          # still shown as working
    assert not expired_unfilled(5, 83, 10, nov19, today)         # partially filled: reconcile
    assert not expired_unfilled(5, 83, 0, now, today)            # today's session is not over
    assert not expired_unfilled(5, 83, 0, "garbage", today)      # unknown time stays blocking
    vnq = {"order_id": "3116597", "symbol": "VNQ", "side": 1, "qty": 83, "cum_qty": 0, "status": 5,
           "price": 94.98, "create_time": nov19}
    assert order_finished(vnq, today) and pending_intents([vnq], {}) == []


def test_identical_duplicate_request_ids_are_allowed_but_changed_orders_are_not():
    row = {"request_id": "same", "symbol": "US.NVDA", "side": "buy", "quantity": 10,
           "limit_price": 150.0, "setup_hash": "a" * 64}
    events = [{"type": "order.requested", "payload": row},
              {"type": "order.requested", "payload": dict(row)}]
    check_execution_journal(events, LifecycleState())
    for field, value in (("limit_price", 151.0), ("multiplier", 100),
                         ("option", {"underlying": "US.NVDA", "expiry": "2026-12-18", "right": "call", "strike": 150.0}),
                         ("setup_hash", "b" * 64), ("order_type", "market"),
                         ("submit_before", "2026-11-26T15:00:00+00:00")):
        changed = events + [{"type": "order.requested", "payload": {**row, field: value}}]
        try:
            check_execution_journal(changed, LifecycleState())
        except Exception as exc:  # noqa: BLE001 - PaperApiError
            assert "conflicting duplicate" in str(exc)
        else:
            raise AssertionError(f"a changed {field} with the same request id must block")


def test_legacy_rows_without_request_ids_no_longer_block_the_reserve_check():
    events = [{"type": "order.requested", "payload": {"symbol": "US.VNQ", "side": "buy", "remark": "x"}},
              {"type": "order.requested", "payload": {"request_id": "a", "symbol": "US.SPY"}}]
    check_execution_journal(events, LifecycleState())
    unsafe = events + [{"type": "order.requested", "payload": {"authorization": {"mode": "lifecycle"}}}]
    try:
        check_execution_journal(unsafe, LifecycleState())
    except Exception as exc:  # noqa: BLE001 - PaperApiError
        assert "unclassified" in str(exc)
    else:
        raise AssertionError("a lifecycle row without request_id must still block")
