# Bounded read-only broker preflight — 2026-11-19

- Delegation clock: 2026-11-19 11:08:17 UTC (06:08 ET, pre_market). Reads executed 11:09:00–11:10:25 UTC.
- Mode: ROLLOUT HOLD active (execution_enabled=false). **broker_writes=0.** No orders, reservations, approvals, cancel/modify, state/config/journal edits, git push, or Telegram. Preview only; not armed.
- Repo: /data/workspace/tyche HEAD 28246a164fc58272fb45c5bdaadee68702a31c71; verified ancestor contains tested 7288d68758ec2fedcee137622fee472be5d9a41d. Repo unmodified.
- Calendar context (from delegation, live at 11:07:25Z): trading_day=true, phase=pre_market, new_entries=false, max_orders=0, event_caution=false; event: Anthropic (ANT) Nasdaq IPO debut.

## Per-read results (each attempted once, all success)

| # | Read | Result | Artifact |
|---|------|--------|----------|
| 1 | sim_trade_account_list | success (ret_code 0) | mcp/01-accounts.json |
| 2 | sim_trade_cash_info | success | mcp/02-cash.json |
| 3 | sim_trade_position_list (market 100) | success | mcp/03-positions.json |
| 4 | sim_trade_history_order_list unfiltered, page 1; pagination.has_more=false → complete (1 page, 3 orders) | success | mcp/04-orders-1.json |
| 5 | quote_stock_quote US.SPY | success | mcp/05-quotes.json |

Oldest broker read (observed_at): 2026-11-19T11:09:00Z (accounts/cash/positions batch); quote read ~11:10:00Z.

## 1. Account
- Challenge account masked …2598, account_type=2, market_id=100 (US paper, challenge). Matches allowlist scope. Other accounts in list untouched.

## 2. Cash / NAV reconciliation (USD)
- total_asset (broker NAV): **100,185.29**
- cash (balance): 65,244.61 (65.12% NAV)
- frozen (hold): **0.00**
- market_val: 34,940.68 (long only; short_mv 0)
- buying power (max_power_long): 165,429.90 (margin figure, not a spending authorization)
- Check: 65,244.61 + 0.00 + 34,940.68 = 100,185.29 ✓ exact.

## 3. Positions
| Symbol | Qty | Sellable (qty_avbl) | Cost | Last (broker) | MV | P&L |
|--------|-----|--------------------|------|---------------|-----|-----|
| SPY | 28 | 28 | 731.54 | 739.42 | 20,703.76 | +220.64 (+1.08%) |
| EFA | 142 | 142 | 100.495 | 100.26 | 14,236.92 | −33.37 (−0.23%) |

- Whole quantities only. **Options: NO** (option metadata read skipped per instructions). No short, fractional, or unsupported exposure.
- Matches prior known state SPY 28 + EFA 142. Combined MV = 34.88% NAV — above PB-001 25% sleeve cap; existing holdings, NOT liquidation permission.
- Protection gap: no broker-native stops exist (paper broker); held-position protection depends on the (held) engine lanes. Position prices in payload are broker marks; SPY mark 739.42 is consistent with pre-market, not the RTH close.

## 4. Order history (complete, unfiltered; has_more=false on page 1)
| Masked ID | Symbol | Side | Qty | Limit | Status | Cum filled | Frozen |
|-----------|--------|------|-----|-------|--------|------------|--------|
| …6597 | VNQ | Buy | 83 | 94.98 | **5** | 0 | 0.00 (account hold=0) |
| …6594 | EFA | Buy | 142 | 101.45 | 4 (full) | 142 @ 100.495 | — |
| …6580 | SPY | Buy | 28 | 733.17 | 4 (full) | 28 @ 731.54 | — |

- **…6597 UNRESOLVED MANUAL-REVIEW flag PRESERVED.** Status 5 semantics unproven; NOT classified terminal (only full status 4 with matching cum qty is verified terminal). Created 2026-11-18T17:53:07Z, last update 2026-11-19T01:01:00Z (after EOD). Frozen funds are 0, so it is not currently freezing cash, but its terminal state remains unverified — needs provider evidence / separately approved manual review. No cancel attempted (hold + always_ask policy).
- No other pending/unknown orders. Day order count so far: 0 new orders today.

## 5. Quote connector verification — US.SPY
- sec_status NORMAL, suspension=false.
- Regular-session last: 730.20, data_time 2026-11-18T21:00:00.268Z (16:00 ET RTH close); prev_close 732.44.
- pre_market: 739.465 (+1.268%); after_market: 735.57; overnight: 738.55.
- Bid/ask: not present in stock-quote payload (order book not fetched — out of preflight scope).
- Freshness note: main last_price is prior RTH close (expected pre-market); session sub-objects show live extended-hours trading. Quote age would fail the kernel's 60s regular-quote gate for entries — irrelevant today (new_entries=false, max_orders=0), but noted for feed-health honesty.

## Drift vs prior EOD refs (2026-11-18)
- NAV 100,185.29 vs prior_close_nav 99,914.93 → **+270.36 (+0.27%)**, driven by SPY/EFA marks.
- NAV exceeds high_water_nav 100,000.00 by +185.29 → new high-water candidate; NOT written to any state (hold).
- Holdings unchanged (SPY 28, EFA 142); frozen cash 0 vs VNQ order unresolved — consistent with prior flag, no new information resolving it.

## Artifacts (private run dir)
Base: /data/drive/tyche-raw/2026-11-19-preflight-1107/
- mcp/01-accounts.json — sha256 a3b50775239ed4f3a6c39b61412e7954ae62f7b04e8da65f94c643284216b739
- mcp/02-cash.json — sha256 d66bad5428e1c0988b84b088363f534fc831bf41bc53cd2853ea81d5ff3a3fe7
- mcp/03-positions.json — sha256 bd4f536cf1c3705105c1e38c917b6094d78098dc63cb9752347f3fa49bfb5033
- mcp/04-orders-1.json — sha256 6eb7ba504ace8cfe83611ffa8fac31f78063d8abe9a269dfa2c217557ca1fbfb
- mcp/05-quotes.json — sha256 ec6452e0e2581454475c0feed86096620038ce226f7d184845bc9f590a9e8b17
- report.md (this file)

Note: raw captures contain full broker IDs; they remain in the private run dir only. This report masks IDs to last 4.

## Confirmation
- broker_writes=0. All five reads attempted exactly once; no retries needed. No previews, ticks, chains, or research run. Rollout hold intact; preview only; not armed. Hourly lifecycle monitoring deployed; orders unarmed.