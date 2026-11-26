"""Exit-note drafting: the kernel proposes bounds, it never approves them.

These tests pin the two properties the pre-armed-exit design rests on: every number in a
drafted line comes from a record the kernel already trusts (the journaled stop, the broker
quantity) rather than an opinion, and anything it cannot ground is refused out loud.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tyche.approvals import ApprovalBatch, authorize_order
from tyche.cli import app
from tyche.envelope import Proposal, exit_levels, propose_exit_envelope
from tyche.journal import append_event
from tyche.models import AccountSnapshot, OptionContract, Position
from tyche.tactical import MonitorState
from tyche.watchlist import Watchlist, WatchlistEntry

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
HASH = "a9a899f896ac0353cd85043aba118e3fda5d315477fcdabebe07a0c079199d25"
PUT = "US.MSFT261231P460000"


def entry(**overrides) -> dict:
    """A bullish watchlist plan, as the tactical lane journals it under `protected_setup`."""
    base = {
        "symbol": "US.MSFT", "sleeve": "equity", "strategy": "PB-002 tactical break",
        "entry_low": 490.0, "entry_high": 495.0, "stop": 470.0, "target": 540.0,
        "expiry": date(2026, 12, 31), "setup_id": "TAC-20261119-MSFT-L4", "direction": "bullish",
    }
    base.update(overrides)
    return WatchlistEntry.model_validate(base).model_dump(mode="json")


def requested(**payload) -> dict:
    return {"type": "order.requested", "payload": payload}


def snap(*positions: Position, env: str = "paper") -> AccountSnapshot:
    return AccountSnapshot(account_id="***598", cash=10_000.0, positions=list(positions),
                           env=env, source="manual")


def stock(symbol: str = "US.MSFT", qty: int = 39, available: int | None = None) -> Position:
    return Position(symbol=symbol, quantity=qty, available_quantity=available,
                    avg_cost=480.0, last_price=500.0)


def propose(positions: list[Position], events: list[dict], **overrides) -> Proposal:
    env = overrides.pop("env", "paper")
    kwargs = {"today": TODAY, "collar_pct": 0.05, "max_orders_per_day": 6, "now": NOW}
    kwargs.update(overrides)
    return propose_exit_envelope(snap(*positions, env=env), events, **kwargs)


def test_journaled_contract_gives_the_floor_and_the_hash_is_copied():
    events = [requested(symbol="US.MSFT", side="buy", quantity=39, setup_hash=HASH,
                        setup_id="TAC-20261119-MSFT-L4", strategy_id="PB-002", protected_setup=entry())]
    line = propose([stock()], events).lines[0]
    assert line["source"] == "journal_contract" and line["bound"] is True
    assert line["setup_hash"] == HASH  # verbatim: it folds in the account id and the config hash
    assert line["stop"] == 470.0 and line["limit_min"] == pytest.approx(470.0 * 0.95)
    assert line["max_qty"] == 39 and line["strategy_id"] == "PB-002"


def test_journaled_order_stop_is_its_own_source():
    line = propose([stock("US.AMD", 10)], [requested(symbol="US.AMD", side="buy", stop_price=200.0)]).lines[0]
    assert line["source"] == "journal_order" and line["stop"] == 200.0
    assert line["limit_min"] == pytest.approx(190.0)
    assert line["bound"] is False and "setup hash" in line["warn"]


def test_newest_request_protects_the_position():
    events = [requested(symbol="US.MSFT", stop_price=400.0), requested(symbol="US.MSFT", protected_setup=entry())]
    levels, problems = exit_levels(events)
    assert problems == []
    assert levels["US.MSFT"].stop == 470.0 and levels["US.MSFT"].source == "journal_contract"
    assert propose([stock()], events).lines[0]["limit_min"] == pytest.approx(446.5)


def test_newer_monitor_rebinds_only_the_same_protected_setup():
    original = requested(symbol="US.MSFT", protected_setup=entry(), setup_hash=HASH)
    state = MonitorState(protected={"US.MSFT": entry()}, protected_hashes={"US.MSFT": "b" * 64})
    rebound = {"type": "tactical.monitor", "payload": {"state": state.model_dump(mode="json"),
                                                        "rebind": {"reason": "operator rule change"}}}
    assert exit_levels([original, rebound])[0]["US.MSFT"].setup_hash == "b" * 64
    routine = {"type": "tactical.monitor", "payload": {"state": state.model_dump(mode="json")}}
    assert exit_levels([original, routine])[0]["US.MSFT"].setup_hash == HASH
    mismatch = MonitorState(protected={"US.MSFT": entry(stop=460.0)},
                            protected_hashes={"US.MSFT": "c" * 64})
    changed = {"type": "tactical.monitor", "payload": {"state": mismatch.model_dump(mode="json")}}
    assert exit_levels([original, changed])[0]["US.MSFT"].setup_hash == HASH
    later = requested(symbol="US.MSFT", protected_setup=entry(), setup_hash="d" * 64)
    assert exit_levels([original, rebound, later])[0]["US.MSFT"].setup_hash == "d" * 64


def test_a_position_without_a_level_is_refused_not_invented():
    proposal = propose([stock()], [])
    assert proposal.lines == [] and proposal.batch is None and not proposal.armable
    assert "no journaled stop" in proposal.skipped[0]["why"]


def test_the_collar_is_the_only_operator_number_and_it_widens_downward():
    events = [requested(symbol="US.MSFT", stop_price=470.0)]
    assert propose([stock()], events, collar_pct=0.02).lines[0]["limit_min"] == pytest.approx(460.6)
    assert propose([stock()], events, collar_pct=0.10).lines[0]["limit_min"] == pytest.approx(423.0)
    for bad in (0.0, 0.5, -0.05):
        with pytest.raises(ValueError, match="collar_pct"):
            propose([stock()], events, collar_pct=bad)


def test_unsettled_quantity_protects_nothing():
    events = [requested(symbol="US.MSFT", stop_price=470.0)]
    assert "nothing sellable today" in propose([stock(available=0)], events).skipped[0]["why"]
    assert propose([stock(available=12)], events).lines[0]["max_qty"] == 12


def test_option_lines_follow_the_desk_switch():
    contract = OptionContract(underlying="US.MSFT", expiry=date(2026, 12, 31), right="call", strike=460.0)
    held = [Position(symbol="US.MSFT261231C460000", quantity=5, avg_cost=8.0, last_price=9.0, option=contract)]
    events = [requested(symbol="US.MSFT261231C460000", stop_price=6.0)]
    assert "options are not enabled" in propose(held, events).skipped[0]["why"]
    line = propose(held, events, options_enabled=True).lines[0]
    assert line["multiplier"] == 100 and line["limit_min"] == pytest.approx(5.7)


CALL = "US.NVDA261218C150000"


def call_contract() -> OptionContract:
    return OptionContract(underlying="US.NVDA", expiry=date(2026, 12, 18), right="call", strike=150.0)


def call_position(cost: float = 10.0) -> Position:
    return Position(symbol=CALL, quantity=1, avg_cost=cost, last_price=8.09, option=call_contract())


def call_plan(**overrides) -> dict:
    """A long call as the research file writes it: levels stated against the shares, not the premium."""
    return entry(symbol=CALL, option=call_contract(), entry_low=144.0, entry_high=146.0, stop=141.0,
                 target=156.0, premium_limit=1_000.0, setup_id="TAC-20261125-NVDA-C150", **overrides)


def test_a_contract_floor_is_never_an_underlying_price():
    """The plan's 141 stop belongs to the shares; a contract cannot be sold at 133.95."""
    events = [requested(symbol=CALL, protected_setup=call_plan())]
    line = propose([call_position()], events, options_enabled=True).lines[0]
    assert line["stop_basis"] == "premium drawdown floor"
    assert line["stop"] == pytest.approx(10.0 * 0.60) and line["limit_min"] == pytest.approx(6.0 * 0.95)


