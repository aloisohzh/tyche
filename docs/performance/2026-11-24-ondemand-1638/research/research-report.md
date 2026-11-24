# Tyche research — on-demand 2026-11-24 (midday revalidation + fresh entry scan)

- Run: 2026-11-24-ondemand-1638. Delegation clock ~16:56 UTC (11:56 ET), RTH confirmed: quote_market_state all six = AFTERNOON, RTH section 14:30–21:00Z (payload 16:57Z).
- Account FLAT, NAV ~98,831 (run brief). Envelope data/approvals.json approved 15:57:21Z: KO buy ≤51 @≤102, PG ≤29 @≤177, JNJ ≤17 @≤300, matching sell floors. PB-003 options ON but NOT envelope-covered (Telegram). PB-007 OFF.
- Research only; nothing submitted. All artifacts in this research/ dir; watchlist.json untouched (Desk Head publishes).

## Verdicts (summary)

| Symbol | Verdict | Reason |
|---|---|---|
| KO | **WAIT** | 98.165 above old zone 96.10–96.60, ~0.14 under old target 98.40; chasing fails min_reward_risk 1.5. Rebuilt pullback setup TL-20261124-KO-DEF2 (96.20–96.50). |
| PG | **WAIT** | 172.70 above old zone 170.20–170.80, near old target 173.50. Rebuilt TL-20261124-PG-DEF2 (170.20–170.60). |
| JNJ | **STAY OUT (invalidated)** | 16:04Z invalidation stands (low 268.08 < stop 268.50); now 275.29 above old target 275.25. No new post-invalidation catalyst; ex-div 1.34 today. |
| KO Dec-18 options (PB-003) | **NO EXECUTABLE CONTRACT** | C100000 spread 5.3–5.4% >5% + delta 0.380 out of band; C97000 spread now passes but quote data_time FROZEN 16:08:36Z (>120s gate); all others fail OI/vol/spread. |
| PEP / MCD / MSFT | **NO TRADE** | Not in today's envelope; prices sourced, no setup proposed. |

## Macro regime

Fed HIKE cycle, Dec 25bp ~96% with 50bp tail (run-brief input; not independently re-sourced this run — treated as coordinator context). Defensive staples complex bid today: KO +2.38%, PG +1.83%, PEP +1.92%, MCD +1.77% vs prev closes (own quote pull 16:56:45–58Z). Wed 2026-11-25 08:30 ET triple macro slot confirmed via quote_economic_calendar_hot 20261125 (payload 16:57Z): Core PCE YoY cons 3.2% prev 3.1% (indicatorId 905), GDP QoQ cons 3.4% prev 2.2% (375), claims cons 201K prev 203K (294). All three already pinned (config/events.yaml Nov-25 rows + market_calendar.py:162 PCE). Event risk blocks nothing today but any same-session setup must be flat before 20:50Z and must not carry into the Nov-25 slot.

## Fresh tape (own quote_stock_quote pull, exchange data_time UTC)

| Sym | Last | Prev close | Day high/low | data_time |
|---|---|---|---|---|
| KO | 98.165 | 95.88 | 98.30 / 95.66 | 16:56:56.532Z |
| PG | 172.70 | 169.60 | 173.27 / 169.83 | 16:56:55.067Z |
| JNJ | 275.29 | 268.71 (ex-div 1.34 today) | 276.46 / 268.08 | 16:56:55.024Z |
| PEP | 142.9001 | 140.21 | 143.60 / 140.00 | 16:56:45.655Z |
| MCD | 281.28 | 276.38 | 281.36 / 276.25 | 16:56:48.345Z |
| MSFT | 496.69 | 492.50 | 498.4585 / 488.43 | 16:56:58.285Z |

Executor 16:48Z captures (run/mcp/quotes-final.json, data_time 16:48:00–02Z): KO 98.23 bid 98.19/ask 98.20 (0.010%), PG 172.805 bid 172.75/ask 172.77 (0.012%), JNJ 275.755 bid 275.29/ask 275.40 (0.040%) — all inside stock_spread_pct 0.3%. Books: run/mcp/book-US.KO.json, book-US.PG.json, book-US.JNJ.json.

