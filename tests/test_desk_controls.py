"""Desk operator controls: envelope arm/re-arm, kill-switch, broker reconcile, account map."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE_CHALLENGE_ID = "9999598"  # synthetic; masks to ***598
FAKE_PERSONAL_ID = "9999748"  # synthetic; masks to ***748

LINES = [
    {"symbol": "DBC", "side": "buy", "max_qty": 100, "limit_max": 29.5},
    {"symbol": "GLD", "side": "sell", "max_qty": 50, "limit_min": 300.0},
]


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("desk_server_controls_test", ROOT / "dashboard" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def desk(srv, tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    journal.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(srv, "JOURNAL", journal / "events.jsonl")
    monkeypatch.setattr(srv, "HALT", journal / "halt.json")
    monkeypatch.setattr(srv, "APPROVALS", data / "approvals.json")
    monkeypatch.setattr(srv, "_git_push_approvals", lambda message: (False, "git disabled in test"))
    return tmp_path


def test_arm_fresh_envelope(srv, desk):
    out = srv.arm_envelope({"max_orders": 2, "note": "test batch", "orders": LINES})
    assert out["ok"] and out["armed"]
    assert out["pushed"] is False and out["git_error"] == "git disabled in test"
    saved = json.loads(srv.APPROVALS.read_text(encoding="utf-8"))
    assert saved["as_of"] == datetime.now(srv.ET).date().isoformat()
    assert saved["approved_by"] == "operator (dashboard)"
    assert saved["max_orders"] == 2
    assert out["approvals"]["mode"] == "armed"
    assert out["approvals"]["auto_active"] is True


def test_arm_rejects_invalid_line(srv, desk):
    out = srv.arm_envelope({"max_orders": 1, "orders": [{"symbol": "DBC", "side": "buy", "max_qty": 100}]})
    assert out["ok"] is False
    assert "Envelope invalid" in out["error"]
    assert not srv.APPROVALS.exists()


def test_arm_reuse_last_requires_backup(srv, desk):
    out = srv.arm_envelope({"reuse_last": True})
    assert out["ok"] is False
    assert "No previous envelope" in out["error"]


def test_arm_reuse_last_falls_back_to_current(srv, desk):
    srv.arm_envelope({"max_orders": 2, "orders": LINES})
    out = srv.arm_envelope({"reuse_last": True})
    assert out["ok"] and out["armed"]
    saved = json.loads(srv.APPROVALS.read_text(encoding="utf-8"))
    assert "auto re-arm" in saved["approved_by"]
    assert saved["as_of"] == datetime.now(srv.ET).date().isoformat()


def test_arm_reuse_last_redates_backup(srv, desk):
    backup = srv.APPROVALS.with_name("approvals.disarmed.json")
    backup.write_text(json.dumps({
        "as_of": "2026-11-18", "approved_at": "2026-11-18T13:30:00Z", "approved_by": "operator",
        "max_orders": 2, "orders": LINES, "note": "original batch",
    }), encoding="utf-8")
    out = srv.arm_envelope({"reuse_last": True})
    assert out["ok"] and out["armed"]
    saved = json.loads(srv.APPROVALS.read_text(encoding="utf-8"))
    assert saved["as_of"] == datetime.now(srv.ET).date().isoformat()
    assert "auto re-arm" in saved["approved_by"]
    assert "re-armed for today" in saved["note"]
    assert [(o["symbol"], o["side"], o["max_qty"]) for o in saved["orders"]] == [
        ("DBC", "buy", 100), ("GLD", "sell", 50),
    ]
    assert saved["orders"][0]["limit_max"] == 29.5
    assert saved["orders"][1]["limit_min"] == 300.0


def test_halt_control_roundtrip_journals_transitions(srv, desk):
    out = srv.halt_control({"halted": True, "reason": "test halt"})
    assert out["ok"] and out["halt"]["halted"] is True
    assert json.loads(srv.HALT.read_text(encoding="utf-8"))["halted"] is True
    out = srv.halt_control({"halted": False})
    assert out["ok"] and out["halt"]["halted"] is False
    assert out["halt"]["reason"] == "operator resume via dashboard"
    types = [e["type"] for e in srv.read_events(srv.JOURNAL)]
    assert types == ["halt.engaged", "halt.released"]


def test_halt_control_rejects_non_bool(srv, desk):
    out = srv.halt_control({"halted": "yes"})
    assert out["ok"] is False
    assert not srv.HALT.exists()


def test_halt_overrides_armed_envelope(srv, desk):
    srv.arm_envelope({"max_orders": 2, "orders": LINES})
    out = srv.halt_control({"halted": True, "reason": "override test"})
    assert out["approvals"]["mode"] == "armed"
    assert out["approvals"]["auto_active"] is False
    assert out["approvals"]["halted"] is True


def test_cloud_snapshot_broker_reconcile(srv, tmp_path, monkeypatch):
    perf = tmp_path / "perf"
    run = perf / "2026-11-18-x"
    (run / "mcp").mkdir(parents=True)
    drill = tmp_path / "drill"
    drill.mkdir()
    (drill / "accounts.json").write_text(json.dumps({"data": {"accounts": [
        {"account_id": FAKE_CHALLENGE_ID, "account_type": 2, "market_id": 100},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(srv, "PERF_DIR", perf)
    monkeypatch.setattr(srv, "DRILL_DIR", drill)
    (run / "snapshot.json").write_text(json.dumps({
        "account_id": "[REDACTED]", "cash": 57360.28, "positions": [], "env": "paper",
        "account_type": 2, "market_id": 100, "gross_exposure": 34729.51, "nav": 92089.79,
    }), encoding="utf-8")
    out = srv.cloud_snapshot(srv.load_cloud_runs())
    assert out["order_hold"] is None and out["broker_total_asset"] is None
    (run / "cash.json").write_text(json.dumps({
        "ret_code": 0, "data": {"hold": "7884.33", "total_asset": "99974.12"},
    }), encoding="utf-8")
    out = srv.cloud_snapshot(srv.load_cloud_runs())
    assert out["order_hold"] == 7884.33
    assert out["broker_total_asset"] == 99974.12
    assert out["broker_total_asset"] == pytest.approx(out["nav"] + out["order_hold"])


def test_build_state_snapshots_map(srv, desk, monkeypatch):
    perf = desk / "perf"
    run = perf / "2026-11-18-cloud"
    (run / "mcp").mkdir(parents=True)
    drill = desk / "drill"
    drill.mkdir()
    (drill / "accounts.json").write_text(json.dumps({"data": {"accounts": [
        {"account_id": FAKE_CHALLENGE_ID, "account_type": 2, "market_id": 100},
        {"account_id": FAKE_PERSONAL_ID, "account_type": 1, "market_id": 100},
    ]}}), encoding="utf-8")
    (run / "snapshot.json").write_text(json.dumps({
        "account_id": "[REDACTED]", "cash": 57360.28, "positions": [], "env": "paper",
        "account_type": 2, "market_id": 100, "gross_exposure": 34729.51, "nav": 92089.79,
    }), encoding="utf-8")
    (drill / "snapshot.json").write_text(json.dumps({
        "account_id": FAKE_PERSONAL_ID, "cash": 900000.0, "positions": [], "env": "paper",
        "gross_exposure": 99101.96, "nav": 999101.96,
    }), encoding="utf-8")
    monkeypatch.setattr(srv, "PERF_DIR", perf)
    monkeypatch.setattr(srv, "DRILL_DIR", drill)
    state = srv.build_state()
    assert state["feed"]["primary_account"] == "***598"
    assert state["snapshot"]["account"] == "***598"
    assert set(state["snapshots"]) == {"***598", "***748"}
    assert state["snapshots"]["***748"]["nav"] == 999101.96
    blob = json.dumps(state)
    assert FAKE_CHALLENGE_ID not in blob and FAKE_PERSONAL_ID not in blob