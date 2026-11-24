"""PB-007 fib pullback replayed over daily history: does the frozen rule set have an edge?

Research only. Nothing here touches the journal, the broker or a plan: it reads a long OHLC CSV
(the same file `tyche fib-scan` reads), walks it one session at a time with the live `signal()`
and `size()`, and reports fee-net R per trade plus a pass/fail against the four criteria the
operator agreed on 2026-11-24 (>= 30 trades, mean R > 0 after fees, profit factor >= 1.2, worst
drawdown no deeper than SPY's over the same span).

The daily replay has to choose an order inside each bar, and every choice is the cautious one:

- A signal on day t's close may fill only on day t+1 (the live entry window): it fills when the
  bar trades through the zone, at the open when the open is inside it, else at the limit
  (`entry_high`). A bar that never reaches the zone, or opens below it, does not fill.
- The stop is checked before the target, also on the fill day, so a bar that touches both is a
  loss. A gap through the stop exits at the open.
- A daily close below the slow SMA exits at the next open (the playbook's regime invalidation);
  the holding deadline exits at that session's close.
- One open position per symbol, at most `max_open` at once, ranked like `scan()`.
- No event blackout: there is no historical event calendar, so FOMC/CPI/PCE days are traded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from tyche.config import FibPullbackConfig
from tyche.fees import stock_fees
from tyche.strategies.fib_pullback import Bar, FibSignal, signal, size, sma


@dataclass
class Trade:
    symbol: str
    signal_date: date
    entry_date: date
    entry: float
    stop: float
    target: float
    quantity: int
    exit_date: date | None = None
    exit: float | None = None
    exit_reason: str = ""
    sessions: int = 0
    fees: float = 0.0
    pnl: float = 0.0
    r: float = 0.0

    def row(self) -> dict:
        out = asdict(self)
        for key in ("signal_date", "entry_date", "exit_date"):
            out[key] = out[key].isoformat() if out[key] else None
        return out


@dataclass
class Summary:
    start: date | None
    end: date | None
    trades: int
    wins: int
    win_rate: float | None
    avg_win_r: float | None
    avg_loss_r: float | None
    mean_r: float | None
    profit_factor: float | None
    net_pnl: float
    return_pct: float
    max_drawdown_pct: float
    spy_return_pct: float | None
    spy_max_drawdown_pct: float | None
    checks: dict[str, bool | None] = field(default_factory=dict)
    verdict: str = "fail"


def _fill(sig: FibSignal, bar: Bar) -> float | None:
    """Fill price on the session after the signal, or None when the bar never reaches the zone."""
    if bar.open < sig.entry_low:
        return None  # gapped below the zone: the live check sees last < entry_low and does not buy
    if bar.low > sig.entry_high:
        return None  # never traded down to the limit
    return round(min(bar.open, sig.entry_high), 2)


def _max_drawdown(curve: list[float]) -> float:
    peak, worst = curve[0], 0.0
    for value in curve:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def backtest(bars_by_symbol: dict[str, list[Bar]], cfg: FibPullbackConfig, *, nav: float = 100_000.0,
             start: date | None = None, end: date | None = None,
             benchmark: str = "US.SPY") -> tuple[list[Trade], Summary]:
    symbols = sorted(s for s in bars_by_symbol if s in set(cfg.symbols))
    series = {s: sorted(bars_by_symbol[s], key=lambda b: b.date) for s in symbols}
    index = {s: {b.date: i for i, b in enumerate(series[s])} for s in symbols}
    days = sorted({b.date for s in symbols for b in series[s]})
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    open_trades: dict[str, Trade] = {}
    pending: dict[str, FibSignal] = {}
    pending_exit: set[str] = set()
    closed: list[Trade] = []
    equity, curve = nav, [nav]

    def close(trade: Trade, d: date, price: float, reason: str) -> None:
        nonlocal equity
        trade.exit_date, trade.exit, trade.exit_reason = d, round(price, 2), reason
        fees = sum(stock_fees("buy", trade.quantity).values()) + sum(stock_fees("sell", trade.quantity).values())
        trade.fees = round(fees, 4)
        trade.pnl = round((trade.exit - trade.entry) * trade.quantity - fees, 2)
        risk = (trade.entry - trade.stop) * trade.quantity
        trade.r = round(trade.pnl / risk, 4) if risk > 0 else 0.0
        equity += trade.pnl
        closed.append(trade)

    for d in days:
        # 1. exits on today's bar, for positions opened before today
        for sym in list(open_trades):
            i = index[sym].get(d)
            if i is None:
                continue
            bar, trade = series[sym][i], open_trades[sym]
            trade.sessions += 1
            if sym in pending_exit:
                pending_exit.discard(sym)
                close(open_trades.pop(sym), d, bar.open, "regime.lost")
                continue
            if bar.low <= trade.stop:
                close(open_trades.pop(sym), d, min(bar.open, trade.stop), "stop")
            elif bar.high >= trade.target:
                close(open_trades.pop(sym), d, max(bar.open, trade.target), "target")
            elif trade.sessions >= cfg.max_hold_sessions:
                close(open_trades.pop(sym), d, bar.close, "deadline")
            elif bar.close < sma([b.close for b in series[sym][: i + 1]], cfg.regime.sma_slow):
                pending_exit.add(sym)
        # 2. fills for yesterday's signals, ranked like scan(), within the slot limit
        ranked = sorted(pending.values(), key=lambda s: (-len(s.confluence), -s.reward_risk, s.symbol))
        pending = {}
        for sig in ranked:
            if len(open_trades) >= cfg.max_open or sig.symbol in open_trades:
                continue
            i = index[sig.symbol].get(d)
            if i is None:
                continue
            bar = series[sig.symbol][i]
            price = _fill(sig, bar)
            qty = size(sig, equity, cfg)
            if price is None or qty <= 0:
                continue
            trade = Trade(sig.symbol, sig.as_of, d, price, sig.stop, sig.target, qty)
            if bar.low <= trade.stop:  # stop before target, on the fill day too
                trade.sessions = 1
                close(trade, d, min(price, trade.stop), "stop")
                continue
            open_trades[sig.symbol] = trade
        # 3. today's close -> tomorrow's candidates
        for sym in symbols:
            if sym in open_trades:
                continue
            i = index[sym].get(d)
            if i is None or i + 1 < cfg.min_bars:
                continue
            sig, _reason = signal(sym, series[sym][: i + 1], cfg)
            if sig is not None:
                pending[sym] = sig
        curve.append(equity)

    for sym, trade in list(open_trades.items()):  # mark the leftovers at the last close
        last = series[sym][-1] if not end else [b for b in series[sym] if b.date <= end][-1]
        close(trade, last.date, last.close, "open.at_end")

    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    spy_ret = spy_dd = None
    bench = sorted(bars_by_symbol.get(benchmark, []), key=lambda b: b.date)
    bench = [b for b in bench if (not days or days[0] <= b.date <= days[-1])]
    if len(bench) >= 2:
        spy_ret = round(bench[-1].close / bench[0].close - 1, 6)
        spy_dd = round(_max_drawdown([b.close for b in bench]), 6)
    n = len(closed)
    mean_r = sum(t.r for t in closed) / n if n else None
    pf = gross_win / gross_loss if gross_loss > 0 else (None if not wins else float("inf"))
    dd = round(_max_drawdown(curve), 6)
    checks = {
        "trades_at_least_30": n >= 30,
        "mean_r_above_zero": mean_r is not None and mean_r > 0,
        "profit_factor_at_least_1_2": pf is not None and pf >= 1.2,
        "drawdown_no_deeper_than_spy": None if spy_dd is None else dd >= spy_dd,
    }
    verdict = "pass" if all(v is True for v in checks.values()) else (
        "inconclusive" if checks["trades_at_least_30"] is False or checks["drawdown_no_deeper_than_spy"] is None
        else "fail")
    summary = Summary(
        start=days[0] if days else None, end=days[-1] if days else None, trades=n, wins=len(wins),
        win_rate=round(len(wins) / n, 4) if n else None,
        avg_win_r=round(sum(t.r for t in wins) / len(wins), 4) if wins else None,
        avg_loss_r=round(sum(t.r for t in losses) / len(losses), 4) if losses else None,
        mean_r=round(mean_r, 4) if mean_r is not None else None,
        profit_factor=round(pf, 4) if pf not in (None, float("inf")) else pf,
        net_pnl=round(equity - nav, 2), return_pct=round(equity / nav - 1, 6),
        max_drawdown_pct=dd, spy_return_pct=spy_ret, spy_max_drawdown_pct=spy_dd,
        checks=checks, verdict=verdict,
    )
    return closed, summary


__all__ = ["Summary", "Trade", "backtest"]
