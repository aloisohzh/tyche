from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tyche.cli import app
from tyche.config import load_config
from tyche.journal import append_event
from tyche.lifecycle import (
    Approval,
    BrokerOrder,
    LifecycleBook,
    LifecyclePlan,
    LifecycleState,
    MarketEvent,
    MarketSnapshot,
    Quote,
    Reservation,
    Review,
    account_hash,
    reconcile,
    tick,
)
from tyche.lifecycle_cli import locked_state
from tyche.models import AccountSnapshot, OptionContract, Position
from tyche.pipeline import rules_hash

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 19, 15, 5, tzinfo=UTC)
ACCOUNT = "SIM-TEST"


def setup_case(*, held=10, price=100.0, approved=True, **overrides):
    config = load_config(ROOT)
    plan = LifecyclePlan(
        plan_id="test-spy", revision=1, symbol="US.SPY", strategy_id="PB-001",
        rules_hash=rules_hash(ROOT, "PB-001"), thesis="Trend remains intact with bounded risk.",
        invalidation_rules=["Sourced material event contradicts the thesis"],
        created_at=NOW - timedelta(minutes=30), mode="adopt_position" if held else "new_entry",
        quantity=10, entry_low=99, entry_high=101, stop={"price": 95},
        take_profit={"price": 110}, entry_expires_at=NOW + timedelta(hours=1),
        exit_deadline=NOW + timedelta(days=1), **overrides,
    )
    book = LifecycleBook(plans=[plan], reviews=[Review(
        plan_hash=plan.fingerprint(), reviewed_at=NOW - timedelta(minutes=5),
        valid_until=NOW + timedelta(minutes=55), verdict="valid",
        reason="Fresh price and material news review passed.", evidence=["https://example.test/news"],
    )], news_checked_at=NOW, news_feed_ok=True)
    market = MarketSnapshot(
        observed_at=NOW, snapshot=AccountSnapshot(
            account_id=ACCOUNT, env="paper", source="sim_list", account_type=2, market_id=100,
            cash=99000, positions=[Position(symbol="US.SPY", quantity=held, avg_cost=100,
                                           last_price=price)] if held else [],
        ), regime="neutral", conviction="medium", broker_nav=100000, prior_close_nav=100000, high_water_nav=100000,
        available={"US.SPY": held}, quotes=[Quote(symbol="US.SPY", last=price, at=NOW,
                                                tradable=True)], orders=[], orders_complete=True,
    )
    state = LifecycleState(approvals=[Approval(
        plan_hash=plan.fingerprint(), contract=plan.model_copy(deep=True),
        account_hash=account_hash(ACCOUNT), approved_at=NOW,
        operator_ref="test operator approval", auditor_ref="test auditor review",
        adopted_quantity=held,
    )] if approved else [])
    return plan, book, market, state, config


def decision(case, now=NOW):
    _, book, market, state, config = case
    return tick(book, market, state, config, now)["decisions"][0]


@pytest.mark.parametrize("price,action,reason", [
    (100, "hold", "no exit trigger"), (94, "sell", "stop_loss"),
    (95, "sell", "stop_loss"), (110, "sell", "take_profit"),
])
def test_adopted_position_exits(price, action, reason):
    result = decision(setup_case(price=price))
    assert (result["action"], result["reason"]) == (action, reason)
    assert result["authorized"] == (action == "sell")


def test_fresh_new_entry_authorized():
    result = decision(setup_case(held=0))
    assert result["action"] == "buy" and result["authorized"]
    assert 99 <= result["limit_price"] <= 101


