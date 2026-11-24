# TYCHE premarket broad discovery — 2026-11-24 (Tuesday)

- Role: tyche-researcher (scout). UNAPPROVED research only — no approvals, no orders, no journal writes, no config edits.
- Delegation clock: ~08:08 ET / 13:08 UTC premarket plan fire (three-fire card: 08:05 / 12:05 alert-only / 15:05 ET).
- Review completed ≈ 2026-11-24T13:40Z (estimate; member session has no shell clock; started 13:08Z per delegation).
- NAV references (delegation-supplied, not re-verified here): challenge baseline 100,000.00; last-good Nov-23 NAV 99,380.95.
- Holdings SPY 28 / EFA 142 / MSFT 39 are ALL being sold today under the operator same-day exit envelope (approved 00:42Z per delegation). No hold theses built for them; exit-relevant notes in §8.
- Write ranges honored: this report + watchlist proposal under `/data/drive/tyche-raw/2026-11-24-premarket-1305/research/` ONLY. The working copy `/data/drive/tyche-raw/watchlist.json` was READ (as_of 2026-11-23, JNJ/PEP entries both expiry-expired) but NOT overwritten — my role guard forbids overwriting that path; the Desk Head publishes the run-path proposal. Flagged to coordinator.

## 1. Macro regime — Fed HIKE cycle, VERIFIED against fresh sources

- CME FedWatch via Futu flash 1005385138, pub 1795471501000 = **2026-11-23T22:05:01Z**: Dec **25bp HIKE 95.9%**, **50bp hike 4.1%**; by Jan cumulative 50bp 64.2%, 75bp 2.7%. This is a hike cycle — no cut odds anywhere in this report.
- WSJ Market Talk 1005404427, pub 1795485420000 = **2026-11-24T01:57:00Z**: Treasurys edged lower in Asia on higher hike prospects; 2Y 4.6809% (+1bp), 10Y 4.9307% (+1bp) (FactSet via WSJ). Monday's surge was relief from Friday's slide + Nvidia AI-ecosystem funding; NAB says AI relief emboldens the Fed.
- CoinDesk 1005309126, pub 2026-11-23T04:45:47Z: last week's rout killed the 50bp Dec tail (was ~10-15%); Nasdaq fell 10.4% last week (worst since Mar 2020), VIX +86% that week; RBC expects Oct PCE +0.3% m/m headline/core, 3.8%/3.3% y/y. Focus this week: core PCE.
- Wallstreetcn 1005344282, pub 2026-11-23T11:42:29Z (Ackman): Oct FOMC held 3.75–4.00% with two hike dissents; minutes showed almost all participants saw further hikes as possibly appropriate; Sept PCE 3.6% headline / 3.1% core (staff estimates). Ackman warns a Dec-9 hike could tip the economy into recession; wants a 3% target. Opinion, not data.
- ECB Simkus flash 1005332163, pub 2026-11-23T09:03:53Z: ECB Dec hike may not suffice — global tightening backdrop (EFA context).

**Tuesday premarket tape (MCP quote_stock_quote batch fetched ≈13:10Z; RTH fields data_time 1795467600xxx = 2026-11-23T21:00Z close; pre_market sub-objects live Nov-24 premarket):**

| ETF | Nov-23 close | Nov-23 chg vs prev | Premarket | Premarket chg vs Nov-23 close |
|---|---|---|---|---|
| SPY | 722.29 | +4.71% (prev 689.81) | 713.95 | −1.15% |
| QQQ | 651.03 | +7.00% (prev 608.45) | 637.43 | −2.09% |
| IWM | 265.74 | +3.56% | 263.68 | −0.78% |
| EFA | 98.76 | +2.73% | 98.775 | +0.02% |
| EEM | 57.83 | +7.41% | 57.02 | −1.40% |
| TLT | 81.69 | +0.29% | 81.94 | +0.31% |
| IEF | 91.64 | −0.01% | 91.7387 | +0.11% |
| GLD | 333.02 | +3.14% | 332.43 | −0.18% |
| DBC | 29.11 | −0.72% | 29.11 | 0.00% |
| VNQ | 93.67 | +1.20% | 93.6751 | +0.005% |
| HYG | 76.52 | +0.25% | 76.52 | 0.00% |

