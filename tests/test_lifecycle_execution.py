from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_lifecycle import NOW, ROOT, setup_case, write_case
from typer.testing import CliRunner

from tyche.cli import app
from tyche.journal import append_event, journal_lock, read_events


@pytest.fixture
def execution(tmp_path, monkeypatch):
    case = setup_case(price=94)
    paths = write_case(tmp_path, case)
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    args = ["lifecycle", "execute-exit", "--book", paths["book"], "--market", paths["market"],
            "--state", paths["state"], "--plan-id", case[0].plan_id,
            "--hash", case[0].fingerprint(), "--config-root", str(ROOT),
            "--journal", str(journal)]
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda: NOW)
    return args, case, paths, journal


def run(execution):
    return CliRunner().invoke(app, execution[0])


def test_exit_check_is_read_only_and_reports_the_approved_sell(execution):
    before = Path(execution[2]["state"]).read_bytes()
    result = run(execution)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["dry_run"] and not payload["submitted"] and not payload["attempted"]
    assert payload["decision"]["action"] == "sell"
    assert "Moomoo MCP" in payload["next"]
    assert Path(execution[2]["state"]).read_bytes() == before
    assert len(read_events(execution[3])) == 1


def test_exit_check_never_authorizes_an_entry(tmp_path, monkeypatch):
    case = setup_case(held=0)
    case[2].broker_nav = 99000
    paths = write_case(tmp_path, case)
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda: NOW)
    result = CliRunner().invoke(app, [
        "lifecycle", "execute-exit", "--book", paths["book"], "--market", paths["market"],
        "--state", paths["state"], "--plan-id", case[0].plan_id,
        "--hash", case[0].fingerprint(), "--config-root", str(ROOT), "--journal", str(journal),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["decision"]["action"] == "buy"
    assert not payload["decision"]["authorized"]


@pytest.mark.parametrize("mode", ["missing_book", "invalidated", "target", "deadline"])
def test_approved_protection_survives_research_gaps(execution, mode):
    _, case, paths, _ = execution
    if mode == "missing_book":
        Path(paths["book"]).unlink()
    elif mode == "invalidated":
        case[1].reviews[0].verdict = "invalidated"
        Path(paths["book"]).write_text(case[1].model_dump_json())
    elif mode == "target":
        case[2].quotes[0].last = 110
        Path(paths["market"]).write_text(case[2].model_dump_json())
    else:
        case[3].latched_exits[case[0].fingerprint()] = "holding_deadline"
        Path(paths["state"]).write_text(case[3].model_dump_json())
    result = run(execution)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert not payload["submitted"]
    assert payload["decision"]["action"] == "sell"


def test_halt_does_not_disable_an_approved_protective_sell(execution):
    from tyche.halt import set_halt
    set_halt(execution[3].parent, True, "synthetic halt")
    result = run(execution)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["decision"]["action"] == "sell"


def test_journal_reservation_without_state_is_rejected(execution):
    append_event(execution[3], "order.requested", {
        "request_id": "orphan", "plan_hash": execution[1][0].fingerprint(),
        "account_hash": "0" * 64, "symbol": "US.SPY", "side": "sell",
        "quantity": 10, "limit_price": 93.72,
        "authorization": {"mode": "lifecycle", "plan_hash": execution[1][0].fingerprint()},
    })
    result = run(execution)
    assert result.exit_code == 1
    assert "missing from lifecycle state" in result.stdout


@pytest.mark.parametrize("mutation", ["journal_pending", "journal_rollback", "competition_cap",
                                      "available", "nav_mismatch", "state_missing"])
def test_mcp_reservation_enforces_execution_guards(execution, mutation):
    args, case, paths, journal = execution
    market = case[2]
    if mutation in {"journal_pending", "journal_rollback", "competition_cap"}:
        count = case[4].risk.competition_order_cap if mutation == "competition_cap" else 1
        for index in range(count):
            append_event(journal, "order.requested", {
                "request_id": f"legacy-{index}", "symbol": "US.EFA" if count > 1 else "US.SPY",
                "side": "buy", "quantity": 1, "limit_price": 100,
                "authorization": {"as_of": NOW.date().isoformat(),
                                  "mode": "lifecycle" if mutation == "journal_rollback" else "tactical"},
            })
    elif mutation == "available":
        market.available["US.SPY"] = 4
    elif mutation == "nav_mismatch":
        market.snapshot.cash += 1000
    else:
        Path(paths["state"]).unlink()
    Path(paths["market"]).write_text(market.model_dump_json())
    result = CliRunner().invoke(app, ["lifecycle", "reserve", *args[2:]])
    assert result.exit_code == 1, result.output
    assert not json.loads(result.stdout).get("authorized")


def test_mcp_reservation_holds_journal_lock(execution, monkeypatch):
    from tyche import lifecycle_cli
    original = lifecycle_cli.append_locked

    def append(path, kind, payload):
        with pytest.raises((RuntimeError, OSError)), journal_lock(path):
            pytest.fail("reservation and journal write must share a lock")
        return original(path, kind, payload)

    monkeypatch.setattr(lifecycle_cli, "append_locked", append)
    result = CliRunner().invoke(app, ["lifecycle", "reserve", *execution[0][2:]])
    assert result.exit_code == 0, result.output
