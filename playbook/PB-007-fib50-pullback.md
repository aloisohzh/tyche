---
id: PB-007
title: Fib 50% pullback (trend-filtered mean reversion)
classification:
  holding_period: Swing            # 1 to 10 sessions, hard deadline in the lifecycle contract
  strategy_type: Mean reversion    # buy the pullback into the 50% retracement of an impulse leg
  execution_style: Fully automated # deterministic scanner; entries only under an operator-approved lifecycle
  instruments: [Stocks]            # large caps and sector ETFs, no options leg
  regime_fit: [Bull, Range]        # SMA50/200 filter keeps it out of downtrending names by construction
  direction: Long
  validation: Unvalidated
---

# PB-007 - Fib 50% pullback (trend-filtered mean reversion)

- **Status:** pre-registered, disabled (`config/strategies/pb-007.yaml: enabled: false`). The first
  window run is a test of the plumbing (scan -> review -> audit -> approve -> fill -> R), not an
  edge claim.
- **Rules hash:** `e26f006da28a` (sha256 of `config/strategies/pb-007.yaml` + `config/universe.yaml`, CRLF
  normalized, first 12). First registration for this lane; record it with `tyche rules-freeze --record`
  before the first approval.
- **Validation:** unvalidated. No backtest, no matched-null comparison; the LEAN sanity check is
  parked as research (ADR 0015).
- **Sleeve:** equity (swing), 20% NAV allocation cap carved from the tactical stock budget
- **Env:** paper (competition)
- **Why PB-007:** PB-006 was already claimed by the planned sector-rotation sleeve (L-029), and an id is
  claimed once and kept forever.

## Thesis
In an uptrend, a sharp impulse leg up is followed by a pullback that often stalls around half of the
leg, where the 50% Fibonacci level, the rising 50-day average and the breakout area of the prior swing
(support / demand) sit close together. Buying that pullback with a limit order, a stop just under the
deeper retracement levels and a target at the prior swing high exploits trend-followers who missed the
leg buying the first discount. The moving-average regime filter keeps the setup out of downtrends,
where "pullbacks" keep going.

## Edge
Why it should work after fees: the geometry is asymmetric by construction - entry at the 50% level,
stop under the 78.6% level, target at the 100% level gives about 1.6-1.8R at the limit price and more
when filled deeper in the zone. Break-even win rate at 1.7R is 1 / (1 + 1.7), about 37%. Fees are
about $2 per round trip on a $5,000 position (0.04% of notional) against a 1R of 2-3%.
Why it might not: pullback buying is long the trend continuing; in chop or at a trend top the 50% level
breaks and the stop is paid repeatedly. Fib levels are self-fulfilling only where enough participants
watch them. Fortuna's gauntlet already rejected RSI-2 mean reversion as indistinguishable from random
(see [validation](../docs/validation/README.md)); this setup must clear the same bar later.
Drift ≠ edge: the comparison that matters is against random long entries in the same regime with the
same stop/target geometry, which is post-window work.

