# TYCHE ON-DEMAND RUN - 2026-11-24 (private run report)

Run: 2026-11-24-ondemand-1604. Started 16:04 UTC (11:04 ET), calendar phase midday = regular session.
Operator on-demand full trading run per card ON-DEMAND clause (not a scheduled fire; not the 12:05 alert-only fire).
Repo/LC_ROOT: /data/workspace/tyche HEAD e5a71ac (contains tested release 3312287ce282cedacdafab552b40678e386ea90d).
Ledger: journal/events.jsonl in this run dir; parent lineage 2026-11-24-premarket-1305 (81 events f90ca1b3...), shared with PB-004 scalp card. No scalp-lock.json present at start; no concurrent scalp writer observed.

## Gates
- Calendar: trading_day true, half_day false, phase midday, event_caution false, events [].
- Strategy overlay (rotation directive): activity monitor, new_entries false, max_orders 1 - applies to PB-001 rotation lane; on-demand card authorizes tactical entries under envelope/Telegram.
- Halt: released (repo data/halt.json 2026-11-23T15:11:25Z operator release governs; halt-status halted=false).
- Switches: PB-001 on, PB-002 on, PB-003 on (operator override; options_live true - switch wins over tactical.yaml options_enabled per 2026-11-24 ruling, implemented in config.py options_live), PB-004 on (scalp card owns; desk never touches), PB-007 OFF (failed backtest PF 0.66) - skipped entirely.
- Envelope data/approvals.json approved 2026-11-24T15:57:21Z, max_orders 6: KO buy<=51@<=102 / sell>=87; PG buy<=29@<=177 / sell>=151; JNJ buy<=17@<=300 / sell>=257. Symbol-level pre-approval (no setup_hash lines; tactical_cli reserve accepts per e5a71ac). Options explicitly NOT pre-approved.
- NAV refs: prior_close_nav 99,380.951 (Nov-23 close-fire last healthy read), HWM 100,000.00 baseline (no verified close above it).

## Reconcile (executor task 1, reads 16:07-16:14Z)
- Account ***598 (business id [REDACTED]): NAV/total_asset 98,831.144, cash 98,831.144, frozen 0, mv 0. FLAT (3 zero-qty rows).
- History 14 rows, one page, has_more=false. Ownership CLEAN: newest order 3124586 (desk exit 13:12:46Z); zero pending/live orders; no unattributed texts.
- FILLS-FIRST journaled (broker status4 verified): SPY 3124584 sell 28 @715.19; EFA 3124585 sell 142 @98.75; MSFT 3124586 sell 39 @489.903 - all filled 14:30:03Z open. Ledger 85 events after fills.
- VNQ 3116597 / SMH 3118500: CLOSED per operator ruling 2026-11-24; not journaled, not blocking.
- Protection: flat book, no uncovered lots, no protection gaps. Production lifecycle state bytes unchanged (isolated dry ticks).
- Lifecycle tick (dry, live clock): SPY/EFA r2 adoption blocked "adoption plan cannot open a new position"; AAPL PB-007 blocked "entry expired or lifecycle invalidated"; gaps []. No lifecycle submissions.
- Tactical tick v2 (fresh batch 16:13:46-48Z): KO/PG/JNJ wait "research review older than 30 minutes" (old watchlist); feed gates pass. Alert "monitor starting or heartbeat gap; rebuild entry confirmations".
- Feed note: quote top-level last + order book agree (KO 98.14/98.15, PG 173.07/173.11, JNJ 275.38/275.49); a lower `price` sub-field (KO 96.02 / PG 169.56 / JNJ 271.00) disagrees. Two independent quote+book pairs (researcher 16:07Z, executor 16:13Z) agree on the top-level/book view; the book is the executable truth. Watchlist zones (set premarket) sit BELOW that market: pullback-only, no chase. No zone was widened.

## Research (researcher, reviewed_at 16:10:05Z, valid_until 17:05:00Z, news_feed_ok true)
- KO TL-20261124-KO-DEF1 VALID. Last 97.975 (16:07Z) above zone 96.10-96.60. Catalysts: MS Buy/103 11:33Z, BofA Buy/100 10:31Z, RBC Buy/96 08:32Z; CFO succession resolved (Elkins eff 2027-04-02, pre-review). Flow FAIL 3-day main -117.4M.
- PG TL-20261124-PG-DEF1 VALID. Last 172.97 above zone 170.20-170.80. No new material news since 13:05Z.
- JNJ TL-20261124-JNJ-DEF1 INVALIDATED for new entry: session low 268.08 < stop 268.50 AND high 275.70 > target 275.25; last 275.69 above target. Ex-div verified: 270.05 - 1.34 = 268.71 = feed prev_close. Re-expression needs a new setup + operator review.
- Tape: risk-off rotation confirmed - SPY -1.22%, QQQ -2.83%, TLT +0.33% (16:08Z). Fed HIKE regime kept operator-pinned; no fresh odds tool; no cut odds written.
- PB-003 contract: US.KO261218C97000 (97C, exp 2026-12-18, DTE 24, STANDARD/AMERICAN, x100). Quote 16:08:36Z delta 0.6149, IV 18.92%, OI 122, vol 94; book 16:09:39Z bid 2.60x10 / ask 2.67x30, spread 2.66% <=5%. Only full gate pass (nearest-delta weeklies failed spread 8-16% or volume). Raw chain persisted research/pb003-chain-raw.json (copied from /tmp/tool-outputs/mcp_a942d03b6989ab4f9ea6348f.txt by desk).
- Events pinned by desk after source validation: 2026-11-25 GDP QoQ 2nd estimate 08:30 ET (indicatorId 375, cons 3.4% prev 2.2%, BEA schedule) and Initial Jobless Claims 08:30 ET Wed shift (indicatorId 294, cons 201K prev 203K, DOL schedule). PCE same slot already a static anchor. config/events.yaml updated.