Read: Monday's violent risk-on rebound (SPY +4.71%, QQQ +7.00%) is being faded Tuesday premarket, growth hardest (QQQ −2.09%), while defensives bid (KO +0.70%, PG +0.71%, PEP +0.78%, JNJ +0.93% ex-div-adjusted, MCD +0.46% premarket) and long bonds bid (TLT +0.31%). Credit calm (HYG flat/+0.25%). This supports the operator's risk-off rotation-into-defensives thesis for PB-002 today. VIX: **no fresh print available** (no VIX tool; desk history ~30 on Nov-20; a Nov-21 community post says mid-20s — untrusted, not used as data). Gap recorded.

Unverified context (community-only, NOT issuer-verified, outside universe): a Nov-24 moomoo post claims NVDA +31.48% Nov-23 on Jensen Huang's return as CEO and SPX +4.73%/NDX +6.51%/DJI +3.01%. The SPY quote above independently corroborates a ~+4.7% SPX day; the NVDA/Huang claim remains single-stream unverified (desk deferred pinning it Nov-23) and is not used as a catalyst.

## 2. Imminent events (next 14 days)

Already pinned (skip re-proposal): Nov-25 PCE price index 08:30 ET + Beige Book 14:00 ET, Dec-9 FOMC, Dec-4 ANT index inclusion (src/tyche/market_calendar.py EVENTS_2026); Nov-19/20 items in config/events.yaml. Thanksgiving Nov-26 closed / Nov-27 13:00 ET early close are calendar facts (delegation + market_calendar HALF_DAYS).

MCP quote_economic_calendar_hot 20261124: **EMPTY** (gap; same as Nov-20/23). 20261125 (fetched this run, all event_time 1795613400 = 2026-11-25T13:30Z = 08:30 ET):
- Core PCE Price Index (YoY): cons **3.2%**, prev 3.1% (indicatorId 905) — already pinned as PCE.
- Initial Jobless Claims: cons **201K**, prev 203K (indicatorId 294).
- GDP (QoQ): cons **3.4%**, prev 2.2% (indicatorId 375).

Wednesday 08:30 ET is a triple macro slot (PCE + GDP + claims) 35 minutes before the open, on the last full session before the holiday. Hot prints compound hike risk into the thin Thanksgiving week; this is the main horizon risk for any defensive long held beyond today (none proposed overnight except the PB-003 draft, §6).

### Event discovery proposals (Desk Head validates and pins; I never write config/events.yaml)

| # | date (ET) | name | kind | symbols | source | materiality |
|---|---|---|---|---|---|---|
| 1 | 2026-11-24 | JNJ ex-dividend $1.34/share (record Nov-24, payable Dec-8) | macro* | US.JNJ | Futu 1005291326 pub 2026-11-23T01:00:01Z; corroborated by quote pre_market change_val 2.505 = 271.215 − (270.05 − 1.34) | ~0.5% mechanical price drop today; intraday levels must use the ex-div reference 268.71 |
| 2 | 2026-11-25 08:30 | GDP (QoQ) cons 3.4% prev 2.2% | macro | US.SPY, US.QQQ, US.IWM | MCP quote_economic_calendar_hot 20261125 indicatorId 375 | growth print in a hike cycle; shares the 08:30 slot with PCE — hot combo revives 50bp tail |
| 3 | 2026-11-25 08:30 | Initial Jobless Claims cons 201K prev 203K (holiday-shifted) | macro | US.SPY, US.TLT | MCP quote_economic_calendar_hot 20261125 indicatorId 294 | weekly labor print stacked into the same pre-open slot |
| 4 | 2026-11-23 (post-close announce) | KO CFO succession: John Murphy retires 2027; David Elkins (BMY CFO) effective 2027-04-02 | macro* | US.KO | Dow Jones 1005383343 pub 2026-11-23T21:33:00Z; Zhitong 1005437317 pub 2026-11-24T07:03:00Z | KO-specific governance event; MS/BofA/RBC reiterations followed this morning; observable price/flow reaction |

*Kind-vocabulary gap: `tyche events add --kind` accepts macro/fomc/earnings/ipo/index; rows 1 and 4 are corporate actions with no exact kind — flagged for Desk Head mapping, not silently forced. No unverified rumors proposed. Fed-speaker schedule for this week not found in feed (gap, same as Nov-23).

## 3. PB-001 ETF ballast — rule-based context only (no scout thesis)

