---
name: broker-capture
description: Use when the coordinator delegates the position-first reconciliation at any fire, and before any preview, tick or submit. Trigger at the start of every executor delegation.
role: executor
version: 1
---

# Broker capture

Reads first, every fire, before anything new. The files you write are the kernel's only view of the broker, so they are saved as returned, never edited.

## 1. Account
sim_trade_account_list, then sim_trade_cash_info and sim_trade_position_list for the exact allowlisted US paper account named in the brief (account_type 1 or 2, market_id 100). Save the unmodified payloads as accounts.json, cash.json, positions.json in the private run directory. Record the OLDEST read time; it is the observed_at for the whole batch and is never refreshed by rewriting a file.

## 2. Order history, every page
sim_trade_history_order_list from the first unfiltered page until pagination.has_more is explicitly false. Save either one orders.json with has_more false, or orders-1.json, orders-2.json ... consecutively from 1 with every real has_more flag (src/tyche/lifecycle_cli.py capture refuses a mixed or non-consecutive set). Never infer completeness from a filename.

## 3. Quotes, books, chains
quote_stock_quote, quote_order_book, quote_market_state and the completed daily quote_cur_kline bars the lane needs, saved as quotes.json, book-<symbol>.json and bars-<symbol>.json. For options, quote_option_chain on the equity or ETF underlying with filter_standard=STANDARD and an explicit expiry range, saved as chain-<symbol>.json; verify symbol, right, strike, expiry and lot against the chain and write contracts.json for every option holding and every option in history. A chain listing is not execution validation. Optional closes.json maps symbol to {close, close_at} for the latest completed regular-session close.

## 4. Normalize
Tactical: `tyche tactical capture --dir RUN --account-id ID --prior-close-nav NAV --high-water-nav NAV`. Lifecycle: `tyche lifecycle capture --dir RUN --account-id ID --observed-at TIME --prior-close-nav NAV --high-water-nav NAV --regime R --conviction C --out MARKET`. NAV references come from reconciled journal evidence; regime and conviction from the deterministic kernel plan. Age limits are the keys in config/tactical.yaml and the plan.

## 5. Inspect
`tyche tactical tick` and `tyche lifecycle tick` without --record. Report every held symbol's coverage, missing plan or grant, stale data, pending orders and unsupported exposure. Stale or one-sided books, missing metadata and auth failures block entries, never the reconciliation itself. No hand-transcribed prices, no fabricated timestamps, no full account ids in the report.
