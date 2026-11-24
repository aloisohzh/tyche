"""Desk operator controls: envelope arm/re-arm, kill-switch, broker reconcile, account map."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

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
    monkeypatch.setattr(srv, "REPO_HALT", data / "halt.json")
    effective_halt = srv.effective_halt
    monkeypatch.setattr(srv, "effective_halt", lambda journal_dir, root: effective_halt(journal_dir, tmp_path))
    monkeypatch.setattr(srv, "APPROVALS", data / "approvals.json")
    monkeypatch.setattr(srv, "APPROVAL_DRAFT", data / "approvals.proposed.json")
    monkeypatch.setattr(srv, "DATA_DIR", data)
    monkeypatch.setattr(srv, "_git_push_approvals", lambda message: (False, "git disabled in test"))
    monkeypatch.setattr(srv, "_git_push_paths", lambda message, paths: (False, "git disabled in test"))
    return tmp_path


def test_arm_fresh_envelope(srv, desk):
    out = srv.arm_envelope({"max_orders": 2, "note": "test batch", "orders": LINES})
    assert out["ok"] and out["armed"]
    assert out["pushed"] is False and out["git_error"] == "git disabled in test"
    saved = json.loads(srv.APPROVALS.read_text(encoding="utf-8"))
    assert saved["as_of"] == datetime.now(srv.ET).date().isoformat()
    assert saved["approved_by"] == "operator (dashboard)"
    assert saved["max_orders"] == 2
    assert out["approvals"]["mode"] == "bounds"
    assert out["approvals"]["auto_active"] is True


def test_arm_rejects_invalid_line(srv, desk):
    out = srv.arm_envelope({"max_orders": 1, "orders": [{"symbol": "DBC", "side": "buy", "max_qty": 100}]})
    assert out["ok"] is False
    assert "Envelope invalid" in out["error"]
    assert not srv.APPROVALS.exists()


def test_arm_reuse_last_requires_backup(srv, desk):
    out = srv.arm_envelope({"reuse_last": True})
    assert out["ok"] is False
    assert "No previous bounds" in out["error"]


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
    assert out["approvals"]["mode"] == "bounds"
    assert out["approvals"]["auto_active"] is False
    assert out["approvals"]["halted"] is True


def test_halt_control_writes_shared_repo_flag(srv, desk, monkeypatch):
    perf = desk / "perf"
    perf.mkdir()
    drill = desk / "drill"
    drill.mkdir()
    monkeypatch.setattr(srv, "PERF_DIR", perf)
    monkeypatch.setattr(srv, "DRILL_DIR", drill)
    out = srv.halt_control({"halted": True, "reason": "cloud reach"})
    assert out["ok"] and out["pushed"] is False
    shared = json.loads(srv.REPO_HALT.read_text(encoding="utf-8"))
    assert shared["halted"] is True and shared["set_by"] == "operator (dashboard)"
    state = srv.build_state()
    assert state["halt"]["halted"] is True and state["halt"]["source"] in {"journal", "repo"}
    srv.halt_control({"halted": False})
    assert json.loads(srv.REPO_HALT.read_text(encoding="utf-8"))["halted"] is False
    assert srv.build_state()["halt"]["halted"] is False


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
    # The account value is the broker's total: cash held for a resting order still counts.
    assert out["nav"] == 99974.12


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


# ------------------------------------------------------------------ exit-note drafting
PLAN = {
    "symbol": "US.MSFT", "sleeve": "equity", "strategy": "PB-002 tactical break",
    "entry_low": 490.0, "entry_high": 495.0, "stop": 470.0, "target": 540.0,
    "expiry": "2026-12-31", "direction": "bullish", "setup_id": "TAC-20261119-MSFT-L4",
}
SETUP_HASH = "a9a899f896ac0353cd85043aba118e3fda5d315477fcdabebe07a0c079199d25"


def feed_desk(srv, monkeypatch, rows, *, env="paper"):
    """Put one paper book on the desk and freeze the collar the drafter reads."""
    monkeypatch.setattr(srv, "live_broker_snapshot", lambda: (None, None))
    monkeypatch.setattr(srv, "broker_capture", lambda: None)
    monkeypatch.setattr(srv, "load_cloud_runs", list)
    monkeypatch.setattr(srv, "cloud_snapshot", lambda runs: None)
    monkeypatch.setattr(srv, "load_snapshot", lambda: {
        "account": "***598", "env": env, "cash": 10_000.0, "positions": rows,
    })
    risk = SimpleNamespace(exit_collar_pct=0.05, max_orders_per_day=6)
    monkeypatch.setattr(srv, "load_config",
                        lambda root: SimpleNamespace(risk=risk, tactical=SimpleNamespace(options_enabled=False)))


def row(symbol="US.MSFT", qty=39, cost=480.0, last=500.0):
    return {"symbol": symbol, "quantity": qty, "avg_cost": cost, "last_price": last}


def journaled_entry(srv, **payload):
    srv.append_event(srv.JOURNAL, "order.requested",
                     {"symbol": "US.MSFT", "side": "buy", "quantity": 39, "setup_hash": SETUP_HASH,
                      "strategy_id": "PB-002", "protected_setup": PLAN, **payload})


def test_propose_drafts_from_what_the_desk_is_showing(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row()])
    out = srv.propose_envelope()
    assert out["ok"] is True
    line = out["proposal"]["lines"][0]
    assert (line["symbol"], line["max_qty"], line["bound"]) == ("US.MSFT", 39, True)
    assert line["limit_min"] == pytest.approx(446.5) and line["source"] == "journal_contract"
    assert out["proposal"]["draft_file"].endswith("approvals.proposed.json")
    assert srv.APPROVAL_DRAFT.is_file()
    # Drafting must not touch the file the executor reads.
    assert not srv.APPROVALS.exists()
    assert out["approvals"]["mode"] == "ask"


def test_propose_with_an_empty_book_drafts_nothing(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [])
    out = srv.propose_envelope()
    assert out["ok"] is True and out["proposal"]["proposed"] == 0
    assert not srv.APPROVAL_DRAFT.exists() and not srv.APPROVALS.exists()


def test_propose_refuses_a_broken_journal(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row()])
    lines = srv.JOURNAL.read_text(encoding="utf-8").splitlines()
    srv.JOURNAL.write_text(lines[0].replace(SETUP_HASH, "0" * 64) + "\n", encoding="utf-8")
    out = srv.propose_envelope()
    assert out["ok"] is False and "journal integrity" in out["error"]
    assert not srv.APPROVAL_DRAFT.exists()


def test_propose_refuses_a_non_paper_feed(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row()], env="live")
    out = srv.propose_envelope()
    assert out["ok"] is False and "paper-only" in out["error"]


def test_propose_refuses_options_and_reports_them(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row(), row("US.MSFT261231C460000"), row("US.SPY", 21)])
    out = srv.propose_envelope()
    refused = {r["symbol"]: r["why"] for r in out["proposal"]["skipped"]}
    assert "verified contract" in refused["US.MSFT261231C460000"]
    assert "no journaled stop" in refused["US.SPY"]
    assert out["proposal"]["proposed"] == 1
    assert [line["symbol"] for line in out["proposal"]["lines"]] == ["US.MSFT"]


def test_duplicate_feed_rows_are_never_merged_into_one_line(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row(), row(qty=10)])
    out = srv.propose_envelope()
    assert out["proposal"]["proposed"] == 1
    assert "duplicate position row" in out["proposal"]["skipped"][0]["why"]


def test_arm_from_draft_is_the_only_writer_of_the_envelope(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row()])
    srv.propose_envelope()
    out = srv.arm_envelope({"use_draft": True})
    assert out["ok"] and out["armed"] and out["pushed"] is False
    saved = json.loads(srv.APPROVALS.read_text(encoding="utf-8"))
    today = datetime.now(srv.ET).date().isoformat()
    assert saved["as_of"] == today and saved["approved_by"] == "operator (dashboard, drafted from open positions)"
    assert not saved["note"].startswith("DRAFT ONLY") and "armed from the open-position draft" in saved["note"]
    assert saved["orders"][0]["setup_hash"] == SETUP_HASH  # bound to the journaled setup, unedited
    assert saved["orders"][0]["limit_min"] == pytest.approx(446.5)
    assert out["approvals"]["mode"] == "bounds" and out["approvals"]["auto_active"] is True


def test_arm_from_draft_refuses_a_stale_note(srv, desk):
    srv.APPROVAL_DRAFT.write_text(json.dumps({
        "as_of": "2026-11-18", "approved_at": "2026-11-18T13:30:00Z", "approved_by": "kernel draft",
        "max_orders": 3, "orders": [{"symbol": "US.MSFT", "side": "sell", "max_qty": 39, "limit_min": 400.0}],
    }), encoding="utf-8")
    out = srv.arm_envelope({"use_draft": True})
    assert out["ok"] is False and "not today" in out["error"]
    assert not srv.APPROVALS.exists()


def test_arm_without_a_draft_or_without_the_desk_book(srv, desk):
    assert srv.arm_envelope({"use_draft": True})["ok"] is False
    assert "Propose first" in srv.arm_envelope({"use_draft": True})["error"]


def test_an_empty_proposal_clears_a_stale_draft(srv, desk, monkeypatch):
    feed_desk(srv, monkeypatch, [row()])
    srv.APPROVAL_DRAFT.write_text(json.dumps({"as_of": "2026-11-18", "orders": []}), encoding="utf-8")
    out = srv.propose_envelope()
    assert out["proposal"]["proposed"] == 0 and out["proposal"]["draft_cleared"] is True
    assert not srv.APPROVAL_DRAFT.exists()
    assert out["approvals"]["draft"] is None


def test_desk_state_shows_the_waiting_draft(srv, desk, monkeypatch):
    journaled_entry(srv)
    feed_desk(srv, monkeypatch, [row()])
    srv.propose_envelope()
    draft = srv.build_approvals()["draft"]
    assert draft["dated_today"] is True and draft["collar_pct"] == 0.05
    assert draft["lines"][0]["symbol"] == "US.MSFT" and draft["lines"][0]["bound"] is True
    assert draft["refused"] == []