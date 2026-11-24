# PB-004 SCALP FIRE scalp-1637 — Executor Report (PAPER)

SCALP RUN end: time limit (hard stop 16:47:00Z; flow completed 16:45:59Z, zero submits).

## Clock timings (UTC)
- 16:38:26 session start (desk verified 16:37:52 at gates); first feed read (bars) 16:38:40.
- 16:41:52 books round; 16:43:33 quotes+account trio+history round.
- 16:45:08 fills-first check complete; stale-feed condition identified.
- 16:45:30 ONE recapture of quotes (permitted single retry); 16:45:41 cycle run; 16:45:42 cycle exit 0.
- 16:45:54 post-history re-read + journal verify. All work finished before the 16:47:00 hard stop.

## Run directory
/data/drive/tyche-raw/2026-11-24-scalp-1637/ (feed dir = run dir)

## Account reconciliation (business id masked ****2598, US margin paper, market 100, account_type 2)
- Cash/total asset: 98,831.144 USD; frozen/hold 0; max buying power long 197,662.288.
- Positions: SPY/MSFT/EFA all qty 0 (flat). No open lots in the five scalp symbols; no open tyche-scl lot.
- History: sim_trade_history_order_list, unfiltered, single page, pagination.has_more=false (14 orders). sim_trade_order_list remains UNREGISTERED in executor MCP — noted in mcp-anomaly/README.txt.
- Ledger journal: 90 events, chain intact (`tyche journal-verify` OK). sha256 b50430ad854eb75de9f1cb75e7c2f03562528b8d5a7ec100e0e07bff93104a21.

## Feed health
- Bars: 1-min x30, all five symbols ret_code 0.
- Books: all five two-sided (NASDAQ+ARCA), top-of-book NVDA 150.62/150.65, AMD 398.61/398.70, AVGO 299.52/299.68, MU 622.94/623.28, SMH 418.85/418.99 — spreads <0.05%; no gateway truncation seen this fire.
- Quotes: all five ret_code 0, sec_status NORMAL, no suspensions.
- Trio (accounts/cash/positions) healthy, ret_code 0, mutually corroborating (flat + full cash + today's exits filled).
- NAV refs used as directed: prior_close_nav 99,380.951; high_water_nav 100,000.0. Cash/NAV ≈ 99.45%, drawdown vs HWM ≈ 1.17% (inside 4% soft limit).

## Fills-first actions
- Broker tyche-scl request ids in history: 5388f21a, 79bbee16, a0ff23cd, a4619198, ad9d8115, bb75c14b, e0956d36 — ALL seven already present in the journal. No new fills to journal.
- scalp-1622 window (~16:22-16:29Z): broker history shows NO orders beyond the Nov-19 incident set and the three tyche-exit orders — nothing missing receipts, nothing journaled.
- SMH 3118500 and VNQ 3116597 (status 5, zero fill): per operator ruling 2026-11-24 treated as CLOSED — not journaled further, not blocking.
- No writes made to the journal this run (correct: nothing broker-shows was journal-lacks).

## Cycle decisions (tyche tactical scalp --record, exit 0)
- as_of 2026-11-24T16:45:42Z. orders: [] — ZERO requests, zero skips/denials, submitted=false, alerts: [].
- Decisions: all five (NVDA/AMD/AVGO/MU/SMH) = wait, reason "entry quote missing/stale".
- Root cause: the known broker epoch offset (~+31.5M s) makes feed data_time stamps sit ~40 min ahead of the real UTC clock; under the <60s freshness rule every quote evaluates stale regardless of recapture. Recapturing cannot cure it — same structural result as fires 1-7 today. No submission was possible or attempted.
- Derived snapshot files written by the kernel: tactical-account.json, tactical-quotes.json.

## Submits
- None. Zero-order outcome; envelope untouched (0 of max_orders 200 used this fire).

## Artifact hashes (sha256, first 16)
- cycle-output.json 47ab62fc553ec02d
- orders.json 786f568c92ded698 (orders-history-post.json byte-identical merge, dedup order_id, 14 ids)
- quotes.json 863b9cd1dfd2fce7 (final = 16:45:30Z recapture)
- tactical-quotes.json f6c3b6bd36f1a3b2

## Protection gaps / risks
- No held lots => no resting protection needed; flat account is fully protected by construction.
- Feed-staleness blocker is systemic (broker clock epoch offset), not a transient outage: fires will keep producing zero-order wait outcomes until the kernel or desk compensates for the offset. Recommend desk route this finding to tooling; no executor action can resolve it under verbatim-capture discipline.

Final ledger: 90 events, chain intact, sha256 b50430ad...104a21 (unchanged this fire). scalp-lock.json left in place (desk owns).
