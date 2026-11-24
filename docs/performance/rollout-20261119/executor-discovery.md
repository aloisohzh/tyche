# Executor Discovery — rollout-20261119 (READ-ONLY, deployment verification)

- Agent: tyche-executor (Executor, tyche-desk)
- Run date: 2026-11-19 UTC; delegation clock 02:58 UTC; queries executed ~03:00 UTC
- Mode: read-only broker discovery. ZERO broker writes performed: no submit/cancel/modify, no lifecycle/reserve/approval actions, no journal writes, no git operations, no Telegram. `execution_enabled` untouched (stays FALSE).
- Raw captures: this directory's `mcp/` folder ONLY (never in the git repo). Account masked as `...598` in this report; full id appears only in raw capture files.

## 1. Account validation — PASS

Source: `mcp/accounts.json` (sim_trade_account_list, verbatim).

- 8 paper accounts returned. Challenge account `...598` ("Moomoo x Qoder AI Paper Trading Agent Challenge"):
  - `account_type: 2` (in {1,2}) — PASS
  - `market_id: 100` — PASS
  - env: paper (sim_trade account list; challenge paper account) — PASS
  - Allowlist: env `TYCHE_ALLOWED_ACCOUNT_IDS` contains exactly 1 entry; challenge account id matches it — PASS (checked programmatically without echoing the env value).
- Note: a second US market_id=100 account exists (`...748`, "US Margin Account [Paper Trading]", type 1). It is NOT the allowlisted challenge account and was not queried.

## 2. Cash / NAV

Source: `mcp/cash.json` (sim_trade_cash_info, verbatim).

| Field | Value |
|---|---|
| balance (cash) | 65,244.61 |
| hold (frozen) | 0 |
| mv / long_mv | 34,682.52 |
| short_mv | 0 |
| total_asset (NAV) | 99,927.13 |
| max_power_long | 165,171.74 |
| realized_profit / unrealized_profit | null / null |

Frozen = 0 is consistent with the operator's observation that the VNQ cash freeze was released.

## 3. Positions — MATCH expectation

Source: `mcp/positions.json` (sim_trade_position_list, market 100, verbatim).

| Symbol | Qty | Qty avbl | Cost/buy avg | Cur price | MV | P&L |
|---|---|---|---|---|---|---|
| SPY | 28 | 28 | 731.54 | 730.2 | 20,445.60 | -37.52 |
| EFA | 142 | 142 | 100.495 | 100.26 | 14,236.92 | -33.37 |

- Exactly 2 positions, no option positions. Matches operator expectation (SPY 28, EFA 142, no options).
- Position ids: SPY 719425, EFA 719431. Both `pstn_type: 0`, `market: 100`.

## 4. Order inventory (complete) — 3 orders total

Sources: `mcp/orders-page-01.json` … `orders-page-03.json`, `mcp/orders-query-log.json`.

| order_id | symbol | side | qty | limit price | status (raw) | cum_qty (raw) | avg_fill_price (raw) |
|---|---|---|---|---|---|---|---|
| 3116580 | SPY | 1 (buy) | 28 | 733.17 | 4 | "28" | "731.54" |
| 3116594 | EFA | 1 (buy) | 142 | 101.45 | 4 | "142" | "100.495" |
| 3116597 | VNQ | 1 (buy) | 83 | 94.98 | 5 | "0" | "0" |

All three: `order_type: 1` (limit), `order_trade_time_type: 1` (intraday only), `time_in_force: 0`, `aux_price: null`, order text "tyche 2026-11-18 rebalance … plan f11456df".

### VNQ 3116597 — raw fields VERBATIM (semantics of status 5 NOT verified; no label assigned)

```json
{"aux_price":null,"avg_fill_price":"0","create_time":"1795024387000000","cum_qty":"0","market":2,"order_id":"3116597","order_trade_time_type":1,"order_type":1,"price":"94.98","qty":"83","side":1,"status":5,"stock_name":"Vanguard Real Estate ETF","symbol":"VNQ","text":"tyche 2026-11-18 rebalance 11% VNQ, plan f11456df","time_in_force":0,"update_time":"1795050060000000"}
```

- `status: 5`, `cum_qty: "0"`, `avg_fill_price: "0"`. Matches operator's 02:49 UTC observation (previously status 2 resting at 18 Nov EOD).
- The order record contains NO explicit frozen/freeze field. Freeze release is evidenced indirectly by `cash.json` `"hold":"0"` and full buying power restored.
- Timestamps (µs → UTC): create 1795024387000000 = 2026-11-18 17:53:07 UTC; update 1795050060000000 = 2026-11-19 01:01:00 UTC (18 Nov 20:01:00 ET, i.e. just after the after-hours close). The status transition therefore occurred between 18 Nov EOD and the operator's 02:49 UTC observation.
- SPY create/update: 2026-11-18 17:44:56 / 17:45:00 UTC. EFA create/update: 2026-11-18 17:49:36 / 17:49:45 UTC.

