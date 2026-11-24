# Desk narrative — 2026-11-18 (PRE-MARKET RE-PLAN)

- Desk: tyche (Moomoo x Qoder AI Agent Paper Trading Challenge, window 17–28 Nov 2026).
- Phase: scheduled pre-market run, 13:45 UTC start; plan rebuilt 13:49 UTC; audit returned ~13:58 UTC; narrative written ~14:02 UTC. Session 14:30–21:00 UTC.
- This run SUPERSEDES the earlier pre-market run today (~12:58–13:05 UTC), persisted at /data/drive/tyche-raw/2026-11-18-premarket/. Reason: operator raised the per-order notional cap 20%→30% (commit 18b97cf, authored 13:18 UTC, "Operator-approved" per commit message; risk-card and tests updated in the same commit). The earlier plan blocked the SPY leg under the old cap; a deterministic re-plan under the new config is the correct response, not a manual edit.
- Account: competition paper account ****2598 (env=paper, account_type=2, market_id=100, source=sim_list; allowlist matched via TYCHE_ALLOWED_ACCOUNT_IDS). Full id never written in reports.
- Kill-switch: NOT engaged (no journal/halt.json). Journal: chain intact, 2 events (both plan.created; zero order events).

## State restore (ephemeral sandbox)

Fresh session found an empty journal. Restored verbatim from the Drive locker: journal/events.jsonl (1 event), data/prices.csv, reports/2026-11-18-research.md, plans/2026-11-17-plan.{json,md} (prior version). Restored hashes matched the earlier narrative's pins exactly (prices 7e6500d5…, prior plan dbd2e15d…). No hand edits to config/, plans/, journal/ at any point; the new plan was written by the kernel CLI.

## Inputs and provenance (desk-head recomputed 14:01 UTC, post-audit — C5 attestation)

| Artifact | sha256 | Notes |
|---|---|---|
| plans/2026-11-17-plan.json | f11456dfafe83dfa6fd55de15fca7b8742cca4a20d809e407289c806b7016931 | kernel re-plan 13:49 UTC, as-of 2026-11-17 close |
| runs/2026-11-18/snapshot.json | 48c1d73d49b80656fff518968edb0e1665f70a943caebb7937e975676989f99e | fresh executor fetch 13:48 UTC; NAV 100,000.00, cash 100,000.00, 0 positions; prior_close_nav=high_water_nav=100,000.0 (C3 reference; flat account reconciles) |
| data/prices.csv | 7e6500d583c204fafa70ed76e3190f4bf8ae4c39a0c458ae0b39e373db9b4b52 | unchanged; 11 symbols x 370 daily bars through 2026-11-17; no kline re-fetch needed pre-open |
| config/risk.yaml | 96b6b0c11b652eef979f2425decebf98df0dcf7a8ea8bcd7ccf8f00afbfab83a | max_order_notional_pct 0.30; unchanged pre/post audit |
| config/strategy.yaml | bdcff4418a2ad856d3da7e2c286de5d8808a0b50f5181e6ecd5cb14e2874d1e5 | unchanged |
| config/universe.yaml | a7b97e01de7a7cb985336779d997c22871d1ee9c8e477032d5eb067f8e2365d0 | unchanged |
| reports/2026-11-18-research.md | 92bc7061022778be14a88a4e06b9c0020eee048f5eb4513a3bb2a0f5b0284b77 | earlier body + appended U1–U7 refresh (~13:50 UTC) |
| reports/2026-11-18-audit.md | 65a6e58da9ff617da48b3c9aba594a6469c6256b9b65f4adadef1610d4777409 | re-plan audit, supersedes ~13:04 UTC audit |
| commit 18b97cf | git show verified by desk head | cap change + turnover default alignment (25%→50% code vs docs) + root-anchored gitignore; auditor could not verify commit without shell — this row is the C5 attestation |

Pipeline: executor fetched accounts/cash/positions via MCP (raw payloads in runs/2026-11-18/mcp/), ran `tyche snapshot`, added the NAV reference fields. Researcher refreshed news/thesis (no shell in its session; report-only). Desk head ran `tyche plan --prices data/prices.csv --account runs/2026-11-18/snapshot.json`. No quantities invented or altered.

## Regime and thesis

Kernel regime: **neutral** (2/4: equity_trend PASS, golden_cross PASS, vol_calm FAIL, credit_trend FAIL), portfolio vol 8.71%, vol scale 1.00. Targets: SPY 30%, CASH 30%, EFA 20%, VNQ 10.96%, DBC 9.04%. Research refresh concurs: neutral with risk_off skew. Key news (untrusted data, UTC timestamps in research report): Waller floats 50bp Dec risk (13:27); Oct retail sales in line/ex-autos beat, CME Dec 25bp 95.7%; FOMC October minutes CONFIRMED 19:00 UTC today (news schedule; calendar API still empty — data gap); US strike on Iranian Qeshm Island site supports the DBC leg; NVDA H200 China halt confirmed but bounce firmed (SPY pre 735.21, +0.38%).

Invalidation levels (research): SPY close < ~727.5 (200d SMA flip zone 725–730); EFA close < 100.00; VNQ close < 93.50 (REVISED from 94.78, which was 0.12% below close — inside daily noise; 93.50 ≈ 1.5 daily σ below close); DBC close < 30.00 (kept tight deliberately, noise-adjacent, flagged). Tape overlay: QQQ red close on high volume = sell-the-news.

