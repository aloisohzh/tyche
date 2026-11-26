---
id: PB-003
title: Tactical long options (one call or one put on a desk pick)
# The four classification dimensions are independent (see playbook/README.md). Only playbook/INDEX.yaml
# and this block describe a playbook; nothing here is restated in an agent prompt (L-033).
classification:
  holding_period: Swing             # hours to a few sessions; every setup carries an explicit exit deadline
  strategy_type: Event-driven       # same researcher-written thesis and catalyst as PB-002
  execution_style: Semi-automated   # the researcher proposes, the kernel gates, the operator sets the approval bounds
  instruments: [Options]            # one standard long call or one standard long put; nothing sold to open
  regime_fit: [Bull, Bear, Range]   # calls for a bullish pick, puts for a bearish one
  direction: Both                   # bullish = long call, bearish = long put; no shorts, no spreads
  validation: Unvalidated           # no historical options data via MCP; this is a forward paper test
---

# PB-003 - Tactical long options (one call or one put on a desk pick)

- **Status:** on from 2026-11-24 through Fri 27 Nov 2026 (the last session of the challenge window), by the
  operator switch in `data/strategies.json`. `options_enabled` in `config/tactical.yaml` stays `false`: the
  switch, not the yaml, now decides (`AppConfig.options_live`), so turning options on or off never
  re-hashes the lane. From 25 to 27 Nov 2026 an entry inside the operator's standing paper approval
  (`data/standing-approval.json`: at most 5 contracts an order on a defensive, 3 on US.NVDA with a $20
  per-contract cap) is placed by `tyche cycle` with no per-order ask; selling a held contract never needs a
  line.
- **Rules hash:** `5927c156880d` (sha256 of `config/tactical.yaml` + `config/universe.yaml`, CRLF normalized,
  first 12). PB-002 and PB-003 are one lane with one parameter file, so they share this hash. On
  2026-11-26 the operator relaxed the option spread cap from 5% to 10% and the day-volume floor from 50
  to 20 for the researched KO call; no loss, premium, allocation, open-interest, delta or expiry limit
  changed. `1bbbe1901dde` was the prior hash; see the
  [PB-002 page](PB-002-tactical-stocks.md) for the earlier history (2026-11-25: US.NVDA joined the lane). This page
  adds no rules bytes of its own, so no separate re-freeze.
- **Validation:** unvalidated. The first paper option order was filled on 2026-11-25; one trade is a
  plumbing check, not evidence of edge.
