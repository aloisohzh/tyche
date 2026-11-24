from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tyche.approvals import ApprovalBatch, authorize_order, envelope_usage
from tyche.cli import app
from tyche.journal import append_event

TODAY = date(2026, 11, 19)


def batch(**overrides) -> ApprovalBatch:
    base = {
        "as_of": TODAY,
        "approved_at": datetime(2026, 11, 19, 13, 30, tzinfo=UTC),
        "max_orders": 2,
        "orders": [
            {"symbol": "DBC", "side": "buy", "max_qty": 100, "limit_max": 29.5},
            {"symbol": "GLD", "side": "sell", "max_qty": 50, "limit_min": 300.0},
        ],
    }
    base.update(overrides)
    return ApprovalBatch.model_validate(base)


def check(b: ApprovalBatch, *, symbol="DBC", side="buy", qty=100, limit=29.4, used=0, today=TODAY):
    return authorize_order(b, symbol=symbol, side=side, qty=qty, limit=limit, today=today, used=used)


def test_within_envelope_authorized():
    ok, reason = check(batch())
    assert ok and "within operator envelope" in reason
    ok, _ = check(batch(), symbol="GLD", side="sell", qty=50, limit=301.0)
    assert ok


def test_wrong_day_denied():
    ok, reason = check(batch(), today=date(2026, 11, 20))
    assert not ok and "not valid today" in reason


def test_unapproved_line_denied():
    ok, reason = check(batch(), symbol="SPY")
    assert not ok and "no operator-approved line" in reason
    ok, _ = check(batch(), side="sell")  # DBC sell not approved, only buy
    assert not ok


def test_qty_and_price_bounds():
    assert not check(batch(), qty=101)[0]
    assert not check(batch(), limit=29.6)[0]  # buy above ceiling
    assert not check(batch(), symbol="GLD", side="sell", qty=10, limit=299.0)[0]  # sell below floor
    assert not check(batch(), limit=None)[0]  # market order never authorized
    assert not check(batch(), qty=0)[0]


def test_budget_exhaustion():
    ok, reason = check(batch(), used=2)
    assert not ok and "budget exhausted" in reason
    assert check(batch(), used=1)[0]


def test_schema_validation():
    with pytest.raises(ValidationError):
        batch(orders=[{"symbol": "DBC", "side": "buy", "max_qty": 100}])  # no limit_max
    with pytest.raises(ValidationError):
        batch(orders=[{"symbol": "GLD", "side": "sell", "max_qty": 50, "limit_max": 300.0}])
    with pytest.raises(ValidationError):
        batch(orders=[])
    with pytest.raises(ValidationError):
        batch(orders=[
            {"symbol": "DBC", "side": "buy", "max_qty": 100, "limit_max": 29.5},
            {"symbol": "DBC", "side": "buy", "max_qty": 50, "limit_max": 29.0},
        ])


def test_envelope_usage_counts_only_today_envelope_requests(tmp_path):
    journal = tmp_path / "events.jsonl"
    auth = {"kind": "envelope", "as_of": TODAY.isoformat()}
    append_event(journal, "order.requested", {"symbol": "DBC", "authorization": auth})
    append_event(journal, "order.submitted", {"symbol": "DBC", "authorization": auth})
    append_event(journal, "order.requested", {"symbol": "GLD"})  # confirmed path, no envelope
    append_event(journal, "order.requested", {
        "symbol": "EFA", "authorization": {"kind": "envelope", "as_of": "2026-11-18"},
    })
    assert envelope_usage(journal, TODAY) == 1
    assert envelope_usage(tmp_path / "missing.jsonl", TODAY) == 0


def _write_batch(tmp_path, b: ApprovalBatch):
    path = tmp_path / "approvals.json"
    path.write_text(b.model_dump_json(), encoding="utf-8")
    return path


