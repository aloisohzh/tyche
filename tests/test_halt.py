from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tyche.cli import app
from tyche.config import RiskPolicy
from tyche.halt import (
    effective_halt,
    is_halted,
    read_halt,
    read_repo_halt,
    repo_halt_path,
    set_halt,
)
from tyche.journal import read_events, verify_chain
from tyche.models import AccountSnapshot, OrderIntent, Position, Side
from tyche.risk import RiskState, evaluate_intent


def test_set_and_read_halt(tmp_path: Path) -> None:
    assert not is_halted(tmp_path)
    set_halt(tmp_path, True, "drill")
    assert is_halted(tmp_path)
    assert read_halt(tmp_path)["reason"] == "drill"
    set_halt(tmp_path, False, "resume")
    assert not is_halted(tmp_path)


def test_halt_drill_blocks_buys_allows_sells(tmp_path: Path) -> None:
    set_halt(tmp_path, True, "drill")
    snapshot = AccountSnapshot(
        account_id="SIM-DEMO-US",
        cash=94_000.0,
        positions=[Position(symbol="US.SPY", quantity=10, avg_cost=500, last_price=600)],
    )
    state = RiskState(
        nav=snapshot.nav, prior_close_nav=snapshot.nav, halted=is_halted(tmp_path)
    )
    policy = RiskPolicy()
    buy = OrderIntent(symbol="US.SPY", side=Side.BUY, quantity=2, limit_price=600.0, reason="drill")
    sell = OrderIntent(symbol="US.SPY", side=Side.SELL, quantity=5, limit_price=600.0, reason="drill")
    buy_verdict = evaluate_intent(buy, snapshot, policy, state, 600.0, {"US.SPY"}, {"US.SPY": "equity"})
    sell_verdict = evaluate_intent(sell, snapshot, policy, state, 600.0, {"US.SPY"}, {"US.SPY": "equity"})
    assert not buy_verdict.allowed
    assert any(b.rule == "halt.active" for b in buy_verdict.breaches)
    assert sell_verdict.allowed


def test_halt_resume_commands_journal(tmp_path: Path) -> None:
    journal = tmp_path / "events.jsonl"
    engaged = CliRunner().invoke(app, ["halt", "--reason", "drill", "--journal", str(journal)])
    assert engaged.exit_code == 0
    assert is_halted(tmp_path)
    released = CliRunner().invoke(app, ["resume", "--journal", str(journal)])
    assert released.exit_code == 0
    assert not is_halted(tmp_path)
    types = [event["type"] for event in read_events(journal)]
    assert types == ["halt.engaged", "halt.released"]
    ok, _, _ = verify_chain(journal)
    assert ok


def _write_repo_halt(root: Path, halted: bool, ts: str, reason: str = "cloud") -> None:
    path = repo_halt_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"halted": halted, "reason": reason, "ts": ts}), encoding="utf-8")


def test_effective_halt_repo_flag_alone_blocks(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    _write_repo_halt(tmp_path, True, "2026-11-19T02:00:00+00:00")
    eff = effective_halt(journal, tmp_path)
    assert eff["halted"] is True and eff["source"] == "repo"
    assert read_repo_halt(tmp_path)["halted"] is True


def test_effective_halt_newest_active_wins(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    set_halt(journal, True, "older desk halt")
    older = read_halt(journal)["ts"]
    _write_repo_halt(tmp_path, True, "2099-01-01T00:00:00+00:00", "newer cloud halt")
    eff = effective_halt(journal, tmp_path)
    assert eff["halted"] is True and eff["source"] == "repo"
    assert eff["reason"] == "newer cloud halt" and eff["ts"] > older


def test_effective_halt_or_semantics_fail_safe(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    set_halt(journal, True, "desk engaged")
    _write_repo_halt(tmp_path, False, "2099-01-01T00:00:00+00:00")
    eff = effective_halt(journal, tmp_path)
    assert eff["halted"] is True and eff["source"] == "journal"


def test_effective_halt_both_released_clears(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    set_halt(journal, False, "resume")
    _write_repo_halt(tmp_path, False, "2099-01-01T00:00:00+00:00")
    eff = effective_halt(journal, tmp_path)
    assert eff["halted"] is False and eff["source"] == "repo"


def test_cli_halt_writes_shared_repo_flag(tmp_path: Path) -> None:
    journal = tmp_path / "journal" / "events.jsonl"
    journal.parent.mkdir()
    result = CliRunner().invoke(app, ["halt", "--reason", "drill", "--journal", str(journal)])
    assert result.exit_code == 0
    root = journal.resolve().parent.parent
    shared = read_repo_halt(root)
    assert shared["halted"] is True and shared["set_by"] == "operator (CLI)"
    assert effective_halt(journal.parent, root)["halted"] is True
    CliRunner().invoke(app, ["resume", "--journal", str(journal)])
    assert effective_halt(journal.parent, root)["halted"] is False