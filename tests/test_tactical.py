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
from tyche.market_calendar import ET
from tyche.models import AccountSnapshot, OptionContract, OrderIntent, Position, Side, apply_fill
from tyche.risk import RiskState, evaluate_intent
from tyche.tactical import MarketQuote, MonitorState, config_hash, plan_tick, setup_hash
from tyche.trade_risk import compute_expectancy
from tyche.watchlist import Factor, Outlook, Watchlist, WatchlistEntry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 19, 15, 5, tzinfo=UTC)
OPT = "US.NVDA261127P155000"
CONTRACT = OptionContract(underlying="US.NVDA", expiry=date(2026, 11, 27), right="put", strike=155)
# Every order needs a written technical AND fundamental reason (operator rule 2026-11-24).
REASONS = (Factor(name="reclaim", axis="technical", state="pass", why="closed above 151 on volume"),
           Factor(name="guidance raise", axis="fundamental", state="pass", why="FY guide lifted 8%"))


def case(option=False, held=False):
    config = load_config(ROOT)
    config.tactical.enabled = True  # PB-004 owns live symbols in repo config; tests opt in
    config.tactical.options_enabled = True
    # Pin the lane universe to the fixture symbol so tests do not track live config.
    config.tactical.symbols = ["US.NVDA"]
    config.tactical.etf_symbols = []
    config.tactical.monitor_interval_seconds = 120
    # Pin the clocks too: these drills test the mechanisms at a two-minute cadence, whatever the live
    # lane in config/tactical.yaml is set to (15-minute agent runs from 2026-11-25).
    config.tactical.max_quote_age_seconds = 120
    config.tactical.max_snapshot_age_seconds = 120
    config.tactical.max_confirmation_ticks = 5
    config.tactical.max_review_age_seconds = 1800
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
                           exit_at=NOW.replace(hour=20, minute=45), factors=list(REASONS))
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


def test_plan_carries_the_per_trade_thesis_block():
    book, snapshot, quotes, orders, events, contracts, state, config = case()
    book.entries[0] = book.entries[0].model_copy(update={
        "synthesis": "Reclaimed 151 on volume",
        "edge": "2R into the prior high",
        "bear_case": "fails back below 145",
        "invalidation": "daily close below 145",
        "horizon": "2-4 weeks",
        "thesis_ref": "scout-2026-11-19-nvda",
        "factors": [*REASONS, Factor(name="CPI print", axis="macro", state="unknown", why="not published")],
        "outlook": Outlook(regime="neutral", conviction="medium",
                           alignment={"technical": "bull", "macro": "neutral"}),
    })
    args = [book, snapshot, quotes, orders, events, contracts, state, config]
    result = ready(args)
    thesis = result["orders"][0]["thesis"]
    assert thesis["thesis"] == "Synthetic catalyst thesis"
    assert thesis["thesis_ref"] == "scout-2026-11-19-nvda"
    assert thesis["direction"] == "bullish" and thesis["source"] == "scout"
    assert {f["axis"] for f in thesis["factors"]} == {"technical", "fundamental", "macro"}
    assert result["orders"][0]["reasons"] == {"technical": "reclaim: closed above 151 on volume",
                                              "fundamental": "guidance raise: FY guide lifted 8%"}
    assert thesis["outlook"]["conviction"] == "medium"
    assert thesis["invalidation"] == "daily close below 145"


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
    config.risk.max_option_premium_pct = 0.25  # boundary fixture: 24,400 held + 600 = 25% of 100k NAV
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
    if stale == "quote":  # freshness is the order book's own time (2026-11-25): an old book is stale
        args[2][0].book_at -= timedelta(seconds=args[7].tactical.max_quote_age_seconds + 1)
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
        quote.book_at -= timedelta(seconds=args[7].tactical.max_quote_age_seconds + 1)
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


@pytest.mark.parametrize("mutation", ["oi", "volume", "dte", "premium", "greeks", "disabled", "switched_off"])
def test_option_entry_gates(mutation, monkeypatch):
    args = case(True)
    if mutation == "switched_off":  # PB-003 off in the operator switch file (2026-11-24 switch route)
        monkeypatch.setattr(type(args[7]), "strategy_enabled", lambda self, pid: pid != "PB-003")
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
        args[7].tactical.enabled = False
    assert not run(args, NOW + timedelta(seconds=120))["orders"]


