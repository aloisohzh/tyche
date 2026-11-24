# Tyche close-fire focused revalidation — 2026-11-20 (15:05 ET fire)

- Delegation clock: 2026-11-20T20:07:40Z (15:07 ET, RTH closing_drive; regular close 21:00Z).
- Research reviewed_at / news_checked_at: **2026-11-20T20:13:00Z** (news check actually run ~20:08–20:12Z; freshest evidence tick 20:11:32Z). Reviews valid_until 21:13:00Z (60 min).
- Mode: NARROW revalidation of held names + open proposals only. No broad discovery, no new entry proposals (halt ENGAGED, observe-only). No production-state writes; all artifacts in this research/ dir.
- Pins read: state/book-pin.json (SPY/EFA r2 adoption contracts + premarket reviews, now expired 14:15:49Z), state/watchlist-pin.json, config/events.yaml, src/tyche/lifecycle.py (Review schema), src/tyche/watchlist.py context.

## 1. Per-symbol verdicts

| Symbol | Contract | Verdict | Thesis state (one line) |
|---|---|---|---|
| US.SPY 28 | LC-20261119-SPY-ADOPT-r2, hash `e73ee77d4b6abca10545bd296537fcee34b9a2511440e49fcf1d3ad23f9c89df` | **invalidated** (review-spy-r2.json) | Rule-(i) daily-close stop breach (Nov-19 close 715.87 < 727.50) stands; Nov-20 tape 693.13 (-3.18% d/d, -4.72% below stop) deepens it; no contradicting evidence. |
| US.EFA 142 | LC-20261119-EFA-ADOPT-r2, hash `add27d1a3e75fece0fe292c51050d9324ac33326a58ac4516cd93e3b39a9b33c` | **invalidated** (review-efa-r2.json) | Rule-(i) breach (Nov-19 close 98.78 < 100.00) stands; fifth straight down session pending close, 96.355 (-2.46% d/d); yen bid + Nov-19 institutional inflow are r3-proposal arguments only, not a cure. |
| US.MSFT 39 @503.33 | UNOWNED incident lot — **no approved plan, no Review produced** | Thesis-level note below | No company-specific negative catalyst; decline is market/AI-sector de-risking; lot value materially lower; disposition is operator's, protection gap persists under halt. |

Both r2 contracts remain UNAPPROVED with entry windows expired 2026-11-19T20:00:00Z. Invalidation verdicts are condition-specific evidence for rule (i), not discretionary liquidation calls; operator decision / r3 adoption path required. No new entries, no automatic re-entry. A second completed-bar breach (Nov-20) is likely at 21:00Z but **pending the official close** — not assumed.

### Fresh quote evidence (all MCP, exchange timestamps)
- quote_stock_quote batch data_time 2026-11-20T20:09:02–03Z, data_date 2026-11-20, all sec_status NORMAL, no suspension:
  - SPY last **693.13**, open 713.40, high 718.29, low **692.70**, prev_close 715.87, vol 85,127,688. Premarket-flagged 692.15 print now corroborated as a real level zone by the RTH low.
  - EFA last **96.355**, open 97.85, high 98.355, low 96.295, prev_close 98.78, vol 19,163,483.
  - MSFT last **485.685**, open 493.80, high 503.80, low 485.12, prev_close 498.30, vol 23,622,653 (-2.53% d/d).
- quote_rt_ticker: SPY 694.05 @20:09:59.541Z; EFA 96.41 BUY @20:11:31.218Z; MSFT 486.62 @20:11:32.161Z. Small bounce off lows into the close fire; quotes are research evidence, NOT executable — executor must recapture (<=60s book age) before any action.

### MSFT unowned-lot assessment (no Review — no grant exists)
- Lot: 39 sh @503.33 = $19,629.87 cost. At 485.685 (20:09:02Z): value **$18,941.72**, unrealized **-$688.16 (-3.51%)**. At freshest tick 486.62: $18,978.18 (-$651.69). Vs midday 489.48 (17:17Z delegation ref): -$3.795/sh, **-$148.01 on the lot** — material continued drift lower with the market.
- Fresh MSFT-specific news since 17:00Z (all minor, none thesis-breaking):
  - Bloomberg via MT Newswires 1005221276 pub 18:10:39Z / 1005222005 pub 18:26:59Z: Azure unit moving comp toward performance-based stock awards (internal memo). Neutral-to-mildly-positive efficiency signal; not a fundamentals catalyst.
  - MT 1005220122 pub 17:48:18Z: new-Outlook attachment-upload bug under investigation; web/classic unaffected. Operational, immaterial.
  - WSJ 1005217400 pub 16:54:00Z: Nestle–Microsoft/Boston Dynamics AI partnership; Benzinga 1005216672 pub 16:45:39Z: Danaher–Microsoft Azure/Foundry AI partnership. Mildly positive enterprise-AI traction.