def test_a_journaled_premium_stop_beats_the_drawdown_floor():
    events = [requested(symbol=CALL, protected_setup=call_plan(), premium_stop=7.50)]
    line = propose([call_position()], events, options_enabled=True).lines[0]
    assert line["stop_basis"] == "journaled premium stop" and line["limit_min"] == pytest.approx(7.125)


def test_a_contract_the_broker_gives_no_cost_for_is_refused_not_invented():
    proposal = propose([call_position(cost=0.0)], [requested(symbol=CALL, protected_setup=call_plan())],
                       options_enabled=True)
    assert proposal.lines == [] and "no premium to floor a contract on" in proposal.skipped[0]["why"]



def test_a_bearish_expression_is_not_protected_by_a_sell_floor():
    contract = OptionContract(underlying="US.MSFT", expiry=date(2026, 12, 31), right="put", strike=460.0)
    held = [Position(symbol=PUT, quantity=5, avg_cost=8.0, last_price=9.0, option=contract)]
    bearish = entry(symbol=PUT, sleeve="credit", direction="bearish", option=contract, premium_limit=12.0,
                    setup_id="TAC-20261119-MSFT-P1", entry_low=8.0, entry_high=9.0, stop=11.0, target=5.0)
    proposal = propose(held, [requested(symbol=PUT, protected_setup=bearish)], options_enabled=True)
    assert proposal.lines == [] and "buying back" in proposal.skipped[0]["why"]


