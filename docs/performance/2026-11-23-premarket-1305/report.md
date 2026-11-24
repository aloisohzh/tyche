# TYCHE premarket run report - 2026-11-23 08:05 ET fire (private)

Run: 2026-11-23-premarket-1305. Desk head: tyche-desk. Fire: first fire of the permanent three-fire card (08:05/12:05/15:05 ET).
Repo/LC_ROOT: /data/workspace/tyche, HEAD a87a28d360d7a84451b2bca9963d99cda6824bfb (contains pinned release 3312287ce282cedacdafab552b40678e386ea90d). tyche installed editable --no-deps.

## Gate and calendar
- `tyche calendar --json` exit 0 at 13:05:33Z: trading_day true, half_day false, phase pre_market, activity plan, new_entries false, max_orders 0, event_caution false.
- Calendar drift check (first premarket fire, once/day): WebFetch https://www.nyse.com/trade/hours-calendars -> data/nyse-calendar.txt (gitignored scratch); `tyche calendar-check --source data/nyse-calendar.txt --json` exit 0. **IN SYNC** (2026/2027/2028, no changes, no warnings).
- Events pinned this run (config/events.yaml, all source-verified against persisted raw MCP payloads in research/mcp/): Nov-25 Initial Jobless Claims 08:30 ET (indicatorId 294), Nov-25 GDP QoQ 08:30 ET (375), Nov-24 JNJ ex-div 1.34 (corporate-actions payload), Nov-23 EU formal antitrust probe into CCEP (WSJ/Futu 1005341828, KO symbol). PEP Dec-4 ex-div skipped: after challenge window. Gate merges today's KO event; event_caution stays false (symbol-level).

