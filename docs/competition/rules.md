# Competition contract — distilled rules (source of truth for tyche)

Distilled from the participant handbook and the 43-slide kickoff briefing.
Persisted here because the original fetches live in Qoder's tmp folder and expire.
**Verify against the official handbook/Luma page before relying on a number for a trade.**
Numbers below are quoted from the handbook unless marked `(briefing)`.

## Window and clock

- Development + trading window: **17–28 Nov 2026**. Submission deadline **30 Nov 2026, 23:59 SGT**. Top-10 presentation 8 Dec.
- US trading effectively ends at the **regular close on the final competition day**. Thanksgiving **Thu 26 Nov closed**; **Fri 27 Nov is a half day, 13:00 ET close** `(briefing — confirm)`.
- Trading hours: **04:00–20:00 ET** (pre-market, regular, after-hours all available). Regular session 09:30–16:00 ET; in November (EST) that is **14:30–21:00 UTC**.
- Weekly return marks: **22:00 ET each Friday**.
- Remaining sessions from 18 Nov: 18, 19, 20, 23, 24, 25, 27 (26 closed) ≈ **7 sessions**.

## Eligible instruments and account

- Only **US-listed stocks, ETFs, and options**. Everything else excluded.
- Start **USD 100,000** virtual. Competition account is a paper account (`account_type` 2, `market_id` 100) — **not** a `SIM-` prefixed id. The full account id is held in vault/env (`TYCHE_ALLOWED_ACCOUNT_IDS`), never committed.
- Auth: select **Market Data** permission only; do **not** grant live trading execution / account-order permissions.
- The competition account **cannot be reset**. Test on a separate personal paper account first (id likewise in vault/env).
- Reset Card / revival / any fund-restore mechanism = **automatic disqualification**.

## Limits

| Rule | Value |
|---|---|
| Min stock price | **USD 1.00** |
| Min market cap (stocks and options) | **USD 500 million** |
| Executed orders per day | **200** (cancels/amends excluded) |
| Max concurrent positions | **100** |
| Single-stock exposure | **≤ 40% of total account assets**; exempt if exceeded solely by price move or option exercise. tyche targets **35–38%** headroom. |
| Long margin | 50% initial / 40% maintenance |
| Short margin | 60% initial / 50% maintenance |
| Financing interest (daily after close) | margin **4.8%/yr**, short **6.0%/yr** |
| Forced liquidation | if remaining liquidity **< 0** intraday |

## Options

- **ITM options expiring today auto-exercise after close**; underlying bought/sold if funds allow, else forced liquidation to meet margin. OTM expire worthless. Settled at the expiry-date closing price.
- Multi-leg: place as **separate leg orders**; each leg counts against the 200/day allowance. Briefing recommends single-leg.
- **No historical options data via MCP** (still in development) — options backtesting needs external data.
- Sim order types: **Limit / Market only** — no broker-native stops/trailing/algos on the paper path. Protection must be synthetic (monitor) or structural (defined-risk spreads).

## Order matching and fees

- Trade-by-trade volume simulation. Price condition alone does not fill. If **market volume × 20 < order qty**, partial fill; remainder pending until matched/cancelled. → respect liquidity; use limit orders.
- **Virtual fees (handbook §8):**
  - Stocks: commission **$0**; platform **$0.99/order**; TAF **$0.000166/share sold**, cap **$8.30/trade**.
  - Options: commission **$0.65/contract** (premium > $0.10) or **$0.15** (≤ $0.10), **min $1.99/order**; platform **$0.30/contract**; TAF **$0.00279/contract**; regulatory **$0.015/contract**.
- Handbook mandate: **account for commissions and slippage** when evaluating strategy and recording trades in the journal.
- Sim MCP order/history objects expose **no fee fields** → tyche models fees (`FeeRecord`, source `model`) and reconciles against account cash at EOD.

## Settlement

- Final results use **regular-market closing prices on the final day**. Value of options exercised on the final day is included. **After-hours trades on the final day are excluded.**
- → Be flat or hedged before the final regular close; do not rely on after-hours exits.

## Judging criteria (subject to change)

| Criterion | Weight |
|---|---:|
| Risk-adjusted return | 25% |
| Qoder & Qoder Cloud Agent usage (multi-agent, automation, dashboards, reports, reusable skills) | 30% |
| Strategy & risk design (thesis, edge, **invalidation conditions**, position limits, drawdown responses, kill switches) | 30% |
| Reusability & documentation (reference-ready templates, skills/scripts, slides or report) | 15% |

Submission: a **Qoder-generated presentation deck** + a **runnable trading-agent package**, including strategy explanation, risk limits, a **log of trading decisions**, fills/results, and a demo of **what worked, what failed, and why**. Early submission allowed.

## Handbook engineering guidance (§7–§9) — treat as requirements

- Build a **dashboard** (positions, P&L, equity curve, open orders, drawdown, decision log); it is explicitly rewarded and proves unattended operation. Record a short screen capture for submission.
- **Version everything you tune**: re-run 3–4 fixed evaluation prompts and diff before promoting a change; **pin skill/agent versions** on the trading agent (no `latest`).
- **Log decisions as a first-class artifact**, including **rejections and why** (a rejection log answers "what failed and why").
- Topology (§8.2): **researcher → executor → risk auditor**, auditor in a **separate session so it cannot be talked into agreeing**; orchestrator rule: *"never let the executor act on the researcher's output without the auditor's approval."*
- Forward Mode (§9): one role per agent; **define file ownership** (shared filesystem); **state delegation criteria + output formats in the coordinator prompt** (selecting agents does not force delegation); **pin child versions**; **grant credentials only to agents that need them** (coordinator usually none).
- Schedules: each run is a **new session** (no chat carry-over) unless `reuse_session`; make instructions **self-contained**; configure files explicitly; match frequency to duration (concurrency 1); dedupe with stable IDs; set an end time for temporary monitoring.

## Event calendar `(briefing — confirm against an official calendar)`

- 17 Nov: retail sales 08:30 ET; NVDA earnings.
- **18 Nov: FOMC minutes 14:00 ET.**
- **25 Nov: PCE 08:30 ET; Beige Book 14:00 ET.**
- 26 Nov: Thanksgiving, closed. 27 Nov: half day, 13:00 ET close.