def test_watchlist_levels_are_a_fallback_and_say_so():
    book = Watchlist(as_of=TODAY, entries=[WatchlistEntry.model_validate(entry(stop=460.0))])
    line = propose([stock()], [], watchlist=book).lines[0]
    assert line["source"] == "watchlist" and line["stop"] == 460.0
    assert "no journal contract" in line["source_label"]
    # A journaled level still outranks the plan book.
    grounded = propose([stock()], [requested(symbol="US.MSFT", stop_price=470.0)], watchlist=book)
    assert grounded.lines[0]["source"] == "journal_order"


def test_closed_and_invalidated_plans_offer_no_level():
    book = Watchlist(as_of=TODAY, entries=[
        WatchlistEntry.model_validate(entry(symbol="US.AAA", setup_id="S-1", status="exited")),
        WatchlistEntry.model_validate(entry(symbol="US.BBB", setup_id="S-2", status="dropped")),
        WatchlistEntry.model_validate(entry(symbol="US.CCC", setup_id="S-3", invalidated=True)),
    ])
    proposal = propose([stock()], [], watchlist=book)
    assert proposal.lines == [] and "no journaled stop" in proposal.skipped[0]["why"]


def test_a_live_book_is_not_drafted_and_the_proposal_says_it_is_a_draft():
    events = [requested(symbol="US.MSFT", stop_price=470.0)]
    with pytest.raises(ValueError, match="paper positions only"):
        propose([stock()], events, env="live")
    payload = propose([stock()], events).as_payload()
    assert payload["draft"] is True and payload["armed"] is False
    assert payload["proposed"] == 1 and payload["positions_seen"] == 1
    assert payload["envelope"]["note"].startswith("DRAFT ONLY - not armed.")
    assert payload["envelope"]["approved_by"] == "kernel draft (not an operator approval)"


def test_order_budget_allows_retries_up_to_the_daily_cap():
    events = [requested(symbol="US.AAA", stop_price=100.0), requested(symbol="US.BBB", stop_price=100.0)]
    book = [stock("US.AAA", 10), stock("US.BBB", 10)]
    assert propose(book, events, max_orders_per_day=4).batch.max_orders == 4  # the daily cap binds
    assert propose(book, events, max_orders_per_day=100).batch.max_orders == 6  # three tries per line
    assert propose(book[:1], events, max_orders_per_day=100).batch.max_orders == 3


def test_a_drafted_envelope_only_authorises_its_own_bounds():
    """The draft is a real ApprovalBatch, so prove exactly what it would let the executor do."""
    events = [requested(symbol="US.MSFT", side="buy", quantity=39, setup_hash=HASH, protected_setup=entry())]
    batch = ApprovalBatch.model_validate(propose([stock()], events).batch.model_dump(mode="json"))
    floor, today = batch.orders[0].limit_min, batch.as_of
    assert authorize_order(batch, symbol="US.MSFT", side="sell", qty=39, limit=floor + 1,
                           today=today, used=0)[0]
    assert not authorize_order(batch, symbol="US.MSFT", side="sell", qty=39, limit=floor - 1,
                               today=today, used=0)[0]
    assert not authorize_order(batch, symbol="US.MSFT", side="buy", qty=1, limit=1.0,
                               today=today, used=0)[0]
    assert not authorize_order(batch, symbol="US.MSFT", side="sell", qty=40, limit=floor + 1,
                               today=today, used=0)[0]
    assert not authorize_order(batch, symbol="US.MSFT", side="sell", qty=39, limit=floor + 1,
                               today=date(2026, 11, 21), used=0)[0]
    assert batch.max_notional is None  # an exit is bounded by quantity and floor, not by spend


