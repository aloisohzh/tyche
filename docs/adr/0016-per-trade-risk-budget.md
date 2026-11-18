# ADR 0016 — Per-trade risk budget and R-multiple expectancy

- Status: Accepted
- Date: 2026-11-18
- Deciders: operator (approved in desktop chat), desk-head
- Related: ADR 0012 (no broker-native stops), ADR 0013 (protection monitor), PB-001 playbook

## Context

The challenge risk-management framework splits control into a price side
(direction, timing, volatility; cut losers, hold winners) and a size side
(entry/exit rules, max loss, position size), intersecting at positive
expectancy. It names two sizing rungs: (1) fixed dollar/% risk per trade,
(2) Van Tharp R-multiples and Kelly.

Audit of the platform before this ADR: price-side signals and account-level
max loss (soft/hard drawdown, daily loss limit) were implemented; position
sizing was volatility-based with exposure caps. Missing: a per-trade max-loss
budget (size ignored stop distance), R-multiple accounting (expectancy section
was a placeholder with `closed_n=0`), and any Kelly layer. "Max loss tells you
how much" was true per account, not per trade.

## Decision

1. **Per-trade risk budget (rung 1).** `risk.risk_per_trade_pct = 0.01`
   (1% NAV). Each strategy carries `initial_stop_pct` (PB-001: 0.08). Buy
   intents get `stop_price = limit × (1 − initial_stop_pct)` and quantity is
   clamped to `min(vol_size, floor(risk_per_trade_pct × NAV / (limit − stop)))`.
   The risk kernel independently breaches `trade.risk_budget` when
   `qty × (limit − stop) > risk_per_trade_pct × NAV`, so manual or legacy
   intents cannot bypass the budget.
2. **Coherence with the drawdown ladder.** Four top-N names × 1% initial risk
   = 4% total initial risk = `soft_drawdown_pct`. A full stop-out of the book
   trips the soft rung (halve new buys); the hard rung (6%) remains the
   circuit breaker.
3. **R-multiple journaling (Van Tharp layer).** Initial R = entry − stop,
   fixed at plan time and journaled in `plan.created` intents. Fills are
   journaled as `order.filled` with canonical payload
   `{symbol, side: buy|sell, quantity, price, order_id?}` via
   `tyche record-order` (validated at the CLI boundary). `tyche.trade_risk`
   computes FIFO round trips fee-net (`tyche.fees`), realized R per closed
   lot, per-sleeve win%/avgWin/avgLoss/expectancy in R and %NAV, and open-lot
   initial risk. `tyche expectancy --json` exposes the report; the dashboard
   expectancy section and a new `initial_risk` contract field render it.
4. **Honesty rules preserved.** Fills without a side, sells without an entry
   lot, and buys without a plan stop are counted as `unattributed_fills` or
   yield `realized_r = None` — never guessed. Expectancy stays `provisional`
   below 30 closed trades. E[R] requires both win and loss observations.
5. **Kelly deferred.** Half-Kelly capped sizing is a future option only after
   ≥30 closed trades give a trustworthy expectancy estimate; with `closed_n=0`
   its input is undefined and applying it would fabricate edge.

## Consequences

- Position sizes shrink to ≈12.5% NAV per name at the default 1%/8% pairing
  (vs ≈30% before); gross exposure and portfolio vol fall, cash rises. This is
  the intended reading of "max loss tells you how much".
- The stop is a sizing and accounting anchor until ADR 0013's monitor enforces
  it intraday; until then exits remain rule-based (rebalance/invalidation) and
  the divergence is disclosed on the dashboard. Implementing the monitor is
  the queued follow-up; its watchlist invalidation levels can now be seeded
  from the plan's `stop_price`.
- Executor must journal canonical `order.filled` events at EOD reconcile for
  realized R to populate; until then the scorecard honestly shows open risk
  only. Executor prompt amendment is a separate approved cloud change.
- Alternatives rejected: ATR-based stops (price feed carries closes only, no
  high/low); broker-native stops (unavailable on sim, ADR 0012); Kelly now
  (undefined edge input).