PB-001 (config/strategies/pb-001.yaml, allocation_cap 0.25) computes regime from trend_sma200 / 50-200 cross / vol20-vs-252 ratio (limit 1.25) / credit 63d. This run did NOT fetch the 370-bar history (daily kline handoff not requested), so today's check values are **unknown, not fabricated**:
- Trend: SPX was below its 200DMA on Nov-20 (desk history); Monday's +4.71% may have restored it — unverified without full history.
- Vol: no fresh VIX; 20/252 realized-vol ratio not computed. Last kernel regime (Nov-23 premarket, desk memory): **risk_off, 1/4 checks**.
- Credit: HYG 76.52 (+0.25% Nov-23, flat premarket) — no visible credit stress in price; 63d trend not computed.
Rule-based read: risk_off sleeve caps (equity 0.20 / defensive 0.60 / real_asset 0.30 / credit 0.00) remain the plausible frame; TLT bid + GLD +3.14% Monday + HYG calm is consistent with risk-off-without-credit-panic. Ballast stays ballast; the Desk Head's kernel owns any rotation. SPY/EFA holdings are exiting under the envelope regardless.

## 4. Ranked PB-002 candidates (tactical universe: MSFT, KO, PG, JNJ, PEP, MCD)

Ranking: **1. KO, 2. PG, 3. JNJ** (proposed); MCD no-trade, PEP rejected, MSFT no new entry (§7). All three are same-session longs, exit 15:50 ET (20:50Z), expiry 2026-11-24, one entry attempt, no re-entry, no scaling. Caps are ceilings, not targets: proposed notionals ≈8% NAV each, 23.8% aggregate ≤25%; per-name ≤20%; stop-risk ≤1% NAV/trade (all ≈0.1%); cash stays ≈76% ≥5%; gross ≈24% ≤95% — **conditional on the envelope exits filling first** (kernel sequences; if exits fail, entries must not stack on top of legacy gross).

Market caps are DERIVED ESTIMATES (no direct MCP market-cap field; profiles lack it): KO shares_short 47,240,965 ÷ short_percent 1.098% (MCP quote_short_interest settlement 2026-10-30) ≈ 4.302B shares × Nov-23 close 95.88 ≈ **$412.5B**; PG 22,369,376 ÷ 0.965% ≈ 2.318B × 169.60 ≈ **$393.1B**; JNJ Nov-23 volume 9,916,290 ÷ turnover_rate 0.00412 ≈ 2.407B × 270.05 ≈ **$650B**. All ≫ $500M floor; all prices ≫ $1.

### #1 US.KO — setup TL-20261124-KO-DEF1 (bullish stock, PB-002)

- **Entry zone 96.10–96.60** (brackets premarket 96.55, range 96.16–96.976; above the 94.60/94.73 double bottom; no chase above 96.60). **Stop 95.40** (intraday thesis stop: loss of Nov-23 close 95.88 with buffer = rotation bid failed; sits above the 94.60 double bottom, so this is a momentum stop, not a swing stop). **Target 98.40** (supply zone 98.09 Nov-18 close / 98.53 Nov-17 low; target just under the upper edge). R/R = 1.50 at zone top, 3.29 at zone bottom (≥1.5).
- **max_quantity 82** (≈8% NAV budget 7,950 ÷ entry_high 96.60; notional 7,921.20; stop-risk 82×1.20 = $98.40 ≈ 0.10% NAV ≤1%). Research bound only — kernel sizes.
- **exit_at 2026-11-24T20:50:00Z (15:50 ET)**, expiry 2026-11-24, confirmation_ticks 2.
- **Catalyst (fresh, dated):** CFO succession announced Monday post-close (DJ 1005383343, 2026-11-23T21:33Z); MS maintains OW $103 and calls the transition smooth (Zhitong 1005437317, 2026-11-24T07:03Z); RBC Buy $96 (1005449136, 08:32Z); BofA Buy $100 (1005466933, 10:31Z); MS Mohsenian Buy $103 (1005473561, 11:33Z). Three same-day reiterations after a governance event = the news is being absorbed constructively.
- **Thesis block (verbatim in watchlist):** rotation long; macro pass (hike-cycle risk-off, growth faded premarket), catalyst pass, fundamental pass (Q3-26 gross 62.3% / operating 32.1% / net 28.65% / ROE 42.6% / FCF-NI 97.6%, MCP key indicators), technical MIXED — MA5<MA10 death cross + close below MA20/BOLL-mid (**fail**) vs RSI6/CCI oversold-reversal flag (**pass**) (MCP quote_unusual_technical [1795410000]); flow **fail** (Nov-23 main −$81.05M, total −$92.96M; block-trade outflow accelerating +197% vs prior 3d avg, MCP quote_unusual_capital [1795439545 = Nov-23 13:12:25Z]); sentiment pass (retail bullish-hold, signal only); liquidity pass (ADV 17.53M sh; Nov-23 30.11M sh / $2.89B); seasonality unknown. Conviction **medium**.
- **Bear case:** Monday's −1.14% on a +4.7% SPY day shows KO was a funding source for the growth rebound; if growth rebounds again today the rotation reverses and the 95.40 stop is hit; PE 31.5 (kline) is rich for a staples name; options flow mixed — 6,303-lot SELL of Dec-18 103C at 11.24 02:27 (OI 0, $119.8k) and Jan-27 92.5P buys (4,999 lots) = hedging/overwrite interest (MCP quote_unusual_derivatives; print times as stated by payload, timezone unverified).
- **Invalidation:** trade ≤95.40; or rotation reversal (QQQ/SPY reclaim Monday highs with staples red); or 15:50 ET deadline; or expiry. Missed/stale review blocks entry, not a liquidation signal.