## Universe / liquidity filter
`config/strategies/pb-007.yaml` `symbols`: 16 mega/large caps (AAPL, GOOGL, AMZN, META, TSLA, JPM, V,
MA, UNH, XOM, COST, HD, LLY, NFLX, ORCL, WMT) and 8 sector ETFs (XLF, XLE, XLK, XLV, XLI, XLY, XLP,
XLU). Symbol-disjoint from the ballast universe, the scalp names and the tactical test name; the
config loader refuses an overlap (ADR 0017). All above $1.00 and $500M. Spread gate at entry:
`max_spread_pct` 0.3% (checked by the lifecycle lane's quote freshness and the reserve step); order
size stays far below the sim's volume x 20 rule at 10% NAV.

## Entry trigger
All inputs are completed daily OHLC bars through the previous session; no LLM input anywhere.
Implemented in `src/tyche/strategies/fib_pullback.py`, asserted by `tests/test_fib_pullback.py`.

1. Regime: close > SMA200, SMA50 > SMA200, SMA50 > SMA50 ten bars earlier.
2. Impulse leg over the last 30 bars: H = highest high (bar iH), L = lowest low from the start of the
   lookback up to iH. iH is 2 to 15 bars old. H - L >= 3 x ATR14 (simple mean true range).
3. Levels from the high: fib0.382 = H - 0.382(H-L), fib0.5, fib0.618, fib0.786.
4. Zone holding: every close since iH >= fib0.618. Zone reached: yesterday's low <= fib0.382.
5. Reward/risk at the limit (target - fib0.5) / (fib0.5 - stop) >= 1.5.

The scan (`tyche fib-scan`) emits a `LifecyclePlan` per qualifying symbol: `entry_high` = fib0.5,
`entry_low` = fib0.618, stop and target below, one plan per symbol, at most `max_open` (4) open
lifecycles, ranked by confluence (SMA50 inside the zone, prior swing high within 0.5 ATR of fib0.5)
then reward/risk. The lifecycle lane reserves ONE limit order when the live quote sits inside
[entry_low, entry_high] at a scheduled check during the regular session; in the current cadence that is
the 15:05 ET fire, so v1 is a close-of-day pullback entry. Entry expires at that session's close minus
10 minutes. On FOMC / CPI / PCE days (calendar gate events) the scan emits no plans.

## Invalidation
Per trade, before fill: a daily close below fib0.618, or the regime filter failing, cancels the plan;
no re-arm on that leg. After fill, any one kills it: last price <= stop (synthetic, ADR 0012/0013 -
stops can gap); a daily close below SMA200 (regime lost) -> exit at the next session; the holding
deadline (10 sessions, clamped to the window's last session by `--flat-by`); a sourced material event
marked `invalidated` by the researcher's review. All five are written into the plan's
`invalidation_rules` so the auditor and the reviewer see the same list.
Strategy level: after >= 30 closed trades, E[R] <= 0, profit factor < 1.2 or sleeve drawdown > 4% ->
retire (`tyche strategy-score`, ADR 0016). Inside the window: 6 consecutive full-R losses -> disable
and review.

## Sizing
Risk unit R = entry_high - stop, fixed at plan time. Stop = fib0.786 - 0.10 x ATR14.
Risk per trade **0.5% NAV** (`risk_per_trade_pct`), quantity = floor(0.005 x NAV / R), capped at
**10% NAV notional** per name (`max_notional_pct`, equal to `max_weight`). Max 4 open, lane
allocation cap 20% NAV, cash floor 5% unchanged. One entry per leg, no scaling, no re-entry.
Worked example: L = 100, H = 110, ATR = 2 -> fib0.5 = 105, fib0.618 = 103.82, fib0.786 = 102.14,
stop = 101.94, target = 110; risk 3.06, reward 5.00, 1.63R. NAV $100k -> 163 shares by risk, capped to
95 shares by notional (about $10k, planned risk about $291).

## Exit
Target: limit sell at H. Stop: synthetic, checked at every desk fire and the protection monitor; exit
with a limit at the bid. Regime exit: close < SMA200 -> sell next session. Time exit: the plan's
`exit_deadline` (10 sessions, or the window's last session, 30 minutes before that day's close). A halt
blocks new entries only.

## Regime fit
Per symbol by the SMA filter (rules 1). Additionally off for new entries on event days named in
`no_entry_event_kinds` and whenever the calendar gate reports `new_entries: false`; event caution halves
the risk budget at reserve time as it does for every lane.

## Fees / slippage
Stock: $0.99/order + TAF $0.000166/share on sells (cap $8.30). Entry is a limit inside the zone (no
half-spread paid); exits at the bid pay about half a spread (<= 0.15% at the 0.3% gate). Modeled per
`src/tyche/fees.py`; expectancy is always fee-net.

## How edge is measured
Nothing new: the scan journals `plan.created` with each intent's limit and stop, the executor records
fills with `strategy_id: PB-007`, and `config.sleeve_map()` gives every PB-007 symbol a sleeve. From
there `tyche expectancy --json` gives initial and realized R, win rate and fee-net expectancy, and
`tyche strategy-score --strategy PB-007 --sleeve equity` gives profit factor, drawdown and the
mount/hold/retire decision (provisional below 30 closed trades). Expect 3-12 trades in the window;
SE(E[R]) is about 1.2 / sqrt(n), so +-0.35R at 12 trades. Report the number, never the adjective.

## Desk workflow (proposed card clause, not yet spliced)
08:05 fire: executor pulls daily klines (`quote_cur_kline`, ktype day, num=370) for the PB-007
symbols, `python scripts/mcp_prices.py /tmp/tool-outputs --ohlc --out data/ohlc.csv`, then
`tyche fib-scan --bars data/ohlc.csv --account <snapshot> --book <run>/pb007-book.json --flat-by
<last session> --record`; preview each plan; researcher reviews each plan hash with evidence; auditor
runs the exact-order audit; the digest lists plan hashes, levels and R. Operator: `tyche lifecycle
approve` per hash. 12:05: watch and shout only. 15:05: exits first, then `lifecycle tick` /
`reserve` for plans whose quote is inside the zone; record fills with the strategy id; append
expectancy and strategy-score output to the close report. Enabling the lane also needs the
allocation-cap sum to fit (the 20% is carved from the 45% tactical stock cap), which is an operator
config change, not something a run may do.

## Evidence
- Kernel: `src/tyche/strategies/fib_pullback.py`, `src/tyche/lifecycle.py` (scope-aware caps),
  `src/tyche/config.py` (`FibPullbackConfig`, `scope_symbols`, `sleeve_map`), `tyche fib-scan`.
- Tests: `tests/test_fib_pullback.py`.
- ADRs: [0014](../docs/adr/0014-per-strategy-isolation.md), [0016](../docs/adr/0016-per-trade-risk-budget.md),
  [0017](../docs/adr/0017-strategy-kind-and-scope.md).
- Journal rows, plan hashes, vetoes and `strategy.decision` rows: to be filled once the lane trades.