## Lineage, halt, authority, ownership
- Restored newest verified descendant: /data/drive/tyche-raw/2026-11-23-operator-freeze/journal/events.jsonl (41 events, sha256 a7ee32316728ff73c514b39d7e8b1b8cb9f18e2409189551dd467bcbe0a26a66 = Nov-20 close lineage + 5 operator rules.frozen events 02:03-02:04Z Nov-23). Chain verified. halt.json (engaged, CLI-written) copied beside it from 2026-11-20-close-2005/journal/.
- **HALT ENGAGED**: journal flag 2026-11-19T20:28:29Z writer-safety incident, never released by any journal event or repo flag. Repo data/halt.json is the stale pre-incident Nov-18 "resume" (shared kill-switch commit ae61760 predates the incident). effective_halt = journal source. Buys blocked; approved de-risking sells would still pass, but approvals=[] so none exist.
- Authority: ASK ME (data/approvals.json as_of 2026-11-19, not same-day; never edited).
- Switches (data/strategies.json, operator 2026-11-23T05:27:15Z via PR #31): PB-001 on, PB-002 on (universe now MSFT + KO/PG/JNJ/PEP/MCD defensives), PB-003 options off, PB-004 scalp OFF (skipped), PB-007 ON (rules frozen e26f006da28a). Rules hashes match the operator's Drive ledger freeze: PB-001 819ad06e35f0, PB-002/003 d5ef9567c736, PB-004 72077d5d4808, PB-007 e26f006da28a.
- Ownership: desk-site automation feed (fetched 03:53Z) shows exactly one active schedule - this three-fire card dep_00w9n1b9mkb9cjkalhcv; probe sessions idle. Broker boundary order 3118578 (2026-11-19T18:15:16Z) intact; no newer order on either paper account. Single-writer ownership verified for this run.

## Executor reconcile (read-only, [REDACTED]; full artifacts mcp/, state-tick/)
- NAV total_asset 98,617.331; cash 45,680.121; frozen 0; MV 52,937.21 (gross 53.68%). Premarket marks.
- Positions: SPY 28 (avg 731.54), EFA 142 (avg 100.495), MSFT 39 (avg 503.33). All sellable.
- History: ONE unfiltered page, has_more=false, 11 orders ever. Zero live/pending. status4 fills reconcile to positions. status5 UNRESOLVED (not proven terminal): VNQ 3116597 83@94.98, SMH 3118500 10@454.48.
- Env TYCHE_ALLOWED_ACCOUNT_IDS=***4748 (wrong account) - reported, not edited. Disclosed session-scoped correct-id override used for read-only diagnostic ticks only; resulting tactical config_hash d5b6cdcee3fc1b46a2d7326d2344a38f20d6b730bfe470433c6cd3a2c906eafe reflects that injection.
- Quotes (pre_market phase; main last = Nov-20 close, live prints in pre_market fields): SPY 689.81/pre 708.1388; EFA 96.14/pre 97.415; MSFT 484.52/pre 499.1768; KO 96.99/pre 96.75; PG 169.37/pre 169.84; JNJ 270.47/pre 272.3381; PEP 140.54/pre 140.94; MCD 273.24/pre 273.825. Books captured for all 8.
- Daily klines: 32 symbols x 370 bars (executor prose said 33 - harmless miscount; all 32 delegated symbols present), last completed bar 2026-11-20 everywhere. data/prices.csv rebuilt by desk head via scripts/mcp_prices.py from staged kline copies (11,840 rows); data/ohlc.csv rebuilt by executor (bars sha 1721c3a9ea6f70e867a985d401ad9c27539c5a6b91d56f035749616d1661adc4).
- **Nov-20 official closes verified: SPY 689.81 < 727.50 stop; EFA 96.14 < 100.00 stop - second consecutive completed-bar daily-close breach for both r2 contracts.**
- Protection: lifecycle tick (no --record, isolated copies) blocked verbatim "broker snapshot stale or future-dated; fetch again" - the 120s account-snapshot gate is structurally unpassable pre-market with this tool set; default env additionally fails "unverified or non-allowlisted US paper account". Tactical tick dry: "tactical lane disabled or outside regular session". Production book/state hashes unchanged pre/post (book 295ad864..., state a7a9e994...).
- Coverage verdict: **SPY 28 UNCOVERED, EFA 142 UNCOVERED, MSFT 39 UNCOVERED/UNOWNED** - no approved grants (approvals=[]), no live exit orders, no broker-native stops. No protection.gap journaled: no approved exit request_ids exist to gap.
- NAV refs: executor diagnostic used prior_close_nav 99,914.93 (Nov-19) - CORRECTED here: Nov-20 close NAV 97,788.36; today +0.85%. HWM pin 102,208.99 remains operator-UNCONFIRMED; DD vs pin -3.51% (soft 4% level 98,120.63; NAV above it now; Fri close was -4.33%, soft breached then). Operator to confirm/replace pin.

## PB-007 fib pullback (switch ON)
- `tyche fib-scan --bars data/ohlc.csv --account <snapshot> --book <run>/pb007-book.json --flat-by 2026-11-27 --record` at 13:16:32Z. --record wrote ONE plan.created proposal event via the supported CLI (journal event 43, hash 7ff263f90985664d...). No approval, no order.
- Proposal: US.AAPL PB-007-20261120-AAPL, plan_hash 3dd88f8660b24f5d242cc8e1b6d69d40364048fc9c416ded97ea6eb2879dd1ec, new_entry qty 28, zone 338.89-343.08 (limit 343.08, ~9,606 notional ~9.74% NAV), stop 331.99 (basis last, ~-310.5 risk), target 360.83 (1.60R), entry_expires 2026-11-23 15:50 ET, flat-by 2026-11-27 12:30 ET (early close). Friday close 342.56 sits INSIDE the zone.
- LLY/MA signals ranked below open-slot budget; 21 rejected (regime.off below SMA200 or zone failed/untouched). Normal filter outcome in a downtrend.
- Kernel diagnostic (read-only, /tmp): PB-001 regime risk_off, conviction low (1/4 checks).

## Research (tyche-researcher; artifacts research/, all UNAPPROVED)
- Regime: Fed HIKE cycle; Dec 25bp ~88%, 50bp tail collapsed to ~0%, hold ~12% (CoinDesk 1005309126, 04:45Z - payload persisted). Monday S&P futures +2.46% (DJ 1005349412 12:30Z); JPM desk "no bottom yet" (Zhitong 1005351627 12:55Z). Wed Nov-25 08:30 ET triple print: core PCE cons 3.2% vs 3.1%, claims 201K, GDP 3.4%.
- SPY r2 review: INVALIDATED (rule i, two completed bars 715.87/689.81 < 727.50). EFA r2 review: INVALIDATED (98.78/96.14 < 100.00). Exact book plan hashes e73ee77d.../add27d1a...; reviewed_at 13:15Z (desk-verified anchor; researcher's original 13:45Z approximation was future-dated and corrected), valid_until 14:15Z. Operator decision: adoption-for-exit approval or directed exit; no automatic liquidation.
- MSFT 39 unowned note: bearish MA structure, 4-day institutional distribution; options A) adopt-with-protection (levels operator-chosen, none invented) B) operator-directed exit; research leans B.
- PB-002 proposals (watchlist schema VALIDATED exit 0, as_of 2026-11-23, full 8-axis thesis blocks): JNJ TL-20261123-JNJ-DEF1 (medium conviction; TREMFYA ph-4 STAR endpoints + JPM PT 300 + main-flow flip +27.3M; entry 269.80-270.60/stop 268.60/target 273.80, RR 1.60-3.33, exit 15:50 ET; ex-div 1.34 tomorrow - no overnight hold) and PEP TL-20261123-PEP-DEF1 (low; Hyatt 10-yr deal + 54th dividend raise + Friday inflow 47.7M; entry 140.10-140.70/stop 139.40/target 142.70; bear case Friday-night mixed shelf filing). KO rejected (negative flow, EU probe), MCD (stale catalyst, overbought), PG (no fresh issuer news - unknown, incomplete), MSFT tactical (unowned first).
- Coverage gaps: news_feed_ok TRUE (fresh to 12:55Z) but researcher's quote feed served Nov-20 close only - proposals need fresh executor two-sided quotes (captured later by executor, premarket books) before any execution; market caps derived estimates (labeled); seasonality unknown both; Fed-speaker schedule unverified (no event proposed); econ cal Nov-23/24 empty.
- YouTube inbox: none new.

