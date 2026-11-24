---
id: PB-003
title: Tactical long options (one call or one put on a desk pick)
# The four classification dimensions are independent (see playbook/README.md). Only playbook/INDEX.yaml
# and this block describe a playbook; nothing here is restated in an agent prompt (L-033).
classification:
  holding_period: Swing             # hours to a few sessions; every setup carries an explicit exit deadline
  strategy_type: Event-driven       # same researcher-written thesis and catalyst as PB-002
  execution_style: Semi-automated   # the researcher proposes, the kernel gates, the operator approves on Telegram
  instruments: [Options]            # one standard long call or one standard long put; nothing sold to open
  regime_fit: [Bull, Bear, Range]   # calls for a bullish pick, puts for a bearish one
  direction: Both                   # bullish = long call, bearish = long put; no shorts, no spreads
  validation: Unvalidated           # no historical options data via MCP; this is a forward paper test
---

# PB-003 - Tactical long options (one call or one put on a desk pick)

- **Status:** on from 2026-11-24 through Fri 27 Nov 2026 (the last session of the challenge window), by the
  operator switch in `data/strategies.json`. `options_enabled` in `config/tactical.yaml` stays `false`: the
  switch, not the yaml, now decides (`AppConfig.options_live`), so turning options on or off never
  re-hashes the lane. Every entry still waits for the operator's Telegram `/approve` in Ask me mode, or a
  same-day envelope in Within my bounds.
- **Rules hash:** `a1d9df1c687c` (sha256 of `config/tactical.yaml` + `config/universe.yaml`, CRLF normalized,
  first 12). PB-002 and PB-003 are one lane with one parameter file, so they share this hash; see the
  [PB-002 page](PB-002-tactical-stocks.md) for the history. This page adds no rules bytes, so no re-freeze.
- **Validation:** unvalidated. No option order has been sent on this account before this test.
- **Sleeve:** option premium, capped at 5% of NAV in total (`max_option_premium_pct`, cut from 25% on
  2026-11-24) and 0.75% of NAV premium per trade (`option_risk_per_trade_pct`).
- **Env:** paper (competition)

## Thesis
The desk already writes a dated, sourced thesis with an entry zone, a stop, a target and an exit deadline
for its tactical picks (PB-002). PB-003 expresses the same kind of pick with one bought option instead of
shares: a long call when the thesis is bullish, a long put when it is bearish. A put is the only way the
desk can act on a bearish view, because it never shorts shares. The loss is capped at the premium paid.

## Edge
None claimed yet. Options can turn a correct directional call into a larger percentage gain than shares,
but time decay and the bid/ask spread work against every holder, and a small move in the right direction
can still lose money. The aim of this first week is plumbing proof: that an option order can be planned,
approved, filled, protected and closed on this paper account, with fees journaled.

## Universe / liquidity filter
Underlyings are the tactical lane's symbols in `config/tactical.yaml` (today MSFT, KO, PG, JNJ, PEP, MCD).
The contract must be a standard, 100-share, US-listed call or put from `quote_option_chain`, with:
- expiry after Fri 27 Nov 2026 and within 30 days (the lane's 2-30 day limits),
- open interest ≥ 100 and day volume ≥ 50,
- bid/ask spread ≤ 5% of the price,
- delta between 0.45 and 0.80 in absolute value, with implied volatility present,
- ask no higher than the researcher's `premium_limit` on the setup.

## Entry trigger
Only at the 15:05 ET fires of Tue 24 and Wed 25 Nov 2026. The same gate as PB-002, applied to the underlying: a fresh researcher-reviewed setup, the underlying's
last price inside the entry zone for the configured number of fresh quotes, reward/risk ≥ 1.5 measured on
the underlying, and an exit deadline. Bullish setups may only carry a call, bearish setups only a put
(`WatchlistEntry` refuses anything else). The order is a limit buy at the option's ask.

## Invalidation
Per trade: the underlying reaches the setup's stop; the option's bid falls to 60% of the price paid (a 40%
premium loss); the researcher invalidates the setup; or the exit deadline arrives. Any of these produces a
limit sell at the bid at the next fire or monitor check.
For the test: any rejected or unfillable option order, or a position the desk cannot close, ends it.

## Sizing
One contract is 100 options. Quantity is the largest whole number of contracts whose full premium plus
modeled fees fits 0.75% of NAV, also capped by the 5% total option premium (held plus pending) and by the
per-order NAV budget. Usually one contract.

## Exit
Target: sell at the bid when the underlying reaches the setup's target. Stop: the underlying's stop or the
40% premium loss, whichever comes first (synthetic, checked at each 08:05 and 15:05 fire; not a resting
broker stop). Time: the setup's exit deadline, set to the next fire after entry. Entries happen only at the
15:05 ET fires of Tue 24 and Wed 25 Nov, and an overnight sell goes through the operator exit path (the
desk asks on Telegram, then sells with `tyche exit-now`), never below 60% of the price paid. The 12:05
fire never submits, so on the Fri 27 Nov half day the last sell chance is the 08:05 fire. Every contract
must expire after 27 Nov, so a contract still held at the final close is valued at market and can never
be exercised inside the window.

## Regime fit
Any: the direction of the pick picks the right. The operator can switch PB-003 off from the dashboard at
any time; exits keep running while it is off.

## Fees / slippage
Options: $0.65 per contract commission (premium above $0.10), $0.30 platform, small TAF and regulatory fees,
minimum $1.99 per order (docs/competition/rules.md). Modeled in sizing and journaled. The 5% spread cap
bounds slippage, but a wide option spread is the largest cost of this lane.

## Pass / fail (this test, 24-27 Nov 2026)
- **Pass:** at least one option trade is bought and sold cleanly on the paper account, with the plan,
  approval, fill, exit and fees in the journal and the result on the dashboard.
- **Fail:** option orders are rejected by the broker, cannot be filled inside the limits, or a position
  cannot be closed before the deadline.
- Profit is not judged: three sessions are far too few. A pass earns a longer test with a profit rule
  (avg trade > 0 after fees over 30 finished trades), like PB-002 and PB-007.

## Evidence
- Lane code: `src/tyche/tactical.py` (option gates, sizing, premium-loss and expiry exits),
  `src/tyche/risk.py` (premium cap, no-short rule), `src/tyche/broker/tactical_data.py` (chain parsing).
- Rules: `config/tactical.yaml`, `config/risk.yaml`; switch: `data/strategies.json`.
- Decision: operator chose "Buy calls/puts, 5% slice" on 2026-11-24 (project thread "Add an options trading
  strategy"). Covered calls and cash-secured puts were not chosen: they sell options to open, which the
  kernel's no-short rule and ADR 0012 refuse.