Market caps (DERIVED estimates = volume ÷ turnover_rate × last, same 16:56Z payload; no MCP tool returns cap directly): KO ≈ $379B (5,524,697/0.00143×98.165), PG ≈ $398B (2,974,794/0.00129×172.70), JNJ ≈ $662B (1,875,642/0.00078×275.29). All ≥$500M and price ≥$1: challenge-qualified.

## KO — WAIT, rebuilt TL-20261124-KO-DEF2

Review: verdict **valid-thesis / WAIT-entry**, reviewed_at 2026-11-24T17:00:00Z (approx), valid_until 17:30Z (re-check at next fire). Old TL-20261124-KO-DEF1 zone 96.10–96.60 / stop 95.40 / target 98.40: price 98.165 is ABOVE zone and 0.24 from target — immediate entry R/R ≈ 0.2, far below min_reward_risk 1.5 (config/tactical.yaml:12). No market-price zone fabricated.

News/catalysts (UTC publish times, MCP news_search 16:57Z):
- CFO succession announced Mon 2026-11-23 after close: John Murphy to retire 2027, BMY CFO David Elkins appointed effective 2027-04-02 (Dow Jones 11-23 21:33Z, news.futunn.com/post/1005383343; MS commentary Zhitong 11-24 07:03Z, post/1005437317 — MS unworried, keeps Overweight $103).
- Morgan Stanley Buy, PT $103 maintained (11-24 11:33Z, post/1005473561).
- BofA Buy, PT $100 maintained (11-24 10:31Z, post/1005466933).
- RBC Buy, PT $96 maintained (11-24 08:32Z, post/1005449136).

