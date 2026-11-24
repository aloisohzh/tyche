# TYCHE CLOSE-FIRE READ-ONLY RECONCILE — Executor report
Run: 2026-11-20-close-2005 | Clock at delegation 20:07:40Z (15:07 ET, closing_drive, regular close 16:00 ET / 21:00Z, full session)
Mode: STRICTLY READ-ONLY at broker. HALT ENGAGED (operator CLI, 2026-11-19T20:28:29Z, writer-safety incident). Production approvals=[], latched_exits={}. No reserve/submit/cancel/modify, no --record, no gate flips, no envelope writes, no journal append. Broker reads + dry-run engine only.

## 0. Env / provenance disclosure
- Repo: /data/workspace/tyche HEAD e53d0453235e318e7f3d9f3d6fe2b10c433f0097 (clean, tyche installed editable, src import verified).
- Session env `TYCHE_ALLOWED_ACCOUNT_IDS=[REDACTED]` provisions the ***4748 US Margin Paper account, NOT the challenge account. Every engine command this run used the session-scoped prefix `TYCHE_ALLOWED_ACCOUNT_IDS=[REDACTED]` (disclosed: lifecycle capture x3, lifecycle tick x3, tactical capture, tactical tick, tactical scalp). No file/config changes; injection only alters the effective process env. Tactical config_hash observed 160b7d96f5c2… (injected), matching the known injected-hash quirk.
- Pins verified: book-pin sha 02f781288ba113d3729cece98b7399821c4afbe56385be7d94927208fad243a6 (2 plans: SPY/EFA adopt rev2, daily_close stops 727.50 / 100.00); state-pin sha a7a9e994… verified BEFORE and AFTER all ticks (production state byte-identical; dry ticks made zero semantic changes). /data/drive/tyche-raw/lifecycle/ never touched.
- Journal (desk head owns it this run; NOT appended): 33 events; run.start 20:07:32Z and research.published 20:18:01Z are this run's desk-head events. Journal order.submitted events exist only for the 3 Nov-18 rebalance orders; zero journal receipts for the 8 Nov-19 unattributed orders (consistent with the halt reason).

## 1. Account / NAV / drawdown (challenge account ***598, type 2, market 100)
Reads at ~20:09:05Z / 20:14:50Z / 20:15:55Z / 20:21Z (all persisted):
| observed | cash | frozen (hold) | MV | NAV total_asset | DD vs HWM 102,208.99 |
|---|---|---|---|---|---|
| 20:09:05Z | 45,680.12 | 0.00 | 52,047.66 | 97,727.78 | -4.384% |
| 20:14:50Z | 45,680.12 | 0.00 | 52,089.45 | 97,769.57 | -4.343% |
| 20:15:55Z | 45,680.12 | 0.00 | 52,108.24 | 97,788.36 | -4.325% |
| 20:19Z (tactical) | 45,680.12 | 0.00 | 52,094.78 | 97,774.90 | -4.338% |
| 20:21Z (scalp) | 45,680.12 | 0.00 | 52,085.23 | 97,765.35 | -4.348% |

- **SOFT DD BREACHED**: threshold 98,120.63 (-4%); NAV below it on every read today (hard floor 96,076.45 NOT breached).
- vs prior_close_nav 99,914.93: -2.15% (daily-loss limit 2.5% NOT breached).
- Cash 45,680.12 matches reference. Frozen 0 — note: the two status-5 orders show NO frozen funds despite 11.27M notional submitted (VNQ 83@94.98) and 4.5M (SMH 10@454.48).

## 2. Positions (all pstn_type 0, qty_avbl = qty → fully sellable)
| lot | qty | avg/cost | cur (final 20:21Z) | MV | vs stop |
|---|---|---|---|---|---|
| SPY | 28 | 731.54 | 693.98 | 19,431.44 | -5.16% cost; 3.91% below daily_close stop 727.50 |
| EFA | 142 | 100.495 | 96.455 | 13,696.61 | -4.02% cost; 3.54% below daily_close stop 100.00 |
| MSFT | 39 | 503.33 | 486.07 | 18,956.73 | **UNOWNED** — no lifecycle grant, no adoption approval |