## Publication
- Watchlist working copy /data/drive/tyche-raw/watchlist.json republished 16:15Z: 4 entries, schema-validated (tyche.watchlist.Watchlist), sha256-16 3a0a0f3d559ce801. KO/PG reviews refreshed; JNJ invalidated=true; KO-OPT1 added UNAPPROVED. Immutable levels unchanged. Copy: research/watchlist-published.json.
- Option setup_hash (entry, config, account [REDACTED]): 0a670fa374c6e241da29f362410d20737b0082c6afbd6336e9357eaad18d99f8.

## Proposal approval (Telegram)
- Proposal #1 ref a51a8a33 sent 16:16Z (msg 52): BUY 1 US.KO261218C97000 limit 2.67 x100, exit_floor 1.60, premium 267 (0.27% NAV), pullback-only (KO must trade 96.10-96.60; last 98.145), exit_at 17:05Z alert-only-fire timing tension flagged operator-owned. 10-minute window.
- Result: APPROVED. outcome decided, approved [1], decided_at 2026-11-24T16:22:04Z, deadline 16:26:37Z. Order block matches exactly (BUY 1 US.KO261218C97000 @2.67 x100, exit_floor 1.60, setup_hash 0a670fa3...). `tyche approve-telegram` journaled approval.telegram (ledger 88 events, chain verified 16:22:21Z).
- Entry still pullback-only: KO must trade 96.10-96.60; executor task 2 checks fresh quotes + tactical tick. Option entry window closes 16:55Z (exit_at 17:05Z minus 600s planner margin).

## Orders
- ZERO orders submitted by this run. No reserve, no submit.
- Executor task 2 (reads 16:23-16:27Z, tick 16:27:02Z exit 0 orders=[]): KO wait "outside entry zone; do not chase" (last 98.22, book 98.23/98.24); PG same (173.21, book 173.21/173.24); JNJ out-of-batch (invalidated); KO-OPT1 wait "missing/stale/non-tradable quote or order book".
- Option triple-block: (1) underlying 98.22 above zone 96.10-96.60; (2) fresh book ask 2.85 > approved premium_limit 2.67 (bid 2.75x1 / ask 2.85x103, spread 3.51%); (3) option quote data_time FROZEN at 16:08:36.518Z across two pulls while greeks updated (delta 0.6271->0.6282) - fails the 120s quote gate. NEW FEED ANOMALY: illiquid-contract quote tick not updating; PB-003 effectively unenterable until a fresh print lands. Operator approval (16:22:04Z) lapses with this run; no re-entry without a fresh ask.
- Ownership re-check 16:27:10Z: 14 orders one page, identical to task 1, no new tyche-scl- orders, zero pending. config_hash 7103d1e142897acd... (tick).
- Option feed staging verified: option quotes enter via quotes.json + book-<opt>.json + chain-<sym>.json (tactical_data.normalize_quotes); chain 348 rows verifies STANDARD/lot100/CALL/strike97/exp2026-12-18.

## Close-out
- run.end journaled 16:28Z; ledger 89 events chain verified.
- Premarket unpushed event-pins commit c914cb4 replayed from Drive bundle as 553155b (cherry-pick onto e5a71ac); desk's duplicate GDP/claims pins dropped in favor of the richer premarket pins (time_et 08:30, symbols, BEA URL). config/events.yaml now carries both Nov-25 events.
- Digest sent 16:29Z: msg 55 ref fc70ccad rc 0 (sentinel v1, ON-DEMAND RUN title, not urgent).
- PUBLISH: result recorded below after the script runs.

## Notes / deviations
- reconcile.completed payload carries an estimated utc field (16:23:30Z) written ahead of the true clock (~16:17Z); the journal chain ts is the authoritative time. No review/approval time was fabricated.
- Executor task-1 report had a garbled hash table; corrected table received and recorded (cash c8d6dfc9c04432f8, quotes 4c8c9afbd50a2379, orders 786f568c92ded698).
- PB-004 scalp lane untouched by this run (card rule). sim_trade_order_list unregistered (7th+ fire) - history pagination authoritative.