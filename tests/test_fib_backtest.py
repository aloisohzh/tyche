"""PB-007 backtest: the replay uses the live rules and is cautious inside each bar."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from typer.testing import CliRunner

from tyche.cli import app
from tyche.config import load_config
from tyche.strategies.fib_backtest import backtest
from tyche.strategies.fib_pullback import Bar, signal

ROOT = Path(__file__).resolve().parents[1]


def cfg():
    return load_config(ROOT).strategy_by_id("PB-007")


def series(after: list[tuple[float, float, float, float]], *, total=300, start=date(2025, 1, 1)) -> list[Bar]:
    """Uptrend, impulse, pullback into the zone (the signal day is the last pre-built bar), then
    the given (open, high, low, close) bars after the signal."""
    out, d, px = [], start, 80.0
    n_imp = n_pull = 15
    for i in range(total):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if i < total - n_imp - n_pull:
            px = 80 + i * 0.1
        elif i < total - n_pull:
            px += 2.0
        else:
            px -= 1.0
        out.append(Bar(date=d, open=px, high=px + 0.8, low=px - 0.8, close=px))
        d += timedelta(days=1)
    for o, h, lo, c in after:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(Bar(date=d, open=o, high=h, low=lo, close=c))
        d += timedelta(days=1)
    return out


def _sig():
    base = series([])
    sig, why = signal("US.AAPL", base, cfg())
    assert sig is not None, why
    return base, sig


def run(after):
    base, sig = _sig()
    data = {"US.AAPL": series(after)}
    trades, summary = backtest(data, cfg(), start=base[-1].date)
    return sig, trades, summary


def test_fills_next_day_at_the_limit_and_hits_the_target():
    _, sig = _sig()
    mid = sig.entry_high + 0.5
    sig, trades, _ = run([(mid, mid + 0.5, sig.entry_high - 0.2, mid),
                          (mid, sig.target + 1, mid - 0.1, sig.target + 0.5)])
    assert len(trades) == 1
    t = trades[0]
    assert t.entry == sig.entry_high and t.exit_reason == "target" and t.exit == sig.target
    assert t.r > 1.4  # ~reward_risk minus fees


def test_a_bar_that_touches_stop_and_target_counts_as_a_loss():
    _, sig = _sig()
    o = sig.entry_high
    sig, trades, _ = run([(o, o + 0.1, o - 0.1, o), (o, sig.target + 5, sig.stop - 5, o)])
    assert trades[0].exit_reason == "stop" and trades[0].r < -0.99


def test_gap_below_the_zone_does_not_fill():
    _, sig = _sig()
    low = sig.entry_low - 3
    _, trades, summary = run([(low, low + 0.5, low - 0.5, low)])
    assert trades == [] and summary.trades == 0


def test_gap_through_the_stop_exits_at_the_open():
    _, sig = _sig()
    o = sig.entry_high
    _, trades, _ = run([(o, o + 0.1, o - 0.1, o), (sig.stop - 2, sig.stop - 1, sig.stop - 3, sig.stop - 2)])
    assert trades[0].exit == round(sig.stop - 2, 2) and trades[0].r < -1


def test_deadline_exits_at_the_close_after_max_hold_sessions():
    _, sig = _sig()
    o = sig.entry_high
    flat = [(o, o + 0.1, o - 0.1, o)] * (cfg().max_hold_sessions + 2)
    _, trades, _ = run(flat)
    assert trades[0].exit_reason == "deadline" and trades[0].sessions == cfg().max_hold_sessions


def test_fewer_than_30_trades_is_inconclusive_not_pass():
    _, sig = _sig()
    mid = sig.entry_high + 0.5
    _, _, summary = run([(mid, mid + 0.5, sig.entry_high - 0.2, mid), (mid, sig.target + 1, mid - 0.1, sig.target)])
    assert summary.trades == 1 and summary.checks["trades_at_least_30"] is False
    assert summary.verdict == "inconclusive"


def test_cli_reports_json_and_writes_trades(tmp_path):
    _, sig = _sig()
    mid = sig.entry_high + 0.5
    rows = series([(mid, mid + 0.5, sig.entry_high - 0.2, mid), (mid, sig.target + 1, mid - 0.1, sig.target)])
    csv = tmp_path / "ohlc.csv"
    lines = ["date,symbol,open,high,low,close"]
    lines += [f"{b.date},US.AAPL,{b.open},{b.high},{b.low},{b.close}" for b in rows]
    lines += [f"{b.date},US.SPY,{b.open},{b.high},{b.low},{b.close}" for b in rows]
    csv.write_text("\n".join(lines) + "\n")
    out = tmp_path / "trades.csv"
    result = CliRunner().invoke(app, ["fib-backtest", "--bars", str(csv), "--config-root", str(ROOT),
                                      "--start", str(rows[-3].date), "--trades", str(out), "--json"])
    assert result.exit_code == 1  # inconclusive is not a pass
    report = json.loads(result.output)
    assert report["trades"] == 1 and report["verdict"] == "inconclusive"
    assert report["spy_return_pct"] is not None and report["exits"] == {"target": 1}
    assert out.read_text().startswith("symbol,")
