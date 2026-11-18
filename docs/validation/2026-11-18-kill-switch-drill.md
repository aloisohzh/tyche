# Kill-switch drill — 2026-11-18 — PASS

Live end-to-end drill of the halt/kill-switch on the **personal paper account (…748**,
type 1, market 100), per the competition rule that drills never touch the challenge
account (…598, untouched throughout). Path: **MCP-only** (the cloud sandbox has no moomoo
CLI); journaling via `tyche record-order`. Runbook: [halt-kill.md](../runbooks/halt-kill.md).

## Pass criteria vs result

| Criterion | Result | Evidence |
|---|---|---|
| Halt blocks new buys | **PASS** | 3× `halt.skip` journaled (QQQ 682, EFA 1724, VNQ 1157); broker order history for the day contains **no** drill buys |
| De-risking sells remain allowed under halt | **PASS** | Sell order 3115472 submitted while halted, filled 10/10 |
| Tamper-evident audit trail | **PASS** | `tyche journal-verify` → OK, 20 events, chain intact |
| Challenge account pristine | **PASS** | Every order on …748; zero orders placed on …598 |
| Operator gate on every submission | **PASS** | Explicit preview + authorization before each order write (seed and drill sell) |

## Timeline (UTC, 2026-11-18)

| Time | Event | Broker order / journal |
|---|---|---|
| 05:17:04 | Seed limit buy 10 SPY @733.20 → queued (market closed) | 3115303 |
| 05:19:39 | Seed cancelled unfilled (status 5) | 3115303 |
| ~09:05 | Market-order seed attempt **rejected by backend** (market closed, ret_code −5); no order created | — |
| 09:07:52 | Corrected to marketable limit 745.00; `order.requested` | journal |
| 09:11:35→45 | Seed filled 10 @ **735.99** (status 4) | 3115432 |
| 09:34:26 | Drill plan created (as_of 2026-11-17, regime neutral) | `plan.created` |
| 09:34:50 | **Halt engaged** ("kill-switch drill") | `halt.engaged` |
| 09:34:56–09:35:07 | Buys withheld: QQQ 682 @292.70, EFA 1724 @77.28, VNQ 1157 @86.34 | 3× `halt.skip` |
| 09:40:09 | Drill sell requested: SELL 10 SPY @731.71, remark `tyche-drill-2026-11-18-s1` | `order.requested` |
| 09:43:42→48 | **Sell filled 10/10 @ 737.04** (status 4, pre-market, time_type 2) | 3115472 |
| 09:44:00 | `order.submitted` journaled with order id | journal |
| 09:44+ | Reconcile: day's order history = exactly 3 orders (3115303 cancelled, 3115432 seed fill, 3115472 drill sell); position list shows SPY qty 0, realized +10.50 | MCP reads |
| 09:45:07 | Resume; `journal-verify` OK 20 events | `halt.released` |

Plan detail: APPROVED sell SPY 10 @731.71 ($7,317); APPROVED buys QQQ/EFA/VNQ (withheld by
halt); BLOCKED buy HYG (`portfolio.gross` 98.6% > 95%, `portfolio.min_cash` 1.4% < 5%) —
the risk kernel's own rejection, independent of the halt.

## Fixture disclosure (honesty)

`prices-scenario.csv` is a **labeled drill fixture, not market data**: demo prices re-dated
to 2026-11-17 with US.SPY replaced by a synthetic path (800 → 732.44) to knock out SPY
momentum so the plan contains both buys and a sell of the seeded position. The personal
account's real holdings are non-universe names the kernel cannot sell
(`universe.membership`), hence the 10-share SPY seed. Broker prices/fills above are real
paper-broker state; only the planning inputs were synthetic.

## Cost

Round trip 735.99 → 737.04 on 10 shares: **+$10.50 gross**, small fees (~$1/leg). The drill
was approximately cost-neutral.

## Lessons recorded

- Paper **market orders are rejected while the market is closed**; use a marketable limit.
- A submit is not a fill: reconcile from broker order state, never from the submit response.
- Non-idempotent submissions: inspect order state before any resubmit; operator gate each time.

## Evidence pointers

- Journal: `journal/events.jsonl` (hash-chained, gitignored; sanitized excerpts above;
  verify with `tyche journal-verify`).
- Run dir: `plans/drill-2026-11-18/` (gitignored: accounts/cash/positions JSONs, fixture,
  plan, DRILL-STATE.md).
- Broker order ids: 3115303 (cancelled), 3115432 (seed fill), 3115472 (drill sell fill).
- Deterministic halt tests: `tests/test_risk.py` (`halt.active` blocks buys, allows sells).