@pytest.mark.parametrize("volume,bid,ask,allowed", [
    (20, 5.70, 6.30, True),
    (19, 5.95, 6.05, False),
    (20, 5.60, 6.40, False),
])
def test_relaxed_option_spread_and_volume_boundaries(volume, bid, ask, allowed):
    args = case(True)
    args[0].entries[0].premium_limit = 7.1
    quote = args[2][-1]
    quote.volume, quote.bid, quote.ask, quote.last = volume, bid, ask, ask
    assert not run(args)["orders"]
    now = NOW + timedelta(seconds=120)
    advance(args, now)
    result = run(args, now)
    assert bool(result["orders"]) is allowed, result
    if not allowed:
        reason = next(d["reason"] for d in result["decisions"] if d["symbol"] == OPT)
        assert "spread" in reason or "liquidity" in reason


def test_option_entry_needs_the_pb003_switch_not_the_yaml(monkeypatch):
    args = case(True)
    args[7].tactical.options_enabled = False  # the yaml flag no longer gates entries
    monkeypatch.setattr(type(args[7]), "strategy_enabled", lambda self, pid: True)
    run(args)
    advance(args, NOW + timedelta(seconds=120))
    assert run(args, NOW + timedelta(seconds=120))["orders"], "switch on must let a valid long option enter"


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
    risk = args[7].risk
    # A debit one contract bigger than the per-trade premium budget, read from the policy rather than
    # hard-coded, so "too big" still means too big when the operator moves the cap (2026-11-25: 0.75% ->
    # 1.5% of NAV, which is what made one NVDA Dec-18 150 call affordable at all).
    too_big = 1 + int(risk.option_risk_per_trade_pct * 100000 // 600)
    intent = OrderIntent(symbol=OPT, option=CONTRACT, side="buy", quantity=too_big,
                         limit_price=6, reason="test")
    verdict = evaluate_intent(intent, args[1], args[7].risk, RiskState(nav=100000), 6, {"US.NVDA"}, {}, underlying_price=150)
    assert any(b.rule == "trade.risk_budget" for b in verdict.breaches)
    state = RiskState(nav=100000, pending_orders=[intent])
    verdict = evaluate_intent(intent, args[1], args[7].risk, state, 6, {"US.NVDA"}, {}, underlying_price=150)
    assert any(b.rule == "order.pending" for b in verdict.breaches)


def test_the_shipped_option_budget_buys_the_contract_the_filters_allow():
    """At 0.75% of NAV the budget was ~$740 and the desk could not size anything it was allowed to trade.

    The only tactical contract clearing PB-003's own liquidity gates on 2026-11-25 was the NVDA 18 Dec
    150 call at 9.70, i.e. $970 plus fees. `config/risk.yaml` is not a lane rules file, so no rules hash
    notices this number move - this test is the catch, and the lane's ceiling stays inside the 2% the
    model allows (PB-003 page).
    """
    risk = load_config(ROOT).risk
    nav = 98_831.14  # paper NAV read 2026-11-25, account flat
    debit = 970 + estimate_fees("US.NVDA261218C150000", "buy", 1, 9.70, "option").total
    assert int(risk.option_risk_per_trade_pct * nav) >= debit
    assert risk.option_risk_per_trade_pct <= 0.02
    assert risk.max_option_premium_pct == pytest.approx(0.05)


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
    paths = {key: tmp_path / f"{key}.json" for key in ("book", "account", "quotes", "orders", "envelope", "lifecycle-state")}
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


@pytest.mark.parametrize("blocker", [None, "unbound", "exit", "setup", "date", "pending", "corruption", "stalequote"])
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
    journal = tmp_path / "events.jsonl"
    append_event(journal, "tactical.monitor", {"state": args[6].model_dump(mode="json")})
    monkeypatch.setattr("tyche.tactical_cli.now_utc", lambda: now)
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda _: args[7])
    cmd = ["tactical", "reserve", "--symbol", OPT, "--journal", str(journal), "--config-root", str(tmp_path)]
    for key, path in paths.items():
        cmd.extend(["--" + key, str(path)])
    runner = CliRunner()
    if blocker == "unbound":
        # The operator's symbol-level pre-approval: no setup hash on either line still authorizes the
        # kernel's own setup inside the line's bounds.
        for line in batch.orders:
            line.setup_hash = None
        paths["envelope"].write_text(batch.model_dump_json())
        blocker = None
    if blocker:
        if blocker in {"exit", "setup", "date"}:
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
            data[-1]["book_at"] = (NOW - timedelta(seconds=1)).isoformat()
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