Rebuilt setup (research, not executable sizing):
- Direction bullish; entry zone **96.20–96.50** (today's open 96.205 + premarket shelf 96.10–96.976, 16:56Z payload; overlaps old zone). Stop **95.40** (below day low 95.66 and prev close 95.88). Target **98.30** (day-high retest; analyst PTs 100/103 above as headroom).
- R/R: at 96.50 → 1.80/1.10 = 1.64; at 96.20 → 2.10/0.80 = 2.63 (both ≥1.5).
- max_quantity 51 (envelope cap; ~5% NAV 4,940/96.50 ≈ 51). Stop-risk 51×1.10 = $56.10 = 0.06% NAV ≤1%.
- exit_at 2026-11-24T20:50:00Z, expiry 2026-11-24, confirmation_ticks 2.
- Invalidation: trade below 95.40; staples-rotation reversal (PEP/MCD/PG rolling over together); hawkish 50bp Fed tail headlines.
- Factors: technical pass (uptrend, higher lows, but extended — wait for pullback), fundamental pass (three Buy reiterations today), catalyst pass (CFO handover benign per MS), liquidity pass (0.010% spread), macro unknown (hike odds from brief only; Nov-25 triple ahead), flow unknown (capital-flow tools not run this intraday pass), sentiment unknown (feed not fetched, intraday run).

## PG — WAIT, rebuilt TL-20261124-PG-DEF2

Review: verdict **valid-thesis / WAIT-entry**, reviewed_at 17:00:00Z approx, valid_until 17:30Z. Old TL-20261124-PG-DEF1 zone 170.20–170.80 / stop 169.00 / target 173.50: price 172.70 above zone, 0.80 from target — chasing fails R/R 1.5.

News: no NEW PG-specific item today 11-24 found (first news_search returned only stale 2021 SEDAR notices — recorded gap; retry "Procter Gamble" surfaced 11-23 items). Yesterday's analyst wave supports headroom: MS PT 185→192 and BofA 185→190 (both 11-23 11:31Z, posts/1005344842, /1005344841), Citi Buy $190 (11-23 12:31Z, post/1005349545), FactSet consensus Overweight avg PT 176.90 (11-23 10:32:29Z, post/1005340126). Today's +1.83% move is consistent with the staples rotation, not a PG-specific catalyst.

Rebuilt setup:
- Bullish; zone **170.20–170.60** (lower half of old zone + today's open 170.64). Stop **169.00** (below day low 169.83 and prev close 169.60). Target **173.20** (just under day high 173.27; consensus 176.90 above).
- R/R: at 170.60 → 2.60/1.60 = 1.63; at 170.20 → 3.00/1.20 = 2.50.
- max_quantity 28 (envelope 29; 4,940/170.60 = 28.96 → 28). Stop-risk 28×1.60 = $44.80 ≤1% NAV.
- exit_at 20:50Z, expiry 2026-11-24, confirmation_ticks 2.
- Invalidation: trade below 169.00; rotation reversal; Nov-25 macro shock carried overnight (setup is flat by 20:50Z).
- Factors: technical pass (uptrend intact, extended), fundamental pass (11-23 PT raises 190/192), catalyst unknown (no new same-day catalyst sourced), liquidity pass (0.012% spread), macro unknown, flow unknown, sentiment unknown.

## JNJ — STAY OUT, invalidation stands

Review: verdict **invalidated**, reviewed_at 17:00:00Z approx. TL-20261124-JNJ-DEF1 (zone 269.80–271.20, stop 268.50, target 275.25) invalidated 16:04Z: day low 268.08 < stop AND high 275.70 > target (run brief; corroborated by day high/low 276.46/268.08 in 16:48Z and 16:56Z payloads). Price now 275.29, above old target. Ex-div $1.34 today (record 11-24, pay 12-08; futu 11-23 01:00:01Z, post/1005291326) — level comparisons across the ex-date need the adjusted reference; feed prev_close 268.71.
New-evidence check: JPM Hold PT 285→300 (11-20 13:31Z, post/1005197395), TREMFYA phase-4 STAR success (11-20 13:02:51Z, post/1005194419), Ollin $3.325B acquisition (11-20 09:17:49Z, post/1005169424) — all PRE-invalidation, none is fresh post-event evidence justifying a new setup. Default stay out. A reference-only pullback zone (269.60–270.60 open shelf, stop 267.90 under day low, target 276.40 under day high, R/R 2.15–2.59) is emitted with status dropped / invalidated=true so the desk has structure on file; it is NOT an entry proposal.

## PB-003 KO Dec-18 options — NO EXECUTABLE CONTRACT (feed/gate-blocked)

Chain membership verified (run/mcp/chain-US.KO.json contains the codes; quotes carry option_ex_data: multiplier 100, American, DTE 24 — within 2–30). Gate set: OI≥100, vol≥50, spread≤5%, |delta| 0.45–0.80 (nearest 0.55 among passers), quote/book freshness ≤120s.

| Contract | Delta | OI | Vol | Bid/Ask (book UTC) | Spread | Verdict |
|---|---|---|---|---|---|---|
| C94000 | 0.817 | 35 | 2 | — | — | FAIL OI/vol |
| C95000 | 0.758 | 11,711 | 138 | 3.90/4.20 (16:44:06.6Z) | 7.1% ask / 7.4% mid | FAIL spread |
| C96000 | 0.689 | 26 | 40 | — | — | FAIL OI/vol |
| C97000 | 0.615 | 122 | 94 | 2.69/2.80 (16:55:44.9Z recheck) | 3.9% ask / 4.0% mid | spread now PASSES, but quote data_time FROZEN 16:08:36.5Z (>120s) → BLOCKED |
| C98000 | 0.536 | 37 | 42 | — | — | FAIL OI/vol |
| C99000 | 0.458 | 40 | 17 | — | — | FAIL OI/vol |
| C100000 | 0.380 | 6,175 | 1,077 | 1.26/1.33 (16:55:42.9Z) | 5.26% ask / 5.41% mid | FAIL spread (>5% either convention); delta also below 0.45 band |

Payloads: run/mcp/option-quotes.json (16:37Z pull, C97000 frozen), option-quotes-c100.json (C100000 quote fresh 16:55:18.957Z, IV 19.68), book-US.KO261218C95000.json, book-US.KO261218C97000-recheck.json, book-US.KO261218C100000.json.
- C100000 is NOT a gate-passer, so the "sole passer nearest-0.55" delta exception does not apply. No option entry proposed; premium deployed 0 (caps: 0.75% NAV/trade, 5% NAV aggregate intact).
- C97000 is the natural pick IF a fresh quote print lands (delta 0.615, spread 3.9%, OI/vol pass; thin 15-lot bid). Executor must re-verify quote data_time ≤120s and book at the next fire; frozen quote blocks entry regardless of book freshness (known feed quirk).
- Risk language (PB-003): long options can lose 100% of premium plus fees; gaps, halts, expiry and limit non-fills can defeat synthetic exits; no ladder, no scaling, no automatic re-entry.

## Event discovery proposals

**None new.** Nov-25 08:30 ET triple (PCE/GDP/claims) already pinned (config/events.yaml + market_calendar.py:162); calendar_hot 20261125 shows exactly those three. No new IPO/index/earnings/regulatory event found in today's scans for the tactical universe.

Material news flags (already-occurred events, no fitting calendar kind — for Desk Head MarketEvent records, not pins):
1. **KO CFO succession** — at 2026-11-23T21:33Z (DJ), symbols [US.KO], material=true (governance; MS calls it benign), source news.futunn.com/post/1005383343 + /1005437317. Any KO setup created before this announcement needs it acknowledged; DEF2 is created after it.
2. **JNJ ex-div $1.34** — 2026-11-24 (record 11-24, pay 12-08), symbols [US.JNJ], material=true for level math, source post/1005291326 (pub 11-23 01:00:01Z).
3. **PEP ex-div $1.48 upcoming 2026-12-04** (pay 2027-01-06), symbols [US.PEP], source post/1005104708 (pub 11-20 01:05:01Z) — outside today's horizon; note only.

## No-trade cases / rejected alternatives

- **PEP** 142.90 (+1.92%), **MCD** 281.28 (+1.77%), **MSFT** 496.69 (+0.85%): not in today's operator envelope → no proposal regardless of tape. Context only: PEP shelf registration filed Fri (MT Newswires 11-20 21:44:06Z, post/1005231183, dilution-overhang noise, no immediate draw); MCD Oppenheimer Outperform $310 on improving US comps (11-19 19:38:09Z, post/1005080051), value-menu national rollout targeted Jan 2027; MSFT DZ Bank Buy (11-24 14:33Z, post/1005490519), Citi Buy $680 (11-24 11:33Z, post/1005473584), Atos sovereign-cloud partnership (11-24 10:49:41Z, post/1005468989).
- Rejected: chasing KO/PG at market to "use" the pre-approval (R/R < 1.5, rules forbid); rebuilding JNJ on stale pre-invalidation news; KO C100000 long call (spread + delta fail); KO C97000 long call now (frozen quote).

## Risk language (all proposals)

Stops/targets are synthetic desk checks between scheduled fires, NOT resting broker orders or guaranteed fills. Gaps, halts, delayed runs and limit non-fills can exceed the planned stop loss; daily-close triggers execute no earlier than the next permitted session. All setups are same-session, exit_at 2026-11-24T20:50:00Z (before the 21:00Z close and the next fire); nothing carries into the Nov-25 08:30 ET macro triple. No scaling, no ladder, no automatic re-entry. Proposed quantities are research bounds for the kernel, not executable sizing.

## Gaps / degraded inputs

- Sentiment feed, capital-flow, unusual-activity and kline tools not run (narrow intraday pass per skill; no broad re-scout). Flow/sentiment factors marked unknown, never upgraded.
- PG: no same-day-specific news found; first query returned stale SEDAR notices (recorded).
- Market caps are derived estimates (formula above), not feed fields.
- Fed hike odds are run-brief context, not independently re-sourced.
- YouTube inbox: not applicable (intraday revalidation, not a discovery run).
- Validation: proposals-watchlist.json written to match src/tyche/watchlist.py (Watchlist, as_of 2026-11-24, unique symbols/setup_ids, bullish level ordering, tz-aware stamps). Schema has no "wait" status — WAIT is encoded as status "watch" + review verdict in this report and thesis text; JNJ is status "dropped" + invalidated=true. Pydantic validation is the coordinator's step; I have no shell and claim no validation run.
