"""PB-004 scalp: deterministic breakout, hard exits, budget and envelope arming."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tyche.approvals import ApprovalBatch
from tyche.config import ScalpConfig, load_config
from tyche.journal import append_event, read_events
from tyche.models import AccountSnapshot, OrderIntent
from tyche.scalp import (
    Bar,
    ScalpLot,
    ScalpState,
    bars_from_kline,
    breakout,
    plan_scalp,
    scalp_state,
)
from tyche.tactical import MarketQuote
from tyche.tactical_cli import _arm_scalp

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 19, 15, 30, tzinfo=UTC)  # 10:30 ET, mid-session
TODAY = NOW.date()


def quote(symbol: str = "US.NVDA", *, last: float = 100.0, bid: float = 99.99,
          ask: float = 100.01, at: datetime = NOW) -> MarketQuote:
    return MarketQuote(symbol=symbol, at=at, book_at=at, last=last, bid=bid, ask=ask,
                       tradable=True)


def snapshot(*, captured_at: datetime = NOW) -> AccountSnapshot:
    return AccountSnapshot(account_id="SIM-TEST", cash=100000.0, captured_at=captured_at,
                           env="paper", source="demo", prior_close_nav=100000.0,
                           high_water_nav=100000.0)


def breakout_bars(*, close: float = 100.6, base_high: float = 100.0) -> list[Bar]:
    bars = [Bar(at=NOW - timedelta(minutes=10 - i), open=99.5, high=base_high, low=99.0,
                close=99.8) for i in range(6)]
    bars.append(Bar(at=NOW, open=100.1, high=100.7, low=100.0, close=close))
    return bars


def config():
    cfg = load_config(ROOT)
    cfg.scalp = ScalpConfig(enabled=True)
    return cfg


def lot(symbol: str = "US.NVDA", **overrides) -> ScalpLot:
    fields = {"symbol": symbol, "quantity": 10, "entry": 100.0, "stop": 99.75,
              "target": 100.5, "opened_at": NOW - timedelta(minutes=2),
              "deadline": NOW + timedelta(minutes=18)}
    fields.update(overrides)
    return ScalpLot(**fields)


def test_kline_payload_parses_sorted_bars():
    payload = {"ret_code": 0, "data": {"kline_list": [
        {"time_key": int((NOW - timedelta(minutes=1)).timestamp() * 1000),
         "open_price": 1, "high_price": 2, "low_price": 0.5, "close_price": 1.5},
        {"time_key": int(NOW.timestamp() * 1000),
         "open_price": 1.5, "high_price": 3, "low_price": 1.4, "close_price": 2.5},
    ]}}
    bars = bars_from_kline(payload)
    assert [bar.close for bar in bars] == [1.5, 2.5]
    assert bars[-1].at == NOW


def test_breakout_needs_close_above_prior_highs_and_up_bar():
    assert breakout(breakout_bars(), 5)
    assert not breakout(breakout_bars(close=99.9), 5)          # below prior highs
    assert not breakout(breakout_bars()[:5], 5)                  # too few bars


def test_state_rebuilds_lots_cooldown_and_today_round_trips():
    # Explicit event stamps, not the wall clock: scalp_state keeps only requests and round
    # trips whose ET date equals `today`, so appending with the real clock made this test pass
    # on 2026-11-19 and fail every day after. Same shape as the sibling replay tests.
    events = [
        {"ts": "2026-11-19T15:30:00+00:00", "type": "plan.created", "payload": {"plan": {
            "nav": 100000.0, "orders": [{"intent": {
                "strategy_id": "PB-004", "symbol": "US.NVDA", "side": "buy", "stop_price": 99.75,
                "target_price": 100.5, "limit_price": 100.0}}]}}},
        {"ts": "2026-11-19T15:30:10+00:00", "type": "order.filled", "payload": {
            "strategy_id": "PB-004", "symbol": "US.NVDA", "side": "buy", "quantity": 10,
            "price": 100.0}},
        {"ts": "2026-11-19T15:30:20+00:00", "type": "order.requested", "payload": {
            "strategy_id": "PB-004", "symbol": "US.NVDA", "request_id": "req-1"}},
    ]
    state = scalp_state(events, TODAY, 20)
    assert state.lots["US.NVDA"].quantity == 10
    assert state.lots["US.NVDA"].stop == 99.75
    assert "US.NVDA" in state.last_request
    events.append({"ts": "2026-11-19T15:31:00+00:00", "type": "order.filled", "payload": {
        "strategy_id": "PB-004", "symbol": "US.NVDA", "side": "sell", "quantity": 10,
        "price": 100.4}})
    state = scalp_state(events, TODAY, 20)
    assert state.lots == {}
    assert state.round_trips_today == 1


def test_fill_without_strategy_id_resolves_through_request():
    events = [
        {"ts": "2026-11-19T15:00:00+00:00", "type": "order.requested", "payload": {
            "strategy_id": "PB-004", "symbol": "US.NVDA", "request_id": "req-1"}},
        {"ts": "2026-11-19T15:00:05+00:00", "type": "order.filled", "payload": {
            "symbol": "US.NVDA", "side": "buy", "quantity": 10, "price": 100.0,
            "request_id": "req-1"}},
    ]
    state = scalp_state(events, TODAY, 20)
    assert state.lots["US.NVDA"].quantity == 10
    assert abs(state.lots["US.NVDA"].stop - 99.75) < 1e-9


def test_entry_fires_on_breakout_with_fixed_risk_sizing():
    cfg = config()
    report = plan_scalp({"US.NVDA": quote()}, {"US.NVDA": breakout_bars()}, ScalpState(),
                        snapshot(), cfg, NOW)
    assert len(report["orders"]) == 1, report
    intent = report["orders"][0]["intent"]
    assert intent["side"] == "buy" and intent["strategy_id"] == "PB-004"
    assert intent["limit_price"] == 100.01
    assert abs(intent["stop_price"] - 99.76) < 0.005
    assert intent["quantity"] * 100.01 <= 0.05 * 100000
    assert report["orders"][0]["plan"]["target"] > intent["stop_price"]
    assert not report["submitted"]


def test_exits_take_precedence_and_sell_at_bid():
    cfg = config()
    state = ScalpState(lots={"US.NVDA": lot()})
    stop = plan_scalp({"US.NVDA": quote(last=99.70)}, {"US.NVDA": breakout_bars()}, state,
                      snapshot(), cfg, NOW)
    assert stop["orders"][0]["intent"]["side"] == "sell"
    assert stop["orders"][0]["intent"]["limit_price"] == 99.99
    assert "stop" in stop["orders"][0]["intent"]["reason"]

    timeout = ScalpState(lots={"US.NVDA": lot(deadline=NOW - timedelta(seconds=1))})
    flat = plan_scalp({"US.NVDA": quote()}, {}, timeout, snapshot(), cfg, NOW)
    assert "timeout" in flat["orders"][0]["intent"]["reason"]


def test_entries_respect_cooldown_budget_halt_and_open_limit():
    cfg = config()
    args = {"US.NVDA": quote()}
    bars = {"US.NVDA": breakout_bars()}

    cooling = ScalpState(last_request={"US.NVDA": NOW - timedelta(seconds=30)})
    assert not plan_scalp(args, bars, cooling, snapshot(), cfg, NOW)["orders"]

    spent = ScalpState(round_trips_today=50)
    assert not plan_scalp(args, bars, spent, snapshot(), cfg, NOW)["orders"]

    assert not plan_scalp(args, bars, ScalpState(), snapshot(), cfg, NOW, halted=True)["orders"]

    full = ScalpState(lots={f"US.SYM{i}": lot(f"US.SYM{i}") for i in range(4)})
    report = plan_scalp(args, bars, full, snapshot(), cfg, NOW)
    assert not report["orders"]


def test_stale_snapshot_or_wide_spread_blocks_entries():
    cfg = config()
    stale = plan_scalp({"US.NVDA": quote()}, {"US.NVDA": breakout_bars()}, ScalpState(),
                       snapshot(captured_at=NOW - timedelta(minutes=5)), cfg, NOW)
    assert not stale["orders"] and "stale" in stale["alerts"][0]
    wide = plan_scalp({"US.NVDA": quote(bid=99.5, ask=100.5)}, {"US.NVDA": breakout_bars()},
                      ScalpState(), snapshot(), cfg, NOW)
    assert not wide["orders"]


def test_arm_scalp_journals_plan_and_request_within_envelope(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    envelope = tmp_path / "approvals-scalp.json"
    intent = OrderIntent(symbol="US.NVDA", side="buy", quantity=10, limit_price=100.0,
                         stop_price=99.75, strategy_id="PB-004", reason="test")
    proposals = [{"order_hash": "h1", "intent": intent.model_dump(mode="json"),
                  "plan": {"symbol": "US.NVDA", "stop": 99.75, "target": 100.5},
                  "thesis": {"thesis": "synthetic breakout", "direction": "bullish"}}]
    envelope.write_text(_envelope(max_qty=40).model_dump_json(), encoding="utf-8")
    armed = _arm_scalp(proposals, envelope, journal, TODAY, 0)
    assert armed[0]["request"]["request_id"].startswith("tyche-scl-")
    events = read_events(journal)
    assert [event["type"] for event in events][-2:] == ["plan.created", "order.requested"]
    assert events[-2]["payload"]["plan"]["thesis"]["thesis"] == "synthetic breakout"

    envelope.write_text(_envelope(max_qty=5).model_dump_json(), encoding="utf-8")
    append_event(journal, "gate.wait", {"request_id": armed[0]["request"]["request_id"]})
    denied = _arm_scalp(proposals, envelope, journal, TODAY, 0)
    assert "exceeds" in denied[0]["denied"]


def test_entry_proposal_carries_a_per_trade_thesis():
    cfg = config()
    report = plan_scalp({"US.NVDA": quote()}, {"US.NVDA": breakout_bars()}, ScalpState(),
                        snapshot(), cfg, NOW)
    thesis = report["orders"][0]["thesis"]
    assert "NVDA" in thesis["thesis"] and "breakout" in thesis["thesis"]
    assert thesis["direction"] == "bullish" and thesis["source"] == "deterministic"
    assert {f["axis"] for f in thesis["factors"]} >= {"technical", "liquidity"}
    unknown = [f for f in thesis["factors"] if f["state"] == "unknown"]
    assert unknown and unknown[0]["axis"] == "macro"
    assert thesis["edge"] and thesis["invalidation"] and thesis["bear_case"]


def test_exit_proposal_uses_the_long_retry_window():
    cfg = config()
    cfg.scalp.exit_submit_window_seconds = 600
    state = ScalpState(lots={"US.NVDA": lot()})
    report = plan_scalp({"US.NVDA": quote(last=99.70)}, {}, state, snapshot(), cfg, NOW)
    order = report["orders"][0]
    assert order["intent"]["side"] == "sell"
    assert datetime.fromisoformat(order["submit_before"]) == NOW + timedelta(seconds=600)


def test_arm_scalp_keeps_an_active_exit_request(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    envelope = tmp_path / "approvals-scalp.json"
    envelope.write_text(_envelope(max_qty=40).model_dump_json(), encoding="utf-8")
    future = datetime.now(UTC) + timedelta(minutes=5)
    append_event(journal, "order.requested", {
        "strategy_id": "PB-004", "symbol": "US.NVDA", "side": "sell", "quantity": 10,
        "limit_price": 99.99, "request_id": "tyche-scl-old", "submit_before": future.isoformat()})
    armed = _arm_scalp([_sell_proposal(future)], envelope, journal, TODAY, 0)
    assert "active request pending" in armed[0]["skipped"]
    assert sum(1 for e in read_events(journal) if e["type"] == "order.requested") == 1


def test_arm_scalp_journals_one_gap_then_rearms_an_expired_exit(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    envelope = tmp_path / "approvals-scalp.json"
    envelope.write_text(_envelope(max_qty=40).model_dump_json(), encoding="utf-8")
    past = datetime.now(UTC) - timedelta(minutes=5)
    future = datetime.now(UTC) + timedelta(minutes=10)
    append_event(journal, "order.requested", {
        "strategy_id": "PB-004", "symbol": "US.NVDA", "side": "sell", "quantity": 10,
        "limit_price": 99.99, "request_id": "tyche-scl-old", "submit_before": past.isoformat()})
    armed = _arm_scalp([_sell_proposal(future)], envelope, journal, TODAY, 0)
    assert armed[0]["protection_gap"]["resolution"] == "expired"
    assert armed[0]["request"]["request_id"].startswith("tyche-scl-")
    again = _arm_scalp([_sell_proposal(future)], envelope, journal, TODAY, 0)
    assert "active request pending" in again[0]["skipped"]
    gaps = [e for e in read_events(journal) if e["type"] == "protection.gap"]
    assert len(gaps) == 1


def test_arm_scalp_never_doubles_an_exit_the_broker_shows_live(tmp_path):
    journal = tmp_path / "events.jsonl"
    append_event(journal, "test", {})
    envelope = tmp_path / "approvals-scalp.json"
    envelope.write_text(_envelope(max_qty=40).model_dump_json(), encoding="utf-8")
    now = datetime.now(UTC)
    append_event(journal, "order.requested", {
        "strategy_id": "PB-004", "symbol": "US.NVDA", "side": "sell", "quantity": 10,
        "limit_price": 99.99, "request_id": "tyche-scl-live",
        "submit_before": (now - timedelta(minutes=1)).isoformat()})
    rows = [{"symbol": "US.NVDA", "side": 2, "qty": 10, "cum_qty": 0, "status": 2,
             "text": "tyche-scl-live", "order_id": "b-1"}]
    armed = _arm_scalp([_sell_proposal(now + timedelta(minutes=10))], envelope, journal,
                       TODAY, 0, rows=rows)
    assert "live order" in armed[0]["skipped"]
    types = [e["type"] for e in read_events(journal)]
    assert "protection.gap" not in types
    assert types.count("order.requested") == 1


def _sell_proposal(submit_before: datetime) -> dict:
    intent = OrderIntent(symbol="US.NVDA", side="sell", quantity=10, limit_price=99.99,
                         strategy_id="PB-004", reason="stop exit")
    return {"order_hash": "h-sell", "intent": intent.model_dump(mode="json"),
            "submit_before": submit_before.isoformat()}


def _envelope(*, max_qty: int) -> ApprovalBatch:
    return ApprovalBatch.model_validate({
        "as_of": TODAY.isoformat(), "approved_at": NOW.isoformat(), "max_orders": 120,
        "orders": [{"symbol": "US.NVDA", "side": "buy", "max_qty": max_qty, "limit_max": 110.0},
                   {"symbol": "US.NVDA", "side": "sell", "max_qty": 40, "limit_min": 50.0}]})