def test_private_account_injection_does_not_change_the_rules_fingerprint(monkeypatch):
    monkeypatch.delenv("TYCHE_ALLOWED_ACCOUNT_IDS", raising=False)
    before = load_config(ROOT)
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "PRIVATE-PAPER-ID")
    after = load_config(ROOT)
    assert "PRIVATE-PAPER-ID" in after.risk.account_allowlist
    assert config_hash(after) == config_hash(before)


def test_held_setup_records_its_current_config_hash():
    args = case(held=True)
    state, config = args[6], args[7]
    run(args)
    assert state.protected_hashes["US.NVDA"] == setup_hash(args[0].entries[0], config, "SIM-TEST")


def test_routine_ticks_do_not_rebind_a_changed_config():
    args = case(held=True)
    state, config = args[6], args[7]
    old_hash = setup_hash(args[0].entries[0], config, args[1].account_id)
    state.protected_hashes["US.NVDA"] = old_hash
    config.tactical.min_option_volume += 1
    assert setup_hash(args[0].entries[0], config, args[1].account_id) != old_hash
    run(args)
    assert state.protected_hashes["US.NVDA"] == old_hash


def test_only_a_deliberate_monitor_event_can_replace_a_trusted_setup_hash():
    from tyche.tactical_cli import monitor_state
    args = case(held=True)
    entry, config = args[0].entries[0], args[7]
    old_hash = setup_hash(entry, config, args[1].account_id)
    monitored = MonitorState(protected={entry.symbol: entry}, protected_hashes={entry.symbol: "b" * 64})
    requested = {"type": "order.requested", "payload": {"protected_setup": entry.model_dump(mode="json"),
                                                          "setup_hash": old_hash}}
    routine = {"type": "tactical.monitor", "payload": {"state": monitored.model_dump(mode="json")}}
    rebound = {"type": "tactical.monitor", "payload": {"state": monitored.model_dump(mode="json"),
                                                        "rebind": {"reason": "operator rule change"}}}
    assert monitor_state([requested, routine]).protected_hashes[entry.symbol] == old_hash
    assert monitor_state([requested, rebound]).protected_hashes[entry.symbol] == "b" * 64


def test_rebind_updates_a_held_setup_without_requesting_an_order(tmp_path, monkeypatch):
    args = case(True, held=True)
    entry, snapshot, config = args[0].entries[0], args[1], args[7]
    old_config = config.model_copy(deep=True)
    old_config.tactical.min_option_volume = 50
    old_hash = setup_hash(entry, old_config, snapshot.account_id)
    new_hash = setup_hash(entry, config, snapshot.account_id)
    assert old_hash != new_hash
    snapshot.broker_nav = snapshot.nav
    account = tmp_path / "tactical-account.json"
    account.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    journal = tmp_path / "journal" / "events.jsonl"
    journal.parent.mkdir()
    append_event(journal, "order.requested", {
        "symbol": entry.symbol, "side": "buy", "quantity": 1, "limit_price": 6,
        "protected_setup": entry.model_dump(mode="json"), "setup_hash": old_hash,
    })
    monkeypatch.setattr("tyche.tactical_cli.now_utc", lambda: NOW)
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda root: config)
    command = ["tactical", "rebind", "--account", str(account), "--journal", str(journal),
               "--config-root", str(ROOT), "--reason", "test option gate change"]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    events = read_events(journal)
    assert [e["type"] for e in events] == ["order.requested", "tactical.monitor"]
    assert events[-1]["payload"]["state"]["protected_hashes"][entry.symbol] == new_hash
    assert events[-1]["payload"]["rebind"]["updated"] == [entry.symbol]
    assert verify_chain(journal)[0]
    count = len(events)
    snapshot.captured_at = NOW - timedelta(seconds=config.tactical.max_snapshot_age_seconds + 1)
    account.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    stale = CliRunner().invoke(app, command)
    assert stale.exit_code != 0
    assert len(read_events(journal)) == count
    snapshot.captured_at = NOW
    snapshot.broker_nav = None
    account.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    missing_nav = CliRunner().invoke(app, command)
    assert missing_nav.exit_code != 0 and "no broker NAV" in missing_nav.output
    assert len(read_events(journal)) == count


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


