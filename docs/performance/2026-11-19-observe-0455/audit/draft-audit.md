# Tyche independent draft audit — lifecycle adoption proposals (US.SPY / US.EFA)

**STATUS: DRAFT — NOT AN APPROVAL, NO EXECUTION AUTHORITY.**
**Not executable: rollout hold.** execution_enabled=false (config/tactical.yaml:5, verified). Hourly lifecycle monitoring deployed; orders unarmed. This audit is not operator authorization; deployment permission is not a setup grant; test success is not a broker fill. No execution-approved Audit JSON is issued (rollout hold forbids it). No operator grant, approval, reservation or latch exists or is created by this document.

- Auditor: tyche-risk-auditor (independent; Read/Glob/Grep/Write only; no shell, no broker/MCP tools).
- Coordinator-supplied clock: **2026-11-19 05:14 UTC = 00:14 ET Nov 19**. Market CLOSED (broker market-state AFTER_HOURS_END, time_date 20261118). Next scheduled hourly run **2026-11-19 13:05 UTC (08:05 ET)** — verified against market_calendar.py:26-27,426-441 (hourly 08:05–17:05 ET, trading days only).
- Scope: existing holdings only — US.SPY 28 sh, US.EFA 142 sh — plus relevant events. Account masked [REDACTED] (account_type=2, market_id=100, single-entry TYCHE_ALLOWED_ACCOUNT_IDS match per executor's redacted proof; full IDs exist only in private raw payloads and are never reproduced here).
- Run dir: /data/drive/tyche-raw/2026-11-19-observe-0455/. All evidence below was read directly by the auditor unless explicitly labeled **attested** (desk-head sha256 recomputation — audit condition C5: I have no shell and cannot recompute sha256; content-level consistency was verified instead).

---

## 1. Per-proposal verdicts

### LC-20261119-SPY-ADOPT-r1 — plan_hash 8ca9176daf7d09b4030cc15cf5460896fd871ef2c66b48db60fc6f886fbdd954
**Verdict: APPROVE-WITH-CHANGES (draft-quality assessment only — NOT executable approval; not executable: rollout hold).**
The draft contract is complete, internally consistent, quantity-reconciled to broker evidence, and its price levels are anchored to verified market data. Required before any future approval: fresh exact-hash review + fresh quotes at check time (current review expires 06:10Z, hours before the 13:05Z run), resolution of every activation blocker in §7, a reviewed release reconciling the config/rules-hash divergence, and explicit operator approval of the full immutable contract. Minor draft note: entry_low 726.80 is the Nov 18 low 726.795 rounded UP 0.005 (band does not strictly contain the observed low; it contains cost 731.54 and close 730.20 — acceptable for an adoption anchor, but the rounding should be stated in the plan, as it is in review-report.md §4).

### LC-20261119-EFA-ADOPT-r1 — plan_hash 237408a874860bebfe8731bbfec7742d18f42e2dc717646b24afa46600903395
**Verdict: APPROVE-WITH-CHANGES (draft-quality assessment only — NOT executable approval; not executable: rollout hold).**
Same conditions as SPY, plus two explicit **trader/operator decision points** (not auditor decisions, see §8): (a) engine-anchor reward/risk **0.701 < 1** (even cost-basis R/R is only 1.283); (b) research verdict **uncertain** with fresh EFA-specific equity news MISSING since the Nov 18 close. The uncertain verdict correctly blocks NEW entries; it does not block retained protective stop/target/deadline checks on an existing holding (engine-verified, §6). Adoption is protection of an existing holding, not a new bullish entry — but the operator may instead choose immediate de-risking or a revised contract; that choice is not mine to make. Any change requires a new revision/hash, full preview, fresh independent audit and explicit operator approval.

Neither verdict arms anything. APPROVE-WITH-CHANGES is NOT executable approval; the coordinator must re-plan/re-refresh and obtain a new exact-contract review after rollout release.

---

## 2. Check C1 — Quantities, cash, NAV, order history: **PASS** (2 caveats)

Verified by hand from raw captures (mcp/, reads 04:59:07–05:00:11Z per query-log.json / orders-query-log.json):

- **Positions** (positions.json, read 04:59:19–04:59:27Z): SPY qty 28 = qty_avbl 28, cost 731.54, mark 730.20, mv 20,445.60, P&L −37.52; EFA qty 142 = qty_avbl 142, cost 100.495, mark 100.26, mv 14,236.92, P&L −33.37. Matches book.json, market.json and both plans exactly. No options, no shorts (short_mv=0), no fractional quantities — stock-only adapter coverage OK.
- **Fills** (orders-page-01.json, unfiltered, has_more=false, next_key="0"): 3116580 SPY buy 28, status 4, cum_qty 28, avg_fill 731.54 (= position cost exactly); 3116594 EFA buy 142, status 4, cum 142, avg_fill 100.495. Create/update epochs recomputed: 17:44:56/17:45:00Z and 17:49:36/17:49:45Z Nov 18 — match journal order.submitted timestamps (17:45:09Z, 17:49:48Z). Status 4 + full cumulative fill is the only recognized terminal proof (engine BrokerOrder.complete, lifecycle.py:156-159; fill_bounds :147-153 rejects inconsistent status-4).
- **VNQ 3116597**: buy 83 @ 94.98, status 5, cum_qty 0, avg_fill 0, update 1795050060 = 2026-11-19 01:01:00Z. **Status-5 canceled-vs-expired semantics are labeled UNKNOWN** in reconciliation.md §4 and orders-query-log.json — not guessed. Proven: zero fills, no VNQ position, frozen released. Freeze arithmetic: 83×94.98 = 7,883.34 + 0.99 implied fee = 7,884.33 = EOD frozen; **57,360.28 (EOD cash) + 7,884.33 = 65,244.61 = current balance exactly** ✓. No desk cancel/modify (journal confirms). Engine treats status 5 as non-complete/blocking (lifecycle.py:151,159) — correct; it does not block SPY/EFA decisions (pending checks filter by symbol, lifecycle.py:454,495) but WOULD block any future VNQ lifecycle until broker semantics are resolved.
- **Cash residual**: 100,000.00 − 20,483.12 (28×731.54) − 14,270.29 (142×100.495) − 1.98 fees = **65,244.61** ✓ = cash.json balance. **NAV = 65,244.61 + 34,682.52 = 99,927.13** ✓ = broker total_asset; hold/frozen = 0. mv cross-check: 28×730.20 + 142×100.26 = 34,682.52 ✓ (regular-close marks; SPY after-hours 735.57 is NOT in broker NAV ✓).
- **Journal** (/data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl, READ-ONLY): 12 events; prev_hash chain links verified visually end-to-end; last hash 5df92f3dcae0d59f4e5d50e64b148cd8138fce69f23c1d525a4628a9c75499c3 matches expected. eod.reconcile @ 2026-11-18T21:11:13.022797Z: prior_close_nav 99,914.93, high_water 100,000.00, cash 57,360.28, frozen 7,884.33, fees_implied=fees_modeled=1.98, reconcile_ok=true, residual 0.0 ✓. All 12 sha256 event-hash recomputations are **desk-head-attested (C5)**; chain-link and content consistency I verified myself. NAV drift: 99,927.13 vs prior close +12.20 (+0.012%); vs high water −72.87 (−0.073%) — far inside 2.5% daily / 4% soft / 6% hard limits.

**Caveat C1-a (logged anomaly, residual risk):** the windowed history probe (time_begin=0, time_end=2026-11-18T00:00Z) returned the SAME 3 orders created AFTER time_end — server-side time-window params appear unhonored. Correctly logged as an anomaly and treated as duplicate confirmation only; completeness rests on the **unfiltered has_more=false** exhaustion. That is the best available evidence, but a server-side filtering defect means window-based completeness proofs are unreliable on this API; keep relying on unfiltered exhaustion.
**Caveat C1-b:** orders show market=2 vs account market_id=100 — normalization quirk, same account, documented. market.json orders_complete=true is justified only by the unfiltered exhaustion.

## 3. Check C2 — Price geometry, anchors, deadlines, windows: **PASS** (1 minor note)

- SPY: **725.00 < 726.80 <= 735.06 < 749.50** ✓; EFA: **99.40 < 99.96 <= 100.87 < 101.90** ✓ (engine validator lifecycle.py:58-59 enforces the same).
- Anchors vs raw klines (15 completed K_DAY autype=1 bars 2026-10-29→11-18 each, bar presence confirmed): SPY Nov 18 L/H **726.795/735.06** ✓, Nov 17 low **727.00** ✓, Nov 16 high **749.82** ✓ (target 749.50 sits 0.32 under — design choice, labeled); EFA Nov 18 L/H **99.96/100.87** ✓, Nov 17 high **102.00** ✓ (target 101.90 sits 0.10 under), Nov 6 low **101.27** ✓ (range floor broken by Nov 18 close 100.26 ✓). Down-day sequences −1.91/−1.01/−0.31% (SPY) and −1.47/−1.26/−1.08% (EFA) match change_rate fields ✓. Stop buffers (~0.25–0.3% SPY, ~0.56% EFA) are explicitly labeled risk-design choices; anchor lows are market-derived ✓.
- Minor note: SPY entry_low 726.80 > observed low 726.795 by 0.005 (rounding, documented in review-report.md §4; band contains cost and close; adoption anchors only, NO new buys — adopt_position cannot open a position, lifecycle.py:463-464).
- Timing: created_at 2026-11-19T05:10Z < entry_expires 2026-11-19T16:00-05:00 (21:00Z) <= exit_deadline 2026-11-27T12:05-05:00 (17:05Z) ✓ (validator :60-61). Nov 27 2026 is a trading half-day (market_calendar.py:82, HALF_CLOSE 13:00 :32); 09:30 <= 12:05 < 13:00 ✓ (:65-66). Nov 26 Thanksgiving closed (market_calendar.py:51). Hourly cadence 08:05–17:05 ET (:26-27): on Nov 27 the 12:05 ET fire is CLOSING_DRIVE (half-day closing drive starts 12:00, :36) and 13:05 ET is after the 13:00 close — **12:05 ET is exactly the last scheduled hourly RTH check** ✓ and equals exit_deadline ✓, inside the challenge window ✓.
- Slippage 20 bps <= 30 required ✓ (both plans; sell limit = trigger-time last × (1−20bps), ROUND_CEILING, lifecycle.py:381-388 — no fixed sell limit is approved now; previews contain no order lines).
- Reviews: reviewed_at 05:10Z, valid_until 06:10Z = **exactly 60 min** ✓ (Review.bounded :85-91 allows ≤1h); both expire **before** the next run 13:05Z and are explicitly labeled **PENDING-REFRESH / NOT actionable** in book.json reviews, reviews-draft.json and risk-report.md ✓. reviewed_at == created_at satisfies the engine's reviewed_at >= created_at requirement (:343-344).
- Quote exchange timestamps recomputed: 1795035600268 ms = **2026-11-18T21:00:00.268Z** (SPY), 1795035600000 = 21:00:00Z (EFA) = 16:00 ET regular close ✓. All quotes are stale (>300s quote_max_age; >60s tactical limits irrelevant — market closed, no entries possible). Fresh quotes + fresh review mandatory at the next check.

## 4. Check C3 — Source timestamps, news completeness, events: **PASS with documented gaps**

- News publish epochs recomputed from news-extracts.json: CFTime 1795049859000 = **2026-11-19T00:57:39Z** (post/1004960262) ✓; Jin10 1795044573000 = **2026-11-18T23:29:33Z** (post/1004952667) ✓; Fisco 1795040595000 = **22:23:15Z** (post/1004948915) ✓; Fisco 1795038667000 = **21:51:07Z** (post/1004946744) ✓; Zhitong 1795048627000 = **2026-11-19T00:37:07Z** (post/1004961079) ✓. Hawkish Oct 27-28 FOMC minutes confirmed by three independent timestamped sources; Fisco date typo flagged and resolved via cross-sourcing ✓.
- **Dec 9 25bp HIKE >95% priced — labeled second-hand** ("CME FedWatch via CryptoTicker", "no direct CME access this run") ✓; exact 50bp tail % explicitly **unsourced** ✓. This is a HIKE cycle: no cut-odds language anywhere in the run artifacts (grep verified; only "NOT cuts" negation and the "cuts both ways" idiom).
- **EFA fresh symbol-specific news MISSING** (Japan/Europe search returned only stale items, newest 2026-10-13) → verdict **uncertain** ✓ — correct handling: uncertainty blocks NEW entries, not retained approved stop/target/deadline checks (engine held-path, §6). news_feed_ok=true is scoped to macro coverage with the EFA gap recorded ✓.
- Scheduled events verified from raw-calendar-hot.json epochs: claims 1795095000 = **Nov 19 13:30Z (08:30 ET)** ✓; Core PCE (prev 3.1%) + claims + GDP (cons 3.4%, prev 2.2%) 1795613400 = **Nov 25 13:30Z** ✓ — largest sourced macro risk, immediately before the Thanksgiving gap. **Empty hot lists Nov 20/23/24/27 are labeled a coverage gap, not proof of quiet** ✓ (_meta + review-report §3). Engine's own pinned calendar also carries Nov 25 PCE and Nov 18 minutes (market_calendar.py:124-126) — consistent.
- events-draft.json: **11 events, all with IDs, timestamps, sources**; date-only markers (Waller interview, NVDA release) explicitly labeled ✓; minutes release 14:00 ET per desk directive with exact minute labeled unsourced ✓. LPR marked non-material for EAFE (ex-China) — reasonable. Book reviews acknowledge all material events for their symbols (SPY 9, EFA 9; unacknowledged ones are other-symbol or non-material) ✓. Minutes/Waller predate plan created_at and ARE reviewed (post-event review satisfied) ✓.
- Benign discrepancy: SPY overnight last 734.57 in research capture (04:58Z) vs 734.59 in executor capture (04:59Z) — live overnight-session drift between two genuine captures; each artifact is internally consistent with its own source. Not an error.
- Monitoring-feasibility gaps to carry into hourly reviews: (a) EFA invalidation rule (b) needs USDJPY quotes — no FX feed in the current capture set; must be re-sourced via news each check or the rule is unmonitorable; (b) SPY invalidation rule (c) "on the release" at 08:30 ET cannot be observed tick-exactly by an hourly cadence (08:05 check is pre-release; next checks 09:05/10:05) — up to ~1h observation latency; (c) claims/PCE at 08:30 ET fall within 30 min of the 08:05 ET check → engine blocks entries then (lifecycle.py:353-354); exits unaffected.

## 5. Check C4 — Fee/risk arithmetic: **PASS** (all figures recomputed by hand)

Denominator: broker total_asset **99,927.13** (frozen 0) ✓ throughout risk-numbers.json.

| Figure | SPY (28 sh) | EFA (142 sh) | Verified |
|---|---|---|---|
| Engine loss at stop from entry_high | 28×(735.06−725.00)=**281.68** (0.282% NAV) | 142×(100.87−99.40)=**208.74** (0.209%) | ✓ |
| P&L cost→stop | 28×6.54=**−183.12** (−0.183%) | 142×1.095=**−155.49** (−0.156%) | ✓ |
| Mark→stop (forward downside) | 28×5.20=**−145.60** (−0.146%) | 142×0.86=**−122.12** (−0.122%) | ✓ |
| P&L cost→target | 28×17.96=**+502.88** | 142×1.405=**+199.51** | ✓ |
| Mark→target | 28×19.30=+540.40 | 142×1.64=+232.88 | ✓ |
| Preview gain from anchor high | 28×14.44=404.32 | 142×1.03=146.26 | ✓ |
| R/R (engine anchor, before fees) | 404.32/281.68=**1.435** | 146.26/208.74=**0.701** | ✓ |
| Exit fee model | 0.99+min(28×0.000166, 8.30)=**0.9946** | 0.99+min(142×0.000166, 8.30)=**1.0136** | ✓ vs fees.py:17-19,42-46 |
| Slippage 20bps at stop | 28×725×0.002=**40.60** | 142×99.40×0.002=**28.23** | ✓ |
| Worst planned incl slip+fees | 281.68+40.60+0.9946=**323.27** (0.324%) | 208.74+28.23+1.0136=**237.98** (0.238%) | ✓ |

Combined: engine anchors 490.42 (0.491%); vs cost 338.61 (0.339%); forward from marks 267.72 (0.268%); **worst incl slippage+fees 561.25 = 0.562% NAV < 1% stock stop-risk budget** ✓. Note risk_per_trade_pct applies at buy time (risk.py:80-84, buy-only); adoption places no buys. Engine anchors from entry_high are conservative vs actual cost basis.

**Fee caveat:** the Nov 18 "match" (model 1.98 = implied 1.98) is against fees **implied from the cash residual**, not broker-reported fee fields — the sim MCP exposes none (fees.py docstring; journal fees_modeled=fees_implied). Modeled fees are NOT confirmed charged fees; sell-side TAF-on-sell is a provisional convention. Keep labeling source="model".

## 6. Check C5 — Allocation/cap semantics + exit reachability: **PASS** (semantics/code); hash values **UNVERIFIABLE (C5, attested)**

- **allocation_cap ≠ max_weight — no conflation.** Current root config/strategies/pb-001.yaml:4 `allocation_cap: 0.25` is the WHOLE PB-001 sleeve budget: rotation.py:269 (current root, src/tyche/strategies/rotation.py) `max_invested = min(strategy.allocation_cap, 1.0 - strategy.min_cash_weight)`. `max_weight: 0.30` (pb-001.yaml:13) is the strategy per-name ceiling; rotation.py:184 `caps = min(asset.max_weight, strategy_max)` with universe per-asset SPY 0.30 / EFA 0.20 (config/universe.yaml:7,19). Prior auditor conflation is not repeated.
- **Holdings vs budgets:** market-value basis 20,445.60/99,927.13 = **20.46%** + 14,236.92/99,927.13 = **14.25%** = **34.71% NAV**; cost basis 20,483.12 = **20.50%** + 14,270.29 = **14.28%** = **34.78% NAV** (the delegation's figures are cost-basis; risk-numbers.json labels them invested_pctNAV; reconciliation.md uses MV — both correct, different bases). **Either basis exceeds the 25% current-root PB-001 sleeve budget.** These are EXISTING holdings: the breach is a finding and an activation-reconciliation item, **not permission to liquidate**, and ceilings are not required allocations. Per-name: SPY 20.46%/20.50% < 30% ✓; EFA 14.25%/14.28% < 20% ✓ under both regimes.
- **Release vs current divergence (content-verified; hashes attested):** release pb-001.yaml has NO allocation_cap; release rotation.py:269 uses `1.0 - min_cash_weight` (=0.95) — the release engine has **no allocation_cap field at all** (grep: zero matches in release config.py). Precision correction to coordinator-config-caps.md: the "defaults to 0.95 in config.py" statement describes the CURRENT root (config.py:69); in the release the field is absent entirely — same substantive conclusion (no 25% sleeve budget in release). Release risk.yaml: turnover **0.50** / orders **6**, no competition_order_cap line (engine default 200, release config.py:118), no option caps; current risk.yaml: turnover **1.50** / orders **40**, competition_order_cap 200, option_risk_per_trade_pct 0.0075, max_option_premium_pct 0.25. universe.yaml byte-identical content in both roots ✓. Current config.py:242-245 cross-lane check: 0.25 + 0.45 (tactical.yaml:8) + 0.25 = 0.95 = max_gross_exposure ✓. rules_hash 7799974f9fd0 (release) vs 4105d7a680a3 (current) — divergence confirmed at content level; exact hash values desk-head-attested (C5). **Activation requires a reviewed release reconciling these with operator-approved caps; silent substitution is forbidden.**
- **EXITS remain possible despite entry-blocking caps/breaches — line evidence (pinned engine):**
  - lifecycle.py:420-451 (held-position path): stop/target/deadline evaluated and latched BEFORE ownership, quote and session gates; a review problem only warns (:407-409) and downgrades to "review" when there is NO exit trigger (:447-449); with an exit trigger the decision is "sell" (:451), quantity = min(owned, held, available) (:452). Expired/uncertain review never suppresses a triggered protective exit (module docstring :3-4).
  - lifecycle.py:472-473: halt gate sits in the NO-holding branch only — "halt blocks entries, not protective exits".
  - pipeline.py:65-70 act_wait: `if side == Side.SELL or sleeve == "defensive" or held: return "act"` — sells always act; it is only consulted on the buy path (lifecycle.py:488-492).
  - risk.py:85-123: halt, hard/soft drawdown, daily-loss, position.max_weight, portfolio.gross, portfolio.min_cash, sleeve.max_weight, orders.daily_count and turnover.daily are ALL `if buy` — sells exempt ("exits retain capacity", :121). Sells remain subject to broker-safety checks: position.no_short (:74-75), order.pending (:72-73), price.limit_deviation (:68-69), min_notional (full-position exits exempt, :78-79), and competition_order_cap 200 which applies to both sides (:118-119).
  - lifecycle.py:598-603 (tick): an approved contract dropped from book.json is re-added while the position exists — "a scout refresh cannot delete protection"; :605 sorts protection work first; :604-615 a bad proposal cannot stop another position's protection.
  - lifecycle.py:501-503: outside RTH, submission is blocked but "exit trigger remains latched" — daily-close/hourly detection persists; execution no earlier than the next permitted session.

## 7. Check C6 — Ownership / storage / activation blockers: **CONFIRMED — ALL STAND** (technical; separate from trader decisions)

1. **No production lifecycle ledger.** /data/drive/tyche-raw/lifecycle **DOES NOT EXIST** (independently confirmed: directory absent). No grants, reservations, latches or approvals anywhere on Drive; no watchlist.json found under tyche-raw (no tactical-lane duplicate ownership of SPY/EFA). Nothing was created by this audit.
2. **Distributed mutual exclusion unproven.** Rehearsal dir lifecycle-rehearsal-20261119-a/: probe.json verified (nonce 787f4ae0…, code_hash bd8d6ad3…, git_head 1e902cf5… exact pin, written_at 2026-11-19T03:50:32.579332Z). owner.lock/ reported as an EMPTY directory — I found no files inside (consistent; directory existence itself unverifiable without shell). rclone FUSE mkdir/rename/flock/fsync is NOT proven distributed CAS/locking; same-session reads prove nothing cross-session. **Single durable writer covering BOTH lanes remains an activation requirement.**
3. **Config/rules-hash divergence** release vs current (§6) — activation blocker, not equivalent policy.
4. **Rollout hold**: execution_enabled=false (tactical.yaml:5, read directly); option round-trip broker validation and 120-second tactical monitoring unverified. The NVDA artifacts in rollout-20261119/post-template-verification/ are template verification only — corroborated by the complete order history showing NO NVDA order or position. Broker drill / reserve→submit path never exercised. These are tactical-lane requirements; they do not block stock-only adoption mechanics but DO block overall release.
5. **Reviews expire 06:10Z, before the next run 13:05Z** — both drafts are pending-refresh; fresh quotes (≤300s) and fresh exact-hash review (≤60min) mandatory before any lifecycle action.
6. **Tick evidence verified:** plan/tick-synthetic-observe.json = live-clock tick exit 1, reason "broker snapshot stale or future-dated; fetch again" — exactly the validate_market message (lifecycle.py:303-306, 120s snapshot window); honest closed-market result. plan/tick-synthetic-replay.json (checked_at 04:59:30Z, cadence 60, gaps []) shows BOTH symbols action=**review**, reason "**held position has no approved lifecycle ownership**", quantity 0, limit null, **authorized=false**, warning "research review expired or future-dated" — matches code exactly: reviews drafted 05:10Z are future-dated at replay time (:343-345); no approval exists (:439-441); quotes stale at 04:59:30Z so no stop/target evaluation possible and **nothing latched**; synthetic state /tmp/lifecycle-synthetic-0455/ contains **no files** (consistent with EMPTY state, no --record, nothing written). The --at/--no-record invocation flags themselves are desk-head-attested (C5). Would-latch results are never durably armed.
7. Engine pin: /tmp/tyche-lifecycle-KXBWpbxx/.git/HEAD → refs/heads/lifecycle-hourly-release → **1e902cf57c26599b69c49496e81b7a493ae5bc49** (exact pin, read directly from ref files; git object integrity attested). Ordinary repo untouched. Schema/preview/capture exit codes are desk-head-attested; preview CONTENT verified: approved=false, submitted=false, plan bodies identical to book.json, plan_hash fields match the exact fingerprints below.

## 8. Trader/operator decisions vs technical blockers — explicit separation

**(a) Technical integration blockers (coordinator/desk-head must resolve; §7):** durable cross-lane single writer + production ledger; config/rules-hash reconciliation via reviewed release; rollout hold + operator release; option round-trip + 120s tactical validation + broker drill; fresh review/quotes at check time; status-5 broker semantics; history time-window API anomaly.

**(b) Trader/operator decisions (NOT auditor decisions; I change no quantities/prices):**
- **EFA R/R 0.701** from the engine anchor (<1; cost-basis 1.283; mark-basis 1.907). The lifecycle lane has no R/R schema gate (tactical min_reward_risk 1.5 does not apply to lifecycle adoption), but accepting sub-1 anchor R/R on a protective adoption — versus de-risking now or revising stop/target via a NEW revision — is the operator's call. My flag: the tight stop under a broken range floor makes a stop-out-then-rebound scenario plausible; the modest 101.90 target caps recovery upside.
- **Stop tightness vs PB-001 initial_stop_pct 0.08** (8% would imply ~673.02 SPY / ~92.46 EFA): proposed structural stops are far tighter, with documented rationale (8% unreachable in a 6-trading-day window; 1%-NAV budget favors tight structural stops). Reasonable, but it converts the design from "catastrophe stop" to "structure stop" with materially higher whipsaw probability under hourly synthetic monitoring. Operator must accept that trade-off explicitly.
- **Sleeve-budget breach handling** (34.71% MV / 34.78% cost vs 25% current-root budget): existing holdings, no liquidation permission. Options (reduce at market, revise the operator-approved budget in a reviewed release, or accept the breach with entries blocked) belong to the operator. Exits must remain possible under any choice (engine-verified §6).

## 9. Plain-language risk summary (per output policy)

**US.SPY — SPDR S&P 500 ETF (stock ETF; strategy PB-001 ballast; ADOPTION of 28 existing shares; side: no buys, protective full-position SELL only on trigger; multiplier 1).** Cost 20,483.12 = 20.50% NAV; mark 20,445.60 = 20.46% NAV. Stop 725.00 (basis last), target 749.50 (basis last), adoption window expires Nov 19 16:00 ET, time exit Nov 27 12:05 ET. Exit limit would be set at trigger time from fresh last with 20bps slippage bound (≈$40.60 at stop); modeled exit fee $0.99. Planned stop loss vs cost −$183.12 (−0.183% NAV); worst planned incl slippage+fees from anchor $323.27 (0.324% NAV). **Worst case is loss of the entire $20,483.12 investment** — the stop is an estimate, NOT a guarantee or maximum. Gaps, halts, stale feeds and non-fills can exceed it. Hourly synthetic checks are NOT broker-native stops; between checks (up to 60 min intraday, ~15h overnight, ~41.5h Nov 25 close→Nov 27 open Thanksgiving gap) there is NO monitoring; daily-close triggers would execute no earlier than the next session (both triggers here are basis=last). Full-position exit only; no ladder, no scaling, no shorting, no automatic re-entry; the lifecycle cannot re-enter after close (lifecycle.py:460-461). Limit exits can non-fill; unknown/canceled/rejected statuses require reconciliation, not assumption.

**US.EFA — iShares MSCI EAFE ETF (stock ETF; PB-001 ballast; ADOPTION of 142 existing shares; protective SELL only; multiplier 1).** Cost 14,270.29 = 14.28% NAV; mark 14,236.92 = 14.25% NAV. Stop 99.40, target 101.90 (both basis last), same window/deadline. Slippage bound ≈$28.23 at stop; modeled exit fee $1.01. Planned stop loss vs cost −$155.49 (−0.156% NAV); worst planned incl slippage+fees $237.98 (0.238% NAV). **Worst case: entire $14,270.29.** Same hourly/non-fill/gap limitations as SPY, plus: three straight down sessions, close below the early-Nov range floor, firm USD headwind, fresh symbol-specific news unavailable (uncertain verdict), anchor R/R 0.701. Combined worst planned across both: **$561.25 = 0.562% NAV** (<1% budget) — but combined theoretical worst is the full $34,753.41 invested.

Current protection status: **holdings have NO resting broker-native stops/targets and NO approved lifecycle contracts** — retained-exit coverage is a live gap to surface at the 13:05Z hourly check. An earlier EOD accounting marker must never suppress a new hourly protection check (engine run.skip precedent exists in the journal for the EOD lane; the lifecycle tick path has no such suppression).

## 10. Missing/unverifiable evidence register (first-class findings)

| # | Item | Status |
|---|---|---|
| U1 | sha256 recomputation of plan fingerprints, book/market/risk-numbers hashes, config hashes, journal event hashes, SHA256SUMS | UNVERIFIABLE without shell — desk-head-attested (C5); content-level consistency verified by auditor |
| U2 | Status-5 broker semantics (canceled vs expired) | UNKNOWN — correctly labeled; blocks future VNQ lifecycle until resolved |
| U3 | History time-window server-side filtering | ANOMALOUS — completeness rests on unfiltered has_more=false |
| U4 | Fresh EFA equity-session news since Nov 18 close | MISSING → uncertain verdict (correct handling) |
| U5 | Calendar hot endpoint Nov 20/23/24/27 | EMPTY = coverage gap, not proof of quiet |
| U6 | Direct CME FedWatch access; exact 50bp tail % | SECOND-HAND via timestamped press; tail unsourced |
| U7 | Charged fee fields | NOT exposed by sim MCP; fees are models vs cash-residual-implied actuals |
| U8 | owner.lock/ directory existence; /tmp synthetic dir; engine invocation flags (--at, no --record); preview/schema exit codes | Attested; file-level absence/presence checks consistent |
| U9 | USDJPY feed for EFA invalidation rule (b) | Not in capture set — hourly re-sourcing dependency |
| U10 | Exact FOMC-minutes release minute; Waller interview time; NVDA release timestamp | Date-only markers, explicitly labeled |
| U11 | Durable cross-session Drive locking | UNPROVEN — activation blocker |

Observation: a reporting/ directory containing a copy of review-report.md appeared in the run dir during this audit (not in my initial listing). No action taken; noted for desk-head awareness (concurrent-session artifact hygiene).

## 11. Conclusion

Both adoption drafts are well-constructed, evidence-anchored protection contracts for reconciled existing holdings, with honest labeling of every coverage gap I probed. **Neither is approvable now**: reviews expire before the next run, no production ledger or durable writer exists, the release/current config divergence is unreconciled, and the rollout hold stands. Verdicts: **APPROVE-WITH-CHANGES for both drafts (draft-quality only; not executable: rollout hold)** — coordinator must re-plan/refresh and obtain a new exact-contract review plus explicit operator approval after a separately reviewed operator release. EFA additionally carries operator decision points (R/R 0.701, uncertain research, stop design). The desk is **NOT armed**; nothing in this report grants execution authority, and no Audit JSON was issued.

---

## Exact hashes (desk-head computed via pinned-engine fingerprint; C5 attested, content-verified)

- LC-20261119-SPY-ADOPT-r1: `8ca9176daf7d09b4030cc15cf5460896fd871ef2c66b48db60fc6f886fbdd954`
- LC-20261119-EFA-ADOPT-r1: `237408a874860bebfe8731bbfec7742d18f42e2dc717646b24afa46600903395`
- plan/book.json: `c710ffe137b968479694c4f34da7420a6ea1ad7beae3061700f5da8de342d166`
- plan/market.json: `13673d965b8de683b22603c8710f149517b47149b5a35d54f7c507fa41b89581` (PRIVATE — contains full account id)
- plan/risk-numbers.json: `1676697ea35198170c0752f1ecb52c1bc19d2855ec48f6b124774a9621c79fff`
- rules_hash: release `7799974f9fd0` (used in plans) vs current root `4105d7a680a3` — DIVERGENT (activation blocker)
- Journal last event hash: `5df92f3dcae0d59f4e5d50e64b148cd8138fce69f23c1d525a4628a9c75499c3` (chain links verified)
- Pinned engine HEAD: `1e902cf57c26599b69c49496e81b7a493ae5bc49` (ref files read directly); ordinary repo HEAD b9ced85 (attested)

## Evidence links and actual times (all 2026-11-19 UTC unless noted)

- mcp/accounts.json (04:59:07–04:59:19), cash.json + positions.json (04:59:19–04:59:27), market-state.json (04:59:27–04:59:33), quotes.json (04:59:33–04:59:36), orders-page-01.json (04:59:36–05:00:02), orders-page-02-window-check.json (05:00:02–05:00:11), query-log.json, orders-query-log.json, reconciliation.md, SHA256SUMS — all under /data/drive/tyche-raw/2026-11-19-observe-0455/mcp/
- research/: review-report.md, plans-draft.json, reviews-draft.json (reviewed_at 05:10, valid_until 06:10), events-draft.json (11 events), raw-quotes-spy-efa.json + raw-market-state.json (fetched 04:58), raw-kline-spy.json / raw-kline-efa.json (15 bars through Nov 18), raw-calendar-hot.json (04:59–05:02), news-extracts.json (pub times Nov 18 21:51:07Z – Nov 19 00:57:39Z)
- plan/: book.json, market.json (observed_at 04:59:07), preview-LC-20261119-SPY-ADOPT-r1.json, preview-LC-20261119-EFA-ADOPT-r1.json (approved=false, submitted=false), tick-synthetic-observe.json (exit 1), tick-synthetic-replay.json (checked_at 04:59:30), risk-numbers.json, risk-report.md (~05:15), coordinator-config-caps.md (04:55–05:05)
- Journal (READ-ONLY): /data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl — 12 events, eod.reconcile 2026-11-18T21:11:13.022797Z
- Engine/config reads: /tmp/tyche-lifecycle-KXBWpbxx/src/tyche/{lifecycle,pipeline,risk,fees,config,market_calendar}.py, src/tyche/strategies/rotation.py, config/{risk.yaml,strategies/pb-001.yaml,universe.yaml}; /data/workspace/tyche/src/tyche/{config.py,strategies/rotation.py}, config/{risk.yaml,strategies/pb-001.yaml,universe.yaml,tactical.yaml}
- Shared state: /data/drive/tyche-raw/lifecycle (ABSENT), lifecycle-rehearsal-20261119-a/probe.json (03:50:32Z), /tmp/lifecycle-synthetic-0455/ (no files)

**AUDIT STATUS: DRAFT — NOT AN APPROVAL, NO EXECUTION AUTHORITY. Not executable: rollout hold. execution_enabled=false; hourly lifecycle monitoring deployed; orders unarmed. Account IDs masked ([REDACTED]). Reviewed at coordinator clock 2026-11-19 05:14 UTC.**