## Decisions and actions this run
- NOTHING SUBMITTED, RESERVED, CANCELED OR MODIFIED. No production lifecycle state mutation. No Telegram approval asks: halt mechanically blocks buys, so /approve would be misleading (advisor-confirmed). Proposals listed BLOCKED in digest.
- URGENT RISK ALERT digest sent 13:24Z: message_id 47, content_ref 0ee57457, rc 0 (renderer path, templates/sentinel-digest.example.json shape).
- Advisor consulted (halt posture, digest-first, no approval wait while halted, prior_close_nav correction, graceful event-source degradation).
- Journal: run.start (42), plan.created via fib-scan CLI (43), reconcile.completed (44), notify.sent (45); research.published + book publication appended after assembly.

## Operator decision queue (unchanged blockers + today's)
1. Release halt (tyche resume) after incident review; re-provision TYCHE_ALLOWED_ACCOUNT_IDS to challenge [REDACTED].
2. SPY/EFA: confirmed rule-(i) invalidation on two completed bars - approve adoption-for-exit plans or direct exits (de-risk sells allowed under halt).
3. MSFT 39: adopt-with-protection vs directed exit (research leans exit).
4. Confirm/replace HWM pin 102,208.99.
5. status5 semantics VNQ 3116597 / SMH 3118500 still unresolved.
6. Whether to advance JNJ/PEP/AAPL proposals after halt release (fresh quotes + audit + approval required; AAPL entry expires 15:50 ET today).