def test_normalization_consolidates_multi_venue_books_to_nbbo():
    stamp = int(NOW.timestamp() * 1000)
    quotes = {"ret_code": 0, "data": {"quote_list": [{"code": "US.MU", "data_time": stamp,
        "last_price": 730.01, "volume": 1000, "sec_status": "NORMAL", "suspension": False}]}}
    books = [{"ret_code": 0, "data": [{"code": "US.MU", "books": [
        {"exchange": "NASDAQ", "exchange_data_time_ms": stamp,
         "bid_list": [{"price": 731.7, "volume": 3}], "ask_list": [{"price": 732.17, "volume": 177}]},
        {"exchange": "ARCA", "exchange_data_time_ms": stamp - 500,
         "bid_list": [{"price": 731.61, "volume": 30}], "ask_list": [{"price": 732.16, "volume": 20}]},
    ]}]}]
    q = normalize_quotes(quotes, books, [])[0]
    assert q.bid == 731.7 and q.ask == 732.16
    assert q.book_at == datetime.fromtimestamp((stamp - 500) / 1000, UTC)


def test_normalization_skips_venues_without_two_sided_market():
    stamp = int(NOW.timestamp() * 1000)
    quotes = {"ret_code": 0, "data": {"quote_list": [{"code": "US.MU", "data_time": stamp,
        "last_price": 730.01, "volume": 1000, "sec_status": "NORMAL", "suspension": False}]}}
    books = [{"ret_code": 0, "data": [{"code": "US.MU", "books": [
        {"exchange": "NASDAQ", "exchange_data_time_ms": stamp,
         "bid_list": [{"price": 731.7, "volume": 3}], "ask_list": [{"price": 732.17, "volume": 177}]},
        {"exchange": "ARCA", "exchange_data_time_ms": stamp,
         "bid_list": [{"price": 731.61, "volume": 0}], "ask_list": [{"price": 732.16, "volume": 20}]},
    ]}]}]
    q = normalize_quotes(quotes, books, [])[0]
    assert q.bid == 731.7 and q.ask == 732.17


def test_exact_reservation_runs_on_a_journaled_telegram_approval_without_an_envelope(tmp_path, monkeypatch):
    """Ask me mode: no data/approvals.json anywhere; the operator's /approve N, journaled with the
    proposal's order block (setup-bound, with its exit floor), is the whole yes for exactly that order."""
    args = case(True)
    args[7].tactical.execution_enabled = True  # synthetic drill only
    proposal = ready(args)["orders"][0]
    now = NOW + timedelta(seconds=120)
    paths = write_cli_case(tmp_path, args)
    assert not paths["envelope"].exists()
    journal = tmp_path / "events.jsonl"
    append_event(journal, "tactical.monitor", {"state": args[6].model_dump(mode="json")})
    approval = {"as_of": NOW.date().isoformat(), "ref": "ab12cd34", "n": 1, "symbol": OPT, "side": "buy",
                "qty": 1, "limit": 6.1, "multiplier": 100, "setup_hash": proposal["setup_hash"],
                "exit_floor": 0.01, "decided_at": NOW.isoformat()}
    monkeypatch.setattr("tyche.tactical_cli.now_utc", lambda: now)
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda _: args[7])
    cmd = ["tactical", "reserve", "--symbol", OPT, "--journal", str(journal), "--config-root", str(tmp_path)]
    for key, path in paths.items():
        cmd.extend(["--" + key, str(path)])
    runner = CliRunner()
    nothing = runner.invoke(app, cmd)
    assert nothing.exit_code == 1 and "no Telegram approval journaled today" in nothing.output
    append_event(journal, "approval.telegram", {**approval, "setup_hash": "someone-elses-setup"})
    unbound = runner.invoke(app, cmd)
    assert unbound.exit_code == 1 and "bind the complete setup" in unbound.output
    append_event(journal, "approval.telegram", approval)
    first = runner.invoke(app, cmd)
    assert first.exit_code == 0, first.output
    payload = json.loads(first.stdout)
    assert payload["authorized"] and payload["request"]["authorization"] == {"kind": "telegram", "as_of": NOW.date().isoformat()}
    assert runner.invoke(app, cmd).exit_code == 1  # one yes, one order
    assert len([e for e in read_events(journal) if e["type"] == "order.requested"]) == 1
    assert verify_chain(journal)[0]


# --- Resting orders (operator direction 2026-11-24): place the order, do not wait for a run -------------


