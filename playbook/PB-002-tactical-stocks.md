---
id: PB-002
title: Tactical stocks (desk picks with a written thesis)
# The four classification dimensions are independent (see playbook/README.md). Only playbook/INDEX.yaml
# and this block describe a playbook; nothing here is restated in an agent prompt (L-033).
classification:
  holding_period: Swing             # one to a few sessions; every setup carries an explicit exit deadline
  strategy_type: Event-driven       # each pick needs a named catalyst and cited evidence before it can trade
  execution_style: Semi-automated   # the researcher proposes, the kernel gates, the operator sets the approval bounds
  instruments: [Stocks]             # shares only; the option leg of the same lane is PB-003
  regime_fit: [Bull, Range]         # long shares need a tape that is not falling; the current picks are defensives
  direction: Long                   # long shares and cash only
  validation: Unvalidated           # no backtest, no gauntlet; the first trades are a test of the plumbing
---

# PB-002 - Tactical stocks (desk picks with a written thesis)

- **Status:** trading in config (`config/tactical.yaml: enabled: true`, `execution_enabled: true`). From
  25 to 27 Nov 2026 an entry inside the operator's standing paper approval
  (`data/standing-approval.json`) is placed by `tyche cycle` with no per-order ask; outside those dates an
  entry again needs a same-day envelope or a Telegram `/approve`. Selling a held lot never needs a line.
- **Rules hash:** `1bbbe1901dde` (sha256 of `config/tactical.yaml` + `config/universe.yaml`, CRLF normalized,
  first 12). PB-002 and PB-003 are one lane with one parameter file, so they share this hash: editing the
  file re-registers the pair. `4d305127a2cd` was the hash until 2026-11-25, when US.NVDA joined from PB-004
  on the operator's swing-hold direction (a scalp lane cannot carry a position overnight, and ownership is
  by ticker). `58a3ce686238` was the hash from 2026-11-24 until 2026-11-25, when the lane's
  clocks were reset for a desk that agents run every 15 minutes instead of a 30-second feed (quotes and
  the account read good for 15 minutes, one confirming quote, research good for the session, ten minutes
  to send a reserved order) and stock exits were priced 0.3% under the bid (`exit_collar_pct`): with the
  old clocks every run refused its own data and the lane placed no order. `tyche cycle` registers the new
  hash on the ledger by itself. `a1d9df1c687c` was the hash from the evening of 2026-11-23 until 2026-11-24, when
  the resting-order settings (`resting_entries`, `resting_reach_pct`, `resting_cutoff_minutes`,
  `resting_take_profit`) were added so the desk places its entry and take-profit orders instead of waiting
  for the next run; `d5ef9567c736` was the hash from the morning of 2026-11-23, when the five
  defensives joined the symbol list, until the evening of 2026-11-23, when the lane cap
  (`stock_allocation_cap`) was cut from 45% to 25% so every lane's cap fits under the 95% gross cap even
  with all switches on (PRD §7 item 15); `b6bc571033ac` was the hash before the defensives. Each re-freeze
  is recorded by `tyche rules-freeze --record` on the Drive ledger
  ([freeze-on-ledger](../docs/runbooks/freeze-on-ledger.md)).
- **Validation:** unvalidated. No backtest, no matched-null comparison, no live sample yet. Drift is not edge.
- **Sleeve:** tactical stock, capped at 25% of NAV in total (45% until 2026-11-23) and 20% of NAV per name.
- **Env:** paper (competition)
- **Why this id:** the registry once reserved PB-002 for an "event drift around FOMC minutes / PCE" idea
  that was never built. `src/tyche/tactical.py` stamps PB-002 on every share intent from the tactical lane,
  so this page describes what the id actually trades. An id is claimed once and kept forever (L-029).

## Thesis
A short list of large, liquid names is watched by the researcher. When one of them has a fresh, named
reason to move (an earnings print, guidance, a sector rotation, a macro print that favours the group), the
researcher writes a one-paragraph thesis with cited sources, an entry zone, a stop, a target and an exit
deadline. The desk buys only at that zone, only on the day the thesis was written, and only
if the target pays at least 1.5 times the distance to the stop. The bet is that a documented, time-boxed
reason plus strict reward-to-risk filtering beats both idle cash and undocumented discretion.

The current list (2026-11-23) is MSFT plus five low-beta defensives: KO, PG, JNJ, PEP and MCD. The
operator's standing thesis behind the defensives is a risk-off rotation into staples and healthcare,
long only: if the broad tape weakens, these names should fall less and recover first, and their earnings
and dividend news give the researcher concrete catalysts to write against.

## Edge
Why it should work after fees: every entry needs reward/risk ≥ 1.5 at the underlying, so a win rate of
40% breaks even before costs, and stock fees ($0.99 per order plus TAF on sells) are small against a
position sized to risk 1% of NAV. The same-day research rule, the entry zone and the "do not chase"
reject keep the desk from buying a story after the move has happened.

Why it might not: a catalyst that is already in the price gives a neat-looking setup with no edge, and a
defensive rotation can stall for weeks while the stop is hit on noise. The lane relies on the quality of
the researcher's picks; the kernel checks form (fields, freshness, zone, ratio, caps) and never the truth of
the thesis. Nothing here has been compared with a random entry in the same names.

