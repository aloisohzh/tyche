# Adversarial design review — 18 Nov 2026

Reviewer stance: assume the design fails until proven otherwise. Goal of tyche: **make money like a
professional trader with strict risk management and human-in-the-loop where it matters** — and score
maximum points in a ~7-session paper window. Over-engineering is a failure mode, not a feature.

## Verdict

The safety core is genuinely good (deterministic kernel, tested invariants, hash-chained journal,
LLM kept outside sizing/submission). But the design as it stands **repeats fortuna's mistake**:
months of governance machinery wrapped around an unvalidated edge. Three structural problems would
sink it in this window, and several proposed v0.2 additions are over-built for 7 sessions.

1. **The execution path probably does not work in the cloud.** v0.1 submits via a subprocess
   `moomoo` CLI with an interactive OAuth browser flow. A cloud sandbox cannot complete that login,
   and the verified competition path is the **Moomoo MCP**. The whole execute step is at risk.
2. **Evidence evaporates.** The sandbox is ephemeral; `journal/`, `plans/`, `reports/` are gitignored.
   Without a persistence step, the decision log and fills — 60% of the judging weight — vanish after
   each run.
3. **There is no edge, and the reference strategy barely trades in-window.** Slow 63/126/252-day
   momentum rotation is market beta, not alpha; over 7 sessions it will mostly sit still. Judges
   reward a thesis + invalidation + activity, not a static ETF book.

And the clock: **~7 sessions** (18, 19, 20, 23, 24, 25, 27 Nov; 26 closed; 27 half-day 13:00 ET).
Sharpe over ~7 daily marks is noise. You cannot reliably out-return the market in 7 days. You **can**
out-engineer, out-discipline, and out-document it — 60% of the score is engineering + design, 15% docs.
Optimize for a **smooth, fee-net equity curve and impeccable evidence**, not a backtested alpha fantasy.

## Critical gaps (must fix; all cheap)

| # | Gap | Fix |
|---|---|---|
| G1 | CLI subprocess + OAuth in cloud sandbox | Replace with an **MCP adapter** behind the existing broker protocol. Auth = Market Data permission only. |
| G2 | `^SIM` guard rejects the real competition account (numeric id, type 2, market 100) | Allowlist: id in vault/env + sim-account-list source + `account_type==2` + `market_id==100` + `env==paper`. Full id never committed. |
| G3 | Ephemeral sandbox loses journal/plans/reports | **Persist every run**: raw → OSS bucket; sanitized summaries → git push. This is load-bearing for judging. |
| G4 | No fees modeled (handbook mandates) | Fee engine (`FeeRecord`, source `model`) on every fill; daily financing accrual; EOD cash reconcile with `fees.unreconciled`. |
| G5 | Stale competition caps | min price **$1.00** (not $0.50); single-asset **40%** (target 35–38%); 200 orders/day; 100 positions; margin/financing; forced-liq guard. |
| G6 | Options absent from models; sim has no stops; ITM auto-exercise | Defined-risk only (single-leg long or verticals as **leg groups**); synthetic protection monitor; **flatten before expiry/final close**; count option exposure toward the 40% cap conservatively. |
| G7 | Final-day settlement | Flat/hedged by **12:45 ET 27 Nov**; after-hours excluded; no overnight reliance. |
| G8 | Human-in-the-loop undefined for scheduled runs | Concrete **standing authorization** switch + per-plan arm (hash) + halt/veto. Paper: arm once daily; live (parked): per-order step-up. |
| G9 | No liquidity/spread gate; sim volume×20 partial fills | ADV / dollar-volume + spread filter; **limit orders only**; size below the volume×20 threshold. |
| G10 | Kill switch documented, never tested | Run a **journaled kill-switch drill** on the personal paper account; evidence it. |

## Over-engineering to cut (park until after the competition)

- **Six planes / six agents / Docker "USB" strategy containers.** The handbook itself prescribes a
  3-role topology (researcher / executor / risk auditor) + coordinator + advisor. Use that.
  Strategies are **in-process plugins** behind a contract; containers/self-hosted are post-window.
- **14 ADRs.** Keep the 6 existing; add only the decisions actually made now (~4). Park the rest.
- **Pre-registered gauntlet, rotated null, 500 nulls, 30-trade checkpoints, 20-trade floors.** None can
  complete in 7 sessions. Replace with: pre-register simple rules, **label the edge unvalidated**, size
  small, and keep a NO-GO ledger. Full validation is post-competition work.
- **Golden-set prompt regression, Outcome rubrics, four-key live-flip governance, fee-calibration
  round-trip.** Park. Keep the *seams* (Env enum, adapter protocol, version pins) so live is a later flip.