def _ready_at(args, price):
    """Two distinct fresh quotes at `price`, as the confirmation gate needs."""
    for q in args[2]:
        q.last, q.bid, q.ask = price, price - 0.05, price + 0.05
    run(args)
    now = NOW + timedelta(seconds=120)
    advance(args, now)
    return run(args, now), now


def test_a_price_just_above_the_zone_rests_a_day_limit_at_the_zone_top_with_both_reasons():
    args = case()
    report, _ = _ready_at(args, 153)   # zone 149-151, reach 3% -> up to 155.53
    [order] = report["orders"]
    assert order["intent"]["side"] == "buy" and order["intent"]["limit_price"] == 151
    assert order["resting"]["kind"] == "entry" and order["resting"]["time_in_force"] == "day"
    assert order["resting"]["expires"].startswith("2026-11-19T16:00")
    assert order["reasons"]["technical"] and order["reasons"]["fundamental"]
    assert order["cancel_first"] == [] and order["protective"] is False
    # Sized from the resting price, never from the chased price.
    stop_distance = 151 - 145
    assert order["intent"]["quantity"] <= args[7].risk.risk_per_trade_pct * 100000 / stop_distance


def test_a_price_beyond_the_reach_is_still_not_chased():
    args = case()
    report, _ = _ready_at(args, 156)
    assert not report["orders"]
    assert report["decisions"][0]["reason"] == "outside entry zone; do not chase"


def test_no_resting_entry_in_the_last_hour_and_none_when_switched_off():
    args = case()
    late = datetime(2026, 11, 19, 20, 10, tzinfo=UTC)  # 15:10 ET, inside the 60-minute cutoff
    for q in args[2]:
        q.last, q.bid, q.ask = 153, 152.95, 153.05
    args[1].captured_at = late
    for q in args[2]:
        q.at = q.book_at = late
    args[0].entries[0].exit_at = late + timedelta(minutes=20)
    run(args, late)
    later = late + timedelta(seconds=120)
    advance(args, later)
    assert not run(args, later)["orders"]
    args = case()
    args[7].tactical.resting_entries = False
    report, _ = _ready_at(args, 153)
    assert not report["orders"]


def test_premarket_rests_the_entry_for_the_open_but_never_sells():
    args = case()
    pre = datetime(2026, 11, 19, 13, 10, tzinfo=UTC)  # 08:10 ET
    args[1].captured_at = pre
    args[0].entries[0].reviewed_at = pre
    for q in args[2]:
        q.at = q.book_at = pre
        q.last, q.bid, q.ask = 150, 149.5, 150.5   # inside the zone, wide premarket spread
    run(args, pre)
    later = pre + timedelta(seconds=120)
    advance(args, later)
    report = run(args, later)
    [order] = report["orders"]
    assert order["intent"]["limit_price"] == 151 and order["resting"]["kind"] == "entry"
    held = case(held=True)
    held[1].captured_at = later
    for q in held[2]:
        q.at = q.book_at = later
        q.last = 140  # stop would be hit in the session
    report = run(held, later)
    assert not report["orders"] and "premarket" in report["decisions"][0]["reason"]


def test_an_entry_without_a_fundamental_reason_is_refused():
    args = case()
    args[0].entries[0].factors = [REASONS[0]]
    assert not ready(args)["orders"]
    assert "fundamental" in run(args, NOW + timedelta(seconds=120))["decisions"][0]["reason"]


def test_a_held_lot_gets_a_resting_take_profit_at_the_target_without_latching():
    args = case(held=True)
    report = run(args)
    [order] = report["orders"]
    assert order["intent"]["side"] == "sell" and order["intent"]["limit_price"] == 165
    assert order["intent"]["quantity"] == 10 and order["resting"]["kind"] == "take_profit"
    assert order["reasons"]["fundamental"].startswith("guidance raise")
    assert order["protective"] is False and not args[6].latched_exits
    # Once it rests at the broker the lot is a hold, not a second sell.
    args[3].append(OrderIntent(symbol="US.NVDA", side=Side.SELL, quantity=10, limit_price=165, reason="resting"))
    report = run(args, NOW + timedelta(seconds=120))
    assert not report["orders"] and report["decisions"][0]["reason"].startswith("hold; take-profit sell resting")


