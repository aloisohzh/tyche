# Desk narrative — 2026-11-18 (PRE-MARKET)

- Desk: tyche (Moomoo x Qoder AI Agent Paper Trading Challenge, day 1 of window 17–28 Nov 2026)
- Phase: pre-market, scheduled run. Clock at plan build: 12:59 UTC; narrative written ~13:05 UTC. Session 14:30–21:00 UTC.
- Account: competition paper account ****2598 (env=paper, account_type=2, market_id=100, source=sim_list; allowlist matched via TYCHE_ALLOWED_ACCOUNT_IDS). Full id never written in reports.
- Kill-switch: NOT engaged (no halt.json). Journal: chain intact (1 event: plan).

## Inputs and provenance

| Artifact | sha256 | Verified |
|---|---|---|
| plans/2026-11-17-plan.json | dbd2e15d9c025973009db5b364914827e6075bbf685067c9bf0fd28dedc03241 | desk head, 12:59 + 13:04 UTC |
| data/prices.csv | 7e6500d583c204fafa70ed76e3190f4bf8ae4c39a0c458ae0b39e373db9b4b52 | 11 symbols x 370 bars, 2025-05-30..2026-11-17 |
| runs/2026-11-18/snapshot.json | 85c44c60af1a051d386c690449b185b9fa517d80c15eaa3fa2b4dcf9048dff39 | NAV 100,000.00 USD, cash 100,000.00, 0 positions |
| config/risk.yaml | 9f1ac093609097c23d6ddee8c7dc149ea496b122d75b7b82f85cfa2a7a3bea9c | unchanged pre/post audit |
| config/strategy.yaml | bdcff4418a2ad856d3da7e2c286de5d8808a0b50f5181e6ecd5cb14e2874d1e5 | unchanged |
| config/universe.yaml | a7b97e01de7a7cb985336779d997c22871d1ee9c8e477032d5eb067f8e2365d0 | unchanged |

Pipeline: researcher fetched all 11 universe klines via MCP (num=370, daily, forward-adjusted; all ret_code=0) and wrote reports/2026-11-18-research.md. Researcher session lacks a shell tool, so the desk head ran scripts/mcp_prices.py on the persisted MCP payloads (/tmp/tool-outputs/mcp_*.txt) to produce data/prices.csv — no prices transcribed or fabricated. Executor fetched accounts/cash/positions via MCP and produced the snapshot via `tyche snapshot`. Plan built with the deterministic kernel: `tyche plan --prices data/prices.csv --account runs/2026-11-18/snapshot.json` (as-of last close 2026-11-17). No quantities invented or altered.

## Regime and thesis

Kernel regime: **neutral** (2/4 checks: equity_trend PASS, golden_cross PASS, vol_calm FAIL, credit_trend FAIL). Portfolio vol estimate 8.71%, vol scale 1.00. Research concurs: neutral with risk_off skew — SPY only +0.7% above its 200d SMA (flip zone ~725–730), 20d/252d vol ratio ~1.65, HYG/IEF below its 63d SMA, Fed hiking risk and geopolitical escalation vs NVDA beat bounce. Research news content treated as untrusted data; FOMC-minutes timing unconfirmed (calendar API empty).

Targets: SPY 30%, CASH 30%, EFA 20%, VNQ 10.96%, DBC 9.04%. Only 4 assets pass absolute momentum (= top_n).

## Plan and risk verdict

| # | Order | Kernel | Auditor | Rule ids / notes |
|---|---|---|---|---|
| 1 | BUY US.SPY 28 @ 733.17 (~$20,528.76) | BLOCKED (qty 0 in plan) | REJECT — block confirmed correct | order.max_notional: 20.53% NAV > 20% cap. No split, no re-plan (deterministic identical). |
| 2 | BUY US.EFA 142 @ 101.45 = $14,405.90 | APPROVED | APPROVE | 14.41% NAV; limit +0.099% vs close 101.35; all rules pass |
| 3 | BUY US.VNQ 83 @ 94.98 = $7,883.34 | APPROVED | APPROVE | 7.88% NAV; +0.095% vs 94.89; RTH limit only |
| 4 | BUY US.DBC 215 @ 30.22 = $6,497.30 | APPROVED | APPROVE | 6.50% NAV; +0.099% vs 30.19; thin book — accept non-fill, never chase |