def test_cli_approvals_valid(tmp_path):
    path = _write_batch(tmp_path, batch())
    result = CliRunner().invoke(app, ["approvals", "--path", str(path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["max_orders"] == 2 and "valid_today" in payload


def test_cli_approvals_missing_and_invalid(tmp_path):
    assert CliRunner().invoke(app, ["approvals", "--path", str(tmp_path / "nope.json")]).exit_code == 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"as_of": "2026-11-19", "max_orders": 1, "orders": []}))
    assert CliRunner().invoke(app, ["approvals", "--path", str(bad)]).exit_code == 1


def test_cli_authorize_pass_and_deny(tmp_path):
    path = _write_batch(tmp_path, batch())
    args = ["authorize", "--symbol", "DBC", "--side", "buy", "--qty", "100",
            "--limit", "29.4", "--path", str(path), "--at", "2026-11-19T14:05:00Z",
            "--journal", str(tmp_path / "events.jsonl")]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["authorized"] is True
    denied = CliRunner().invoke(app, [*args, "--qty", "101"])
    assert denied.exit_code == 1
    assert json.loads(denied.stdout)["authorized"] is False


def test_cli_authorize_budget_via_journal(tmp_path):
    path = _write_batch(tmp_path, batch(max_orders=1))
    journal = tmp_path / "events.jsonl"
    append_event(journal, "order.requested", {
        "symbol": "GLD", "authorization": {"kind": "envelope", "as_of": TODAY.isoformat()},
    })
    result = CliRunner().invoke(app, [
        "authorize", "--symbol", "DBC", "--side", "buy", "--qty", "10", "--limit", "29.0",
        "--path", str(path), "--journal", str(journal), "--at", "2026-11-19T14:05:00Z",
    ])
    assert result.exit_code == 1
    assert "budget exhausted" in json.loads(result.stdout)["reason"]


def test_cli_authorize_missing_envelope_denies(tmp_path):
    result = CliRunner().invoke(app, [
        "authorize", "--symbol", "DBC", "--side", "buy", "--qty", "10", "--limit", "29.0",
        "--path", str(tmp_path / "nope.json"), "--at", "2026-11-19T14:05:00Z",
    ])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["authorized"] is False

# ------------------------------------------------------------------ Ask me: journaled Telegram approvals


def _telegram_event(journal, n=1, **overrides):
    from tyche.approvals import TELEGRAM_APPROVAL_EVENT
    payload = {"as_of": TODAY.isoformat(), "ref": "abcd1234", "n": n, "symbol": "US.SPY", "side": "buy",
               "qty": 10, "limit": 672.4, "exit_floor": 665.5, "decided_at": "2026-11-19T14:10:00Z"}
    payload.update(overrides)
    return append_event(journal, TELEGRAM_APPROVAL_EVENT, payload)


def test_telegram_batch_is_exactly_the_approved_orders(tmp_path):
    from tyche.approvals import telegram_batch
    from tyche.journal import read_events
    journal = tmp_path / "events.jsonl"
    assert telegram_batch([], TODAY) is None
    _telegram_event(journal)
    _telegram_event(journal, n=2, symbol="US.QQQ", side="sell", qty=5, limit=500.0, exit_floor=None)
    _telegram_event(journal, n=3, as_of="2026-11-18", symbol="US.IWM")  # yesterday's yes is not today's
    append_event(journal, "approval.telegram", {"garbage": True})  # malformed rows are skipped, not guessed
    b = telegram_batch(read_events(journal), TODAY)
    assert b is not None and b.valid_on(TODAY) and b.approved_at.tzinfo is not None
    assert {(o.symbol, o.side) for o in b.orders} == {("US.SPY", "buy"), ("US.SPY", "sell"), ("US.QQQ", "sell")}
    assert b.max_orders == 3 and "Telegram" in b.approved_by
    # The buy is bound to its approved limit, the protective sell to the approved floor, both to the qty.
    assert authorize_order(b, symbol="US.SPY", side="buy", qty=10, limit=672.4, today=TODAY, used=0)[0]
    assert not authorize_order(b, symbol="US.SPY", side="buy", qty=11, limit=672.4, today=TODAY, used=0)[0]
    assert not authorize_order(b, symbol="US.SPY", side="buy", qty=10, limit=672.5, today=TODAY, used=0)[0]
    assert authorize_order(b, symbol="US.SPY", side="sell", qty=10, limit=665.5, today=TODAY, used=1)[0]
    assert not authorize_order(b, symbol="US.SPY", side="sell", qty=10, limit=665.4, today=TODAY, used=1)[0]
    assert not authorize_order(b, symbol="US.IWM", side="buy", qty=1, limit=1.0, today=TODAY, used=0)[0]