## 3. Order history — ownership verdict: NO NEW-WRITER INCIDENT SINCE 18:15:21Z BOUNDARY
Full unfiltered pagination fetched (single page, 11 orders, top-level `pagination.has_more:false` — persisted mcp/orders-1.json).
- Latest broker order ever: **3118578 MSFT buy 39 @503.35, create 2026-11-19T18:15:16Z** — inside the delegated boundary (18:15:21Z). The 8 incident orders 3118496–3118536 (17:23:59–17:48:49Z) + 3118578 (18:15:16Z) are ALL pre-existing. **Zero orders created after the boundary → no new writer today.**
- Zero live/pending orders: no status 0/1/2/3 rows; the only non-filled rows are the two status-5 (below).
- Delegation expectation "zero sell orders ever" is INACCURATE: 4 sell orders exist (NVDA 33 @150.112 3118508, AMD 10 @487.615 3118534, MU 7 @702.74 3118536 — all status4, Nov-19 tyche-scl round-trips). They round-trip the Nov-19 scalp buys; those symbols have no positions today, consistent.
- Status-5 UNRESOLVED flags re-verified from raw rows (still status5, cum_qty 0, no funds frozen): VNQ 3116597 (83 @94.98, created 11-18T17:53Z, updated 11-18T20:21Z, raw text "tyche 2026-11-18 rebalance 11% VNQ, plan f11456df") and SMH 3118500 (10 @454.48, created 11-19T17:25:10Z, text tyche-scl-…, updated 17:27:07Z). Status 5 NOT treated as terminal.

## 4. Quotes / books (verbatim, mcp/)
RTH AFTERNOON open, section 1795185000–1795208400 (21:00Z close), all sec_status NORMAL, no suspension. data_time 1795205435–1795205440s (~20:10:40Z), books ~20:12:00Z; final scalp batch 20:21Z. Lasts: SPY 693.51→694.19, EFA 96.375→96.44, MSFT 486.26→486.43. SPY two-sided spreads ~0.005%; EFA/MSFT <0.05%. Pre/post/overnight sub-objects retained in payloads. Note quotes show NVDA -12.3%, AMD -12.8%, MU -14.1%, SMH -10.0% intraday vs prev close — severe semis tape consistent with SPX risk-off.

## 5. Lifecycle engine (isolated copies under state-tick/, pinned engine, dry ticks, no --record)
Production-condition tick (state = PINNED state-pin copy, approvals=[]; market captured 20:15:16Z & 20:16:40Z):
- US.SPY LC-20261119-SPY-ADOPT-r2 → action **review**, "held position has no approved lifecycle ownership", authorized=false, warning "research review expired or future-dated".
- US.EFA LC-20261119-EFA-ADOPT-r2 → same review verdict.
- Gap: "US.MSFT: held position missing a complete lifecycle plan".
- Post-tick state copy byte-identical to pin; no latches, no writes.

Would-exit evidence: completed daily bars (quote_cur_kline, persisted): SPY Nov-19 close **715.87 < stop 727.50**, Nov-20 interim 694.53 (unfinal, 21:00Z pending); EFA Nov-19 close **98.78 < stop 100.00**, Nov-20 interim 96.45. Both daily_close stops ALREADY breached on the completed Nov-19 bar; current quotes sit far below the levels. Today's (Nov-20) daily-close re-evaluation is evidence-unavailable until 21:00Z — correct behavior, not a fabrication.

DIAGNOSTIC tick (state-tick/state.diag.json, synthetic approvals labeled **DIAGNOSTIC-NOT-APPROVED**, run-dir only; NOT production, NOT authorization): SPY → **sell 28 @ limit 691.97, reason stop_loss**; EFA → **sell 142 @ 96.15, reason stop_loss** (limits = last minus 30bps slippage ceiling, quantized). MSFT: no plan → no engine exit path at all.

**PROTECTION GAP (material): all three lots are UNCOVERED right now.** No live exit orders, production approvals empty, halt engaged, MSFT has no plan. If operator wants the SPY/EFA stop exits, that requires fresh exact-order audit + lifecycle grant + reserve under separately approved un-halt; nothing is authorized by this report.

