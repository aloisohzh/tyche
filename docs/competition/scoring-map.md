# Scoring map — criterion → artifact → evidence

The judging weights are in [rules.md](rules.md). This map makes each claim verifiable:
every artifact points at evidence a judge can open. Status: `planned` / `built` / `evidenced`.
Bonus tips and the submission checklist live in [bonus-tips.md](bonus-tips.md).

## Risk-adjusted return — 25%

| Artifact | Evidence | Status |
|---|---|---|
| Fee-net equity curve, daily returns, realized vol, Sharpe, max drawdown, **SPY buy-and-hold baseline** | `tyche performance report` → `docs/performance/<date>-metrics.md` (first: [2026-11-23](../performance/2026-11-23-metrics.md)); dashboard equity panel | built (SPY closes after 17 Nov still to be supplied from a price file) |
| Per-strategy scorecard (ballast vs event sleeves), win/loss, expectancy | journal `trade.closed` rows + performance report | planned |
| Drawdown ladder + daily-loss block actually firing | rejection log by rule in the performance pack (kernel breaches, operator/broker rejections, gate waits); risk-card test | partial (log built; the ladder has not had to fire yet) |
| Turnover / order-count discipline (200/day is a ceiling, not a target) | `tyche performance report` orders-per-day table from `order.submitted` rows | built |

Note: ~7 daily marks make Sharpe a noisy estimate. The honest play is a **smooth equity curve**
(low-vol ballast + small defined-risk event sleeves), not heroic returns. Say so in the report.

## Qoder & Cloud Agent usage — 30%

| Artifact | Evidence | Status |
|---|---|---|
| Multi-agent topology: coordinator + researcher + executor + risk auditor (+ advisor) | `docs/agent-engineering.md`; exported template config with **pinned versions** | planned |
| Delegation contract + file ownership + per-child output formats | coordinator system prompt; `templates/prompts/` | planned |
| Scheduled automation (pre-market plan, intraday monitor, EOD reconcile) | schedule configs + run history; journal `run.*` events | planned |
| Least-privilege scoping (only executor holds trade tools + vault) | permission matrix in agent-engineering.md | planned |
| Dashboard + short screen capture | Sites/local dashboard reading journal + QCA events; capture file | planned |
| Reusable skills + scripts | `skills/`, `scripts/`, `src/tyche/` | partial (core exists) |
| Decision + **rejection** log | journal `order.blocked` / veto rows; dashboard rejection panel | planned |
| Version-pinned tuning loop (fixed eval prompts, diff before promote) | agent-engineering.md eval log | planned |

## Strategy & risk design — 30%

| Artifact | Evidence | Status |
|---|---|---|
| Trading thesis + edge per setup | `playbook/PB-*.md` | planned |
| **Explicit invalidation conditions** per setup and per trade | playbook invalidation section; plan artifact `invalidation` field | planned |
| Risk card: every cap keyed and asserted by a test | `config/risk.yaml` + `tests/test_risk.py` | partial (needs competition deltas) |
| Position limits, drawdown response, **kill switch (tested)** | risk kernel + halt runbook + [drill PASS record](../validation/2026-11-18-kill-switch-drill.md) | evidenced |
| Liquidity/spread gate, fee model, EOD reconcile | risk kernel + fee engine + reconcile report | planned |
| Options leg-group lifecycle + synthetic protection | `src/tyche/monitor.py` + [Level 0 drill rehearsal](../validation/2026-11-21-synthetic-breach-drill.md); defined-risk only, options still disabled | partial (detector built and rehearsed; nothing scheduled, live-session drill leg owed) |
| Pre-registration + honest "unvalidated" labeling | `docs/validation/` | planned |

## Reusability & documentation — 15%

| Artifact | Evidence | Status |
|---|---|---|
| Reference-ready agent templates (exported, pinned) | `templates/` + cloud config export | partial |
| Reusable skills/scripts, typed config, broker adapter, demo data | `src/tyche/`, `scripts/make_demo_data.py`, `config/` | built (v0.1) |
| Final report + Qoder-generated deck explaining how the agent works | `docs/report.md` + slides; links into this map | planned |
| Another person can run it | README quick start + `docs/runbooks/` | partial |

## Evidence integrity

- Journal is hash-chained; `tyche journal-verify` proves tamper-evidence.
- Raw artifacts persist to a bucket each run; **sanitized** summaries commit to git (sandbox is ephemeral).
- No credentials, tokens, or full account identifiers in any committed artifact.