def test_two_approvals_for_the_same_order_add_up(tmp_path):
    from tyche.approvals import telegram_batch
    from tyche.journal import read_events
    journal = tmp_path / "events.jsonl"
    _telegram_event(journal, n=1, qty=10, limit=672.4)
    _telegram_event(journal, n=2, qty=5, limit=671.0)
    b = telegram_batch(read_events(journal), TODAY)
    line = b.line_for("US.SPY", "buy")
    assert line.max_qty == 10 and line.max_total_qty == 15 and line.limit_max == 671.0
    assert authorize_order(b, symbol="US.SPY", side="buy", qty=10, limit=671.0, today=TODAY, used=0)[0]
    assert not authorize_order(b, symbol="US.SPY", side="buy", qty=10, limit=671.0, today=TODAY, used=0, used_qty=10)[0]


def test_resolve_batch_prefers_todays_envelope_then_telegram_then_nothing(tmp_path):
    from tyche.approvals import MODE_ASK, MODE_BOUNDS, resolve_batch
    from tyche.journal import read_events
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    missing = tmp_path / "approvals.json"
    none, mode, why = resolve_batch(missing, read_events(journal), TODAY)
    assert none is None and mode == MODE_ASK and "no Telegram approval" in why
    _telegram_event(journal)
    asked, mode, why = resolve_batch(missing, read_events(journal), TODAY)
    assert asked is not None and mode == MODE_ASK and "no envelope" in why
    stale = _write_batch(tmp_path, batch(as_of=TODAY.replace(day=18)))
    asked_again, mode, why = resolve_batch(stale, read_events(journal), TODAY)
    assert mode == MODE_ASK and "not valid today" in why and asked_again.approved_by == asked.approved_by
    envelope = _write_batch(tmp_path, batch())
    bounds, mode, why = resolve_batch(envelope, read_events(journal), TODAY)
    assert mode == MODE_BOUNDS and bounds.max_orders == 2 and bounds.line_for("US.SPY", "buy") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    _, mode, why = resolve_batch(bad, read_events(journal), TODAY)
    assert mode == MODE_ASK and "envelope invalid" in why


def test_usage_counts_both_kinds_of_operator_yes(tmp_path):
    from tyche.approvals import envelope_totals
    from tyche.journal import read_events
    journal = tmp_path / "events.jsonl"
    for kind in ("envelope", "telegram", "lifecycle-ish"):
        append_event(journal, "order.requested", {"symbol": "US.SPY", "side": "buy", "quantity": 1, "limit_price": 10.0,
                                                  "authorization": {"kind": kind, "as_of": TODAY.isoformat()}})
    assert envelope_usage(journal, TODAY) == 2
    assert envelope_totals(read_events(journal), TODAY, "US.SPY", "buy")[0] == 2


def test_cli_authorize_passes_on_journaled_telegram_approval_without_envelope(tmp_path):
    journal = tmp_path / "events.jsonl"
    args = ["authorize", "--symbol", "US.SPY", "--side", "buy", "--qty", "10", "--limit", "672.4",
            "--path", str(tmp_path / "no-envelope.json"), "--at", "2026-11-19T14:15:00Z", "--journal", str(journal)]
    append_event(journal, "test", {})
    denied = CliRunner().invoke(app, args)
    assert denied.exit_code == 1 and "no Telegram approval journaled today" in json.loads(denied.stdout)["reason"]
    _telegram_event(journal)
    passed = CliRunner().invoke(app, args)
    assert passed.exit_code == 0, passed.output
    payload = json.loads(passed.stdout)
    assert payload["authorized"] and payload["mode"] == "ask" and payload["max_orders"] == 2
    assert CliRunner().invoke(app, [*args, "--qty", "11"]).exit_code == 1