## 6. Tactical lane (dry, no --record)
`tactical tick` (book = run watchlist-pin entries=[], fresh 8-symbol batch ~20:16Z, journal verified chain): phase **closing_drive**, orders [], decisions []; alerts verbatim:
- "monitor starting or heartbeat gap; rebuild entry confirmations"
- "unprotected tactical positions: US.MSFT; block new entries"
No entries proposed — consistent with research (no genuine same-session edge; expired Nov-19 watchlist not reused).

`scalp` PB-004 dry (feed scalpdry/: accounts/cash/positions/quotes/books + 370x 1-min bars for NVDA/AMD/AVGO/MU/SMH from live MCP at ~20:18–20:21Z; envelope {} read-only): all five symbols → **wait, "no 5-bar breakout"**; orders [], alerts [], submitted=false. No missing-feed waits.

## 7. Blockers / staleness
- Halt engaged; all protection decisions deferred to operator. Soft-DD breach active (-4.3% vs HWM) but no engine exit is executable under halt without operator disposition.
- Two status-5 orders (VNQ 3116597, SMH 3118500) remain unresolved; frozen funds 0 despite submitted notionals — flag for broker-semantics review, DO NOT assume canceled.
- MSFT 39 unowned: no lifecycle plan/grant exists; protection gap persists.
- Nov-20 daily-close stop evaluation for SPY/EFA blocked until completed bar exists (21:00Z) — expected.
- Journal research.published 20:18:01Z (+1 event vs delegation's 32) is desk-head provenance, not an executor write.

## 8. Artifact inventory (run dir /data/drive/tyche-raw/2026-11-20-close-2005)
sha256 (key captures):
- mcp/accounts.json 0266474284bad5133a76fdd04fbde49706e12ec4112fb5da2c6de6a74722c8dc (ids verbatim; reporting mask in mcp/accounts.masked.json)
- mcp/cash.json 02731ed20a265dcb0cd5799bfa0d21ac6b87f4e449348373278e2f1aa2f426ba
- mcp/positions.json 9b2186a6cb9a749a13716ff990ca196674692286a9c6ab6becb6dbc39ab42d92
- mcp/orders-1.json b21265cad7e8114803a8bf3496d7d0360fb086f2a257d15100d14b699e42dbb1 (has_more=false at top level per raw MCP shape)
- mcp/quotes.json 7128ec3e9e1edfc88fc153881619d47c51ca257a3a1378205eb6aa262a428b84; later batches cash-2/3, positions-2/3, quotes-2/3 in mcp/
- mcp/book-US.SPY.json 2eb3142f…, book-US.EFA.json 1e5de918…, book-US.MSFT.json b65629aa…, mcp/market-state.json 1420f09e…
- mcp/kline-daily-US.SPY.json a031818a…, kline-daily-US.EFA.json d3a09205…
- capture/{accounts,cash,positions,orders-1,quotes,closes}.json; closes.json 3d88ee75… (Nov-19 official bars; Nov-20 intentionally absent)
- state-tick/market-US.json 0582b1f1…, market-US3.json a9c0c110…, book.json (pin copy), state.pre.json/state.json/state2.json (== pin, verified identical), state.diag.json 7298d3e2… (DIAGNOSTIC-NOT-APPROVED)
- tacfeed/ (8 books + batch + tactical-account.json cb1504b6…, tactical-quotes.json 33db76af…)
- scalpdry/ (bars-US.*.json copied byte-verbatim from live MCP tool outputs mcp_afa0d1124cf478a569f9d65d / mcp_167d846221f441be70639f45 / mcp_3c0006de19f18a75a9897f34 / mcp_55455e5b63d77d7c4433095d / mcp_68bd6454982f2d11eb4a1932, envelope.json ca3d163b…)
- Production paths untouched: state/*-pin.json unmodified; /data/drive/tyche-raw/lifecycle not opened; journal not appended; no Telegram sent.

Executor: tyche-executor, read-only close-fire run, 2026-11-20 20:07–20:24Z.
