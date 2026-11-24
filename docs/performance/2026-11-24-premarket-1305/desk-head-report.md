# TYCHE desk-head run report - 2026-11-24 premarket fire (08:05 ET)

Run: 2026-11-24-premarket-1305. Owner: three-fire desk card (sole scheduled execution owner).
Repo/LC_ROOT: /data/workspace/tyche, HEAD 4372842 (contains tested release 3312287). Halt: released (operator, Nov-23).

## Gate and calendar
- tyche calendar --json exit 0: trading_day true, half_day false, phase pre_market, no events today.
- Calendar drift check (premarket-only): NYSE hours page fetched, flattened to data/nyse-calendar.txt, `tyche calendar-check` exit 0 - **IN SYNC** for 2026/2027/2028 (prior 2028 Juneteenth discrepancy no longer present). No calendar.check journal event owed (sync).

## Lineage
- Restored from newest verified descendant 2026-11-23-close-2005 (59 events, sha 6e839562fea4edb9069b2992e2799ef58b556e35a69949b99bb410095cdcc8aa). No Nov-24 scalp run bundle existed at fire time.
- Final lineage: 74 events, sha 3bfe2ff36cc0c663163f6e6001d6abc3789d0914a80843e51695798e1369a6c0 at journal/events.jsonl.

## Authority and orders
- WITHIN MY BOUNDS: same-day envelope data/approvals.json (approved 2026-11-24T00:42Z), 3 sell lines, max_orders 3. Sell-only: NO buy authority today; entries are unapproved proposals.
- Executor (thread sthr_00wgrdsyfshs043cg216) reconciled first: ownership CLEAN (boundary 3118578 @ Nov-19T18:15:16Z intact; 11 orders, 1 page; 6 tyche-scl rows = PB-004 card, untouched). NAV 98,727.381, cash 45,680.121, frozen 0. Feed healthy.
- OPERATOR EXIT via tyche exit-now, 3/3 submitted, all status2 pending cum 0 (receipts are NOT fills):
  - SELL US.SPY 28 @710.08 (bid 713.65, floor 690) req tyche-exit-732827c19f2debdb73f62f14, receipt 3124584
  - SELL US.EFA 142 @97.88 (bid 98.37, floor 94.50) req tyche-exit-da8d43da202b3f81dcb15de4, receipt 3124585 (one pre-dispatch transport failure; history re-read proved no order, then exactly one submit)
  - SELL US.MSFT 39 @485.26 (bid 487.70, floor 474) req tyche-exit-c82a32a9d62237ea809adeeb, receipt 3124586
- Lifecycle tick (isolated copy, no --record): blocked verbatim "broker snapshot stale or future-dated; fetch again" - expected premarket 120s gate. Production lifecycle state untouched (state a7a9e994..., book bc9e6d50... unchanged).
- PB-007 OFF (operator switch, failed backtest): skipped, no fib-scan. PB-003: no entries at 08:05 (15:05-only). PB-004: read-only.

## Research (thread sthr_00wgrdt067yf4xq3m73u)
- Broad discovery delivered; watchlist validated (tyche watchlist exit 0) and published to /data/drive/tyche-raw/watchlist.json (prior Nov-23 copy backed up in research/). Correction: reviewed_at set to verified file-write time 13:19:30Z (researcher's 13:40Z estimate was future-dated).
- 3 unapproved PB-002 proposals: KO TL-20261124-KO-DEF1 (96.10-96.60/95.40/98.40, max 82, medium), PG TL-20261124-PG-DEF1 (170.20-170.80/169.00/173.50, max 46, medium), JNJ TL-20261124-JNJ-DEF1 (269.80-271.20/268.50/275.25, max 29, LOW, ex-div 1.34 today - executor must re-verify adjusted reference 268.71 at open). All exit 15:50 ET, RR>=1.5, ~23.8% aggregate <=25% cap.
- Regime verified: Fed HIKE cycle, Dec 25bp 95.9%/50bp 4.1% (FedWatch flash Nov-23 22:05Z). Premarket risk-off rotation: QQQ -2.09%, SPY -1.15%, staples/TLT bid.
- PB-003 drafts: one PG or KO Dec-18 long call; contract fields Not verified (chain at 15:05); 1 contract max, premium_limit <=7.45/share (0.75% NAV per-trade, 5% aggregate).

## Events triage
- PINNED (config/events.yaml, commit c914cb4): Nov-25 GDP Q3 second estimate 08:30 ET (independently verified vs https://www.bea.gov/news/schedule + MCP indicatorId 375); Nov-25 Initial Jobless Claims 08:30 ET holiday-shifted (MCP indicatorId 294). Wednesday 08:30 ET is now a verified TRIPLE macro slot (PCE already pinned + GDP + claims).
- NOT PINNED (kind vocabulary gap, macro|fomc|earnings|ipo|index has no corporate-action kind): JNJ ex-div 1.34 today (setup carries the invalidation), KO CFO succession (absorbed, dated in thesis). Kept as report notes.

## NAV refs
- /data/drive/tyche-raw/nav-refs.json written: prior_close_nav 99,380.951 (last healthy Nov-23 close-fire cash read, mcp/cash.json mtime 20:23:54Z, pre-outage; earlier 20:17Z read 99,400.976 superseded), high_water_nav 100,000.00 unchanged (no verified close above baseline; 102,208.99 stays retired). DD -1.27%.

## Prices
- data/prices.csv rebuilt from executor kline handoff: 11 PB-001 universe ETFs x 370 bars (2025-06-05..2026-11-23), 4070 rows; copy in run dir.

## Telegram
- Routine digest sent: message_id 51, ref aaad3722, exit 0. Not urgent (all lots have live resting exit requests; no new breach).

## Problems / next-fire obligations
1. PUBLISH FAILED (last step, run once, no retry): first error `KeyError: 'quantity'` at dashboard/server.py:843 build_orders (via export_dashboard.py --data-only). Bundle copies staged under docs/performance/ (untracked); no commit/push of feed happened. Action: operator fix + run the publish script.
2. Git push of event-pins commit c914cb4 failed (session auth quirk). Bundle: /data/drive/tyche-raw/2026-11-24-sanitized-git/premarket-1305.bundle (origin/main..main). Close fire: fetch+rebase+push.
3. 12:05 ET midday fire OWES: re-check the three resting sells (fill/partial/expiry) FIRST; gap-below-limit means lots stay held; cancel/modify needs separate operator approval. EFA partial-fill risk (thin book).
4. VNQ 3116597 / SMH 3118500 status5 still unresolved.
5. PB-003 config divergence (switch ON vs tactical.yaml options_enabled false) + exit_at/next-fire rule tension: operator must resolve before 15:05 option entries.
6. Nov-18 request_id-less journal rows + MSFT ownership record still owed (exit-now sidesteps, does not fix).
7. JNJ ex-div reference re-verification at open required before any JNJ entry.

## Coverage gaps
- Premarket lifecycle tick structurally blocked (120s gate); coverage reported from isolated capture instead. No RTH fill guarantee on resting limits; synthetic stops between fires are not broker stops. Option chain unverified (no chain pull due at 08:05). Executable spreads/freshness for all proposals unverified until entry-time gates.