def test_a_stop_breach_cancels_the_resting_take_profit_first_and_sells_the_whole_lot():
    args = case(held=True)
    args[1].positions[0].available_quantity = 0   # the broker locked the shares behind the resting sell
    args[3].append(OrderIntent(symbol="US.NVDA", side=Side.SELL, quantity=10, limit_price=165, reason="resting"))
    args[4].append({"order_id": 3124700, "symbol": "US.NVDA", "side": 2, "qty": 10, "cum_qty": 0, "price": 165,
                    "status": 2, "create_time": int(NOW.timestamp() * 1_000_000), "text": "tyche-tac-tp"})
    for q in args[2]:
        q.last, q.bid, q.ask = 144, 143.95, 144.05
    report = run(args)
    [order] = report["orders"]
    assert order["intent"]["side"] == "sell" and order["intent"]["quantity"] == 10
    assert order["intent"]["reason"] == "underlying stop breached" and order["protective"] is True
    assert order["cancel_first"] == ["3124700"]
    assert order["reasons"] == {"technical": "underlying stop breached", "fundamental": "guidance raise: FY guide lifted 8%"}
    assert args[6].latched_exits["US.NVDA"] == "underlying stop breached"


def test_a_cancelled_take_profit_hands_its_quantity_and_slot_back(tmp_path):
    from tyche.approvals import envelope_usage
    journal = tmp_path / "events.jsonl"
    auth = {"kind": "envelope", "as_of": NOW.astimezone(ET).date().isoformat()}
    append_event(journal, "order.requested", {"symbol": "US.KO", "side": "sell", "quantity": 51, "limit_price": 101,
                                             "request_id": "tyche-tac-tp", "authorization": auth})
    append_event(journal, "order.requested", {"symbol": "US.KO", "side": "sell", "quantity": 51, "limit_price": 95,
                                             "request_id": "tyche-tac-stop", "authorization": auth})
    today = NOW.astimezone(ET).date()
    assert envelope_totals(read_events(journal), today, "US.KO", "sell")[0] == 102
    assert envelope_usage(journal, today) == 2
    append_event(journal, "order.cancelled", {"request_id": "tyche-tac-tp", "order_id": "3124700"})
    assert envelope_totals(read_events(journal), today, "US.KO", "sell")[0] == 51
    assert envelope_usage(journal, today) == 1


def test_selling_a_held_lot_reserves_with_no_operator_line(tmp_path, monkeypatch):
    """Selling a lot the desk holds only removes risk, so the entry's approval is its authority: the
    resting take-profit and the stop exit both reserve with no envelope and no Telegram yes. Before
    2026-11-25 the take-profit and the stop that replaces it counted twice against one sell line."""
    args = case(held=True)
    args[7].tactical.execution_enabled = True  # synthetic drill only
    paths = write_cli_case(tmp_path, args)
    monkeypatch.setattr("tyche.tactical_cli.now_utc", lambda: NOW)
    monkeypatch.setattr("tyche.tactical_cli.load_config", lambda _: args[7])
    today = NOW.astimezone(ET).date().isoformat()

    def command(journal):
        append_event(journal, "tactical.monitor", {"state": args[6].model_dump(mode="json")})
        cmd = ["tactical", "reserve", "--symbol", "US.NVDA", "--journal", str(journal), "--config-root", str(tmp_path)]
        for key, path in paths.items():
            cmd.extend(["--" + key, str(path)])
        return cmd
    runner = CliRunner()
    # No exit trigger: the kernel offers the resting take-profit, and it reserves on the entry's authority.
    resting = runner.invoke(app, command(tmp_path / "events-tp.jsonl"))
    assert resting.exit_code == 0, resting.output
    payload = json.loads(resting.stdout)
    assert payload["request"]["reason"] == "resting take-profit at target"
    assert payload["request"]["authorization"] == {"kind": "protective", "as_of": today}
    # Stop breached: the protective sell is reserved with no envelope and no Telegram yes.
    data = json.loads(paths["quotes"].read_text())
    for row in data:
        row["last"], row["bid"], row["ask"] = 144, 143.95, 144.05
    paths["quotes"].write_text(json.dumps(data))
    journal = tmp_path / "events.jsonl"
    cmd = command(journal)
    first = runner.invoke(app, cmd)
    assert first.exit_code == 0, first.output
    payload = json.loads(first.stdout)
    assert payload["request"]["authorization"] == {"kind": "protective", "as_of": today}
    assert payload["request"]["reason"] == "underlying stop breached" and payload["request"]["cancel_first"] == []
    assert payload["request"]["reasons"]["technical"] == "underlying stop breached"
    assert "exit of a held lot" in payload["authority"]
    assert runner.invoke(app, cmd).exit_code == 1  # the reservation blocks a second sell until reconciled
    assert verify_chain(journal)[0]