- **A dashboard "platform".** One page generated from the journal + QCA events, plus a screen capture.
  The handbook rewards a dashboard, not a product.
- **Full backtest harness / walk-forward.** Park. If time permits, a cheap historical sanity check on
  equities via MCP kline (options history is unavailable).

## Strategy critique — the money question

- **Keep the rotation as low-vol ballast, not as the edge.** A 10%-vol, regime-aware ETF book is a
  reasonable answer to the 25% risk-adjusted criterion *if the market is calm*, and it satisfies ≥3
  tickers and the 40% cap. But it is beta. Do not sell it as alpha.
- **The edge story for this window is event-driven + intraday, small and defined-risk:** FOMC minutes
  (18 Nov 14:00 ET), PCE + Beige Book (25 Nov), sector-rotation heat, first/last-hour liquidity.
  Pre-register **2–3 setups**, each with an explicit **invalidation** and a time exit. Honest label:
  unvalidated, small size, event-driven. This is what "strategy & risk design" (30%) actually rewards.
- **Smooth curve beats heroics.** With ~7 marks, avoid big down days; cash is a position; 200 orders/day
  is a ceiling, not a target. Ballast + small event sleeves can produce a low-drawdown curve that scores
  well on risk-adjusted return without needing to beat SPY on raw return.
- **Concentration:** 40% cap → ballast ETFs + 2–3 event names; never let one name approach 40% on entry.

## What to keep (the professional core)

Deterministic risk kernel + tests · plan artifact with **thesis + invalidation + size** · hash-chained
journal · human **arm / halt / veto** · fee-net records · EOD reconcile · event calendar · liquidity gate ·
protection monitor (1–2 min) · MCP adapter · one dashboard · daily digest · final deck.

## Minimal architecture for the window

```text
Coordinator (Desk Head)  — no trade tools, no vault
  ├─ Researcher child    — quote/news MCP only; candidate list + event scan
  ├─ Risk auditor child  — read-only; separate thread; says NO; drawdown report
  ├─ Executor child      — ONLY agent with sim trade tools + moomoo vault; runs deterministic core
  └─ Advisor             — model-only second opinion before arming a plan
Deterministic Python core: data → strategy → targets → intents → risk kernel → plan artifact
                           → (human arm) → MCP submit → reconcile → journal → persist
Schedules: pre-market plan · intraday monitor (1–2 min, regular session) · EOD reconcile + report
```

LLM never sizes or submits. Sizing, risk, fees, journal are code. Auditor approval is required before
the executor acts on researcher output (handbook §8.2). Child versions pinned; coordinator prompt
states delegation criteria, output formats, and file ownership.

## Decisions needed (operator)

1. Approve the **cut list** (park gauntlet/Docker/6-agent/live-flip governance/rubrics).
2. Approve the **3-role + coordinator + advisor** topology.
3. Approve **ballast + small event sleeves** as the window strategy, labeled unvalidated.
4. Approve **persistence**: raw → bucket, sanitized → git (needs an OSS bucket + a least-privilege PAT).
5. Confirm scope: **stocks + defined-risk options**, no naked shorts, no direct shorting.

## Ordered backlog (time-boxed)

- **P0 (before any competition order):** G1 MCP adapter · G2 account allowlist · G3 persistence ·
  G4 fees · G5 caps · G10 kill-switch drill on personal paper.
- **P1:** event playbooks (2–3) + plan `invalidation` field · intraday monitor · dashboard · daily digest.
- **P2:** options leg-group lifecycle + synthetic protection · liquidity/spread gate hardening.
- **P3:** final report + Qoder-generated deck + screen capture; scoring-map evidence pass.
- **Parked (post-window):** gauntlet/rotated null · Docker strategy containers · 6-agent expansion ·
  golden-set regression · Outcome rubrics · four-key live flip · full backtest harness.

## Housekeeping done with this review

- Archived stale demo artifacts: `plans/2026-11-16-plan.{md,json}` → `docs/archive/`.
- Superseded `docs/evaluation.md` → `docs/archive/evaluation-v0.1.md`; living version is
  `docs/competition/scoring-map.md`.
- `docs/operations.md` → `docs/runbooks/operations.md` (v0.1 CLI path; MCP revision pending G1).
- Persisted the competition contract: `docs/competition/rules.md` (tmp fetches expire).
- New doc spine: `docs/README.md` index + conventions; `playbooks/`, `validation/`, `performance/`,
  `agent-engineering.md`, `adr/README.md`.
- Status banners added to `DESIGN.md`, `.qoder/cloud-agent.md`, `README.md` marking v0.1 baseline.
- **Not committed** (repo has zero commits). First commit + push is the next step so the cloud
  template can mount the repo.