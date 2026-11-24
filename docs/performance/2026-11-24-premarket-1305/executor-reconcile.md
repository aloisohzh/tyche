# Executor reconciliation — 2026-11-24 pre-market fire (08:05 ET / 13:05 UTC)

Run: `2026-11-24-premarket-1305` · repo HEAD `4372842` (contains tested release `3312287c`) · phase `pre_market`, full trading day (calendar IN SYNC, no half-day) · account `[REDACTED]` (US paper, account_type 2, market_id 100) · `TYCHE_ALLOWED_ACCOUNT_IDS` = `[REDACTED]` (verified, not overridden) · broker batch `observed_at` = **2026-11-24T13:08:41Z** (oldest read in the batch; quotes/books 13:09–13:12Z).

## 1. Ownership verdict — CLEAN

Full unfiltered history read in one page, `pagination.has_more = false` (11 rows at reconcile). Latest pre-existing order **3118578** (MSFT buy, `tyche-tac-…`) created `2026-11-19T18:15:16Z` — exactly the stated boundary, **no newer order before this fire**. No ownership incident.

Attribution of the 11 rows: 3× `tyche 2026-11-18 rebalance` (SPY/EFA/VNQ), 1× `tyche-tac-` (MSFT), 6× `tyche-scl-` = operator **PB-004 scalp card** (named exception, read-only here), plus the 3 new `tyche-exit-` rows submitted this fire. PB-004 round trips (NVDA/AMD/MU) all status 4 closed; no open scalp position.

## 2. NAV / cash / positions (broker read, 13:08:56Z)

| Item | Value |
|---|---|
| Broker `total_asset` (NAV) | **98,727.381** |
| Cash balance | 45,680.121 (46.3% NAV) |
| Frozen cash (`hold`) | 0.00 |
| Position MV | 53,047.26 (53.7% NAV) |
| Snapshot nav (cash+MV) | 98,724.861 (Δ 2.52 vs broker, mark timing) |

Positions: **SPY 28** (avg 731.54), **EFA 142** (avg 100.495), **MSFT 39** (avg 503.33) — matches expectations; no option holdings, so `contracts.json` not required. Feed health: cash, positions, history all returned **healthy data** — the Nov-23 outage pattern (`cash` -5 + success-with-empty) is **not present**. No payload quarantined to `mcp-anomaly/` this fire.

Risk context: drawdown vs HWM 100,000.00 = **-1.27%** (soft 4% / hard 6% intact); vs prior close NAV -0.66%; cash ≥5% and gross ≤95% respected. Daily-loss 2.5% not breached.

## 3. Order pages summary + boundary check

- `mcp/orders-1.json` — reconcile read, 11 rows, `has_more=false`, pagination top-level. 1 page only.
- `mcp/history-post-submit.json` — 13:13Z re-read, 14 rows, `has_more=false`: exactly **one** order per `request_id`, no duplicates.
- `run/orders.json` — live order list used by `exit-now` for working-sell checks.

**status5 UNRESOLVED (still status 5, cum_qty 0 — not proven terminal, keep flagged):**
- **3116597** VNQ buy 83 @ 94.98 (Nov-18 rebalance) — no VNQ position, never filled, never reconciled to a terminal state.
- **3118500** SMH buy 10 @ 454.48 (`tyche-scl-`, PB-004) — no SMH position. Cancellation is operator-owned (always_ask); not touched this fire.

## 4. Per-lot protection state (before this fire → after)

| Lot | Plan / ownership | Protection before | Protection now |
|---|---|---|---|
| SPY 28 | `LC-20261119-SPY-ADOPT-r2` (PB-001, rules `4105d7a680a3`), stop 727.50 / TP 775.64, exit_deadline 2026-11-27T17:00Z | **None live** — synthetic daily-close stop only, no broker order | **Working sell 3124584** @ 710.08 (limit rests for the open) |
| EFA 142 | `LC-20261119-EFA-ADOPT-r2` (PB-001), stop 100.00 / TP 105.80, exit_deadline 2026-11-27T17:00Z | **None live** | **Working sell 3124585** @ 97.88 |
| MSFT 39 | **No lifecycle plan — unowned lot** (journal defect: 3 Nov-18 `order.requested` rows lack `request_id`) | **None** (pure coverage gap) | **Working sell 3124586** @ 485.26 |
| VNQ / SMH | no position | n/a | status5 orders unresolved → reported, no exposure |

