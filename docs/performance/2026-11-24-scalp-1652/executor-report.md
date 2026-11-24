# PB-004 scalp-1652 executor report (2026-11-24)

SCALP RUN end: 17:01:24Z completed (hard stop 17:02:00Z met).

Clocks: start 16:53:23Z; bars/quotes read 16:53:30-16:53:50Z; books 16:53:48Z;
accounts+history 16:56:5xZ; cash+positions 16:59:0xZ (trio, oldest 16:59);
cycle 17:01:03Z; post-history 17:01:1xZ; verify 17:01:24Z.

Account: challenge paper US margin account (id masked, ...2598), account_type 2, market_id 100.
Cash/NAV at capture: total_asset 98,831.144, flat (positions qty=0, MV 0) — broker truth,
consistent with prior healthy reads.

Feed health: all 14 reads ret_code=0. Bars (1-min x30) x5, books x5 (two-sided, NASDAQ+ARCA,
5 levels), quotes x5, accounts, cash, positions, history (single page, has_more=false).
No outage, nothing quarantined. sim_trade_order_list unregistered (see mcp-anomaly/README.txt).

Fills-first: no-op. No new tyche-scl orders in history; all 7 Nov-19 incident orders already
journaled; SMH 3118500 and VNQ 3116597 status-5 closed per operator ruling — not re-journaled.

Cycle (tyche tactical scalp --record, exit 0): as_of 2026-11-24T17:01:03.177850+00:00.
Decisions: NVDA/AMD/AVGO/MU/SMH all "wait — entry quote missing/stale" (known +31.5M s epoch
offset makes the <60s quote gate unsatisfiable; timestamps not adjusted).
orders=[] requests=[] skipped=[] denied=[] alerts=[] submitted=false.
This is the honest outcome; no recapture (failure was the systemic offset, not capture latency).

Submits: none. No broker writes made this run.

Post-check: history re-read identical to pre-run — zero new orders, zero fills, account flat.
Ledger: 90 events, chain intact, sha256 b50430ad854eb75de9f1cb75e7c2f03562528b8d5a7ec100e0e07bff93104a21
(unchanged from brief baseline; no concurrent-run drift observed).

Artifacts: /data/drive/tyche-raw/2026-11-24-scalp-1652/ (bars-*.json, book-*.json, quotes.json,
accounts.json, cash.json, positions.json, orders.json, orders-history-post.json, cycle.json,
mcp-anomaly/README.txt).
