from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tyche.cli import app
from tyche.config import RiskPolicy
from tyche.halt import is_halted, read_halt, set_halt
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