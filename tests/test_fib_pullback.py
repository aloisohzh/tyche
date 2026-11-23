"""PB-007 fib pullback: the playbook's rules as tests (ADR 0017)."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tyche.cli import app
from tyche.config import FibPullbackConfig, load_config
from tyche.journal import read_events
from tyche.lifecycle import LifecycleBook, LifecyclePlan
from tyche.pipeline import rules_hash
from tyche.strategies import LIFECYCLE_GENERATORS
from tyche.strategies.fib_pullback import (
    Bar,
    build_plan,
    impulse_leg,
    level,
    load_ohlc,
    scan,
    signal,
    size,
)
from tyche.strategy_ledger import score
from tyche.trade_risk import compute_expectancy

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 23, 13, 5, tzinfo=UTC)  # Monday 08:05 ET


def cfg() -> FibPullbackConfig:
    return load_config(ROOT).strategy_by_id("PB-007")


def bars(*, trend=0.1, impulse=2.0, pullback=1.0, n_impulse=15, n_pull=15, total=300,
         width=0.8, start=date(2025, 10, 1)) -> list[Bar]:
    """Synthetic daily bars: a slow uptrend, an impulse leg, then a pullback into the zone."""
    out, d, px = [], start, 80.0
    for i in range(total):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if i < total - n_impulse - n_pull:
            px = 80 + i * trend
        elif i < total - n_pull:
            px += impulse
        else:
            px -= pullback
        out.append(Bar(date=d, open=px, high=px + width, low=px - width, close=px))
        d += timedelta(days=1)
    return out


def test_worked_example_from_the_playbook():
    assert level(100, 110, 0.5) == 105.0
    assert level(100, 110, 0.618) == 103.82
    assert level(100, 110, 0.786) == 102.14
    assert level(100, 110, 0.382) == 106.18


def test_signal_fires_on_a_clean_pullback_and_its_numbers_recompute():
    sig, why = signal("US.AAPL", bars(), cfg())
    assert sig is not None, why
    leg = sig.swing_high - sig.swing_low
    assert sig.entry_high == round(sig.swing_high - 0.5 * leg, 2)
    assert sig.entry_low == round(sig.swing_high - 0.618 * leg, 2)
    assert sig.stop == round(round(sig.swing_high - 0.786 * leg, 2) - 0.10 * sig.atr, 2)
    assert sig.target == round(sig.swing_high, 2)
    assert sig.reward_risk >= 1.5
    assert sig.stop < sig.entry_low <= sig.entry_high < sig.target
    assert sig.last_low <= sig.levels["fib0.382"]
    assert any("SMA50" in note for note in sig.confluence)


@pytest.mark.parametrize("mutate,expected", [
    (lambda b: b[:200], "data.insufficient"),
    (lambda b: [x.model_copy(update={"close": x.close - 60, "open": x.open - 60, "high": x.high - 60, "low": x.low - 60})
                if i >= len(b) - 1 else x for i, x in enumerate(b)], "regime.off"),
    (lambda b: bars(n_pull=0), "leg.stale_or_fresh"),
    (lambda b: bars(n_pull=20), "leg.stale_or_fresh"),
    (lambda b: bars(impulse=0.2, pullback=0.1), "leg.small"),
    (lambda b: bars(pullback=1.6), "zone.failed"),
    (lambda b: bars(pullback=0.5), "zone.untouched"),
    (lambda b: b[:-1] + [b[-1].model_copy(update={"date": b[-2].date})], "data.duplicate_dates"),
])
def test_every_gate_fails_closed_with_a_named_reason(mutate, expected):
    sig, why = signal("US.AAPL", mutate(bars()), cfg())
    assert sig is None
    assert why.startswith(expected), why


def test_reward_risk_gate_uses_the_configured_threshold():
    c = cfg().model_copy(update={"min_reward_risk": 5.0})
    sig, why = signal("US.AAPL", bars(), c)
    assert sig is None and why.startswith("reward_risk.low")


def test_impulse_leg_is_deterministic_on_ties():
    b = bars()
    assert impulse_leg(b, cfg()) == impulse_leg(list(b), cfg())
    i_low, i_high = impulse_leg(b, cfg())
    assert i_low < i_high
    assert b[i_high].high == max(x.high for x in b[-30:])


def test_sizing_is_half_percent_risk_capped_at_ten_percent_notional():
    sig, _ = signal("US.AAPL", bars(), cfg())
    nav = 100_000.0
    qty = size(sig, nav, cfg())
    assert qty * (sig.entry_high - sig.stop) <= 0.005 * nav
    assert qty * sig.entry_high <= 0.10 * nav
    assert qty == min(int(0.005 * nav // (sig.entry_high - sig.stop)), int(0.10 * nav // sig.entry_high))
    assert size(sig, 0.0, cfg()) == 0


def test_plan_is_a_valid_lifecycle_contract_with_the_window_clamp():
    sig, _ = signal("US.AAPL", bars(), cfg())
    plan = build_plan(sig, 100_000, cfg(), rules_hash(ROOT, "PB-007"), NOW, "deadbeef",
                      latest_deadline=date(2026, 11, 27))
    assert isinstance(plan, LifecyclePlan)
    assert plan.strategy_id == "PB-007" and plan.mode == "new_entry"
    assert plan.entry_expires_at.date() == date(2026, 11, 23)
    assert plan.exit_deadline.date() == date(2026, 11, 27)  # clamped to the last session (early close)
    assert plan.exit_deadline.hour == 12 and plan.exit_deadline.minute == 30
    assert "close below SMA200" in " ".join(plan.invalidation_rules)
    assert LifecyclePlan.model_validate_json(plan.model_dump_json()).fingerprint() == plan.fingerprint()
    # a window that ends on the entry day itself is not worth opening
    assert build_plan(sig, 100_000, cfg(), "h", NOW, latest_deadline=date(2026, 11, 23)) is None
    # outside the window it runs the full holding period
    free = build_plan(sig, 100_000, cfg(), "h", NOW)
    assert free.exit_deadline.date() > date(2026, 12, 1)


def test_scan_ranks_by_confluence_then_reward_risk_and_respects_slots():
    c = cfg().model_copy(update={"max_open": 1})
    data = {"US.AAPL": bars(), "US.XLF": bars(trend=0.05)}
    result = scan(data, c, 100_000, "h", NOW)
    assert len(result.plans) == 1
    assert next(s.symbol for s in result.signals) == result.plans[0].symbol
    assert "ranked below" in next(v for k, v in result.rejected.items() if k != result.plans[0].symbol and k in data)
    held = scan(data, c, 100_000, "h", NOW, open_symbols={"US.AAPL"})
    assert held.plans == [] and "held" in held.rejected["US.AAPL"]


def test_event_blackout_keeps_signals_but_emits_no_plans():
    result = scan({"US.AAPL": bars()}, cfg(), 100_000, "h", NOW, event_names=["FOMC minutes 14:00 ET"])
    assert result.signals and result.plans == [] and "blackout" in result.rejected["*"]
    quiet = scan({"US.AAPL": bars()}, cfg(), 100_000, "h", NOW, event_names=["Initial Jobless Claims"])
    assert quiet.plans


def test_stale_bars_are_skipped_not_traded():
    old = bars()[:-1]
    result = scan({"US.AAPL": bars(), "US.XLF": old}, cfg(), 100_000, "h", NOW)
    assert result.rejected["US.XLF"].startswith("data.stale")


def test_registry_names_the_generator():
    assert LIFECYCLE_GENERATORS["PB-007"] == "tyche.strategies.fib_pullback"


def _write_ohlc(path: Path, data: dict[str, list[Bar]]) -> None:
    lines = ["date,symbol,open,high,low,close,volume"]
    for symbol, series in data.items():
        lines += [f"{b.date},{symbol},{b.open},{b.high},{b.low},{b.close},1000000" for b in series]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_cli_scan_writes_a_book_and_journals_a_plan_that_attributes_r(tmp_path, monkeypatch):
    ohlc = tmp_path / "ohlc.csv"
    _write_ohlc(ohlc, {"US.AAPL": bars()})
    assert load_ohlc(ohlc)["US.AAPL"][-1].close == bars()[-1].close
    book, journal = tmp_path / "book.json", tmp_path / "events.jsonl"
    monkeypatch.setattr("tyche.cli.datetime", _Frozen)
    res = CliRunner().invoke(app, ["fib-scan", "--bars", str(ohlc), "--book", str(book), "--journal", str(journal),
                                   "--config-root", str(ROOT), "--flat-by", "2026-11-27", "--record", "--json"])
    assert res.exit_code == 0, res.output
    summary = json.loads(res.output)
    assert summary["plans"][0]["symbol"] == "US.AAPL" and summary["recorded"] is True
    assert "none" in summary["authorization"]
    loaded = LifecycleBook.model_validate_json(book.read_text())
    assert loaded.plans[0].rules_hash == rules_hash(ROOT, "PB-007")
    events = read_events(journal)
    assert [e["type"] for e in events] == ["plan.created"]
    intent = events[0]["payload"]["plan"]["orders"][0]["intent"]
    assert intent["strategy_id"] == "PB-007" and intent["stop_price"] == loaded.plans[0].stop.price
    # a round trip journaled with the strategy id now yields a numeric R and a PB-007 scorecard
    qty, entry, stop = loaded.plans[0].quantity, loaded.plans[0].entry_high, loaded.plans[0].stop.price
    # The journal stamps plan.created with the wall clock, and a fill only inherits a plan's stop when
    # the plan precedes it, so the fills are dated from that stamp (hard-coded dates went stale on
    # 2026-11-23 at 20:05Z and the whole suite went red on main).
    planned = datetime.fromisoformat(events[0]["ts"])
    fills = [
        {"ts": (planned + timedelta(hours=1)).isoformat(), "type": "order.filled",
         "payload": {"strategy_id": "PB-007", "symbol": "US.AAPL", "side": "buy", "quantity": qty, "price": entry}},
        {"ts": (planned + timedelta(days=2)).isoformat(), "type": "order.filled",
         "payload": {"strategy_id": "PB-007", "symbol": "US.AAPL", "side": "sell", "quantity": qty, "price": stop}},
    ]
    sleeves = load_config(ROOT).sleeve_map()
    assert sleeves["US.AAPL"] == "equity"
    report = compute_expectancy(events + fills, sleeves)
    assert report.closed_n == 1 and report.unattributed_fills == 0
    assert report.closed_trades[0].realized_r == pytest.approx(-1.0, abs=0.05)
    decision = score(events + fills, "PB-007", "equity", sleeves, at=NOW)
    assert decision.scorecard.closed_n == 1 and decision.action == "hold"
    assert decision.scorecard.provisional


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


def test_scan_refuses_a_rotation_id():
    res = CliRunner().invoke(app, ["fib-scan", "--bars", "x.csv", "--book", "b.json", "--strategy", "PB-001",
                                   "--config-root", str(ROOT)])
    assert res.exit_code != 0 and "rotation" in res.output
