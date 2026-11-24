# Tyche read-only broker reconciliation — 2026-11-19 observe run (04:55/04:59 UTC)

Mode: OBSERVE ONLY. No broker writes, no reserve/receipt/approve/revoke, no tick --record, no config/schedule changes, no Telegram. execution_enabled=false hold remains. Preview only; not armed. Hourly lifecycle monitoring deployed; orders unarmed.

Clock at reads: 2026-11-19 04:59–05:00 UTC = 2026-11-18 23:59 ET. Market CLOSED (SPY/EFA market_state=AFTER_HOURS_END, time_date=20261118). Next scheduled hourly run 2026-11-19 13:05 UTC per coordinator.

## 1. Account verification
- TYCHE_ALLOWED_ACCOUNT_IDS: single entry, masked [REDACTED]; exact match to challenge account verified programmatically (no full ID printed).
- sim_trade_account_list: challenge account [REDACTED] "Moomoo x Qoder AI Paper Trading Agent Challenge", account_type=2, market_id=100 (US paper margin). Selected; no drill/personal account used (other US paper margin acct ***748 and futures/HK/SG/JP/KR accounts ignored).
- Repos: ordinary /data/workspace/tyche HEAD b9ced85d9c123ea30e1041a02bcce943ee3ac66f (contains tested 7288d68; unmodified). LC_ROOT /tmp/tyche-lifecycle-KXBWpbxx HEAD 1e902cf57c26599b69c49496e81b7a493ae5bc49 (exact pin match).

## 2. Cash / NAV (cash.json, read 04:59:19–04:59:27Z)
| field | value |
|---|---|
| balance (cash) | 65,244.61 |
| hold / frozen | 0.00 |
| long_mv | 34,682.52 |
| short_mv | 0.00 |
| total_asset (NAV) | 99,927.13 |

NAV = balance + long_mv = 99,927.13 exactly. Frozen cash is zero; NAV includes it by definition.

## 3. Positions (positions.json, same read window) — NAV = 99,927.13
| symbol | qty | qty_avbl | buy_avg/cost | cur_price | market value | unrealized P&L | %NAV |
|---|---|---|---|---|---|---|---|
| SPY | 28 | 28 | 731.54 | 730.20 | 20,445.60 | -37.52 (-0.183%) | 20.46% |
| EFA | 142 | 142 | 100.495 | 100.26 | 14,236.92 | -33.37 (-0.234%) | 14.25% |

Total holdings 34.71% NAV; cash 65.29% NAV. Both positions fully available (qty_avbl = qty; no pending sells).
Note: cur_price is the 2026-11-18 regular close (quote data_time 21:00:00Z). SPY after-hours 735.57 / overnight 734.59; EFA after-hours 100.26. Broker NAV marks at regular close, so overnight gains are not in total_asset.

Unsupported exposure: NONE. No options, no shorts (short_mv=0, both pstn_type long), no fractional quantities, no unsupported instruments. Stock-only lifecycle engine can cover both holdings.

## 4. Order history — FULLY EXHAUSTED
Unfiltered first page returned ALL history: 3 orders, pagination.has_more=false, next_key="0" (orders-page-01.json, read 04:59:36–05:00:02Z). No orders exist before 2026-11-18 or on 2026-11-17/19. A windowed probe (epoch..2026-11-18T00:00Z) returned the same 3 orders despite the window — time-window params appear not honored server-side; anomaly logged in orders-query-log.json, completeness rests on the unfiltered has_more=false.

| order_id | symbol | side | qty | limit | status | cum_qty | avg_fill | created UTC | updated UTC |
|---|---|---|---|---|---|---|---|---|---|
| 3116580 | SPY | buy | 28 | 733.17 | 4 | 28 | 731.54 | 2026-11-18 17:44:56 | 2026-11-18 17:45:00 |
| 3116594 | EFA | buy | 142 | 101.45 | 4 | 142 | 100.495 | 2026-11-18 17:49:36 | 2026-11-18 17:49:45 |
| 3116597 | VNQ | buy | 83 | 94.98 | 5 | 0 | 0 | 2026-11-18 17:53:07 | 2026-11-19 01:01:00 |

All three: order_type=1 (limit), order_trade_time_type=1 (intraday/DAY), text "tyche 2026-11-18 rebalance ... plan f11456df". Orders show market=2 (US in order schema) vs account market_id=100 — normalization quirk noted, same account.

Status meanings from cross-evidence:
- Status 4 = FILLED FULLY (verified): cum_qty=qty, avg_fill_price equals position buy_avg_price exactly (731.54 / 100.495), positions exist with matching qty, cash reduced accordingly, journal order.submitted + eod.reconcile fills agree.
- Status 5 = exact broker semantics UNKNOWN (cancelled vs expired not distinguishable from available evidence). Per desk policy status 5 is NOT proven canceled/expired. What IS proven for 3116597: zero fills (cum_qty=0, avg_fill_price=0), no VNQ position, hold=0 (funds released), update at 2026-11-19 01:01:00Z. No pending exposure remains.