- **Sleeve:** option premium, capped at 5% of NAV in total (`max_option_premium_pct`, cut from 25% on
  2026-11-24) and 1.5% of NAV premium per trade (`option_risk_per_trade_pct`, raised from 0.75% on
  2026-11-25: at 0.75% the budget was about $740 and the only tactical contract that passed this lane's
  own liquidity filters - NVDA 18 Dec 150 call, last 9.70 on 24 Nov - costs about $970, so every option
  entry died on "one unit exceeds risk budget"). Both numbers live in `config/risk.yaml`, which is not a
  lane rules file, so changing them re-hashes no playbook: this page is the record. The model ceiling on
  the per-trade key is 2% (`src/tyche/config.py` `RiskPolicy`).
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
Underlyings are the tactical lane's symbols in `config/tactical.yaml` (MSFT, KO, PG, JNJ, PEP, MCD and
US.NVDA on 2026-11-26). The contract must be a standard, 100-share, US-listed call or put from
`quote_option_chain`, with:
- expiry after Fri 27 Nov 2026 and within 30 days (the lane's 2-30 day limits),
- open interest ≥ 100 and day volume ≥ 20,
- bid/ask spread ≤ 10% of the price,
- delta between 0.45 and 0.80 in absolute value, with implied volatility present,
- ask no higher than the researcher's `premium_limit` on the setup.

Historical chain read on 24 Nov under the old 50-volume and 5%-spread gates (read 25 Nov, account closed
for the 26th): one tactical contract cleared those filters - NVDA 18 Dec 150 call
(`US.NVDA261218C150000`), last 9.70, open interest 22,950, day volume 100, delta 0.50, implied vol 74.6%.
The nearer weeklies (4 Dec last 7.25, 11 Dec last 8.92) printed 29 and 30 contracts and failed the old
volume floor; the 155 and 160 strikes carried delta 0.43 and 0.36, under the unchanged 0.45 directional
floor. Those were observations under the old rules, not today's eligibility result. On 26 Nov the
researched KO call was blocked by the old spread and volume gates, so the operator deliberately relaxed
only those two values. Every contract still has to pass the current gates on a fresh quote.

## Entry trigger
At most one standard long call or put per setup, which the researcher may add to the watchlist at the 08:05 ET fire of Wed 25 Nov 2026
(the 15:05 fires of 24 and 25 Nov until the desk moved to `tyche cycle`). Since 25 Nov the desk runs one
command, so any `tyche cycle` fire inside the session through Fri 27 Nov is an eligible entry moment, and
US.NVDA is a lane symbol. The same gate as PB-002, applied
to the underlying: a researcher-reviewed setup dated today, reward/risk ≥ 1.5 measured on the underlying,
and an exit deadline. The option does not wait for the underlying to pull back (operator ruling
2026-11-24): the first run of `tyche cycle` in the regular session that finds the contract inside the
liquidity filter buys it. Bullish setups may only carry a call, bearish setups only a put
(`WatchlistEntry` refuses anything else). The order is a limit buy at the option's ask.

## Invalidation
Per trade: the underlying reaches the setup's stop; the option's bid falls to 60% of the price paid (a 40%
premium loss); the researcher invalidates the setup; or the exit deadline arrives. Any of these produces a
limit sell at the bid at the next run of `tyche cycle` (every 15 minutes in the regular session).
For the test: any rejected or unfillable option order, or a position the desk cannot close, ends it.

## Sizing
One contract is 100 options. Quantity is the largest whole number of contracts whose full premium plus
modeled fees fits 1.5% of NAV (about $1,480 against the 98,831.14 paper NAV read on 2026-11-25), also
capped by the 5% total option premium (held plus pending, about $4,940) and by the per-order NAV budget.
Still usually one contract: two NVDA 18 Dec 150 calls at 9.70 are about $1,940 and do not fit, which is
the point - the debit is the risk, and an option can lose all of it. That makes 1.5% of NAV the real
worst case per option trade, double the 0.75% this lane launched with.

## Exit
**Hold (2026-11-25, v1.33).** A contract already held overnight by design; `hold: swing` drops the last
same-session fallback. With no explicit `exit_at`, a `session` lot was closed 10 minutes before the
regular close; a swing lot is closed by its hold-by date (`expiry`), its stop, the 40% premium drawdown or
the contract's own expiry, whichever comes first. The expiry rule is never relaxed: a contract is always
sold before it can expire or be exercised.

Target: sell at the bid when the underlying reaches the setup's target. Stop: the underlying's stop or the
40% premium loss, whichever comes first (synthetic, checked by every run of `tyche cycle` in the regular
session; not a resting broker stop). Time: the setup's exit deadline, for this test 12:10 ET on the
Fri 27 Nov half day, which leaves the 12:07, 12:22, 12:37 and 12:52 runs to get the sell in. A contract
bought on Wed 25 Nov is held over the Thanksgiving closure; nothing can be done about it while the market
is shut. Selling a held contract needs no operator line. Every contract
must expire after 27 Nov, so a contract still held at the final close is valued at market and can never
be exercised inside the window.

## Regime fit
Any: the direction of the pick picks the right. The operator can switch PB-003 off from the dashboard at
any time; exits keep running while it is off.

## Fees / slippage
Options: $0.65 per contract commission (premium above $0.10), $0.30 platform, small TAF and regulatory fees,
minimum $1.99 per order (docs/competition/rules.md). Modeled in sizing and journaled. The 10% spread cap
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