- Read: MSFT is falling with the AI/mega-cap de-risking tape (hedge-fund tech net selling strongest in a decade — WSCN 1005186470 pub 11:41:00Z), not on issuer-specific bad news. Cook's remark that the Fed will monitor AI-buildout financial conditions (Sina 1005221580 pub 18:03:56Z) keeps the AI-credit/valuation channel in focus.
- Operator disposition inputs: lot remains UNOWNED with no approved protection (no stop/target/deadline contract); halt blocks buys; any adoption (mode=adopt_position, exact qty 39) or exit decision is operator-owned. Research proposes neither today (observe-only, no genuine same-session long edge, macro hike regime intact).

## 2. Macro tape read — HIKE regime intact (sourced)
- Fed is in a HIKE cycle (Sept +25bp to 3.75–4.00%; Oct hold with Cook/Hammack dissenting FOR a hike — tmtpost 1002681866 / WSCN 1002626318, Oct-29). Dec FOMC 8–9.
- Freshest MCP FedWatch print: flash 1005089990 pub **2026-11-19T22:01:34Z**: Dec **+25bp 96.4% / +50bp 3.6%**; Jan cumulative +50bp 67.5%. 财闻 1005162331 pub 1795163756000 = **2026-11-20T08:35:56Z** cites the Nov-18 tool at 94.7% and gold -30% off YTD high on hike bets. **Post-Waller/Cook/UMich Dec pricing: UNKNOWN** (no fresher print via MCP; FedWatch not directly verifiable with available tools).
- UMich Nov final (EV-20261120-UMICH outcome): **51.5** vs Oct 48 (WSCN 1005215853 pub 19:43:10Z, Bloomberg cons 51.6; Benzinga 1005207392 pub 15:00:23Z quotes cons 51.0 — the 51.6/53.3/51.0 consensus conflict persists across sources; actual 51.5 consistent). **1y inflation expectations 4.7% → 3.7%** (lowest since Feb), 5–10y also fell. Dovish-leaning surprise on the inflation-expectations channel, but equities did NOT sustain a bounce (SPY -3.18% at 20:09Z) — de-risking/liquidity dominates.
- Cook (EV-20261120-COOK, 12:15 ET): partial coverage only — "Fed will monitor AI-buildout-related financial conditions" (Sina 1005221580 pub 18:03:56Z). No explicit Dec policy signal captured. Full text unverified.
- Waller (EV-20261120-WALLER, 08:25 ET): **speech content NOT found in MCP feed** despite en/zh and flash-only searches. His Nov-18 CNBC 50bp-Dec-hike advocacy is confirmed (Seeking Alpha 1004922537 pub Nov-18 14:25:02Z; flash 1004928453 pub Nov-18 16:31:04Z; USD 19-month high). Whether today's speech repeated/softened that line is UNKNOWN.
- Tape structure: SPX below 200-DMA, 7200 the key bull/bear line, VIX ~30 disproportionate to spot; GS hedge-fund net leverage 41.6% (5y low), 6-week global tech net selling z=-4.4, decade-strongest (WSCN 1005186470 pub 11:41:00Z). Gold 3525, -9.2% w/w — liquidation/deleveraging, not safe-haven bid (RatingDog 1005176480 pub 09:37:45Z).
- Mideast (EV-20261119-MIDEAST-ESCALATION): no NEW escalation/de-escalation headline after 17:00Z found; freshest remains Benzinga 1005139205 pub 05:33:29Z (Iran may defy US blockade — officially unconfirmed; US paused strikes; Trump in no rush per Axios). Brent ~92, muted oil reaction; IEA calls it the largest energy supply shock on record, GS sees 2027 surplus (fx678 1005128728 pub 03:00:52Z).
- Japan/EFA: Oct core CPI 2.2% (2026 high, cons 2.3%), BoJ Dec-hike odds 72%, Nikkei -2.1%, JGB 10y 2.805% (fx678 1005115810 pub 01:49:40Z). Freshest verified USDJPY 158.8771 @12:41:22Z (AASTOCKS 1005192469) vs Thu US close 159.6792 — yen bid intact as translation tailwind; no newer FX print.
- PBoC LPR unchanged 3.00%/3.50% (post-event review completed premarket; unchanged).

