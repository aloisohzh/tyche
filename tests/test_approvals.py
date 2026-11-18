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