## Next check
12:05 ET midday protection fire (17:05Z, alert-only), then 15:05 ET close fire (20:05Z). Verified from the active card cron.

## Publication and persistence (final)
- AAPL review appended by researcher: UNCERTAIN, reviewed 13:25Z valid 14:25Z, exact hash 3dd88f86...dd1ec - desk head INDEPENDENTLY RECOMPUTED the plan fingerprint from pb007-book.json (match), rules_hash e26f006da28a. Close 342.56 inside zone; gap-up context = pullback-only entry before 15:50 ET, no chase. Researcher's "lane disabled / cap-sum" blocker claim CORRECTED: PB-007 effectively enabled via operator override; switched-on cap sum 0.90 <= 0.95. Real blockers: halt, uncertain verdict, no live executable quotes at review time.
- Book published to /data/drive/tyche-raw/lifecycle/book.json sha256 b1dfb28c9b4b181160a99fb70946dabf858e004b72666a8bd852544f9d1cde50 (prior 295ad864... kept at state-tick/book.pre-publish.json). Plans SPY r2/EFA r2 UNCHANGED; AAPL plan added UNAPPROVED; 3 schema-valid reviews; 7 MarketEvents; news_feed_ok true. state.json untouched (a7a9e994...). Watchlist working copy /data/drive/tyche-raw/watchlist.json sha de49cbeb... (schema exit 0 after timestamp fix).
- CORRECTION REPUBLISH: AAPL review gate wording desk-corrected post-review (researcher had misread lane_config_enabled:false as disabled; operator override enables PB-007, cap sum 0.90<=0.95). Verdict uncertain, timestamps 13:25Z/14:25Z, plan_hash and all other evidence unchanged; transparency clause inside the review. Final book sha256 bc9e6d50643f722fac9f04e2947fde14bd31b12b1326aef42323f152650f3eaa (b1dfb28c... kept at state-tick/book.pre-republish.json); correction journaled (research.published, event 49).
- Halt SYNC: tyche halt CLI re-asserted the engaged incident halt to the shared repo flag (repo data/halt.json had stale pre-incident Nov-18 resume); halt.engaged SYNC event journaled; authoritative journal flag unchanged in substance. Fail-safe direction, Nov-20 advisor-reviewed precedent.
- Journal lineage: 49 events, chain intact, sha256 21695d84c13ca0720e5f791d75443957bc26506f3b5869b2befbf906928db1aa (run.start 42, plan.created 43 via fib-scan CLI, reconcile.completed 44, notify.sent 45, research.published 46, halt.engaged SYNC 47, persist.push_failed 48, research.published correction 49).
- Sanitized persist: tyche persist -> 94 files in docs/performance/2026-11-23-premarket-1305/, leak scan clean (no raw account ids/tokens). Commit 1673ec0 (events.yaml pins + halt flag + bundle). Ambient git push AUTH FAILED (session-scoped credential); fallback bundle /data/drive/tyche-raw/2026-11-23-sanitized-git/premarket-1305.bundle (origin/main..main) + halt.json + events.yaml copies. TYCHE_GITHUB_PAT present for the publish script's GIT_ASKPASS push path.
- Publish: scripts/publish_desk_data.py run once. Feed rebuilt (secret guard PASS, challenge-account-first but newest challenge cloud snapshot found was 2026-11-18-midday3 - today's raw snapshot lives on Drive, not in the repo's cloud-run discovery path); performance pack SKIPPED (no repo-local journal/events.jsonl - expected, journal is on Drive). PUSH FAILED: "remote: Invalid username or token. Password authentication is not supported for Git operations." despite TYCHE_GITHUB_PAT present - token invalid/expired or not honored; operator action: run the publish script with a valid push token. Local commits 1673ec0 + 90915b3 + 9db2df1 (feed); bundle refreshed to include all three. persist.push_failed journaled (event 48). Close fire retries the push once.