## Universe / liquidity filter
Only the symbols in `config/tactical.yaml` (`symbols:`), which must not overlap the rotation ETFs, the
scalp names or the PB-007 list (ADR 0014/0017). Verified market cap ≥ $500M, price ≥ $1.00, bid/ask spread
≤ 0.3% of price at entry. Quotes older than 15 minutes (`max_quote_age_seconds`) reject the tick: the
desk is run by agents every 15 minutes, and a run needs several minutes between reading and deciding.

## Entry trigger
A watchlist setup in `status: watch`, not invalidated and not expired, with a setup id, a thesis, a
catalyst and at least one cited source; reviewed by the researcher the same day
(`max_review_age_seconds`, 12 hours); with an exit deadline at least 10 minutes before the close (left
out, it is the session's exit time; a `swing` setup needs none, since its hold-by date is the deadline).
The last price must sit inside `[entry_low, entry_high]` on one
fresh quote (`max_confirmation_ticks: 1` since 2026-11-25; a second confirming run cost 15 minutes). The order is a
limit at the ask, which must itself be inside the zone. One entry attempt per setup, ever: no re-entry
after a stop, a target or a closed setup. At most 3 new orders per tick.

**Resting entry (2026-11-24).** When the price sits up to `resting_reach_pct` (3%) above the zone, or
premarket inside that reach, the kernel does not wait for a run to catch the pullback: it returns ONE
limit buy resting at `entry_high` (the fair-value top of the zone), time in force DAY, so it fills if the
market comes to the plan's price and expires with the day if it does not. Never within
`resting_cutoff_minutes` (60) of the close, never for options, never a second buy while one rests. Every
entry, resting or immediate, must carry a passing technical AND a passing fundamental factor in its
thesis; the kernel refuses one without both (`reasons` on the order).

## Invalidation
Per trade: the underlying trades at or through the stop; the researcher marks the setup invalidated; the
exit deadline arrives; or the setup's expiry date passes. Any of these produces a limit sell at the bid.
For the strategy: two consecutive weeks in which the picks' realized R is below zero with at least ten
closed trades, or one trade whose loss exceeds its planned stop risk by more than the fee model allows,
sends the lane back to Off until the thesis page is revised and re-registered.

## Sizing
Risk unit R = quantity × (limit − stop). Risk per trade 1% of NAV (`risk_per_trade_pct`), fees included in
the budget. Per-name cap 20% of NAV (`max_name_weight`), lane cap 25% of NAV (`stock_allocation_cap`),
both measured against projected NAV including pending buys. The researcher may set a smaller
`max_quantity` on a setup.

## Exit
**Hold (2026-11-25, v1.33).** Every setup carries a `hold`. `session` is the default, and every setup
written before this change: a day trade, flat by the session's exit time. `swing` holds until its stop,
its target, its contract's expiry or the setup's own `expiry` date, whichever comes first, and is never
sold because a session ended. A swing setup must name that hold-by date: an entry with `"hold": "swing"`
and no `expiry` is left out with a plain reason rather than silently turning into a day trade. The broker
bridge sends DAY orders only, so a swing lot's target sell is re-armed at the first fire of each session
and its stop is checked by each run of `tyche cycle` - an overnight gap is not capped by a resting order
and can cost more than the planned 1% risk.

**Resting take-profit (2026-11-24).** A held lot with no exit trigger gets ONE limit sell resting at the
setup's target (DAY), re-placed each session until it fills, the stop is hit or the deadline passes. A
stop or other protective trigger while it rests returns a sell for the whole lot with `cancel_first`
naming the resting order: cancel it, then sell. Selling a held lot (stop, target, invalidation, time,
the resting take-profit) is authorized by the entry's approval and needs no operator line, so an exit
never waits for one; every run of `tyche cycle` checks them: the 15-minute card and the three desk fires.

Target: limit sell when the last price reaches the setup's target. Stop: limit sell when the last price
reaches the stop (synthetic monitor, not a resting broker stop). Both are priced 0.3% under the bid
(`exit_collar_pct`), because the quote is minutes old by the time the order goes in and an exit that
rests unfilled is a lot left unprotected. Time: the setup's
exit deadline - 10 minutes before the regular close on the final day for a `session` hold; a `swing` hold
has no session clock, only its hold-by date. Fresh invalidation
from the researcher can only tighten protection, never move a stop away.

## Regime fit
Bull or Range. The lane itself has no regime gate; the operator chooses the list and can switch the lane
off from the dashboard (`data/strategies.json`), which blocks new entries while exits keep running.
Today's defensive list is the operator's answer to a weak tape; a bullish tape would call for a different
list, not a different rulebook.

## Fees / slippage
Stock: $0.99 per order plus TAF on sells, modeled in sizing. Half-spread per side as the live-cost
estimate; the 0.3% spread cap bounds it. No overnight financing in a cash paper account.

## Validation status
Unvalidated. First live trades are a test of the research → plan → approve → fill → exit path. Thirty
closed trades are needed before the Score table on the dashboard means anything.

## Evidence
- Lane code: `src/tyche/tactical.py` (entry gate, sizing, exits), `src/tyche/cycle.py` (`tyche cycle`, the one
  command both cards run), `src/tyche/tactical_cli.py` (`scout`, `reserve`).
- Rules: `config/tactical.yaml`, `config/universe.yaml`; freeze row on the Drive ledger per the runbook.
- Trades: the dashboard's Trade ideas table filtered to PB-002, and Finished trades once a position closes.
