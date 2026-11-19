"""Synthetic paper drills. No credentials, network calls, or broker writes."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tyche.approvals import ApprovalBatch, authorize_order, envelope_totals
from tyche.broker.base import PaperBroker
from tyche.broker.mcp_json import build_snapshot, extract_positions
from tyche.broker.tactical_data import normalize_quotes
from tyche.cli import app
from tyche.config import load_config
from tyche.execution_state import combined_usage, pending_intents, unresolved_symbols
from tyche.fees import estimate_fees, reconcile_cash
from tyche.journal import append_event, journal_lock, read_events, verify_chain
from tyche.models import AccountSnapshot, OptionContract, OrderIntent, Position, Side, apply_fill
from tyche.risk import RiskState, evaluate_intent
from tyche.tactical import MarketQuote, MonitorState, plan_tick, setup_hash
from tyche.trade_risk import compute_expectancy
from tyche.watchlist import Watchlist, WatchlistEntry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 19, 15, 5, tzinfo=UTC)
OPT = "US.NVDA261127P155000"
CONTRACT = OptionContract(underlying="US.NVDA", expiry=date(2026, 11, 27), right="put", strike=155)


def case(option=False, held=False):
    config = load_config(ROOT)
    config.tactical.monitor_interval_seconds = 120
    snapshot = AccountSnapshot(account_id="SIM-TEST", cash=100000, captured_at=NOW,
                               source="sim_list", account_type=2, market_id=100,
                               prior_close_nav=100000, high_water_nav=100000)
    entry = WatchlistEntry(symbol=OPT if option else "US.NVDA", sleeve="equity",
                           strategy="catalyst fade" if option else "catalyst reclaim", setup_id="synthetic-1",
                           entry_low=149, entry_high=151, stop=156 if option else 145,
                           target=135 if option else 165, expiry=NOW.date(), thesis="Synthetic catalyst thesis",
                           option=CONTRACT if option else None, direction="bearish" if option else "bullish",
                           catalyst="synthetic earnings surprise", sources=["https://example.test/earnings"],
                           reviewed_at=NOW, market_cap_usd=1e12, premium_limit=6.1 if option else None,
                           exit_at=NOW.replace(hour=20, minute=45))
    book = Watchlist(as_of=NOW.date(), entries=[entry])
    uq = MarketQuote(symbol="US.NVDA", last=150, bid=149.95, ask=150.05,
                     at=NOW, book_at=NOW, tradable=True)
    quotes = [uq]
    if option:
        quotes.append(MarketQuote(symbol=OPT, last=6, bid=5.95, ask=6.05, at=NOW, book_at=NOW,
                                  option=CONTRACT, tradable=True, open_interest=500, volume=400,
                                  delta=-0.6, implied_volatility=55))
    if held:
        qty, price = (1, 6) if option else (10, 150)
        snapshot.cash -= qty * price * (100 if option else 1)
        snapshot.positions = [Position(symbol=entry.symbol, option=entry.option, quantity=qty,
                                       available_quantity=qty, last_price=price, avg_cost=price)]
    return book, snapshot, quotes, [], [], [], MonitorState(), config


def run(args, now=NOW):
    return plan_tick(*args, now)


def advance(args, now):
    args[1].captured_at = now
    for q in args[2]:
        q.at = q.book_at = now


def ready(args):
    assert not run(args)["orders"]
    now = NOW + timedelta(seconds=120)
    advance(args, now)
    return run(args, now)


@pytest.mark.parametrize("option", [False, True])
def test_confirmed_setup_produces_bounded_risk_preview(option):
    args = case(option)
    result = ready(args)
    assert len(result["orders"]) == 1, result
    order = result["orders"][0]
    assert order["intent"]["side"] == "buy"
    assert order["risk"]["product"] == ("long put" if option else "stock")
    assert order["risk"]["planned_stop_risk_usd"] <= (750 if option else 1000)
    assert order["risk"]["nav_pct"] <= .20
    assert not result["submitted"]
    if option:
        assert order["intent"]["quantity"] == 1
        assert order["intent"]["notional"] == 605


@pytest.mark.parametrize("pending_premium", [0, 100])
def test_option_allocation_cap_includes_held_and_pending_premiums(pending_premium):
    config = load_config(ROOT)
    held_contract = OptionContract(underlying="US.SPY", expiry=CONTRACT.expiry, right="call", strike=700)
    pending_contract = OptionContract(underlying="US.AMD", expiry=CONTRACT.expiry, right="call", strike=150)
    snapshot = AccountSnapshot(
        account_id="SIM-TEST", cash=75600 - pending_premium, frozen_cash=pending_premium,
        positions=[Position(symbol="US.SPY261127C700000", option=held_contract, quantity=244,
                            last_price=1, avg_cost=1)],
    )
    pending = [OrderIntent(symbol="US.AMD261127C150000", option=pending_contract,
                           side=Side.BUY, quantity=1, limit_price=1, reason="synthetic pending order")] if pending_premium else []
    intent = OrderIntent(symbol=OPT, option=CONTRACT, side=Side.BUY, quantity=1,
                         limit_price=6, reason="synthetic cap boundary")
    verdict = evaluate_intent(
        intent, snapshot, config.risk, RiskState(nav=snapshot.nav, pending_orders=pending),
        last_price=6, underlying_price=150, universe_symbols={"US.NVDA"}, sleeve_by_symbol={},
    )
    if pending_premium:
        assert not verdict.allowed
        assert {breach.rule for breach in verdict.breaches} == {"option.premium_cap"}
    else:
        assert verdict.allowed, verdict.breaches


@pytest.mark.parametrize("option", [False, True])
def test_hourly_confirmations_require_current_quotes_and_review(option):
    args = case(option)
    args[7].tactical.monitor_interval_seconds = 3600
    assert not run(args)["orders"]
    now = NOW + timedelta(hours=1)
    advance(args, now)
    args[0].entries[0].reviewed_at = now
    result = run(args, now)
    assert len(result["orders"]) == 1, result
    assert "heartbeat gap" not in " ".join(result["alerts"])


@pytest.mark.parametrize("stale", ["quote", "review", "heartbeat"])
def test_hourly_cadence_does_not_relax_data_gates(stale):
    args = case()
    args[7].tactical.monitor_interval_seconds = 3600
    run(args)
    now = NOW + timedelta(seconds=7201 if stale == "heartbeat" else 3600)
    advance(args, now)
    if stale != "review":
        args[0].entries[0].reviewed_at = now
    if stale == "quote":
        args[2][0].at -= timedelta(seconds=61)
    result = run(args, now)
    assert not result["orders"], result
    if stale == "heartbeat":
        assert "heartbeat gap" in " ".join(result["alerts"])


@pytest.mark.parametrize("option", [False, True])
@pytest.mark.parametrize("half_day", [False, True])
def test_hourly_exit_precedes_deadline_and_market_close(option, half_day):
    args = case(option, held=True)
    args[7].tactical.monitor_interval_seconds = 3600
    day, hour = (27, 17) if half_day else (19, 20)
    now = NOW.replace(day=day, hour=hour)
    args[0].entries[0].exit_at = now.replace(minute=45)
    args[0].entries[0].expiry = now.date()
    advance(args, now)
    result = run(args, now)
    assert result["orders"][0]["intent"]["side"] == "sell", result
    assert "expiry" in result["orders"][0]["intent"]["reason"] if option and half_day else (
        "next scheduled check" in result["orders"][0]["intent"]["reason"])


def test_hourly_blocks_entry_without_another_check_before_deadline():
    args = case()
    args[7].tactical.monitor_interval_seconds = 3600
    entry = args[0].entries[0]
    entry.confirmation_ticks = 1
    entry.exit_at = NOW + timedelta(minutes=59)
    result = run(args)
    assert not result["orders"]
    assert "next scheduled check" in result["decisions"][0]["reason"]


def test_duplicate_quote_does_not_count_as_confirmation():
    args = case()
    assert not run(args)["orders"]
    assert not run(args, NOW + timedelta(seconds=1))["orders"]
    advance(args, NOW + timedelta(seconds=500))
    assert not run(args, NOW + timedelta(seconds=500))["orders"]


@pytest.mark.parametrize("mutation", ["stale", "future", "research", "no_catalyst", "no_sources", "no_marketcap",
                                       "spread", "invalidated", "expired", "no_nav", "no_exit", "live", "halted_quote"])
def test_entry_gates_fail_closed(mutation):
    args = case()
    now = NOW + timedelta(seconds=120)
    run(args)
    advance(args, now)
    entry, snapshot, quote = args[0].entries[0], args[1], args[2][0]
    if mutation == "stale":
        quote.at -= timedelta(seconds=61)
    elif mutation == "future":
        snapshot.captured_at += timedelta(seconds=1)
    elif mutation == "research":
        entry.reviewed_at -= timedelta(hours=1)
    elif mutation == "no_catalyst":
        entry.catalyst = ""
    elif mutation == "no_sources":
        entry.sources.clear()
    elif mutation == "no_marketcap":
        entry.market_cap_usd = None
    elif mutation == "spread":
        quote.bid = 145
    elif mutation == "invalidated":
        entry.invalidated = True
    elif mutation == "expired":
        args[0].as_of -= timedelta(days=1)
    elif mutation == "no_nav":
        snapshot.high_water_nav = None
    elif mutation == "no_exit":
        entry.exit_at = None
    elif mutation == "live":
        snapshot.env = "live"
    elif mutation == "halted_quote":
        quote.tradable = False
    assert not run(args, now)["orders"]


@pytest.mark.parametrize("mutation", ["oi", "volume", "dte", "premium", "greeks", "disabled"])
def test_option_entry_gates(mutation):
    args = case(True)
    run(args)
    advance(args, NOW + timedelta(seconds=120))
    quote = args[2][-1]
    if mutation == "oi":
        quote.open_interest = 0
    elif mutation == "volume":
        quote.volume = 0
    elif mutation == "dte":
        args[7].tactical.min_option_dte = 10
    elif mutation == "premium":
        quote.ask = 8
    elif mutation == "greeks":
        quote.delta = None
    elif mutation == "disabled":
        args[7].tactical.options_enabled = False
    assert not run(args, NOW + timedelta(seconds=120))["orders"]


@pytest.mark.parametrize("option", [False, True])
def test_stale_watchlist_and_halt_preserve_exit_and_latch(option):
    args = case(option, held=True)
    entry = args[0].entries[0]
    args[6].protected[entry.symbol] = entry.model_copy(deep=True)
    args[0].entries = []
    args[0].as_of -= timedelta(days=1)
    args[2][0].last = 160 if option else 140
    if not option:
        args[2][0].bid, args[2][0].ask = 139.95, 140.05
    result = plan_tick(*args, NOW, halted=True)
    assert result["orders"][0]["intent"]["side"] == "sell", result
    advance(args, NOW + timedelta(seconds=120))
    args[2][0].last, args[2][0].bid, args[2][0].ask = 150, 149.95, 150.05
    assert run(args, NOW + timedelta(seconds=120))["orders"][0]["intent"]["side"] == "sell"


def test_expiry_half_day_exit_and_premium_drawdown():
    args = case(True, held=True)
    now = datetime(2026, 11, 27, 17, 20, tzinfo=UTC)  # 40 minutes before 13:00 ET close
    advance(args, now)
    result = run(args, now)
    assert "expiry" in result["orders"][0]["intent"]["reason"]
    args = case(True, held=True)
    args[2][-1].last, args[2][-1].bid, args[2][-1].ask = 3.4, 3.35, 3.45
    assert "40%" in run(args)["orders"][0]["intent"]["reason"]


def test_options_multiplier_cash_and_fee_net_pnl():
    intent = OrderIntent(symbol=OPT, option=CONTRACT, side="buy", quantity=2, limit_price=6, reason="test")
    snapshot = AccountSnapshot(account_id="SIM-TEST", cash=10000, frozen_cash=2000)
    bought = apply_fill(snapshot, intent, 2)
    assert intent.notional == 1200 and bought.cash == 8800 and bought.nav == 12000
    assert bought.positions[0].market_value == 1200
    sold = apply_fill(bought, intent.model_copy(update={"side": Side.SELL}), 2, fill_price=7)
    assert sold.cash == 10200 and not sold.positions
    broker = PaperBroker(snapshot)
    broker.submit(intent)
    assert broker.snapshot().cash == 8800
    fees = [estimate_fees(OPT, "buy", 2, 6, "option"), estimate_fees(OPT, "sell", 2, 7, "option")]
    assert reconcile_cash(10000, 10200 - sum(f.total for f in fees), [(2, 6, 100), (-2, 7, 100)], fees).ok
    events = [{"type": "order.filled", "ts": str(i), "payload": {
        "symbol": OPT, "option": CONTRACT.model_dump(mode="json"), "side": side,
        "quantity": 2, "price": price,
    }} for i, (side, price) in enumerate([("buy", 6), ("sell", 7)])]
    report = compute_expectancy(events, {"US.NVDA": "equity"})
    trade = report.closed_trades[0]
    assert trade.pnl_gross == 200 and trade.multiplier == 100
    assert trade.initial_risk_usd == 1200 + fees[0].total
    assert trade.pnl_net == round(200 - sum(f.total for f in fees), 4)
    events[0]["payload"].pop("option")
    assert compute_expectancy(events, {}).unattributed_fills == 2


def test_snapshot_frozen_cash_and_unknown_contract_fail_closed():
    accounts = {"data": {"accounts": [{"account_id": "SIM-TEST", "account_type": 2, "market_id": 100}]}}
    cash = {"data": {"balance": "10000", "hold": "2000", "total_asset": "12600"}}
    positions = {"data": {"positions": [{"symbol": OPT, "qty": "1", "qty_avbl": "1", "cur_price": "6", "cost_price": "6"}]}}
    with pytest.raises(ValueError, match="metadata"):
        build_snapshot("SIM-TEST", accounts, cash, positions)
    snapshot = build_snapshot("SIM-TEST", accounts, cash, positions, contracts={OPT: CONTRACT})
    assert snapshot.nav == snapshot.broker_nav == 12600
    with pytest.raises(ValueError, match="array missing"):
        extract_positions({"data": {}})
    with pytest.raises(ValueError):
        OrderIntent(symbol=OPT, side="sell", quantity=1, limit_price=6, reason="test")
    intent = OrderIntent(symbol=OPT, option=CONTRACT, side="sell", quantity=2, limit_price=6, reason="test")
    with pytest.raises(ValueError, match="available"):
        apply_fill(snapshot, intent, 2)


def test_full_debit_risk_and_pending_exposure():
    args = case(True)
    intent = OrderIntent(symbol=OPT, option=CONTRACT, side="buy", quantity=2, limit_price=6, reason="test")
    verdict = evaluate_intent(intent, args[1], args[7].risk, RiskState(nav=100000), 6, {"US.NVDA"}, {}, underlying_price=150)
    assert any(b.rule == "trade.risk_budget" for b in verdict.breaches)
    state = RiskState(nav=100000, pending_orders=[intent])
    verdict = evaluate_intent(intent, args[1], args[7].risk, state, 6, {"US.NVDA"}, {}, underlying_price=150)
    assert any(b.rule == "order.pending" for b in verdict.breaches)


def test_cumulative_envelope_and_broker_budget():
    batch = ApprovalBatch(as_of=NOW.date(), approved_at=NOW, max_orders=10,
                          orders=[{"symbol": OPT, "side": "buy", "max_qty": 2, "limit_max": 7, "multiplier": 100}])
    kwargs = {"symbol": OPT, "side": "buy", "qty": 1, "limit": 6, "today": NOW.date(), "used": 1, "multiplier": 100}
    assert not authorize_order(batch, **kwargs, used_qty=2)[0]
    assert authorize_order(batch, **kwargs, used_qty=1)[0]
    events = [{"type": "order.requested", "ts": NOW.isoformat(), "payload": {
        "request_id": "r1", "symbol": OPT, "side": "buy", "quantity": 1, "limit_price": 6, "multiplier": 100,
        "authorization": {"kind": "envelope", "as_of": str(NOW.date())}}}]
    assert envelope_totals(events, NOW.date(), OPT, "buy") == (1, 600)
    rows = [{"order_id": "o1", "text": "r1", "symbol": OPT, "qty": "1", "cum_qty": "1",
             "side": 1, "price": "6", "status": 4, "create_time": int(NOW.timestamp() * 1e6)}]
    assert combined_usage(events, rows, NOW.date(), {OPT: CONTRACT}) == (1, 600)
    assert not unresolved_symbols(events, rows)
    rows[0]["cum_qty"] = "0"
    rows[0]["status"] = 2
    assert unresolved_symbols(events, rows) == {OPT}
    assert pending_intents(rows, {OPT: CONTRACT})[0].notional == 600
    rows[0]["qty"] = "1.5"
    with pytest.raises(ValueError):
        pending_intents(rows, {OPT: CONTRACT})


def write_cli_case(tmp_path, args):
    paths = {key: tmp_path / f"{key}.json" for key in ("book", "account", "quotes", "orders", "envelope", "audit", "lifecycle-state")}
    paths["book"].write_text(args[0].model_dump_json(), encoding="utf-8")
    paths["account"].write_text(args[1].model_dump_json(), encoding="utf-8")
    paths["quotes"].write_text(json.dumps([q.model_dump(mode="json") for q in args[2]]), encoding="utf-8")
    paths["orders"].write_text(json.dumps({"ret_code": 0, "data": {"orders": []}}), encoding="utf-8")
    paths["lifecycle-state"].write_text("{}", encoding="utf-8")
    return paths


def test_tactical_reservation_respects_disabled_gate(tmp_path, monkeypatch):
    args = case()
    args[7].tactical.execution_enabled = False
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda _: args[7])
    paths = write_cli_case(tmp_path, args)
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    monkeypatch.setattr("tyche.tactical_cli.now_utc", lambda: NOW)
    cmd = ["tactical", "reserve", "--symbol", "US.NVDA", "--journal", str(journal), "--config-root", str(ROOT)]
    for key, path in paths.items():
        cmd.extend(["--" + key, str(path)])
    result = CliRunner().invoke(app, cmd)
    assert result.exit_code == 1 and "rollout gate disabled" in result.output
    assert len(read_events(journal)) == 1


@pytest.mark.parametrize("blocker", [None, "audit", "exit", "setup", "date", "pending", "corruption", "stalequote"])
def test_exact_reservation_is_atomic_and_one_shot(tmp_path, monkeypatch, blocker):
    args = case(True)
    args[7].tactical.execution_enabled = True  # synthetic drill only
    proposal = ready(args)["orders"][0]
    now = NOW + timedelta(seconds=120)
    paths = write_cli_case(tmp_path, args)
    batch = ApprovalBatch(as_of=NOW.date(), approved_at=NOW, max_orders=5, orders=[
        {"symbol": OPT, "side": "buy", "max_qty": 1, "limit_max": 6.1, "multiplier": 100, "setup_hash": proposal["setup_hash"]},
        {"symbol": OPT, "side": "sell", "max_qty": 1, "limit_min": .01, "multiplier": 100, "setup_hash": proposal["setup_hash"]}])
    paths["envelope"].write_text(batch.model_dump_json(), encoding="utf-8")
    paths["audit"].write_text(json.dumps({"order_hash": proposal["order_hash"], "reviewed_at": now.isoformat(),
        "valid_until": (now + timedelta(seconds=60)).isoformat(), "verdict": "approved", "reference": "synthetic auditor"}), encoding="utf-8")
    journal = tmp_path / "events.jsonl"
    append_event(journal, "tactical.monitor", {"state": args[6].model_dump(mode="json")})
    monkeypatch.setattr("tyche.tactical_cli.now_utc", lambda: now)
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda _: args[7])
    cmd = ["tactical", "reserve", "--symbol", OPT, "--journal", str(journal), "--config-root", str(tmp_path)]
    for key, path in paths.items():
        cmd.extend(["--" + key, str(path)])
    runner = CliRunner()
    if blocker:
        if blocker == "audit":
            data = json.loads(paths["audit"].read_text())
            data["order_hash"] = "different-order"
            paths["audit"].write_text(json.dumps(data))
        elif blocker in {"exit", "setup", "date"}:
            if blocker == "exit":
                batch.orders.pop()
            elif blocker == "setup":
                batch.orders[0].setup_hash = "different-setup"
            else:
                batch.as_of -= timedelta(days=1)
            paths["envelope"].write_text(batch.model_dump_json())
        elif blocker == "pending":
            paths["orders"].write_text(json.dumps({"ret_code": 0, "data": {"orders": [{
                "order_id": "pending-1", "symbol": OPT, "side": 1, "qty": "1", "cum_qty": "0",
                "price": "6.05", "status": 2, "create_time": int(now.timestamp() * 1e6)}]}}))
        elif blocker == "corruption":
            journal.write_text("not json")
        elif blocker == "stalequote":
            data = json.loads(paths["quotes"].read_text())
            data[-1]["at"] = NOW.isoformat()
            paths["quotes"].write_text(json.dumps(data))
        denied = runner.invoke(app, cmd)
        assert denied.exit_code == 1, denied.output
        if blocker != "corruption":
            assert not any(e["type"] == "order.requested" for e in read_events(journal))
        return
    with journal_lock(journal):
        locked = runner.invoke(app, cmd)
        assert locked.exit_code == 1 and "busy" in locked.output
    first = runner.invoke(app, cmd)
    assert first.exit_code == 0, first.output
    payload = json.loads(first.stdout)
    assert payload["authorized"] and not payload["submitted"]
    assert runner.invoke(app, cmd).exit_code == 1
    assert len([e for e in read_events(journal) if e["type"] == "order.requested"]) == 1
    assert verify_chain(journal)[0]


def test_setup_hash_changes_with_risk_or_exit_but_not_review_time():
    args = case()
    entry, config = args[0].entries[0], args[7]
    old = setup_hash(entry, config, "SIM-TEST")
    entry.reviewed_at += timedelta(seconds=5)
    assert old == setup_hash(entry, config, "SIM-TEST")
    entry.stop += 1
    assert old != setup_hash(entry, config, "SIM-TEST")


def test_call_entry_and_stock_strategy_ownership():
    from tyche.models import RotationResult
    from tyche.strategies import build_intents
    args = case(True)
    call = OptionContract(underlying="US.NVDA", expiry=date(2026, 11, 27), right="call", strike=145)
    entry = args[0].entries[0]
    entry.symbol, entry.option, entry.direction = "US.NVDA261127C145000", call, "bullish"
    entry.stop, entry.target = 145, 165
    quote = args[2][-1]
    quote.symbol, quote.option, quote.delta = entry.symbol, call, .6
    result = ready(args)
    assert result["orders"][0]["risk"]["product"] == "long call"
    snapshot = AccountSnapshot(account_id="SIM-TEST", cash=90000, positions=[
        Position(symbol="US.NVDA", quantity=10, avg_cost=150, last_price=150),
        Position(symbol=OPT, option=CONTRACT, quantity=1, avg_cost=6, last_price=6)])
    rotation = RotationResult(regime="risk_on", targets={"CASH": 1.0}, signals={},
                              regime_checks={}, portfolio_vol=0, vol_scale=0)
    assert not build_intents(rotation, snapshot, {"US.NVDA": 150, OPT: 6}, args[7], args[7].strategy_by_id("PB-001"))


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1, 0])
def test_invalid_fill_price_never_mutates_account(price):
    snapshot = AccountSnapshot(account_id="SIM-TEST", cash=10000)
    intent = OrderIntent(symbol="US.NVDA", quantity=1, side="buy", limit_price=150, reason="test")
    with pytest.raises(ValueError, match="finite and positive"):
        apply_fill(snapshot, intent, 1, fill_price=price)
    assert snapshot.cash == 10000 and not snapshot.positions


def test_quote_normalization_matches_observed_mcp_fields():
    stamp = int(NOW.timestamp() * 1000)
    quotes = {"ret_code": 0, "data": {"quote_list": [{"code": OPT, "data_time": stamp, "last_price": 6,
        "volume": 500, "sec_status": "NORMAL", "suspension": False, "option_ex_data": {
            "contract_multiplier": 100, "strike_price": 155, "option_type": "PUT", "delta": -.6, "open_interest": 400, "implied_volatility": 55}}]}}
    books = [{"ret_code": 0, "data": [{"code": OPT, "books": [{"exchange_data_time_ms": stamp,
        "bid_list": [{"price": 5.95, "volume": 20}], "ask_list": [{"price": 6.05, "volume": 30}]}]}]}]
    chains = [{"ret_code": 0, "data": {"option_chain": [{"code": OPT, "stock_owner": "US.NVDA",
        "strike_time": "2026-11-27", "strike_price": 155, "option_type": "PUT", "option_standard_type": "STANDARD", "lot_size": 100}]}}]
    q = normalize_quotes(quotes, books, chains)[0]
    assert q.option == CONTRACT and q.bid == 5.95 and q.fresh(NOW, 60)
    quotes["data"]["quote_list"][0]["option_ex_data"]["contract_multiplier"] = 10
    with pytest.raises(ValueError, match="multiplier"):
        normalize_quotes(quotes, books, chains)