### Pagination coverage evidence

The history tool exposes only `acc_id`, `market`, `time_begin`/`time_end` (µs), `page_size`, `next_key`. There is NO status-filter parameter, so status-sliced sweeps were impossible; coverage was varied by date window:

1. page-01: window 2026-11-01 → 2026-11-20 UTC, page_size 50 → 3 orders, `has_more:false`, `next_key:"0"`.
2. page-02: NO time filter (unbounded), page_size 50 → identical 3 orders, `has_more:false`, `next_key:"0"`.
3. page-03: backstop window 2026-01-01 → 2026-11-01 UTC → 0 orders, `has_more:false`, `next_key:"0"`.

No call offered a continuation cursor; union = {3116580, 3116594, 3116597}. Exhaustion reached on every sweep. Exact parameters and returned pagination metadata per call: `mcp/orders-query-log.json`.

## 5. Tool-availability inventory (exact registered names)

Read/query tools PRESENT:
- `mcp__moomoo__sim_trade_account_list`
- `mcp__moomoo__sim_trade_cash_info`
- `mcp__moomoo__sim_trade_position_list`
- `mcp__moomoo__sim_trade_history_order_list` (order-history query — PRESENT)
- `mcp__moomoo__sim_trade_max_buy_sell` (read-only sizing query; not called)
- `mcp__moomoo__account_order_fees` (read-only per-order fee query; not called)
- `mcp__moomoo__quote_stock_quote` (quote tool — PRESENT; batch realtime quotes, includes `option_ex_data` for option symbols)
- `mcp__moomoo__quote_cur_kline` (K-line)
- `mcp__moomoo__quote_rt_data` (intraday time-share)
- `mcp__moomoo__quote_order_book` (order-book/broker-queue depth — PRESENT)
- `mcp__moomoo__quote_market_state` (market session state)

Write tools PRESENT but NOT USED (paper only): `mcp__moomoo__sim_trade_input_order`, `mcp__moomoo__sim_trade_cancel_order`, `mcp__moomoo__sim_trade_modify_order`.

ABSENT:
- `quote_option_chain` or ANY option-chain query tool — ABSENT. No tool returns a chain/expiry/strike listing.
- Option contract metadata / static-info tool (lot size, expiry list, contract search) — ABSENT. The only option-adjacent data is `option_ex_data` embedded in `quote_stock_quote`, which requires already knowing the exact option symbol; it cannot enumerate a chain.

### Option-chain probe outcome

NOT EXECUTED — no option-chain read tool exists in this session, so there was nothing to call and no `chain-SPY-probe.json` was produced (per instructions the probe is conditional on the tool existing). Consequence: SPY weekly option chains cannot be discovered via MCP with the current tool set; an alternative data path or an added tool is required before any options workflow.

Supplemental read-only check: `quote_market_state` for US.SPY / US.VNQ returned `market_state: "AFTER_HOURS_END"` (trade date 20261118), confirming US market closed at query time. Verbatim capture: `mcp/market-state.json`.

## 6. Anomalies / deviations

1. Shell availability: the delegation stated "you have no shell", but this session does expose a Bash tool. It was used exactly once, strictly read-only, to check the challenge account id against env `TYCHE_ALLOWED_ACCOUNT_IDS` without echoing the env value (output: 1 allowlist entry, match True). No broker writes, no git operations, no repo/journal writes were performed with it. All persistence used the file-write tool as instructed.
2. Order records report `"market":2` even though queried with `market=100` (and positions report `market:100`). Raw value preserved verbatim; no interpretation offered. Flagged for desk-head awareness in case downstream code keys on the order `market` field.
3. VNQ status-5 terminal semantics remain UNVERIFIED. Raw values only (`status:5`, `cum_qty:"0"`, `avg_fill_price:"0"`); no cancelled/expired label assigned. No explicit frozen field exists on order records; freeze release inferred only from cash `hold:"0"`.
4. No status filter on the history-order tool — completeness rests on the unbounded sweep + empty backstop window (section 4), not on status slicing.
5. No option-chain or option static-info tool in the session (section 5) — options discovery is currently impossible via MCP here.
6. `realized_profit`/`unrealized_profit` are null at both cash and position level; per-position `profit` fields are populated. Noted, not interpreted.

## 7. Capture manifest (all under /data/drive/tyche-raw/rollout-20261119/mcp/)

- accounts.json — sim_trade_account_list, verbatim
- cash.json — sim_trade_cash_info (...598), verbatim
- positions.json — sim_trade_position_list (...598, market 100), verbatim
- orders-page-01.json / orders-page-02.json / orders-page-03.json — history sweeps, verbatim
- orders-query-log.json — per-call parameters + returned pagination metadata
- market-state.json — quote_market_state US.SPY/US.VNQ, verbatim
- (no chain-SPY-probe.json — option-chain tool absent; probe conditional not met)

Nothing was acted upon. Report only.