# --- swing holds (operator direction 2026-11-25: no forced same-session close for stocks and options) ---

SWING_TO = NOW + timedelta(days=10)


def swing(args, **updates):
    """Retype the fixture setup as a swing plan; the levels and evidence stay identical."""
    args[0].entries[0] = args[0].entries[0].model_copy(update={"hold": "swing", "expiry": SWING_TO.date(),
                                                              **updates})
    return args


def test_a_session_lot_closes_at_the_exit_time_a_swing_lot_sits_through():
    args = case(held=True)
    late = NOW.replace(hour=20, minute=49)          # one minute before the 15:50 ET session exit
    advance(args, late)
    report = run(args, late)
    [order] = report["orders"]
    assert order["intent"]["reason"] == "time exit before next scheduled check"
    assert args[6].latched_exits == {"US.NVDA": "time exit before next scheduled check"}


def test_a_swing_lot_holds_through_the_session_exit_and_rests_its_target():
    args = swing(case(held=True), exit_at=None)
    late = NOW.replace(hour=20, minute=49)
    advance(args, late)
    report = run(args, late)
    [order] = report["orders"]
    assert order["intent"]["side"] == "sell" and order["intent"]["limit_price"] == 165
    assert order["resting"]["kind"] == "take_profit" and order["protective"] is False
    assert not args[6].latched_exits, "a swing lot must not be closed by the clock of a session"
    assert "swing hold" in order["risk"]["exit"]


def test_a_swing_lot_still_dies_on_its_own_hold_by_date():
    args = case(held=True)
    args[0].entries[0] = args[0].entries[0].model_copy(update={
        "hold": "swing", "expiry": (NOW - timedelta(days=1)).date(),
        "exit_at": (NOW - timedelta(days=1)).replace(hour=20, minute=45)})
    report = run(args)
    [order] = report["orders"]
    assert order["intent"]["reason"] == "swing hold deadline reached"
    assert args[6].latched_exits["US.NVDA"] == "swing hold deadline reached"


def test_a_swing_stop_and_target_still_bite_inside_the_session():
    args = swing(case(held=True), exit_at=None)
    for q in args[2]:
        q.last, q.bid, q.ask = 144, 143.95, 144.05   # under the 145 stop
    report = run(args)
    [order] = report["orders"]
    assert order["intent"]["reason"] == "underlying stop breached" and order["protective"] is True


def test_a_swing_entry_needs_no_exit_at_and_arms_late_in_the_day():
    args = swing(case(), exit_at=None)
    late = NOW.replace(hour=20, minute=46)           # a session plan is cut to 15:50 ET and refused here
    args[0].entries[0] = args[0].entries[0].model_copy(update={"reviewed_at": late})
    advance(args, late)
    assert not run(args, late)["orders"]             # the first tick only collects confirmations
    advance(args, late + timedelta(seconds=120))
    result = run(args, late + timedelta(seconds=120))
    assert len(result["orders"]) == 1, result["decisions"]
    assert result["orders"][0]["intent"]["side"] == "buy"


def test_a_session_entry_still_requires_an_explicit_exit_deadline():
    args = case()
    args[0].entries[0] = args[0].entries[0].model_copy(update={"exit_at": None})
    assert not ready(args)["orders"]
    assert "explicit exit deadline" in run(args, NOW + timedelta(seconds=120))["decisions"][0]["reason"]


def test_a_swing_option_with_no_exit_at_is_not_force_closed_at_the_session_exit():
    args = case(option=True, held=True)
    args[0].entries[0] = args[0].entries[0].model_copy(update={"hold": "session", "exit_at": None})
    late = NOW.replace(hour=20, minute=49)
    advance(args, late)
    report = run(args, late)
    assert [o for o in report["orders"] if o["intent"]["reason"] == "time exit before next scheduled check"]
    args = case(option=True, held=True)
    args[0].entries[0] = args[0].entries[0].model_copy(update={"hold": "swing", "expiry": SWING_TO.date(),
                                                               "exit_at": None})
    advance(args, late)
    report = run(args, late)
    assert not [o for o in report["orders"] if o["intent"]["side"] == "sell"
                and "time exit" in o["intent"]["reason"]], report["decisions"]
