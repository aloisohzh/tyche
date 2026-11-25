---
id: PB-004
title: Intraday momentum scalp (breakout)
classification:
  holding_period: Intraday          # hard timeout 20 minutes, flat before the close
  strategy_type: Breakout           # close through the prior N-bar high
  execution_style: Fully automated  # deterministic, but only under an operator-approved envelope
  instruments: [Stocks]             # single large-cap ETFs/semis, no options leg
  regime_fit: [Bull]                # long breakouts need upside follow-through; bear rallies whipsaw them
  direction: Long
  validation: Unvalidated
---

# PB-004 - Intraday momentum scalp (breakout)

- **Status:** on from 24 to 30 Nov 2026 by the operator's switch, under the standing scalp approval in
  `data/scalp-approvals.json`. Its orders are decided by `tyche cycle` on the 15-minute card. On 24 Nov the
  lane placed no order: it demanded data under two minutes old from runs that take longer than that.
- **Rules hash:** `81518babfb6c` (sha256 of `config/scalp.yaml` + `config/universe.yaml`, CRLF
  normalized, first 12). `6dd1d4e3709a` was the hash until 2026-11-25, when US.NVDA left for PB-002 so the
  desk could hold it as a swing; four names remain (AMD, AVGO, MU, SMH) and `max_open` is still 4. `72077d5d4808` was the hash until 2026-11-25, when the lane was tuned to a desk
  that looks every 15 minutes: its own 15-minute freshness clocks, ten minutes to send a reserved order,
  a breakout that may be any of the last 5 bars, limits priced through the market, a 5-minute life for an
  unfilled entry, and the flatten moved from 10 to 25 minutes before the close. `tyche cycle` registers
  the new hash on the ledger by itself. `72077d5d4808` was the first computable hash for this lane: `rules_hash()` used to look for a
  nonexistent `config/strategies/pb-004.yaml`, so the freeze guard raised and `lifecycle.decide()`
  degraded every PB-004 plan to a blanket block (L-036, [audit §3.8](../docs/reviews/2026-11-20-platform-refinement-audit.md)).
  The lane's bytes now resolve through `PLAYBOOK_LANES`. The hash covers the whole file, so it is the
  first real registration - there is no prior freeze lineage for this strategy.
- **Validation:** unvalidated - no gauntlet, no backtest, small-n intraday sample only.
- **Sleeve:** intraday
- **Env:** paper (competition)

## Thesis
Continuation: a first-minute-scale close through the high of the prior bars, on a tape that is already
active, tends to extend long enough to pay a 2R target before it mean-reverts. The edge, if any, is
in the exit discipline (hard 0.25% stop, 20-minute timeout, flat before the close), not in the entry.

## Edge
Why it should work after fees: risk per trade is 0.1% of NAV, so a 2R payoff needs only a ~34% win
rate to break even before costs; entries are rejected when the spread exceeds 0.1% of price, which
keeps the modeled half-spread small relative to the target.
Why it might not: 5-bar breakouts on 1-minute data fail most of the time in range-bound sessions, and
a 0.25% stop sits inside ordinary noise, so whipsaw losses arrive in clusters. Nothing here has been
validated against a random entry in the same regime. Drift ≠ edge.

## Universe / liquidity filter
`config/scalp.yaml`: US.NVDA, US.AMD, US.AVGO, US.MU, US.SMH. All large and liquid, so the binding
liquidity test is the spread gate, not market cap: `max_spread_pct: 0.001`.

## Entry trigger
Deterministic, per tick:
1. A 1-minute bar **closes above the high of the previous 5 bars and above its own open**
   (`scalp.breakout()`). Any of the latest 5 bars may be that bar (`breakout_window_bars`), provided the
   latest close still holds above the level it broke: a run that looks once every 15 minutes almost never
   lands on the breakout minute itself.
2. Quote is present and fresh within the lane's own `max_quote_age_seconds` (15 minutes; until
   2026-11-25 it borrowed the tactical lane's value and a fixed 120-second account age).
3. Not in the flatten window, kill switch not engaged, fewer than 4 open lots, round trips today
   below 50, symbol out of the 600-second post-request cooldown.

Order: buy limit at the ask plus 0.1% (`entry_buffer_pct`), so an order built from a minutes-old quote
still trades; an entry still unfilled after 5 minutes (`entry_ttl_seconds`) is cancelled by the next run.
Risk kernel (`evaluate_intent`) may cut the quantity; it never raises it.

## Invalidation
Per trade: last price at or below the stop (`limit × (1 - 0.0025)`), or the 20-minute holding deadline,
or the flatten time 25 minutes before the close. There is no chart-level "thesis dead" condition beyond
those, and no stop-basis choice to make: the stop is fixed to the entry limit at request time.
Strategy-level invalidation is the shared risk kernel (daily loss and drawdown halts), not this file.

## Sizing
Risk unit = 0.1% of NAV to the stop.
`quantity = 0.1% NAV / (limit - stop)`, then capped at 5% of NAV notional, then decremented until
`quantity × (limit - stop) + estimated fees ≤ 0.1% NAV`. One unit exceeding the budget rejects the
entry rather than sizing down to it. Max 4 concurrent names, 50 round trips per day.

## Exit
Target at 2R (`limit × (1 + 2 × 0.0025)`), stop as above, timeout at 20 minutes, and a hard flatten 25
minutes before the close: the 15:37 ET run sells every lot and the 15:52 run retries. Exits are sell
limits 0.3% under the bid (`exit_collar_pct`) with a 600-second submit window, and a reservation that was
never sent frees the lot for the next run.

**What a 15-minute look does to this lane.** The stop, the target and the timeout are only seen when a
run looks, so a lot can be well through its 0.25% stop or past its 20 minutes before the desk acts. At
this cadence the lane is close to a coin flip before fees. It stays on because the operator asked for it
through 30 Nov; it is not evidence of an edge.

## Regime fit
Intraday only, and effectively directional: every entry is a long breakout, so a drifting-down session
produces stop clusters rather than losses being offset. No regime gate exists in this lane.

## Fees / slippage
Modeled per `src/tyche/fees.py` ($0.99/order + TAF on sells) and included in the quantity loop above.
Entry at the ask and exit at the bid, so the round trip pays the full spread; at a 0.5% target and a
0.1% spread gate, spread plus commissions can exceed one R on a bad fill.

## Evidence
- Kernel: `src/tyche/scalp.py`, rules in `config/scalp.yaml`
- Id history: this id was double-listed as "sector rotation heat" until 2026-11-20 (L-029); the live
  scalp keeps PB-004 and the planned sleeve moved to PB-006.
- Pre-registration blocker closed 2026-11-20: the lane had no resolvable rules file, so its freeze guard
  raised (L-036). `config/scalp.yaml` now hashes to `72077d5d4808`, declared here and asserted in CI, and
  journaled: `tyche rules-freeze` (L-035, landed 2026-11-21) wrote this lane's first `rules.frozen` row the same
  day as event `5f6d8ab3cc1d`. What is genuinely missing is any validation at all - see Status above.