Both PB-001 stops are breached (SPY mark 714.10 < 727.50; EFA 98.63 < 100.00), consistent with the operator exit note. Residual risk: these are **synthetic limits resting into the open, not guaranteed fills** — a gap below the limit, a halt, or no bid at the open leaves the lot unsold; expiry is end of day if unfilled.

## 5. Operator exit envelope — 3/3 lines attempted, all authorized and submitted

Envelope `config-root data/approvals.json`, `as_of 2026-11-24`, approved `00:42:00Z`, **valid_today=true**, mode `WITHIN MY BOUNDS` (`mode: bounds`), `max_orders 3`, multiplier 1. Path taken: `tyche exit-now` (operator-sanctioned; no lifecycle grant / setup hash / auditor / tactical universe required or used). `lifecycle reserve` / `execute-exit` / legacy `authorize` deliberately **not** used today because of the request_id-less Nov-18 journal rows.

| Line | Bid source (live pre-market book) | Limit = max(floor, bid×0.995) | Qty | exit-now | request_id | submit_before | Receipt | Post-submit status |
|---|---|---|---|---|---|---|---|---|
| US.SPY | ARCA best bid 713.65 (13:10:04Z) | **710.08** (floor 690.00) | 28 | exit 0 | `tyche-exit-732827c19f2debdb73f62f14` | 13:12:50.966Z | **3124584** | status 2 pending, cum 0 |
| US.EFA | NASDAQ/ARCA best bid 98.37 (13:12:15Z) | **97.88** (floor 94.50) | 142 | exit 0 | `tyche-exit-da8d43da202b3f81dcb15de4` | 13:13:50.277Z | **3124585** | status 2 pending, cum 0 |
| US.MSFT | NASDAQ best bid 487.70 (13:12:15Z) | **485.26** (floor 474.00) | 39 | exit 0 | `tyche-exit-c82a32a9d62237ea809adeeb` | 13:14:13.628Z | **3124586** | status 2 pending, cum 0 |

Every limit is above its approved floor; no order was placed below floor; each lot was fully committed (`qty_avbl` → 0 for all three lots after submit). Estimated gross proceeds at limit: SPY 19,882.24 (20.1% NAV) + EFA 13,898.96 (14.1%) + MSFT 18,925.14 (19.2%) ≈ **52,706 (53.4% NAV)**; fees are not modelled in `config/risk.yaml` — the broker receipt governs actual commission/tax.

**Receipts are NOT fills.** At 13:13Z all three are status 2 with cum_qty 0.

### EFA transport note (honest sequence)
The first EFA submit call failed at my own transport layer before dispatch (never reached the broker). Per the uncertain-outcome rule I re-read history at **13:12:25Z** and found **no** EFA row before writing again; exactly one order (3124585) was then submitted. No duplicate exists.

## 6. Lifecycle coverage — read-only, isolated copy (no production mutation)

Copied `lifecycle/state.json` + `book.json` → `state-iso/`; capture inputs in `iso/`. Production `state.json` sha256 `a7a9e99496ffc4f9…` and `book.json` `bc9e6d50643f722f…` verified **unchanged** after the run; isolated state identical to its pre-tick copy.