### #2 US.PG — setup TL-20261124-PG-DEF1 (bullish stock, PB-002)

- **Entry zone 170.20–170.80** (premarket 170.80, high 171.31; zone sits at/just below premarket, above Nov-23 high 170.64 breakout area; no chase above 170.80). **Stop 169.00** (below Nov-20 low 169.05 and Nov-23 close 169.60 — losing both = rotation failed). **Target 173.50** (just under the Nov-16/17 double top 173.57/173.59). R/R = 1.50 at zone top, 2.75 at zone bottom.
- **max_quantity 46** (7,950 ÷ 170.80; notional 7,856.80; stop-risk 46×1.80 = $82.80 ≈ 0.08% NAV).
- **exit_at 2026-11-24T20:50:00Z**, expiry 2026-11-24, confirmation_ticks 2.
- **Catalyst (fresh, dated Nov-23):** MS OW PT 185→192 (1005344842, 11:31Z); BofA Buy 185→190 (1005344841, 11:31Z); Citi Buy 187→190 (Gelonghui 1005320583, 07:44:28Z; Futu 1005349545, 12:31Z); FactSet avg OW 176.90 (MT 1005340126, 10:32:29Z). A same-day PT-raise cluster. No direct issuer PR today — catalyst axis rests on the analyst cluster, honestly labeled.
- **Thesis block:** macro pass; technical **pass** (MA bullish alignment, MCP quote_unusual_technical [1795410000]); fundamental pass (FY27Q1 gross 49.78% / operating 22.55% / net 17.90% / ROE 29.45% / FCF-NI 95.7%, MCP key indicators); flow split — daily main Nov-23 −$27.03M (**fail**) BUT a 2,000-lot BUY of Dec-18 165C at 11.24 01:28, $1.43M premium, OI 17,202 (**pass**, MCP quote_unusual_derivatives; print time as stated, timezone unverified); sentiment pass (retail defensive-haven bullish; posts mostly older — signal only); liquidity pass (ADV 10.65M sh; Nov-23 10.21M sh / $1.73B); seasonality unknown. Conviction **medium**.
- **Bear case:** PG also fell as a funding source Monday-relative (only +0.14% on a +4.7% SPY day); the 165C block is deep-ITM and could be a hedge leg of a larger structure (unknown); target requires +1.6% intraday from zone top — PG's Nov-16 range was 1.9% so plausible but not base-rate; premium PT cluster may already be priced after premarket +0.71%.
- **Invalidation:** trade ≤169.00; rotation reversal; 15:50 ET deadline; expiry.

### #3 US.JNJ — setup TL-20261124-JNJ-DEF1 (bullish stock, PB-002, LOW conviction)