def test_a_switched_off_lane_blocks_entries_but_never_an_exit(tmp_path):
    """The operator switch is an entry gate: turning a lane off must not strand a position it owns."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "strategies.json").write_text(
        json.dumps({"enabled": {"PB-001": False}}), encoding="utf-8"
    )
    config = load_config(ROOT).model_copy(update={"root": tmp_path})
    assert config.strategy_enabled("PB-001") is False

    entry = list(setup_case(held=0))
    entry[4] = config
    result = decision(entry)
    assert result["action"] == "blocked" and result["reason"] == "strategy disabled"

    held = list(setup_case(held=10, price=94.0))
    held[4] = config
    exit_result = decision(held)
    assert exit_result["action"] == "sell" and exit_result["reason"] == "stop_loss"


def test_lifecycle_turnover_includes_full_option_debit():
    case = setup_case(held=0)
    case[4].risk.max_daily_turnover_pct = 0.01
    case[2].orders = [BrokerOrder(
        order_id="option-filled", symbol="US.NVDA261127C150000", side="buy",
        option=OptionContract(underlying="US.NVDA", expiry="2026-11-27", right="call", strike=150),
        quantity=1, filled_quantity=1, status=4, limit_price=6, created_at=NOW,
    )]
    result = decision(case)
    assert not result["authorized"]
    assert "turnover" in result["reason"]


def test_lifecycle_exit_retains_unrelated_option_positions():
    case = setup_case(price=94)
    option = Position(symbol="US.NVDA261127C150000", quantity=1, available_quantity=1,
                      avg_cost=6, last_price=6, option=OptionContract(
                          underlying="US.NVDA", expiry="2026-11-27", right="call", strike=150))
    case[2].snapshot.positions.append(option)
    case[2].snapshot.cash -= 600
    case[2].available[option.symbol] = 1
    result = decision(case)
    assert result["authorized"] and result["action"] == "sell"
    assert result["symbol"] == "US.SPY"


@pytest.mark.parametrize("exposure", ["held", "pending", "reserved"])
def test_entry_respects_whole_ballast_allocation(exposure):
    case = setup_case(held=0)
    _, _, market, state, config = case
    config.strategies[0].allocation_cap = 0.02
    if exposure == "held":
        market.snapshot.positions = [Position(symbol="US.EFA", quantity=15, avg_cost=100, last_price=100)]
        market.snapshot.cash -= 1500
        market.available["US.EFA"] = 15
    elif exposure == "pending":
        market.orders = [BrokerOrder(order_id="pending-efa", symbol="US.EFA", side="buy",
                                    quantity=15, filled_quantity=0, status=2,
                                    limit_price=100, created_at=NOW)]
    else:
        contract = case[0].model_copy(update={"symbol": "US.EFA", "plan_id": "efa", "quantity": 15})
        state.approvals.append(Approval(
            plan_hash=contract.fingerprint(), contract=contract, account_hash=account_hash(ACCOUNT),
            approved_at=NOW, operator_ref="synthetic", auditor_ref="synthetic"))
        state.reservations.append(Reservation(
            request_id="reserved-efa", plan_hash=contract.fingerprint(), account_hash=account_hash(ACCOUNT),
            symbol="US.EFA", side="buy", quantity=15, limit_price=100,
            reason="synthetic", reserved_at=NOW))
    result = decision(case)
    assert not result["authorized"]
    assert result["reason"] == "risk gate: strategy allocation cap"


@pytest.mark.parametrize("cap", ["strategy", "asset"])
def test_entry_respects_strategy_name_caps(cap):
    case = setup_case(held=0)
    if cap == "strategy":
        case[4].strategies[0].max_weight = 0.005
    else:
        case[4].universe.by_symbol()["US.SPY"].max_weight = 0.005
    result = decision(case)
    assert not result["authorized"]
    assert result["reason"] == "risk gate: strategy asset cap"


def test_allocation_breach_does_not_block_protective_exit():
    case = setup_case(price=94)
    case[4].strategies[0].allocation_cap = 0.001
    case[4].strategies[0].max_weight = 0.001
    result = decision(case)
    assert result["authorized"] and result["action"] == "sell"


@pytest.mark.parametrize("mutation,expected", [
    ("stale_review", "review"), ("missing_review", "review"),
    ("news_down", "review"), ("uncertain", "review"), ("invalidated", "blocked"),
    ("future_news", "review"), ("outside_zone", "hold"), ("halt", "blocked"),
    ("rules_changed", "blocked"), ("no_approval", "blocked"),
])
def test_entries_fail_closed(mutation, expected):
    case = setup_case(held=0)
    plan, book, market, state, _ = case
    if mutation == "stale_review":
        book.reviews[0].valid_until = NOW
    elif mutation == "missing_review":
        book.reviews = []
    elif mutation == "news_down":
        book.news_feed_ok = False
    elif mutation == "uncertain":
        book.reviews[0].verdict = "uncertain"
    elif mutation == "invalidated":
        book.reviews[0].verdict = "invalidated"
    elif mutation == "future_news":
        book.news_checked_at = NOW + timedelta(minutes=1)
    elif mutation == "outside_zone":
        market.quotes[0].last = 102
    elif mutation == "halt":
        market.halted = True
    elif mutation == "rules_changed":
        plan.rules_hash = "different-rules"
        book.reviews[0].plan_hash = plan.fingerprint()
        state.approvals[0].plan_hash = plan.fingerprint()
        state.approvals[0].contract = plan.model_copy(deep=True)
    elif mutation == "no_approval":
        state.approvals.clear()
    result = decision(case)
    assert result["action"] == expected
    assert not result["authorized"]


@pytest.mark.parametrize("price,reason", [(94, "stop_loss"), (110, "take_profit")])
def test_stale_research_and_halt_do_not_disable_protection(price, reason):
    case = setup_case(price=price)
    _, book, market, _, _ = case
    book.reviews = []
    book.news_feed_ok = False
    market.halted = True
    result = decision(case)
    assert result["authorized"] and result["reason"] == reason


def test_material_event_requires_new_review_but_not_new_approval_if_plan_unchanged():
    case = setup_case(held=0)
    _, book, _, _, _ = case
    book.events = [MarketEvent(event_id="fed", at=NOW - timedelta(minutes=1),
                              source="https://example.test/fed", summary="Unexpected decision")]
    assert "event" in decision(case)["reason"]
    book.reviews[0].reviewed_at = NOW
    book.reviews[0].acknowledged_events = ["fed"]
    assert decision(case)["authorized"]


def test_imminent_event_blocks_even_if_prematurely_acknowledged():
    case = setup_case(held=0)
    book = case[1]
    book.events = [MarketEvent(event_id="fed", at=NOW + timedelta(minutes=15),
                              source="https://example.test/fed", summary="Scheduled announcement")]
    book.reviews[0].acknowledged_events = ["fed"]
    assert "imminent" in decision(case)["reason"]


def test_unrelated_event_does_not_block_entry():
    case = setup_case(held=0)
    case[1].events = [MarketEvent(event_id="other", at=NOW, symbols=["US.EFA"],
                                source="source", summary="Company-specific news")]
    assert decision(case)["authorized"]


def test_confirmed_invalidation_exits_and_latches():
    case = setup_case()
    plan, book, _, state, _ = case
    book.reviews[0].verdict = "invalidated"
    assert decision(case)["reason"] == "thesis_invalidated"
    assert state.latched_exits[plan.fingerprint()] == "thesis_invalidated"
    book.reviews[0].verdict = "valid"
    assert decision(case)["reason"] == "thesis_invalidated"


def test_uncertainty_is_not_automatic_liquidation():
    case = setup_case()
    case[1].reviews[0].verdict = "uncertain"
    result = decision(case)
    assert result["action"] == "review" and not result["authorized"]


def test_whole_contract_change_requires_reapproval():
    case = setup_case(price=94)
    plan, book, _, _, _ = case
    plan.stop.price = 96
    book.reviews[0].plan_hash = plan.fingerprint()
    assert not decision(case)["authorized"]


def test_approval_bound_to_account_and_revocation():
    case = setup_case(price=94)
    case[3].approvals[0].account_hash = account_hash("another-account")
    assert not decision(case)["authorized"]
    case = setup_case(price=94)
    case[3].approvals[0].revoked = True
    assert not decision(case)["authorized"]


@pytest.mark.parametrize("field", ["observed_at", "quote"])
def test_stale_and_future_data_block(field):
    for delta in (-301, 60):
        case = setup_case(price=94)
        if field == "observed_at":
            case[2].observed_at = NOW + timedelta(seconds=delta)
            with pytest.raises(ValueError):
                decision(case)
        else:
            case[2].quotes[0].at = NOW + timedelta(seconds=delta)
            assert not decision(case)["authorized"]


def test_real_accounts_and_unverified_sources_rejected():
    for field, value in [("env", "live"), ("source", "demo"), ("account_id", "not-allowed"),
                         ("market_id", 1), ("account_type", 99)]:
        case = setup_case(price=94)
        setattr(case[2].snapshot, field, value)
        with pytest.raises(ValueError):
            decision(case)


def test_exit_deadline_still_applies_with_expired_entry_and_research():
    case = setup_case()
    tomorrow = NOW + timedelta(days=1)
    case[2].observed_at = tomorrow
    case[2].quotes[0].at = tomorrow
    result = decision(case, tomorrow)
    assert result["authorized"] and result["reason"] == "holding_deadline"


def test_close_trigger_does_not_fire_on_intraday_touch():
    case = setup_case(price=94)
    plan, book, _, state, _ = case
    plan.stop.basis = "daily_close"
    book.reviews[0].plan_hash = plan.fingerprint()
    state.approvals[0].plan_hash = plan.fingerprint()
    state.approvals[0].contract = plan.model_copy(deep=True)
    assert decision(case)["action"] == "hold"


def test_close_trigger_latches_after_hours_then_executes_next_session():
    case = setup_case(price=94)
    plan, book, market, state, _ = case
    plan.stop.basis = "daily_close"
    book.reviews[0].plan_hash = plan.fingerprint()
    state.approvals[0].plan_hash = plan.fingerprint()
    state.approvals[0].contract = plan.model_copy(deep=True)
    close = NOW.replace(hour=21, minute=0)
    market.observed_at = close + timedelta(minutes=5)
    market.quotes[0].at = close
    market.quotes[0].close, market.quotes[0].close_at = 94, close
    assert not decision(case, market.observed_at)["authorized"]
    assert state.latched_exits[plan.fingerprint()] == "stop_loss"
    tomorrow = NOW + timedelta(days=1)
    market.observed_at = tomorrow
    market.quotes[0].at, market.quotes[0].last = tomorrow, 100
    assert decision(case, tomorrow)["authorized"]


def order(*, qty=10, filled=0, status=2, side="sell", remark="r1"):
    return BrokerOrder(order_id="broker-1", symbol="US.SPY", side=side, quantity=qty,
                       filled_quantity=filled, status=status, created_at=NOW,
                       limit_price=94, remark=remark)


def test_pending_orders_block_duplicates_and_require_cancel_review():
    case = setup_case(price=94)
    case[2].orders = [order()]
    assert "pending" in decision(case)["reason"]


def test_unknown_reservation_never_retried_or_expired_automatically():
    case = setup_case(price=94)
    plan, _, _, state, _ = case
    state.reservations.append(Reservation(
        request_id="r1", plan_hash=plan.fingerprint(), account_hash=account_hash(ACCOUNT),
        symbol="US.SPY", side="sell", quantity=10, limit_price=94, reason="stop_loss",
        reserved_at=NOW - timedelta(days=1),
    ))
    assert "uncertain" in decision(case)["reason"]


def test_reconcile_partial_then_full_exit():
    case = setup_case(price=94)
    plan, _, market, state, _ = case
    state.reservations.append(Reservation(
        request_id="r1", plan_hash=plan.fingerprint(), account_hash=account_hash(ACCOUNT),
        symbol="US.SPY", side="sell", quantity=10, limit_price=94, reason="stop_loss", reserved_at=NOW,
    ))
    market.orders = [order(filled=4)]
    market.snapshot.positions[0].quantity = 6
    market.available["US.SPY"] = 6
    result = decision(case)
    assert not result["authorized"] and state.reservations[0].filled_quantity == 4
    market.orders = [order(filled=10, status=4)]
    market.snapshot.positions = []
    assert decision(case)["action"] == "closed"
    assert state.reservations[0].complete


def test_fill_identity_mismatch_and_regression_rejected():
    case = setup_case(price=94)
    plan, _, market, state, _ = case
    state.reservations.append(Reservation(
        request_id="r1", plan_hash=plan.fingerprint(), account_hash=account_hash(ACCOUNT),
        symbol="US.SPY", side="sell", quantity=10, limit_price=94, reason="stop_loss", reserved_at=NOW,
    ))
    market.orders = [order(side="buy")]
    with pytest.raises(ValueError):
        reconcile(state, market)
    market.orders = [order(filled=4)]
    reconcile(state, market)
    market.orders[0].filled_quantity = 2
    with pytest.raises(ValueError):
        reconcile(state, market)


def test_position_without_plan_reported_as_coverage_gap():
    case = setup_case(approved=False)
    case[1].plans = []
    result = tick(case[1], case[2], case[3], case[4], NOW)
    assert "missing a complete lifecycle" in result["gaps"][0]


def test_watchlist_refresh_cannot_erase_existing_protection():
    case = setup_case(price=94)
    case[1].plans = []
    report = tick(case[1], case[2], case[3], case[4], NOW)
    assert report["decisions"][0]["authorized"]
    assert report["decisions"][0]["reason"] == "stop_loss"


def test_risk_counts_other_orders_and_available_shares():
    case = setup_case(price=94)
    case[2].available["US.SPY"] = 3
    assert decision(case)["quantity"] == 3
    case = setup_case(held=0)
    case[4].risk.max_orders_per_day = 6
    case[2].orders = [order(filled=10, status=4).model_copy(update={
        "order_id": str(i), "symbol": "US.EFA"
    }) for i in range(6)]
    assert "orders.daily_count" in decision(case)["reason"]


def test_yesterday_orders_do_not_consume_today_budget():
    case = setup_case(held=0)
    case[4].risk.max_orders_per_day = 6
    case[2].orders = [order(filled=10, status=4).model_copy(update={
        "order_id": str(i), "created_at": NOW - timedelta(days=1)
    }) for i in range(6)]
    assert decision(case)["authorized"]


def test_schema_rejects_bad_levels_naive_dates_and_after_close_deadline():
    plan = setup_case()[0].model_dump(mode="json")
    for patch in [{"stop": {"price": 102}}, {"created_at": "2026-11-19T13:00:00"},
                  {"take_profit": {"price": float("nan")}},
                  {"exit_deadline": "2026-11-20T21:00:00Z"},
                  {"exit_deadline": "2026-11-21T15:00:00Z"}]:
        with pytest.raises(ValidationError):
            LifecyclePlan.model_validate({**plan, **patch})


def write_case(tmp_path, case):
    paths = {}
    for name, value in zip(("plan", "book", "market", "state"), case[:4], strict=True):
        path = tmp_path / f"{name}.json"
        path.write_text(value.model_dump_json(), encoding="utf-8")
        paths[name] = str(path)
    return paths


def test_cli_preview_includes_risk_and_never_approves(tmp_path):
    paths = write_case(tmp_path, setup_case())
    result = CliRunner().invoke(app, ["lifecycle", "preview", "--book", paths["book"],
                                    "--plan-id", "test-spy"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["risk"]["monitor_interval_minutes"] == 60
    assert not payload["approved"] and not payload["submitted"]


def test_cli_reserve_is_one_shot_and_receipt_is_not_fill(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda at="": NOW)
    paths = write_case(tmp_path, setup_case(price=94))
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    args = ["lifecycle", "reserve", "--book", paths["book"], "--market", paths["market"],
            "--state", paths["state"], "--plan-id", "test-spy",
            "--hash", setup_case()[0].fingerprint(), "--config-root", str(ROOT),
            "--journal", str(journal)]
    runner = CliRunner()
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    request = json.loads(first.stdout)["request"]
    assert request["side"] == "sell"
    assert runner.invoke(app, args).exit_code == 1
    response = runner.invoke(app, ["lifecycle", "receipt", "--state", paths["state"],
                                  "--request-id", request["request_id"], "--order-id", "123"])
    assert response.exit_code == 0
    ledger = LifecycleState.model_validate_json(Path(paths["state"]).read_text())
    assert not ledger.reservations[0].complete and ledger.reservations[0].filled_quantity == 0


def test_reservation_permission_expires_with_entry_contract(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda at="": NOW)
    case = setup_case(held=0)
    plan, book, market, state, _ = case
    market.snapshot.cash = market.broker_nav
    plan.entry_expires_at = NOW + timedelta(seconds=10)
    book.reviews[0].plan_hash = plan.fingerprint()
    state.approvals[0].plan_hash = plan.fingerprint()
    state.approvals[0].contract = plan.model_copy(deep=True)
    paths = write_case(tmp_path, case)
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    result = CliRunner().invoke(app, ["lifecycle", "reserve", "--book", paths["book"],
                                    "--market", paths["market"], "--state", paths["state"],
                                    "--plan-id", "test-spy", "--hash", plan.fingerprint(),
                                    "--journal", str(journal), "--config-root", str(ROOT)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["submit_before"] == plan.entry_expires_at.timestamp()


def test_cli_approve_requires_exact_hash_and_user_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda at="": NOW)
    case = setup_case(approved=False)
    paths = write_case(tmp_path, case)
    args = ["lifecycle", "approve", "--book", paths["book"], "--market", paths["market"],
            "--state", paths["state"], "--plan-id", "test-spy", "--hash", case[0].fingerprint(),
            "--operator-ref", "user approved this exact preview", "--auditor-ref", "auditor approved",
            "--config-root", str(ROOT)]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 1
    result = runner.invoke(app, [*args, "--yes"])
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, [*args, "--yes"]).exit_code == 1  # not duplicated/re-armed


def test_state_lock_and_replay_are_fail_closed(tmp_path):
    path = tmp_path / "state.json"
    with locked_state(path), pytest.raises(ValueError, match="locked"), locked_state(path):
        pass
    paths = write_case(tmp_path, setup_case())
    result = CliRunner().invoke(app, ["lifecycle", "tick", "--book", paths["book"],
                                    "--market", paths["market"], "--state", paths["state"],
                                    "--at", NOW.isoformat(), "--record"])
    assert result.exit_code == 1 and "replay clock" in result.output


def test_invalidated_flat_lifecycle_cannot_rearm_on_later_positive_review():
    case = setup_case(held=0)
    case[1].reviews[0].verdict = "invalidated"
    assert not decision(case)["authorized"]
    case[1].reviews[0].verdict = "valid"
    assert "invalidated" in decision(case)["reason"]


def test_revised_proposal_does_not_replace_the_original_approved_stop():
    case = setup_case(price=94)
    old_hash = case[0].fingerprint()
    case[0].stop.price = 90
    case[1].reviews[0].plan_hash = case[0].fingerprint()
    report = tick(case[1], case[2], case[3], case[4], NOW)
    approved = [d for d in report["decisions"] if d["authorized"]]
    assert len(approved) == 1 and approved[0]["plan_hash"] == old_hash
    assert approved[0]["reason"] == "stop_loss"


def test_time_exit_latches_without_quotes_but_cannot_submit():
    case = setup_case()
    tomorrow = NOW + timedelta(days=1)
    case[2].quotes = []
    case[2].observed_at = tomorrow
    assert not decision(case, tomorrow)["authorized"]
    assert case[3].latched_exits[case[0].fingerprint()] == "holding_deadline"


def test_unfilled_entry_is_not_reported_as_closed():
    case = setup_case(held=0)
    case[2].orders = [order(side="buy")]
    assert "pending" in decision(case)["reason"]


def test_other_symbol_resting_buy_counts_toward_gross_exposure():
    case = setup_case(held=0)
    case[4].risk.max_gross_exposure = 0.10
    case[2].orders = [order(qty=200, side="buy").model_copy(update={"symbol": "US.EFA"})]
    assert "portfolio.gross" in decision(case)["reason"]


def test_daily_entry_budget_preserves_exit_capacity_but_not_competition_cap():
    case = setup_case(price=94)
    case[4].risk.max_orders_per_day = 1
    case[4].risk.competition_order_cap = 2
    case[2].orders = [order(filled=10, status=4)]
    assert decision(case)["authorized"]
    case[2].orders.append(order(filled=10, status=4).model_copy(update={"order_id": "second"}))
    assert "orders.competition_count" in decision(case)["reason"]


def test_low_conviction_blocks_entries_not_protection():
    case = setup_case(held=0)
    case[2].conviction = "low"
    assert "act/wait" in decision(case)["reason"]
    case = setup_case(price=94)
    case[2].conviction = "low"
    assert decision(case)["authorized"]


def test_phase_entry_count_is_not_reset_by_another_tick():
    case = setup_case(held=0)
    case[2].orders = [order(filled=10, status=4).model_copy(update={"order_id": str(i)})
                      for i in range(2)]
    assert "phase entry budget" in decision(case)["reason"]
    assert "phase entry budget" in decision(case)["reason"]


def test_corrupt_duplicate_approval_and_fill_evidence_rejected():
    state = setup_case()[3].model_dump(mode="json")
    state["approvals"].append(state["approvals"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        LifecycleState.model_validate(state)
    state["approvals"] = state["approvals"][:1]
    state["approvals"][0]["contract"]["quantity"] = 11
    with pytest.raises(ValidationError, match="hash mismatch"):
        LifecycleState.model_validate(state)
    with pytest.raises(ValidationError, match="full-fill"):
        order(filled=0, status=4)


@pytest.mark.parametrize("contents", [None, "malformed", "{}"])
def test_missing_or_corrupt_research_preserves_only_approved_exits(tmp_path, monkeypatch, contents):
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda at="": NOW)
    case = setup_case(price=94)
    paths = write_case(tmp_path, case)
    path = Path(paths["book"])
    if contents is None:
        path.unlink()
    else:
        path.write_text(contents)
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    result = CliRunner().invoke(app, ["lifecycle", "reserve", "--book", paths["book"],
                                    "--market", paths["market"], "--state", paths["state"],
                                    "--plan-id", "test-spy", "--hash", case[0].fingerprint(),
                                    "--config-root", str(ROOT), "--journal", str(journal)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["request"]["side"] == "sell" and payload["warnings"]
    assert not payload["submitted"]


def test_cli_journal_failure_retains_reservation_without_emitting_permission(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.lifecycle_cli.now_utc", lambda at="": NOW)
    case = setup_case(price=94)
    paths = write_case(tmp_path, case)
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})

    def broken(*args, **kwargs):
        raise OSError("journal unavailable")

    monkeypatch.setattr("tyche.lifecycle_cli.append_locked", broken)
    result = CliRunner().invoke(app, ["lifecycle", "reserve", "--book", paths["book"],
                                    "--market", paths["market"], "--state", paths["state"],
                                    "--plan-id", "test-spy", "--hash", case[0].fingerprint(),
                                    "--config-root", str(ROOT), "--journal", str(journal)])
    assert result.exit_code == 1 and not json.loads(result.stdout).get("authorized")
    ledger = LifecycleState.model_validate_json(Path(paths["state"]).read_text())
    assert len(ledger.reservations) == 1 and not ledger.reservations[0].complete


def test_bad_proposal_does_not_disable_another_positions_approved_exit():
    case = setup_case(price=94)
    proposal = case[0].model_copy(deep=True, update={
        "symbol": "US.EFA", "plan_id": "bad-proposal", "mode": "new_entry", "strategy_id": "PB-999",
    })
    case[1].plans.insert(0, proposal)
    case[1].reviews.append(case[1].reviews[0].model_copy(update={"plan_hash": proposal.fingerprint()}))
    case[2].quotes.append(Quote(symbol="US.EFA", last=100, at=NOW, tradable=True))
    report = tick(case[1], case[2], case[3], case[4], NOW)
    assert report["decisions"][0]["authorized"] and report["decisions"][0]["symbol"] == "US.SPY"
    assert report["decisions"][1]["action"] == "blocked"


def test_invalid_market_error_does_not_print_account_payload(tmp_path):
    paths = write_case(tmp_path, setup_case())
    market = json.loads(Path(paths["market"]).read_text())
    private_example = "PRIVATE-ACCOUNT-FOR-REDACTION-TEST"
    market["snapshot"]["account_id"] = private_example
    market["snapshot"]["cash"] = -1
    Path(paths["market"]).write_text(json.dumps(market))
    result = CliRunner().invoke(app, ["lifecycle", "tick", "--book", paths["book"],
                                    "--market", paths["market"], "--state", paths["state"],
                                    "--at", NOW.isoformat(), "--config-root", str(ROOT)])
    assert result.exit_code == 1 and private_example not in result.output
    assert "invalid input" in result.output


def test_legacy_execute_cannot_bypass_lifecycle_with_yes(tmp_path, monkeypatch):
    account = "TEST-BROKER-ACCOUNT"
    config = load_config(ROOT)
    config.risk.account_allowlist.append(account)
    monkeypatch.setattr("tyche.cli.load_config", lambda root: config)

    def forbidden(*args, **kwargs):
        raise AssertionError("broker must never be instantiated")

    monkeypatch.setattr("tyche.cli.MoomooCli", forbidden)
    plan = {"as_of": NOW.date().isoformat(), "account_id": account, "nav": 100000,
            "cash": 100000, "regime": "neutral", "targets": {}, "signals": {},
            "regime_checks": {}, "portfolio_vol": 0.1, "vol_scale": 1, "orders": []}
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(plan))
    result = CliRunner().invoke(app, ["execute", "--plan", str(path), "--account-id", account,
                                    "--yes", "--config-root", str(ROOT)])
    assert result.exit_code == 2 and "Legacy execution disabled" in result.output


def capture_files(tmp_path):
    payloads = {
        "accounts": {"data": {"accounts": [{"account_id": ACCOUNT, "account_type": 2, "market_id": 100}]}},
        "cash": {"data": {"balance": 99000, "hold": 0, "total_asset": 100000}},
        "positions": {"data": {"positions": [{"symbol": "SPY", "pstn_type": 0, "qty": "10",
                                             "qty_avbl": "10", "cost_price": 100, "cur_price": 100}]}},
        "quotes": {"data": {"quote_list": [{"code": "US.SPY", "last_price": 100,
                                          "data_time": int(NOW.timestamp() * 1000),
                                          "sec_status": "NORMAL", "suspension": False}]}},
        "orders": {"data": {"orders": [{"order_id": "filled-entry", "symbol": "SPY", "side": 1,
                                      "qty": "10", "cum_qty": "10", "status": 4, "price": 100,
                                      "create_time": int((NOW - timedelta(minutes=5)).timestamp() * 1_000_000),
                                      "text": "test-request"}]}, "pagination": {"has_more": False}},
    }
    for name, payload in payloads.items():
        (tmp_path / f"{name}.json").write_text(json.dumps({"ret_code": 0, **payload}), encoding="utf-8")
    return payloads


def capture_args(tmp_path):
    return ["lifecycle", "capture", "--dir", str(tmp_path), "--account-id", ACCOUNT,
            "--observed-at", NOW.isoformat(), "--prior-close-nav", "100000",
            "--high-water-nav", "100000", "--regime", "neutral", "--conviction", "medium",
            "--out", str(tmp_path / "market.json")]


@pytest.mark.parametrize("metadata", ["valid", "missing", "wrong"])
def test_lifecycle_capture_preserves_option_exposure(tmp_path, metadata):
    payloads = capture_files(tmp_path)
    symbol = "US.NVDA261127C150000"
    payloads["positions"]["data"]["positions"].append({
        "symbol": symbol[3:], "pstn_type": 0, "qty": "1", "qty_avbl": "1",
        "cost_price": 6, "cur_price": 6,
    })
    payloads["orders"]["data"]["orders"].append({
        "order_id": "option-entry", "symbol": symbol[3:], "side": 1,
        "qty": "1", "cum_qty": "0", "status": 2, "price": 6,
        "create_time": int(NOW.timestamp() * 1_000_000), "text": "option-request",
    })
    payloads["cash"]["data"]["total_asset"] += 600
    for name, payload in payloads.items():
        (tmp_path / f"{name}.json").write_text(json.dumps({"ret_code": 0, **payload}))
    if metadata != "missing":
        (tmp_path / "contracts.json").write_text(json.dumps({symbol: {
            "underlying": "US.NVDA", "expiry": "2026-11-27", "right": "call",
            "strike": 150 if metadata == "valid" else 155, "multiplier": 100,
        }}))
    result = CliRunner().invoke(app, capture_args(tmp_path))
    if metadata != "valid":
        assert result.exit_code == 1, result.output
        assert not (tmp_path / "market.json").exists()
        return
    assert result.exit_code == 0, result.output
    market = MarketSnapshot.model_validate_json((tmp_path / "market.json").read_text())
    assert market.snapshot.position(symbol).market_value == 600
    assert market.snapshot.nav == market.broker_nav == 100600
    assert market.orders[-1].multiplier == 100
    assert not market.orders[-1].complete
    assert market.available[symbol] == 1


def test_capture_uses_broker_times_quantities_and_pagination(tmp_path):
    capture_files(tmp_path)
    result = CliRunner().invoke(app, capture_args(tmp_path))
    assert result.exit_code == 0, result.output
    market = MarketSnapshot.model_validate_json((tmp_path / "market.json").read_text())
    assert market.quotes[0].at == NOW
    assert market.snapshot.captured_at == NOW
    assert market.orders[0].complete and market.available["US.SPY"] == 10
    assert market.orders[0].created_at == NOW - timedelta(minutes=5)


@pytest.mark.parametrize("mutation", ["missing_pagination", "more_pages", "unknown_side",
                                      "fractional_quantity", "too_many_available", "failed_read",
                                      "missing_page", "duplicate_order"])
def test_capture_fails_closed_on_incomplete_or_unsupported_payloads(tmp_path, mutation):
    payloads = capture_files(tmp_path)
    if mutation == "missing_pagination":
        payloads["orders"].pop("pagination")
    elif mutation == "more_pages":
        payloads["orders"]["pagination"]["has_more"] = True
    elif mutation == "unknown_side":
        payloads["orders"]["data"]["orders"][0]["side"] = 8
    elif mutation == "fractional_quantity":
        payloads["positions"]["data"]["positions"][0]["qty"] = "0.5"
    elif mutation == "too_many_available":
        payloads["positions"]["data"]["positions"][0]["qty_avbl"] = "11"
    elif mutation == "failed_read":
        payloads["cash"]["ret_code"] = 1
    elif mutation == "duplicate_order":
        payloads["orders"]["data"]["orders"] *= 2
    for name, payload in payloads.items():
        (tmp_path / f"{name}.json").write_text(json.dumps({"ret_code": 0, **payload}))
    if mutation == "missing_page":
        (tmp_path / "orders.json").rename(tmp_path / "orders-2.json")
    result = CliRunner().invoke(app, capture_args(tmp_path))
    assert result.exit_code == 1, result.output
    assert not (tmp_path / "market.json").exists()