- `tyche lifecycle capture --dir iso --account-id [REDACTED] --observed-at 2026-11-24T13:08:41Z --prior-close-nav 99380.951 --high-water-nav 100000.00 --regime risk_off --conviction low --out iso/market-US.json` → `{"captured": true, "submitted": false}` (exit 0).
- `tyche lifecycle tick` (no `--record`, live clock) → exit 1, verbatim: **`{"ok": false, "reason": "broker snapshot stale or future-dated; fetch again", "submitted": false}`** — the expected pre-market structural block: pre-market quote `data_time` = prior RTH close (1795467600000 ms), outside the 120s broker-snapshot gate. Not forced.
- Replay attempts (`--at`, inspection only, never authorization): `13:09:30Z` → `reason: broker order timestamp is in the future`; `13:12:50Z` → `reason: broker snapshot stale or future-dated; fetch again`. Confirms no pre-market window satisfies both gates today.

Per-symbol coverage (from the book + positions, since the engine tick is gated):
- **US.SPY** — plan present (adopt 28); stale/absent live exit before this fire → now covered by broker order 3124584.
- **US.EFA** — plan present (adopt 142) → now covered by broker order 3124585.
- **US.MSFT** — **held position missing a complete lifecycle plan** (coverage gap, unowned lot) → operator exit 3124586 removes the exposure; the ownership/journal defect remains open for the desk.
- **US.AAPL** — `PB-007-20261120-AAPL` new_entry proposal, not held (entry expired 23 Nov); PB-007 is OFF (failed backtest), no fib-scan run.
- Journal state: `approvals=[]`, `reservations=[]`, `latched_exits={}`, `last_tick_at=null` — reported verbatim, not concealed; no empty ledger was created and no adoption grant was invented.

PB-003 options: 15:05-only lane, **no entries at 08:05** — nothing done. PB-004: listed read-only, nothing submitted/re-armed/cancelled.

## 7. PB-001 kline handoff (desk head runs `mcp_prices.py`; no prices transcribed here)

Universe from `config/universe.yaml` (11 ETFs; `config/strategies/pb-001.yaml` carries no separate universe pointer). `quote_cur_kline num=370 ktype=2 autype=1` — all returned **370 bars** (2025-06-05 → 2026-11-23), code verified per file. Copies persisted at `mcp/bars-<symbol>.json`; source temp paths:

| Symbol | File path |
|---|---|
| US.SPY | `/tmp/tool-outputs/mcp_ca3a75644229b4b6cf7c067e.txt` |
| US.QQQ | `/tmp/tool-outputs/mcp_4c8bca4a30260da99384e668.txt` |
| US.IWM | `/tmp/tool-outputs/mcp_df7913e18cc320b99756c671.txt` |
| US.EFA | `/tmp/tool-outputs/mcp_de0b225458e2c0a7ff776e68.txt` |
| US.EEM | `/tmp/tool-outputs/mcp_69b970d51c11038aaa932b10.txt` |
| US.TLT | `/tmp/tool-outputs/mcp_a111620ac17df0fe0c37ae16.txt` |
| US.IEF | `/tmp/tool-outputs/mcp_ef1f5e91198c5ffebbbe0404.txt` |
| US.GLD | `/tmp/tool-outputs/mcp_4c51126a83a62915fb2adeb5.txt` |
| US.DBC | `/tmp/tool-outputs/mcp_4ae17cfeccfaa95c5911431d.txt` |
| US.VNQ | `/tmp/tool-outputs/mcp_f0af120a251e5badbf0a854d.txt` |
| US.HYG | `/tmp/tool-outputs/mcp_84b562bb12dde04f4b1777fa.txt` |

Insufficient bars: none. Note: these `/tmp` files vanish if the sandbox is replaced — the durable copies are `mcp/bars-*.json`.

## 8. NAV references (evidence only — desk head owns `nav-refs.json`, not edited here)