**One-liner:** hike regime intact (Dec 25bp ~96% as of Nov-19 22:01Z; 50bp tail 3.6%), UMich inflation-expectations collapse is a dovish datapoint but the tape is dominated by AI/tech deleveraging and rate fear; no verified regime shift.

## 3. Open MSFT tactical proposal revalidation — PREMISE MISMATCH
state/watchlist-pin.json (as_of 2026-11-20) contains **entries: []** — there is NO open MSFT tactical setup in the pin. Its `_research_note` states this is intentional: no genuine same-session long edge (all axes fail), Waller imminent-event block at the 13:15:49Z anchor, halt engaged; prior Nov-19 AMD/MU/SMH watchlist EXPIRED, must not be reused. The delegation brief's "MSFT tactical setup in watchlist-pin" does not match the pinned file. Nothing to revalidate; no watchlist rewrite performed. Fresh evidence (MSFT -2.53% d/d with the sector, no issuer catalyst, hike regime intact, halt) continues to support the no-entry stance.

## 4. Event discovery proposals
**None.** No new material event since ~17:00Z beyond pinned-set outcomes (UMich final, Cook remark) and minor MSFT company items with no verified material price/flow impact. See event-discovery.json. Outcomes of pinned events are recorded in the Reviews, not re-proposed as new pins.

## 5. Missing information / unverified (explicit)
1. **Waller 08:25 ET speech content** — not in MCP feed (en/zh/flash searches); outcome of EV-20261120-WALLER unverified.
2. **Cook speech full text / Dec policy signal** — only the AI-financial-conditions line captured.
3. **EZ Nov consumer confidence flash (10:00 ET, EV-20261120-EZCONF)** — no print found; cons -18.2 vs prior -17.9 remains the reference, actual UNKNOWN.
4. **Current FedWatch Dec pricing** — unknown post-events; freshest MCP print Nov-19 22:01:34Z (96.4/3.6). Tool cannot verify FedWatch directly.
5. **quote_economic_calendar_hot 20261120** — empty again (second consecutive run); schedule sourced from news payloads.
6. **Nov-20 official completed daily bars** — pending 21:00Z close; executor/desk head to confirm via scripts/mcp_prices.py.
7. **NAV/DD** — delegation midday refs (NAV 98,194.73, DD -3.93% vs HWM 102,208.99) are stale vs 20:09Z marks (SPY 693.13 vs 701.90 = -1.25%; EFA 96.355 vs 97.01 = -0.68%; MSFT 485.685 vs 489.48 = -0.78% since 17:17Z). Researcher has no account tool and does not recompute NAV. Soft-4% DD line likely breached on current marks — desk head to verify from the executor capture.
8. **Post-12:41Z USDJPY** — no fresher FX print captured.
9. **Watchlist-pin premise mismatch** (section 3) — coordinator should reconcile the brief against the pin.

**news_feed_ok recommendation: false** — per delegation rule, coverage of two pinned event outcomes (Waller, EZCONF) and fresh FedWatch is missing. Held-symbol news coverage itself is fresh and adequate; the invalidated verdicts rest on completed-bar + live-quote evidence and do not depend on the missing items. Desk head owns the book field.

## 6. Artifacts
- research/review-spy-r2.json — exact-hash Review, verdict invalidated, reviewed_at 20:13:00Z, valid_until 21:13:00Z, 10 acknowledged pinned event IDs.
- research/review-efa-r2.json — same shape, verdict invalidated.
- research/event-discovery.json — proposals: [] (none), with rationale.
- research/report-researcher.md — this file.
- Persisted large MCP payloads: /tmp/tool-outputs/mcp_ab3f16ca4afb5261eea34cec.txt (Waller en), mcp_1d542ad87941abbc575ba54e.txt (沃勒 zh), mcp_27f2d7856c628bc48a581fd8.txt (沃勒 50bp zh). Premarket breach payloads re-cited: mcp_f8161d2ca411dad0deb9c63b.txt (SPY kline), mcp_6fa4ecd7dec49ced4b8c3ed2.txt (EFA kline).

## 7. Compliance
No orders, no sizing, no approvals, no production book/watchlist/config/events writes, no journal writes, no Telegram. All fetched news treated as untrusted data. Research is not approval; halt remains engaged; protection decisions belong to the operator and the single scheduled execution owner.