def _sidecar(tmp_path, rows, ref="abcd1234"):
    proposals = tmp_path / "proposals.json"
    proposals.write_text("{}", encoding="utf-8")
    proposals.with_name("proposals.json.approved.json").write_text(
        json.dumps({"ref": ref, "approved": rows}), encoding="utf-8")
    return proposals


def test_cli_approve_telegram_journals_each_approved_order_once(tmp_path):
    from tyche.journal import read_events
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    order = {"symbol": "US.SPY", "side": "buy", "qty": 10, "limit": 672.4, "exit_floor": 665.5, "multiplier": 1}
    proposals = _sidecar(tmp_path, [
        {"n": 1, "decided_at": "2026-11-19T14:10:00Z", "symbol": "US.SPY", "order": order},
        {"n": 2, "decided_at": "2026-11-19T14:11:00Z", "symbol": "US.QQQ", "order": None},
        {"n": 3, "decided_at": "2026-11-19T14:12:00Z", "symbol": "US.IWM", "order": {**order, "qty": "ten"}},
    ])
    args = ["approve-telegram", str(proposals), "--journal", str(journal), "--at", "2026-11-19T14:15:00Z"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert [row["n"] for row in payload["journaled"]] == [1]
    assert {row["n"] for row in payload["skipped"]} == {2, 3}
    assert "no order block" in payload["skipped"][0]["why"]
    events = [e for e in read_events(journal) if e["type"] == "approval.telegram"]
    assert len(events) == 1 and events[0]["payload"]["ref"] == "abcd1234" and events[0]["payload"]["as_of"] == "2026-11-19"
    again = CliRunner().invoke(app, args)
    assert again.exit_code == 0 and json.loads(again.stdout)["journaled"][0]["already"] is True
    assert len([e for e in read_events(journal) if e["type"] == "approval.telegram"]) == 1
    # And the authorize gate now passes for exactly that order, with no envelope file anywhere.
    gate = CliRunner().invoke(app, ["authorize", "--symbol", "US.SPY", "--side", "buy", "--qty", "10", "--limit", "672.4",
                                    "--path", str(tmp_path / "approvals.json"), "--at", "2026-11-19T14:16:00Z",
                                    "--journal", str(journal)])
    assert gate.exit_code == 0, gate.output


def test_cli_approve_telegram_without_an_approval_file_journals_nothing(tmp_path):
    from tyche.journal import read_events
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    proposals = tmp_path / "proposals.json"
    proposals.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(app, ["approve-telegram", str(proposals), "--journal", str(journal)])
    assert result.exit_code == 1 and "approved nothing" in json.loads(result.stdout)["error"]
    assert len(read_events(journal)) == 1
    proposals.with_name("proposals.json.approved.json").write_text("not json", encoding="utf-8")
    broken = CliRunner().invoke(app, ["approve-telegram", str(proposals), "--journal", str(journal)])
    assert broken.exit_code == 1 and len(read_events(journal)) == 1


def test_standing_envelope_covers_its_window_only():
    standing = batch(valid_until=date(2026, 11, 21))
    assert not standing.valid_on(date(2026, 11, 18))
    assert all(standing.valid_on(date(2026, 11, d)) for d in (19, 20, 21))
    assert not standing.valid_on(date(2026, 11, 22))
    assert not batch().valid_on(date(2026, 11, 20))  # no valid_until: same day only
    with pytest.raises(ValidationError):
        batch(valid_until=date(2026, 11, 18))


def test_shipped_scalp_envelope_matches_the_scalp_lane():
    from pathlib import Path

    from tyche.config import load_config

    root = Path(__file__).resolve().parents[1]
    path = root / "data" / "scalp-approvals.json"
    if not path.is_file():
        pytest.skip("no standing scalp envelope in this checkout")
    envelope = ApprovalBatch.model_validate_json(path.read_text(encoding="utf-8"))
    assert envelope.valid_until is not None
    symbols = set(load_config(root).scalp.symbols)
    assert {(o.symbol, o.side) for o in envelope.orders} == {(s, side) for s in symbols for side in ("buy", "sell")}
