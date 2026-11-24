---
id: PB-006
title: Sector rotation heat (relative-strength sleeve)
classification:
  holding_period: Position         # held for weeks; reviewed once a week
  strategy_type: Momentum          # owns the sector funds that are rising fastest
  execution_style: Fully automated # a fixed weekly ranking; no judgement call in the pick
  instruments: [Stocks]            # sector ETFs only, no options leg
  regime_fit: [Bull]               # stands down unless the market gate reads risk_on
  direction: Long
  validation: Unvalidated          # no backtest and no trade yet
---

# PB-006 - Sector rotation heat (relative-strength sleeve)

- **Status:** draft. Written 2026-11-24 at the operator's request. **Not built and not tradable:** there
  is no lane in the code, no config file and no switch, so the desk cannot run it. `playbook/INDEX.yaml`
  keeps it `planned`.
- **Rules hash:** none yet. It is computed by the kernel when `config/strategies/pb-006.yaml` exists;
  never hand-written.
- **Validation:** unvalidated. It must pass the backtest bar in "Evidence" before any switch is added.
- **Sleeve:** equity (sector rotation), proposed 15% NAV allocation cap. Not allocated yet.
- **Env:** paper (competition)
- **Why PB-006:** the id was claimed for this idea when the PB-004 collision was renumbered (L-029), and
  an id is claimed once and kept forever.

## Thesis
Money moves between sectors in waves that last weeks to months. When one theme is in favour, the funds
that hold it keep beating the wider market for a while, because large investors build positions slowly
and performance-chasing follows. This setup ranks sector funds once a week by how much they have beaten
SPY and owns the top three, so the sleeve always sits in whatever is hot and leaves it when the heat
fades.

Operator's read on 2026-11-24 (his view, recorded as the reason for writing this now, not a tested
fact): it is "AI craze season" again, so chip and software funds are where the heat should show first.
The rules below do not assume that. If AI funds lead, the ranking picks them; if they do not, it picks
whatever does lead.

## Edge
Why it should work after fees: sector relative strength over one to three months is one of the
better-documented momentum effects, the funds are very liquid (a cent or two of spread), and a weekly
review means only a handful of trades a month, so fees are a rounding error next to a 15% sleeve.

Why it might not: momentum buys what has already gone up. It does worst at turning points, when the
leading sector reverses sharply and the ranking only notices a week later. A hot theme is also a
crowded one: AI funds can fall 10% in a few sessions. And PB-001 already rotates broad ETFs on a similar
signal, so this sleeve may add the same bet twice instead of a new one.

Drift is not edge: in a rising market any basket of sector funds goes up. The test that matters is
whether the top-three basket beats (a) SPY and (b) an equal-weight basket of all twelve funds over the
same dates. If it does not beat both, the ranking adds nothing.

## Universe / liquidity filter
Twelve funds: the ten Vanguard sector ETFs VGT (technology), VHT (health care), VFH (financials), VDE
(energy), VIS (industrials), VCR (consumer discretionary), VDC (consumer staples), VPU (utilities), VAW
(materials), VOX (communication services), plus two AI-heat funds, SOXX (semiconductors) and IGV
(software).

These are deliberately not the SPDR sector funds: XLF, XLE, XLK, XLV, XLI, XLY, XLP and XLU belong to
PB-007, SMH belongs to the scalp lane and VNQ to PB-001, and the config loader refuses a symbol owned by
two lanes (ADR 0017). All twelve are above $1.00 and far above the $500M size floor. Entry is skipped
for a fund whose bid-ask spread is wider than 0.10% at the run.

## Entry trigger
Once a week, at the first 08:05 ET run of the week, using daily closes up to the prior session:

1. For each fund, score = 0.5 x (21-session return minus SPY's 21-session return) + 0.5 x (63-session
   return minus SPY's 63-session return).
2. A fund qualifies only if its score is above zero **and** its last close is above its own 50-day
   simple moving average.
3. Rank the qualifying funds by score. The targets are the top three. Fewer than three qualifying means
   fewer positions; the unused share stays in cash.
4. SOXX and VGT hold many of the same companies, as do IGV and VGT. At most two of {SOXX, IGV, VGT} may
   be held at once; the third slot goes to the next-ranked fund outside that group.
5. Buy each new target with a marketable limit order at the ask plus 0.05%, during the regular session
   only. An order not filled by the 12:05 ET run is cancelled and not chased.

No entries in the last week of a competition window, on a half day, or while the gate is not risk_on.

## Invalidation
Per trade, any one of these ends the position:
- the fund closes below its 50-day simple moving average;
- the fund falls 8% below its entry price (protective stop);
- at a weekly review it is no longer in the top five by score;
- the market gate leaves risk_on (all positions in this sleeve are sold at the next run).

Per strategy, the sleeve is switched off and this page marked killed if, after 30 finished trades, the
average trade is not above zero after fees, or the sleeve has drawn down more than 4% of the account,
or it has failed to beat the equal-weight twelve-fund basket over the same dates.

## Sizing
Proposed sleeve cap 15% of NAV, equal weight: 5% of NAV per fund, three funds at most. With the 8% stop
each position risks about 0.4% of NAV, so the whole sleeve risks about 1.2%. Current caps add to 75%
with every lane on (PB-001 25%, PB-002 25%, PB-003 5%, PB-007 20%), so 15% fits under the 95% gross
limit with 5% to spare. A cap is a config change with a rules re-freeze; this page does not set it.

## Exit
- **Stop:** 8% below entry, watched by the desk at every run (synthetic monitor, not a resting order).
- **Trend exit:** sell at the next run after a close below the 50-day average.
- **Rotation exit:** sell at the weekly review when the fund has dropped out of the top five. Ranks
  four and five are a "hold" zone, so a fund is not sold and re-bought on small rank changes.
- **Gate exit:** sell everything in the sleeve at the next run after the gate leaves risk_on.
- **No profit target:** winners run until one of the exits above fires.
- **Final-day flatten:** all positions are sold at the 15:05 ET run of the last session of a window.

## Regime fit
On only when the market gate reads risk_on. Off in neutral and risk_off: relative strength in a falling
market just means "falling less", and this sleeve only buys. The gate read risk_off on 2026-11-23, so
even a finished build would have stood down that day.

## Fees / slippage
Stock: $0.99 per order plus TAF on sells. A full rotation of all three funds is six orders, about $6,
against a sleeve of roughly $15,000 at 15% of a $100,000 account: 0.04%. Half-spread is a cent or two
on these funds. Expected turnover is two to four orders in a typical week.

## Evidence
None yet. No backtest, no plan artifact, no journal row, no trade.

Before it can be switched on, in this order:
1. Add a `sector_rotation` lane kind and `config/strategies/pb-006.yaml` (symbols, 15% cap,
   `enabled: false`), and add the twelve symbols to `config/universe.yaml`.
2. Backtest on daily bars over at least 2025-05-01 to date, net of fees. Pass bar: profit factor of at
   least 1.2, and a higher return than both SPY and the equal-weight twelve-fund basket, in 2025 and in
   2026 separately. PB-007 failed this kind of test on 2026-11-24; hold this one to the same standard.
3. Freeze the rules (`tyche rules-freeze --record`), change this page's Status and Validation lines, and
   move the roster row from `planned` to `live`.
4. Add the desk card clause for the weekly review, then use the switch in Controls.