VNQ resolution: EOD journal (21:11:13Z) recorded it resting unfilled (then status 2, cum_qty 0) with frozen 7,884.33 (83 x 94.98 = 7,883.34 + ~0.99 implied fee). It never filled. Between EOD and the 03:02Z capture the DAY order left the book (update_time 2026-11-19 01:01:00Z, consistent with post-close day-order expiry processing) and the freeze was released: EOD cash 57,360.28 + frozen 7,884.33 = 65,244.61 = current balance exactly. No cancel/modify was performed by the desk (journal confirms). Terminal label: unfilled, no longer resting, funds released; canceled-vs-expired = UNKNOWN.

Cash reconciliation: 100,000.00 start − SPY 20,483.12 − EFA 14,270.29 − fees 1.98 (eod.reconcile fees_implied) = 65,244.61 ✓ residual 0.00.

## 5. NAV references (authoritative journal, READ-ONLY)
/data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl: 12 events; prev_hash chain verified AND all 12 event hashes recomputed (sha256, compact sorted-keys canonical body) — intact. Last hash 5df92f3dcae0d59f4e5d50e64b148cd8138fce69f23c1d525a4628a9c75499c3 (matches expected). No later descendant found; no appends made.
eod.reconcile @ 2026-11-18T21:11:13.022797Z: prior_close_nav = 99,914.93; high_water_nav = 100,000.00; nav 99,914.93; reconcile_ok=true, residual 0.0 — verified as expected.

Drift: fresh NAV 99,927.13 vs prior close +12.20 (+0.0122%); vs high water −72.87 (−0.0729%). Drawdown well inside 4% soft / 6% hard limits. (EOD NAV included frozen 7,884.33 + then-current marks; freeze release is NAV-neutral; +12.20 is mark movement between EOD marks and regular close.)

## 6. Shared-state inspection (read-only)
- /data/drive/tyche-raw/lifecycle: DOES NOT EXIST — no production lifecycle ledger. Coverage blocker for lifecycle activation stands; nothing created.
- lifecycle-rehearsal-20261119-a/: probe.json (written_at_utc 2026-11-19T03:50:32.579332Z, git_head 1e902cf5… exact pin, nonce + code_hash present); owner.lock/ exists as an EMPTY directory (no owner metadata inside). No grants, reservations, latches, ledger, or active-run files. Not touched.
- rollout-20261119/: state-probe.json (2026-11-19T02:58:05.511712Z, nonsecret nonce, pid 1552); mcp/ captures 02:59–03:01Z (accounts/cash/positions/market-state/orders pages 01–03 + query log; its cash.json already showed hold=0, balance 65,244.61 — consistent with this run); post-template-verification/ NVDA option template artifacts 03:58–03:59Z (chain-US.NVDA-20261127, quotes/books for NVDA and NVDA261127C150000, market-state, SHA256SUMS) — template verification only, NOT a broker execution validation, no NVDA position or order on the challenge account.
- Concurrency: newest artifact anywhere inspected is 03:59Z (~1h before this run); no grants/owners/reservations/latches or active-run evidence; no concurrent session appears active. rclone FUSE directory mtimes all show mount-time 05:00 and are NOT write evidence. Drive durability/distributed exclusion remains unproven — single durable writer across both lanes is still an activation requirement.

## 7. Feed health / caveats
- All MCP reads ret_code=0; no failures.
- Quotes/books are at regular close (data_time 2026-11-18T21:00:00Z); age >60s kernel freshness limits — irrelevant for entries because market CLOSED and execution disabled; no RTH submission possible or attempted.
- No order book fetched (market closed; not needed for reconciliation). No option chain needed (no option exposure).
- No protection orders are broker-native; holdings currently have NO resting broker stops/targets. Lifecycle contracts for SPY/EFA are not complete approved grants in this run — retained-exit coverage remains a gap to surface at the next hourly check.

## 8. Artifacts (this dir: /data/drive/tyche-raw/2026-11-19-observe-0455/mcp/)
accounts.json, cash.json, positions.json, market-state.json, quotes.json, orders-page-01.json, orders-page-02-window-check.json, query-log.json, orders-query-log.json, reconciliation.md, SHA256SUMS.
Actual read windows (UTC): accounts 04:59:07–04:59:19; cash+positions 04:59:19–04:59:27; market-state 04:59:27–04:59:33; quotes 04:59:33–04:59:36; orders p1 04:59:36–05:00:02; orders window-check 05:00:02–05:00:11 (all 2026-11-19).