**OVERALL AUDIT VERDICT: APPROVE** (orders 2–4 as written, conditions C1–C4; SPY stays blocked). Full report: reports/2026-11-18-audit.md. Auditor independently reproduced kernel sizing (turnover factor 0.72180 applied to pre-fit qty 40/197/115/299) and all cap math. Post-trade if all 3 fill: gross 28.76%, cash 71.21% (incl. $2.97 modeled fees), turnover 28.79% <= 50%, equity sleeve 14.39% <= 50%, real_asset sleeve 14.37% <= 20%. (Desk head's delegation estimate of ~17.4% real_asset was wrong; auditor's recomputed 14.37% governs.)

Audit conditions:
- **C1**: execute-time allowlist + sim-list re-check before any submit.
- **C2**: RTH-only limit orders; no chasing DBC/VNQ; accept non-fills.
- **C3**: EOD reconcile_cash and persist prior-close/high-water NAV. Day-1 inert drawdown/daily-loss guards acceptable today (flat account, no history); **day 2 without a NAV reference = REJECT**.
- **C4**: SPY stays blocked. Kernel-owner observation: turnover-budget floor-rounding landed SPY at 20.53% (27 shares would fit) — conservative failure mode; candidate future cap-aware sizing fix, no action today.

Verification limits disclosed by auditor: no shell in its session, so sha256 pins and journal chain were verified content-level by the auditor and recomputed by the desk head (all match, table above). Allowlist env var not readable in auditor session; kernel account guard passed at plan time.

## Decisions and rejections (first-class record)

- DECISION: accept kernel plan as-is; ~71% cash day-1 posture is defensible under neutral-with-risk_off-skew regime. Research expected 50–70% invested; divergence is an observation, not a breach (SPY block is the cause).
- REJECTION: SPY buy remains blocked (order.max_notional). No manual split, no quantity edits, no re-plan.
- REJECTION: no options day 1 (research: ETFs only).
- ADVISORY (researcher, next run): VNQ invalidation close < 94.78 sits only 0.12% below prior close — widen.
- ADVISORY (kernel owner, backlog): cap-aware order sizing so a 30% target can fill within the 20% single-order cap (e.g., 27 SPY shares). Not promoted to a playbook; no config change today.
- Kill-switch not engaged; no feed/auth/journal failures. Immediate Telegram risk alert for the SPY block sent 12:59 UTC (ok, message_id 5).

## Execution gate

NOT ARMED. No orders submitted in this phase. Execution requires explicit operator arming in-session plus per-order operator confirmation (executor sim writes always_ask). Approved orders 2–4 are queued for the execution phase only if the operator arms it.

## Next steps

1. Operator: arm execution (or decline — default is no trade).
2. If armed: executor re-checks C1, previews each order, submits only on per-order confirmation, journals via `tyche record-order`.
3. Intraday: monitor fills; invalidation — SPY close < ~727.5 flips risk_off (equity cap 0.20, credit 0); de-risk per plan.
4. EOD (after 21:00 UTC): reconcile fills+fees (`tyche.fees.reconcile_cash`), write reports/2026-11-18-eod.md, persist prior-close/high-water NAV (C3), persist raw+sanitized, deliver artifacts.

## Persistence addendum (13:07 UTC)

- Raw bundle (22 files: snapshot JSONs, plan json+md, journal, 3 reports, prices.csv, 11 MCP kline payloads) persisted to /data/drive/tyche-raw/2026-11-18-premarket — verified 22 files on Drive.
- Sanitized copies written to docs/performance/2026-11-18 (22 files). Sanitize gate: PASS (no full account ids or auth tokens; checked programmatically against TYCHE_ALLOWED_ACCOUNT_IDS).
- Local commits e85651e + 509a025 created. Note: root .gitignore patterns `reports/`, `plans/`, `journal/` match at any depth and silently shadowed those subdirs of the sanitized sink; fixed via explicit `git add -f` of the sanitized set (22 files now tracked). **Git push FAILED: HTTP 403 "Permission to aloisohzh/tyche.git denied"** on both the vault credential helper and the env-token fallback (tokens never printed). The configured PAT appears to lack repo push scope — operator action needed (persistence runbook provisioning step 2: least-privilege push PAT). Sanitized state is backed up to Drive (/data/drive/tyche-raw/2026-11-18-sanitized-git/, incl. a git bundle of main); push must be retried after the PAT is fixed. No further credential attempts made.
- This is a persistence-sink permission failure, not a trading feed/auth/journal failure: market data, account guard, and journal chain all verified OK. Kill-switch NOT engaged on this basis; flagged to operator in the Telegram digest.