def test_unreadable_protected_setups_are_reported_as_problems():
    proposal = propose([stock()], [requested(symbol="US.MSFT", protected_setup={"symbol": "US.MSFT"})])
    assert proposal.problems and "no longer parses" in proposal.problems[0]
    assert proposal.lines == []


def test_draft_lines_are_valid_sell_lines():
    events = [requested(symbol="US.MSFT", stop_price=470.0), requested(symbol="US.AMD", stop_price=200.0)]
    batch = propose([stock(), stock("US.AMD", 10)], events).batch
    for line in batch.orders:
        assert line.side == "sell" and line.limit_min and line.limit_max is None
    assert batch.valid_on(TODAY) and not batch.valid_on(date(2026, 11, 21))
    with pytest.raises(ValidationError):
        ApprovalBatch.model_validate({**batch.model_dump(mode="json"), "orders": []})


# ------------------------------------------------------------------ command line
def run_cli(*args) -> tuple[int, str]:
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.output


def test_cli_writes_the_draft_file_and_nothing_else(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "order.requested", {"symbol": "US.MSFT", "side": "buy", "setup_hash": HASH,
                                              "protected_setup": entry()})
    account = tmp_path / "snapshot.json"
    account.write_text(snap(stock()).model_dump_json(), encoding="utf-8")
    out = tmp_path / "proposed.json"
    code, _ = run_cli("propose-envelope", "--account", str(account), "--journal", str(journal),
                      "--watchlist", str(tmp_path / "absent.json"), "--out", str(out),
                      "--config-root", str(ROOT), "--collar-pct", "0.10",
                      "--at", "2026-11-20T14:00:00+00:00")
    assert code == 0
    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["draft"] is True and draft["armed"] is False
    assert draft["envelope"]["as_of"] == "2026-11-20"
    assert draft["envelope"]["orders"][0]["limit_min"] == pytest.approx(423.0)
    assert draft["envelope"]["orders"][0]["setup_hash"] == HASH
    assert draft["lines"][0]["source_label"] == "protected setup (journal)"


def test_cli_refuses_and_clears_a_stale_draft_when_nothing_has_a_level(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "order.requested", {"symbol": "US.SPY", "side": "buy", "quantity": 21})
    account = tmp_path / "snapshot.json"
    account.write_text(snap(stock("US.SPY", 21)).model_dump_json(), encoding="utf-8")
    out = tmp_path / "proposed.json"
    out.write_text('{"as_of": "2026-11-18", "orders": []}', encoding="utf-8")
    code, output = run_cli("propose-envelope", "--account", str(account), "--journal", str(journal),
                           "--watchlist", str(tmp_path / "absent.json"), "--out", str(out),
                           "--config-root", str(ROOT), "--at", "2026-11-20T14:00:00+00:00")
    assert code == 1 and not out.exists()
    assert "nothing to propose" in output


def test_cli_will_not_draft_against_a_broken_chain(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "order.requested", {"symbol": "US.MSFT", "stop_price": 470.0})
    line = journal.read_text(encoding="utf-8").replace('"stop_price":470.0', '"stop_price":471.0')
    journal.write_text(line, encoding="utf-8")
    account = tmp_path / "snapshot.json"
    account.write_text(snap(stock()).model_dump_json(), encoding="utf-8")
    out = tmp_path / "proposed.json"
    code, output = run_cli("propose-envelope", "--account", str(account), "--journal", str(journal),
                           "--out", str(out), "--config-root", str(ROOT), "--json")
    assert code == 1 and not out.exists()
    assert "journal integrity" in output