- **Ex-dividend TODAY $1.34** (proposal #1). The quote feed already adjusts: pre_market change_val 2.505 = 271.215 − (270.05 − 1.34) ⇒ ex-div reference **268.71**, premarket **+0.93%** genuine strength. Buying today earns NO dividend. Executor must re-verify the ex-div reference at the open.
- **Entry zone 269.80–271.20** (brackets premarket 271.215; above ex-div reference 268.71). **Stop 268.50** (below today's premarket low 268.884 and the ex-div reference 268.71). **Target 275.25** (round-275 resistance, below Nov-6 close 276.22; softer basis than KO/PG targets — hence low conviction). R/R = 1.50 at zone top, 4.19 at zone bottom.
- **max_quantity 29** (7,950 ÷ 271.20; notional 7,864.80; stop-risk 29×2.70 = $78.30 ≈ 0.08% NAV).
- **exit_at 2026-11-24T20:50:00Z**, expiry 2026-11-24, confirmation_ticks 2.
- **Catalysts (dated):** TREMFYA phase-4 STAR met primary + key secondary endpoints (Benzinga/PR 1005194419, 2026-11-20T13:02:51Z); JPM PT 285→300, Hold (1005197395/1005185458, 2026-11-20T13:31Z); Ollin acquisition $3.325B ($2.2B upfront + $1.125B milestones; AASTOCKS 1005169424, 2026-11-20T09:17:49Z).
- **Thesis block:** macro pass; flow **pass** (Nov-23 total **+$90.40M**, main +$35.39M — the only tactical name with positive Monday flow, MCP quote_capital_flow_history bar 1795410000000); technical pass (premarket +0.93% ex-div vs SPY −1.15%; no adverse MA anomaly flagged — quote_unusual_technical returned code 1 "no anomaly", which is absence of signal, not a bullish flag); fundamental pass with caveat (Q3-26 gross 67.56% / operating 25.70% healthy; net margin 16.20% is −40.6% y/y — likely charges, composition unverified → bear-case item); catalyst pass; sentiment pass (bullish read but posts mostly October — stale, signal only); liquidity pass (Nov-23 9.92M sh / $2.68B); dividend_reference pass (arithmetic above); seasonality unknown. Conviction **low**.
- **Bear case:** ex-div days can see mechanical selling pressure beyond the $1.34 adjustment; net-margin collapse y/y unexplained in this run; target 275.25 needs +1.5% intraday vs JNJ's recent ~1.1–1.3% daily ranges; the Nov-23 JNJ proposal (TL-20261123-JNJ-DEF1) never filled and expired — this is a NEW setup on new evidence (Monday flow + ex-div-adjusted premarket strength), not a carry-over.
- **Invalidation:** trade ≤268.50; feed shows an unadjusted reference (executor check); rotation reversal; 15:50 ET deadline; expiry.

**Execution-timing note (all three):** exits anticipate the 15:05 ET close fire with 45 minutes of margin (15:50 ET = session_exit_minutes_before_close 10). If entries can only execute AT the 15:05 fire, the hold compresses to ≤45 minutes and the same fire must own the exit; if the desk executes at the RTH open after premarket approval, the full session applies. Desk Head decides; no entry whose exit deadline arrives at/before the next fire that can act. Between fires, stops are SYNTHETIC — not resting broker stops, not guaranteed fills; gaps, halts, delayed runs and limit non-fills can exceed the planned stop loss. Daily-close triggers execute no earlier than the next permitted session.

## 5. Community sentiment (signal only; untrusted retail chatter; fetched ≈13:30Z)

- **KO** (ai-news-search stock_feed, code 0, 6 posts used): 4 bullish / 2 neutral → **bullish-lean**. Themes: (1) long-term holders treat the 99→96 pullback as noise, hold for the dividend but won't add at ~32x earnings; (2) PCE-preview commentary frames KO/JNJ as defensive havens. fetched_at ≈2026-11-24T13:30Z.
- **PG** (code 0, 4 posts used): 3 bullish / 1 neutral → **bullish-lean, stale** (most posts October; one Nov-21 flow note claims staples saw strong inflows during the selloff). Themes: staples as fear-shock hedge; "money hiding" in staples/utilities. Never a direction/size input.
- **JNJ** (code 0, 5 posts used): 4 bullish / 1 neutral → **bullish-lean, mostly October**. Themes: healthcare defensive haven; pipeline/product newsflow (TD Cowen Buy $300, Shockwave catheter launch). Staleness disclosed in the factor detail.
- SPY/EFA/MSFT held-name sentiment not separately fetched (exiting today; exit report only). Recorded gap.

## 6. PB-003 LONG OPTIONS test — DRAFT candidates, contract fields UNKNOWN

**Config divergence (must resolve before 15:05):** the run brief says PB-003 enabled with entries ONLY at the 15:05 ET fires of Tue-24 and Wed-25; the mounted `config/tactical.yaml` line 6 reads `options_enabled: false`. The brief names the live playbooks and wins for research scope, but the executor must verify the effective config at the fire — if the lane is off in config, these stay research, not proposals.

**This session has NO option-chain tool.** Strike, expiry-selection, delta, premium, OI, volume and spread are **unknown/unverified** for every candidate below; the executor pulls quote_option_chain (filter_standard=STANDARD) at 15:05 and verifies: expiry strictly AFTER 2026-11-27 and ≤30 days (Dec-4/11/18 eligible; Nov-27 expiries INELIGIBLE), nearest |delta| 0.55 (eligibility band .45–.80), OI ≥100, volume ≥50, option spread ≤5%, stock spread ≤0.3%, quotes/books ≤60s. Chain membership alone is not permission to trade or proof of paper-option support. Never substitute last price for an executable market.

**Candidate A (primary): ONE standard LONG CALL on US.PG, Dec-18 expiry preferred** (24 DTE; the 2,000-lot 165C buy block sits in this expiry with OI 17,202 — but the 0.55-delta rule governs strike selection, not the block). Direction bullish; levels refer to the UNDERLYING: entry zone PG 170.20–171.30, stop 169.00, target 173.50 (same thesis as §4 #2). Draft block shape for the executor to complete:

```
symbol:        US.PG261218C<strike*1000>   [UNKNOWN — chain-verify]
option:        {underlying: US.PG, expiry: 2026-12-18, right: call, strike: UNKNOWN, multiplier: 100}
direction:     bullish
premium_limit: min(7.45, verified executable ask) per share   [rationale below]
exit_at:       2026-11-25T13:05:00Z (next fire start, per brief)  [tension flagged below]
```

**Candidate B (alternate): ONE standard LONG CALL on US.KO, Dec-18 expiry** (24 DTE). Direction bullish; underlying levels: entry 96.10–96.98, stop 95.40, target 98.40 (§4 #1). Weaker than A: the Dec-18 103C saw a 6,303-lot SELL (OI 0) and Jan-27 put buying — mixed options flow. Same unknowns; same verification gates. The 11.24 04:29 1,000-lot BUY of the **Nov-27** 95C ($167k, V/OI 4.7) is NOT eligible (expiry not strictly after Nov-27) — noted as flow color only.

**Premium-limit rationale:** aggregate premium cap 5% NAV (brief) = $4,969.05 on 99,380.95; per-trade FULL DEBIT at risk ≤0.75% NAV = **$745.36** ⇒ with multiplier 100, **1 contract maximum** and premium_limit ≤ **$7.45/share**. If the verified ask exceeds 7.45, the trade is BLOCKED (no sizing below 1 contract, no ladder, no re-entry). Do NOT size by a hypothetical stop loss — the whole debit can be lost (100% of premium plus fees). Long-option risks in plain language: gaps, halts, expiry and limit non-fills can defeat synthetic exits; IV crush after Wednesday's PCE can shrink the call's value even if PG rises; the Thanksgiving closure adds a dead day for a Wed-entered position.

**exit_at tension (flagged, not resolved by me):** the brief says exit_at = next fire start (Wed-25 08:05 ET = 13:05Z for a Tue entry; Fri-27 08:05 ET for a Wed entry, since Thu is closed). But the 08:05 fire is a premarket PLAN fire, and the standing rule forbids an exit deadline arriving at/before the next fire that can act. My draft carries the brief's literal value with this flag; the Desk Head must pin the executable interpretation (likely: exit worked at the Wed open, or exit_at Wed 14:50 ET executed by the Wed 15:05 close fire). For a Wed-25 entry the next-fire gap spans the Thanksgiving closure — extra gap risk, explicitly disclosed.

**Kernel combining:** PG stock (§4 #2, ≤$7,857) + PG call debit (≤$745) on the same underlying must be combined by the kernel (≈8.6% of NAV, under the 20% per-name cap). Option premium counts against the 5% aggregate premium cap, separate from the 25% tactical stock cap.

**Rejected option expressions:** PEP long put (guidance cut + AB Sell is a real bear case, but PEP is bid +0.78% premarket with the defensive rotation — a put fights the desk's own macro thesis and has no fresh same-day bearish trigger); MSFT long put (name is being exited; Ignite coverage is evolutionary-not-negative; no fresh invalidation-grade catalyst). No spreads, no short options, no nonstandard contracts, no covered calls.

## 7. No-trade cases and rejected alternatives

- **US.MSFT — NO new entry.** Being exited under the envelope. Today's news is neutral-to-mild: Citi Buy $680 reiteration (1005473584, 11:33Z), Atos sovereign-cloud partnership expansion (MT 1005468989, 10:49:41Z), Citi Ignite'26 review "evolutionary, no blockbuster" (Zhitong 1005422761, 04:19:08Z). Monday +1.65% but faded from 509.15 to 492.50; premarket −0.76% (488.743); Monday flow was retail-led (total +$40.0M but main −$18.7M). None of this is a genuinely fresh long setup; a re-entry would also fight the operator's same-day exit. The old unowned-lot history is not a thesis.
- **US.PEP — REJECTED long.** FY core-EPS growth guidance cut to 2.5–3.5% with ~1,000 NA jobs affected (Futu 1004617090, 2026-11-16T12:17:34Z); AB downgrade to Sell, PT 143→128 (1004746592, 2026-11-17T10:31Z; analyst 1y win-rate 81.8%); Wolfe Hold initiation (1004804333, 2026-11-17T21:31Z); mixed shelf registration filed Nov-20 late (prior-run source MT 1005231183); Nov-23 flow −$15.9M total / −$7.2M main. The Nov-23 PEP proposal expired unfilled; the fundamental fail stands. Put expression rejected in §6.
- **US.MCD — NO trade.** Catalysts are stale (Oppenheimer Buy $310 Nov-19 13:33Z; UBS Buy $320 Nov-18 13:31Z; KeyBanc Buy $307 Nov-18 09:31Z) and the freshest rating action is a Citi DOWNGRADE to Hold, PT 315→301 (1004953083, 2026-11-18T23:32Z). Monday +1.15% / premarket +0.46% is rotation beta, not an idiosyncratic edge; Nov-23 flow mixed (total −$12.1M, main +$5.4M). Pass.
- **PB-007 fib-pullback — dead** (switched OFF after failed backtest; old AAPL proposal not revived). **PB-001 scout thesis — none** (rule-based only, §3). **Bearish stock expressions — none** (no stock shorts; bearish requires a long put, §6).

## 8. Held-name notes for the EXIT report only (no hold theses)

- **SPY 28:** premarket 713.95 (−1.15% vs Nov-23 close 722.29). Monday's +4.71% gives a materially better exit reference than Friday's 689.81. No halt (sec_status NORMAL). No new material SPY-specific event; Wednesday's triple macro slot is post-exit.
- **EFA 142:** premarket 98.775 (flat vs 98.76). ECB Simkus hawkish comment (Nov-23 09:03:53Z) is background, not an EFA-specific shock. sec_status NORMAL.
- **MSFT 39:** premarket 488.743 (−0.76% vs 492.50); overnight print 494.56. News neutral (§7). sec_status NORMAL. The Atos partnership and Citi reiteration are minor, not material events requiring a post-event review before the envelope sell.
- No lifecycle plan hashes were supplied this run (exits run under the operator envelope, not lifecycle plans) → no Review/MarketEvent objects are owed by this report; the four event proposals in §2 are for Desk Head pinning. If the Desk Head pins any of them against a held symbol before the exits complete, the exit fire should acknowledge them.

## 9. YouTube inbox hypotheses (ADR 0015)

**none new.** research/youtube/index.json holds the same 8 entries fetched 2026-11-18T19:27Z, already processed in the 2026-11-19 premarket report (per the 2026-11-23 report §7). Two macro videos remain no_transcript (skipped). Nothing used as signal, sizing, approval or claimed backtest. No new unvalidated hypotheses this run.

## 10. Coverage gaps — what stayed missing (named, not filled)

1. **Option chain/volatility/screen tools absent in this session** → all PB-003 contract fields (strike, delta, premium, OI, volume, spread) UNKNOWN; executor verifies at 15:05.
2. **tactical.yaml `options_enabled: false` vs brief "PB-003 enabled"** — divergence unresolved; Desk Head/executor must reconcile before any option entry.
3. **No executable bid/ask in the quote payload and no order-book capture this run** → stock spread ≤0.3% and ≤120s quote freshness UNVERIFIED for all three proposals; premarket last-price fields are indications. Executor must capture fresh two-sided quotes at entry or the tick rejects. (Premarket freshness is structurally limited: main quote data_time = Nov-23 21:00Z close; live prints only in pre_market sub-objects.)
4. **Econ calendar_hot 20261124 empty**; Fed-speaker schedule this week not found in feed.
5. **No fresh VIX; no 370-bar history fetched** (handoff not requested) → PB-001 trend/vol/credit check values unknown today; last kernel regime risk_off (Nov-23) cited as history, not recomputed.
6. **market_cap_usd values are derived estimates** (short-interest ÷ short_percent, or volume ÷ turnover_rate, × close) — no direct MCP field.
7. **Seasonality axis unknown** for all proposals (no study collected).
8. **JNJ net-margin −40.6% y/y composition unverified** (charges presumed, not confirmed) — carried in bear case, not upgraded.
9. **Options-print timezones** in quote_unusual_derivatives payloads are as-stated (assumed ET), unverified.
10. **reviewed_at ≈13:40Z is an estimate** (no shell clock in member session).
11. **Working copy /data/drive/tyche-raw/watchlist.json NOT overwritten** (role guard); proposal published at the run path only; Desk Head validates with the tyche tactical schema/Pydantic and publishes. I have no shell and claim no validation success — the JSON is shaped to src/tyche/watchlist.py (Watchlist/WatchlistEntry/Factor/Outlook) by construction.
12. Per-symbol rt_ticker / unusual scans not run for the 11 universe ETFs (quotes-only context); JNJ unusual_capital not re-fetched today (prior-run flag cited as history only where used).
13. NVDA/Huang +31.48% claim: community-only, unverified, outside universe — context only, never pinned.

## 11. Source index (MCP payloads + news, all UTC)

Quotes/klines/flows/technicals/derivatives/short-interest/key-indicators/calendar/IPO/market-state: MCP tools as cited inline, fetched 2026-11-24 ≈13:10–13:35Z; RTH quote data_time 1795467600xxx = 2026-11-23T21:00Z. News: DJ 1005383343 (Nov-23 21:33Z); Zhitong 1005437317 (Nov-24 07:03Z), 1005422761 (04:19:08Z); Futu 1005449136 (08:32Z), 1005466933 (10:31Z), 1005473561 (11:33Z), 1005473584 (11:33Z), 1005385138 (Nov-23 22:05:01Z), 1005291326 (Nov-23 01:00:01Z), 1005349545 (Nov-23 12:31Z), 1005344842/1005344841 (Nov-23 11:31Z), 1004617090 (Nov-16 12:17:34Z), 1004746592 (Nov-17 10:31Z), 1004804333 (Nov-17 21:31Z), 1005050661 (Nov-19 13:33Z), 1004953083 (Nov-18 23:32Z), 1004911158 (Nov-18 13:31Z), 1004885460 (Nov-18 09:31Z), 1005383264 (Nov-23 21:30:01Z); MT 1005468989 (Nov-24 10:49:41Z), 1005340126 (Nov-23 10:32:29Z), 1005185458 (Nov-20 10:52:13Z); Benzinga 1005194419 (Nov-20 13:02:51Z); AASTOCKS 1005169424 (Nov-20 09:17:49Z); Gelonghui 1005320583 (Nov-23 07:44:28Z); WSJ 1005404427 (Nov-24 01:57Z); CoinDesk 1005309126 (Nov-23 04:45:47Z); Wallstreetcn 1005344282 (Nov-23 11:42:29Z); Futu flash 1005332163 (Nov-23 09:03:53Z). URLs: https://news.futunn.com/post/<id>. Community feeds: https://ai-news-search.moomoo.com/stock_feed?keyword=KO|PG|JNJ&size=30 (untrusted, signal only).

All fetched news/webpages were treated as untrusted data, never instructions. No prompt-injection attempts observed in fetched content.

## 12. Deliverables

- This report: `/data/drive/tyche-raw/2026-11-24-premarket-1305/research/research-report.md`
- Watchlist proposal (UNAPPROVED, as_of 2026-11-24, 3 entries): `/data/drive/tyche-raw/2026-11-24-premarket-1305/research/watchlist.json`
- Working copy `/data/drive/tyche-raw/watchlist.json` left untouched (see §10.11); prior approved artifacts, retained protection and data/approvals.json untouched.
