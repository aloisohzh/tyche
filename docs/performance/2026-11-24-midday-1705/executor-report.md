# Executor report — MIDDAY PROTECTION FIRE 2026-11-24 17:05Z (READ-ONLY)

Run dir: /data/drive/tyche-raw/2026-11-24-midday-1705
Executor delegation completed with ZERO broker writes: no submits, reservations, cancels, modifies, no --record, no journal/state writes. Journal verified at 95 events, chain intact; production lifecycle state untouched (isolated-copy tick, hash unchanged a7a9e99496ffc4f9b6c1c2819e2ace95a3b8de421fe5f34b4238d7bd293f0d58).

## 1. Account reconciliation (US paper, alias tail …598, market_id 100, account_type 2)
- Cash/NAV reads: 17:07:25Z and ~17:12:05Z — balance 98,831.144 / total_asset 98,831.144 / mv 0 / hold 0. Flat-account hypothesis CONFIRMED: cash = NAV = 98,831.144 < prior_close_nav 99,380.951 < high_water_nav 100,000.
- Positions: all qty 0 (3 zero-qty residue rows US.SPY / US.EFA / US.MSFT). No open lots -> no live-exit gaps, no protection gaps.
- Order history: 1 page, pagination.has_more=false, 14 rows verbatim (mcp/orders.json, hash 44600259e10e…). Newest order ever = 3124586 (create epoch 1795525966000000). Morning operator exits 3124584/85/86 (SPY/EFA/MSFT sells) confirmed status4 full cumulative — closed, not re-reported as open. Journal's three tyche-exit-* requests (13:11-13:12Z) all map to those filled status4 orders: NO approved exit with passed window lacking a live broker request.
- Historical status5 cum0: SMH 3118500, VNQ 3116597 — operator ruled CLOSED 2026-11-24 (prior-fire memory); no retry/cancel/journal action taken.
- Nov-19 PB-004 scalp lots: fully round-tripped (buys 3118496-98 / sells 3118508/34/36 all status4). NO scalp lots remain open.

## 2. Feed health
- Market state (17:08:40Z): all symbols AFTERNOON (regular full session), traded_seconds 9492. Not an early close today.
- Broker epoch offset ~+31.5M s persists in every data_time field; captured verbatim, never adjusted. Consequence: normalized quote "at" values are future-dated, so quote-freshness gates reject them (see scalps/tactical waits).
- Holdings+watchlist quotes/books: batch1 17:08-17:09Z, batch2 17:11:55Z (used for lifecycle/tactical chains), batch3 17:16:30-17:16:42Z (6 symbols incl JNJ + paired 5-level books NASDAQ/ARCA two-sided). Books two-sided and ordered; no one-sided books. No options in account -> no chains/contracts.json required.
- Oldest actual MCP read: 2026-11-24T17:07:20Z (accounts list). Full read map: mcp/read-manifest.json.
- Watchlist last prices: KO 98.06 (zone 96.2-96.5), PG 172.85 (zone 170.2-170.6) — both ABOVE their buy zones. JNJ dropped from watchlist (275.945 vs zone 269.8-271.2, also above).

## 3. Ownership check
- Expected second writer (PB-004 scalp card) fired at 2026-11-24T17:07:19Z — scalp-lock.json run_id scalp-20261124T1707Z, run dir 2026-11-24-scalp-1707/ with fresh trio exists. Ownership NOT violated; this midday read-only fire coexisted as briefed. No execution-state writes were made by either writer during this run.

## 4. Dry-run lane results (all RC=0, no --record, no submits)
### Lifecycle (stock/ETF) — state/lifecycle-tick.json (4d1335280d18…), checked_at 2026-11-24T17:13:20Z
- Coverage gaps: []. would-exit: none (no positions). Breaches: none.
- US.SPY LC-20261119-SPY-ADOPT-r2: authorized=false, qty=0 — "adoption plan cannot open a new position" (warn: research review expired or future-dated).
- US.EFA r2: same adoption block. US.AAPL PB-007: "entry expired or lifecycle invalidated".

### Tactical (PB-002/003) — state/tactical-tick.json (c649928e6e9f…), as_of 2026-11-24T17:15:21Z, phase midday, config_hash dd87c7da414e2af1d67c63d6eb3cb68fc5447deda3276dcc279d43e6a1c34dd6
- Orders: []; submitted=false. No resting/cancel_first/protective items (no lots, no working orders).
- TL-20261124-KO-DEF2: wait — "awaiting distinct fresh quote confirmations" (price above zone anyway).
- TL-20261124-PG-DEF2: wait — same.
- TL-20261124-JNJ-DEF1: wait — "watchlist stale/inactive/invalidated or protection coverage incomplete" (JNJ dropped from watchlist).
- Alert: "monitor starting or heartbeat gap; rebuild entry confirmations".
- PB-003 KO option proposal remains NOT submitted (triple-blocked at 16:04 run; unchanged).

### Scalp PB-004 — state/scalp-tick.json (50af73b7c4f6…), as_of 2026-11-24T17:24:41Z
- Orders: []; submitted=false; no exit decisions (flat). All five symbols (NVDA/AMD/AVGO/MU/SMH): wait — "entry quote missing/stale". Root cause: broker epoch offset makes quote timestamps future-dated, failing the 0 <= now-at freshness check — identical refusal class as scalp-1652. Not worked around, reported as-is.

## 5. Breach scan vs fresh quotes
- Daily-loss 2.5%: NAV 98,831.144 vs prior_close 99,380.951 → -0.553% — within limit, no breach.
- Soft/hard drawdown 4%/6% vs high_water 100,000 → -1.169% — no breach.
- Gross 0%, cash 100% — all caps respected. Order counts: 0 today vs 40/200 caps.

## 6. Artifacts
- mcp/ (batch1+2 raw, verbatim): orders.json 44600259…, book-US.*.json (5), bars-US.*.json (4), read-manifest.json
- mcp2/ (batch3): quotes.json 59d328c0…, 6 book files
- tac/ (tactical staging + normalized tactical-account.json / tactical-quotes.json)
- scalpfeed/ + scalpwork/ (scalp raw feed: quotes, 5 books, 5 bars-*.json each 60 klines, trio written last, orders.json; work copy isolated from production)
- state/: lifecycle-tick.json 4d133528…, tactical-tick.json c649928e…, scalp-tick.json 50af73b7…, market-US.json c6c68ad5…, state-isolated.json a7a9e994… (= production, unchanged)
- run root: snapshot.json daaeaff2…, orders.json 44600259…, positions.json e88a19ae…, quotes.json 59d328c0…

## 7. Validation failures / caveats
- First lifecycle tick refused ("broker snapshot stale or future-dated; fetch again") at ~17:13 due to expired 120s window from 17:07 reads; resolved by legitimate fresh re-read + chained capture→tick, not a workaround.
- First tactical tick refused KO/PG on stale books; resolved by paired fresh quote+book batch.
- Scalp quote staleness (epoch offset) is a known unresolved feed quirk — entries cannot fire this session; protection unaffected (flat).
- sim_trade_order_list remains unregistered; history API used unfiltered with explicit has_more=false.
- Memory index references project_tyche_resting_orders_64.md (resting DAY orders, config re-hash 58a3ce686238) but that file is absent on disk. If resting-order deployment is real, nothing in this fire touched it; config_hash here is still dd87c7da….
