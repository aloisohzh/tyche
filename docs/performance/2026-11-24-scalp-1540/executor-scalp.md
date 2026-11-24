# PB-004 Scalp Fire — executor-scalp.md
Run: /data/drive/tyche-raw/2026-11-24-scalp-1540 | Lane: US.NVDA US.AMD US.AVGO US.MU US.SMH | Account: ***598 (US margin paper, market_id 100, account_type 2) | Clock: delegation 2026-11-24T15:39:09Z (10:39 ET, RTH midday)

## Verdict
Zero requests, zero submits, zero broker writes this fire. Flat and clean. No second writer detected.

## STEP 0 — Health probe (15:39:40Z)
- Ledger restored and verified: 81 events, chain intact, sha256 f90ca1b390172e1bf853d1e97c6aa9895e1ac4c19a12459dad20eea3c287e13e (matches brief).
- cash: ret_code 0, total_asset/balance 98831.144, mv 0, max_power_long 197662.288.
- positions: 3 rows, all qty 0 (SPY 714.51 / EFA 98.45 / MSFT 494.775 cur prices).
- history: 14 rows, pagination.has_more=false. Healthy — full pipeline authorized. The 15:35Z outage did NOT recur.

## STEP 1 — Capture
- Bars (ktype=1, num=30, x5): read 15:40:09–15:41:14Z; last closes: NVDA 153.125, AMD 406.37, AVGO 303.16, MU 632.5, SMH 425.72 (bars mtime 15:40:09–15:41:14).
- Round A books (~15:41:4x) and a fresh trio/quotes batch (~15:42:18–20Z) were read but only partially persisted; payloads were lost to session context compaction. No fabrication — all gate-relevant files were re-read.
- Final batch: quotes/trio/history read ~15:44:11Z (quotes data_time 1795535050637–1795535051001; last_price NVDA 152.39, AMD 403.99, AVGO 302.2, MU 626.98, SMH 423.69). Default-depth book responses arrived gateway-truncated (unusable); books re-read at num=5, exchange stamps 1795535070239–1795535071802 (~15:44:30Z). Files written verbatim 15:45:00–04Z.
- Gate status at cycle (15:45:09.76Z): trio mtime age <=10s (<=120s OK); quote age ~58s and book age ~40s (<=120s kernel OK, within brief's fresh window at cycle); bars age ~4.5 min (breakout lookback input, no age gate).
- orders.json = verbatim single fully-paginated history read (14 rows, has_more=false).

## STEP 2 — Fills-first (15:45:05Z)
Broker tyche-scl* set = the 7 Nov-19 incident orders, all already reconciled in the ledger. Nothing new to journal. SMH 3118500 (tyche-scl-bb75c14b…) remains status5 / cum_qty 0 — unresolved, never filled; no retry, no cancel per protocol. Desk exit orders 3124584-86 (tyche-exit-*, SPY/EFA/MSFT) are another lane — untouched.

## STEP 3 — Cycle (rc=0, as_of 2026-11-24T15:45:09.755Z)
| symbol | action | reason |
|---|---|---|
| US.NVDA | wait | no 5-bar breakout |
| US.AMD | wait | no 5-bar breakout |
| US.AVGO | wait | no 5-bar breakout |
| US.MU | wait | no 5-bar breakout |
| US.SMH | wait | no 5-bar breakout |
No open lots (flat) -> no exits. requests: none. alerts: none. No arm path -> envelope untouched, journal unmodified.

## STEP 4 — Submits
None (zero requests). No sim_trade_input_order calls.

## STEP 5 — Post
- Post-run history read 15:45:3xZ: byte-identical to pre-run (14 rows, has_more=false) -> no fills, no new orders, no second writer.
- Ledger after run: journal-verify OK, 81 events, sha f90ca1b3…c13e (unchanged — correct, nothing was armed or submitted).
- Exposure: flat (all positions qty 0). No open tyche-scl lot near 20:50Z flatten. Standing unresolved item: SMH buy 3118500 status5, cum 0 — carried as coverage gap, not an active lot.

## Anomalies (see mcp-anomaly/README.txt)
1. sim_trade_order_list unregistered — 5th consecutive fire; reconciliation via history list only.
2. Intermittent gateway truncation on default-depth order_book reads this fire (mitigated via num=5 re-read; truncated data never persisted).
3. Context-compaction payload loss forced one extra recapture round (documented; verbatim discipline maintained).

## Artifact hashes (sha256, first 16)
quotes.json 5d31cb0220784161 | accounts.json 4450619f512cc8f7 | cash.json c8d6dfc9c04432f8 | positions.json 368f8597ef6a6797 | orders.json=orders-history.raw.json=orders-history-post.json 86ac4a159149862c | cycle.json c29d0a5df861bb11 | cycle.err e3b0c44298fc1c14 (empty) | bars US.NVDA f2f4e70313ecda58 / US.AMD 15ec25ff69604ed1 / US.AVGO 477656755e56f1db / US.MU 1bb2d2279d2477f2 / US.SMH 7d05fe0a8e863719 | books US.NVDA 4a791ce1629c53f3 / US.AMD 433e3c4aa5e9c788 / US.AVGO 9a3c1f71c53d80fa / US.MU 60f9180977f58a78 / US.SMH 1225f275b89755b5