## Plan and risk verdict

| # | Order | Kernel | Auditor | % NAV | Notes |
|---|---|---|---|---|---|
| 1 | BUY US.SPY 28 @ 733.17 = $20,528.76 | APPROVED | APPROVE | 20.53% | passes new 30% cap; prior order.max_notional block superseded (correct under old policy) |
| 2 | BUY US.EFA 142 @ 101.45 = $14,405.90 | APPROVED | APPROVE | 14.41% | limit +0.099% vs close 101.35 |
| 3 | BUY US.VNQ 83 @ 94.98 = $7,883.34 | APPROVED | APPROVE | 7.88% | +0.095% vs 94.89; RTH limit only |
| 4 | BUY US.DBC 215 @ 30.22 = $6,497.30 | APPROVED | APPROVE | 6.50% | +0.099% vs 30.19; thin book — accept non-fill, never chase |

**OVERALL AUDIT VERDICT: APPROVE** (all four as written; conditions C1–C3 + C5). Auditor independently reproduced kernel sizing from prices.csv closes (pre-fit 40/197/115/299 = $69,270.93; turnover factor 50,000/69,270.93 = 0.721804 → 28/142/83/215) and all cap math. Post-fill: turnover $49,315.30 = 49.315% ≤ 50% (headroom $684.70); modeled fees $3.96; cash $50,680.74 = 50.68% ≥ 5%; gross 49.27% ≤ 95%; equity sleeve 34.90% ≤ 50%, real_asset 14.37% ≤ 20%; max name 20.5% ≤ 38% target; 4 positions, 4/6 orders. DD/daily-loss guards now ARMED at 0% (NAV reference present — earlier C3 satisfied).

Audit conditions:
- **C1**: execute-time allowlist + sim-list re-check before any submit (code-enforced).
- **C2**: RTH-only fixed limit orders; never chase SPY > 733.17 or thin DBC/VNQ books; accept non-fills; all initiations done or abandoned by 18:30 UTC; no re-submits 18:30–19:30 UTC (FOMC minutes 19:00).
- **C3**: EOD reconcile_cash ($3.96 fees provisional) and persist day-2 NAV references (prior close + high-water). Day-2 open without them = REJECT.
- **C5**: desk-head sha256/chain/commit attestations kept in the record (table above; auditor has no shell).
- **C4 CLOSED**: the day-1 sizing quirk is resolved by alignment, not masked — order cap 30% now equals strategy max target weight 30%, so pre-fit notionals cannot exceed the order cap; floor-after-scale fitting only shrinks (conservative). fit_turnover_budget code unchanged.

Key auditor findings adopted by the desk:
1. Researcher's U5 "turnover may shave the 4th order" warning is mechanically wrong: the turnover guard uses LIMIT notional (risk.py), execute submits fixed qty/limit with no re-sizing, and buy fills ≤ limit, so realized turnover ≤ 49.32% by construction. Upward price drift → non-fill, not a shaved order.
2. Real drift risk: execute pre-flight is BATCH-ATOMIC — any symbol's last price >3% from its fixed limit rejects ALL FOUR orders. Trip bands: SPY <711.82/>755.85; EFA <98.50/>104.59; VNQ <92.21/>97.92; DBC <29.34/>31.15. If it fires: re-plan via kernel, never override.
3. No time-of-day guard exists in code for the FOMC window — C2 is operator/executor discipline, not a kernel guarantee.

## Decisions and rejections (first-class record)

- DECISION: restore persisted state verbatim and re-plan under the operator's new 30% cap; accept kernel output as-is (~49% invested, ~51% cash — the cash is the minutes hedge, consistent with neutral/risk_off skew and research's 50–70% invested expectation).
- DECISION: adopt auditor's correction of the researcher turnover-shave claim; no kernel change.
- REJECTION (historical, superseded): SPY buy blocked under old 20% cap (order.max_notional) in the ~12:58 UTC plan; no manual split was made then or now.
- REJECTION: no options today (research: ETFs only); no leverage, no shorts.
- ADVISORY (backlog, unchanged): cap-aware turnover fitting is now moot for the order cap but the fit still floor-rounds; no action.
- Kill-switch not engaged; no feed/auth/journal failures this run.

## Execution gate

NOT ARMED. No orders submitted in this phase. Execution requires explicit operator arming in-session plus per-order operator confirmation (executor sim writes always_ask). Approved orders 1–4 are queued for the execution phase only if the operator arms it, subject to C1/C2 and the batch-atomic drift bands above.

## Next steps

1. If operator arms execution after 14:30 UTC open: executor re-checks allowlist/sim-list (C1), previews each order, waits for per-order confirmation, journals via `tyche record-order`. Fills reported only from broker order state.
2. Intraday: monitor invalidation levels and the 18:30–19:30 UTC FOMC window (no initiations/re-submits); de-risk per plan on triggers.
3. After 21:00 UTC: EOD reconcile (tyche.fees.reconcile_cash), reports/2026-11-18-eod.md, persist raw + sanitized, persist day-2 NAV references (C3), deliver bundle + EOD report.