- **prior_close_nav candidate: 99,380.951** — source `/data/drive/tyche-raw/2026-11-23-close-2005/mcp/cash.json` (`ret_code 0`, `total_asset "99,380.951"`, observed 2026-11-23T20:29:11Z), carried as `broker_nav` in `2026-11-23-close-2005/state/market-US.json`. Cross-check: position MV sum 53,700.55 + cash 45,680.121 reconciles within 0.28.
- Caveat: that NAV was taken **during the Nov-23 account-service outage**; the four failed/empty contrast reads are quarantined in `2026-11-23-close-2005/mcp-anomaly/account-feed-failures-20261123T2029Z.json`. A later healthy observation `/data/drive/tyche-raw/2026-11-23-close-2005/state/cash-observed.json` shows `total_asset 99,400.976` (MV 53,720.855) — flag for the desk to pick one convention.
- **High-water stays 100,000.00** — no verified close above it (today 98,727.381 < 100,000).

## 9. Pending orders after this fire

| order_id | symbol | side | qty | limit | status |
|---|---|---|---|---|---|
| 3124584 | US.SPY | sell | 28 | 710.08 | 2 pending (rests for the open) |
| 3124585 | US.EFA | sell | 142 | 97.88 | 2 pending |
| 3124586 | US.MSFT | sell | 39 | 485.26 | 2 pending |
| 3116597 | VNQ | buy | 83 | 94.98 | **5 UNRESOLVED** |
| 3118500 | SMH | buy | 10 | 454.48 | **5 UNRESOLVED** (PB-004) |

Order budget: 3/3 envelope, 3/120 daily, 3/200 competition.

## 10. Problems / open items

1. **Pre-market lifecycle tick is structurally blocked** by the 120s broker-snapshot gate (verbatim reason in §6) — per-symbol lifecycle decisions must come from an RTH fire.
2. **US.MSFT 39 has no lifecycle plan** and remains unowned in the ledger lineage; the sale covers today's exposure but the ownership gap persists.
3. **Journal defect persists**: 3 Nov-18 `order.requested` rows lack `request_id`, which is what breaks `lifecycle reserve`/`execute-exit`; `exit-now` was used as the sanctioned bypass.
4. **Two status-5 orders unresolved** (VNQ 3116597, SMH 3118500) — not proven terminal; cancellation needs separate operator approval.
5. **Cap compliance check (no conflict claimed)**: frozen `config/risk.yaml` has `max_order_notional_pct: 0.30` (per-order), `min_cash_weight: 0.05`, `max_gross_exposure: 0.95`, `max_orders_per_day: 120`; `config/strategies/pb-001.yaml` has `allocation_cap: 0.25` (strategy weight) — different dimensions. The largest exit was 20.1% of NAV, inside the 30% single-order cap. These exits are authorized by the operator envelope, not by any ceiling; ceilings are not targets and never authorize selling.
6. **No RTH exit guarantee**: the three sells are resting limits. If the open gaps below them they will not fill; the next scheduled fire must re-check status before any re-entry attempt, and any cancel/modify requires its own operator approval.
7. EFA pre-market depth is thin (19 shares printed; bid 98.37 vs ask 99.15 ≈ 0.8% wide) — fill at 97.88 is plausible but the lot may see partial fills.
8. `nav-refs.json` on Drive is still Nov-18-stale — desk head to refresh at a verified close.

## 11. Artifacts

Run root `/data/drive/tyche-raw/2026-11-24-premarket-1305/`: `snapshot.json`, `orders.json`, `accounts.json`, `cash.json`, `positions.json`, `quotes.json`, `executor-reconcile.md`; `mcp/` (raw verbatim payloads: accounts/cash/positions/orders-1/quotes/books/market-state/history-post-submit/positions-post-submit/bars-*, plus `accounts.masked.json`); `iso/` (capture inputs + `market-US.json`); `state-iso/` (`state.json`, `book.json`, `state.pre-tick.json`, `tick-replay-130930.json`, `tick-replay-131250.json`).

Journal `journal/events.jsonl`: **67 events, chain verified intact** — added `order.requested` + `order.submitted` pairs for all three exits (requested rows written by `exit-now` itself) and one `reconcile.completed`. `tyche record-order` rejects `reconcile.completed` as an event type, so it was appended through the supported library path `tyche.journal.append_event` (same hash chain, 34 prior uses in this lineage); no hand-edited rows.
