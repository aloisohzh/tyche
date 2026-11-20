# tyche - Design Specification

Version 0.1, 18 November 2026. Paper trading only.

> **Status: v0.1 baseline, partially superseded.** The 2026-11-18 adversarial review
> ([docs/reviews/2026-11-18-design-review.md](docs/reviews/2026-11-18-design-review.md)) cuts scope for
> the ~7-session window and flags critical gaps: the CLI execution path moves to **MCP**, the `^SIM`
> guard becomes an **account allowlist**, artifacts must **persist** (ephemeral sandbox), **fees** are
> modeled, and competition caps replace the v0.1 numbers. Non-goals below (no options/intraday) are
> lifted: the window trades **stocks + defined-risk options**. The competition contract lives in
> [docs/competition/rules.md](docs/competition/rules.md). v0.2 will fold these in; until then read this
> file as the safety-core reference, not the current trading plan.
>
> **Live values are not quoted here.** This banner used to restate them ("40 orders/day, 150%
> buy-side turnover") and was wrong within two days of being written, which is exactly the failure
> [docs/lessons/LESSONS.md](docs/lessons/LESSONS.md) L-033 records. `config/risk.yaml` is the only
> authority, [docs/risk-card.md](docs/risk-card.md) is the asserted human view of it, and
> `config/tactical.yaml` gates the options/intraday lane. Where this document and config disagree,
> config and the ADRs win.

## 1. Thesis

Most retail "AI trading agents" fail for one of two reasons: the LLM is given
discretionary control it cannot exercise reliably, or the strategy has no
explicit risk budget. tyche separates the two. A deterministic core owns
every number that can lose money. An LLM adds research context and narrative
around that core, but cannot size, approve, or submit an order.

tyche is a platform, not a single strategy. The strategy layer consumes price
history and configuration and emits target weights plus order intents. Risk,
order construction, execution, reconciliation, and the audit journal are
strategy-agnostic and shared by every strategy. Version 0.1 ships one
strategy as the reference implementation: a regime-aware, volatility-targeted
rotation across US-listed ETFs. Its logic is isolated in `strategies/rotation.py`
and its parameters in `config/strategies/pb-001.yaml` (one file per playbook,
ADR 0014), so another strategy can be added or retired without touching the
shared pipeline or invalidating another strategy's frozen rules hash.

## 2. Goals and non-goals

Goals:

- Compete on risk-adjusted return with a transparent, reproducible process.
- Make every decision explainable from configuration and market data.
- Enforce risk limits in code, before an order reaches the broker.
- Produce a tamper-evident audit trail suitable for judging and review.
- Be runnable by another person with no proprietary data or credentials.
- Keep strategies swappable: a new strategy reuses the same risk kernel, order
  lifecycle, broker adapters, journal, and LLM perimeter.

Non-goals:

- Live trading. The agent rejects accounts that do not match `^SIM`.
- Short selling, options, crypto, or intraday execution.
- High turnover or market timing below the daily cadence.
- Letting an LLM generate orders, quantities, or prices.
- Strategy-specific logic inside the risk kernel, order lifecycle, or journal.

## 3. Architecture

```text
                 +------------------------------+
  Moomoo skills  |  Qoder Cloud Agent (LLM)     |
  news, quotes   |  daily brief, critique, EOD  |
                 +--------------+---------------+
                                | reads plans, writes commentary only
                                v
 +------------------- Python core (deterministic) --------------------+
 | prices -> strategy -> targets -> intents -> risk kernel            |
 |                                        |                           |
 |                                   trade plan (JSON + MD)           |
 |                                        |                           |
 |                              broker adapter (paper only)           |
 |                                        |                           |
 |                              hash-chained audit journal            |
 +--------------------------------------------------------------------+
                                |
                                v
                     Moomoo paper account (SIM)
```

Components:

| Module | Responsibility |
| --- | --- |
| `config.py` | Typed YAML configuration with cross-field validation |
| `strategies/` | Registry (playbook id → target function) plus one module per algorithm; `rotation.py` is the reference: momentum, regime, sizing, sleeve allocation, order intents |
| `risk.py` | Pre-trade invariant checks and quantity adjustments |
| `journal.py` | SHA-256 hash-chained JSONL audit log |
| `broker/base.py` | Broker protocol and in-memory paper broker |
| `broker/moomoo_cli.py` | Subprocess adapter for the official `moomoo` CLI |
| `cli.py` | `doctor`, `plan`, `accounts`, `quote`, `journal-verify` |

The strategy layer is the only strategy-specific code; in v0.1 it expands to
momentum signals, regime classification, volatility targeting, and sleeve
allocation. The risk kernel, order lifecycle, broker adapters, and journal
never inspect strategy internals — they evaluate `OrderIntent` values against
account state and policy, so a new strategy inherits all of them.

The LLM perimeter is deliberately outside this process. It consumes plan
artifacts and market context and produces text. A separate, explicit execution
step is the only path to the broker.

## 4. Reference strategy specification

The platform is structured around a strategy layer that emits target weights
and order intents. v0.1 runs one strategy, specified here in full so its
behavior is auditable. A replacement strategy keeps the shared risk policy
and order lifecycle but changes signals, regime logic, sizing, and allocation.
The plan schema still carries this strategy's regime metadata; generalizing
it is tracked in §12.

The reference strategy rebalances at most daily, holds at most four
instruments, and scales exposure so estimated portfolio volatility stays near
10% annualized. Its design goal is a high Sharpe ratio with shallow
drawdowns, not maximum return.

### 4.1 Universe

Eleven US-listed ETFs across four sleeves, configured in `config/universe.yaml`:

| Sleeve | Instruments |
| --- | --- |
| Equity | SPY, QQQ, IWM, EFA, EEM |
| Defensive | TLT, IEF |
| Real asset | GLD, DBC, VNQ |
| Credit | HYG |

Per-instrument caps: 30% for SPY and QQQ, 20% for EFA, GLD, and HYG, 25% for
TLT and IEF, 15% for IWM, EEM, DBC, and VNQ.

### 4.2 Momentum signal

For each instrument, compute the total return over 63, 126, and 252 trading
days, each ending five trading days before the decision date. The skip window
avoids buying into short-term reversal. Weight the horizons 0.5, 0.3, and 0.2
and normalize by the weights actually available, so a partially warmed-up
history still produces a score. Instruments with non-positive momentum are
ineligible. Rank the remainder by momentum divided by 63-day realized
volatility and select the top four.

### 4.3 Regime classification

Four binary checks, each computed from the universe itself:

| Check | Rule |
| --- | --- |
| `equity_trend` | SPY close above its 200-day SMA |
| `golden_cross` | SPY 50-day SMA above its 200-day SMA |
| `vol_calm` | SPY 20-day realized vol at most 1.25x its 252-day vol |
| `credit_trend` | HYG/IEF ratio above its 63-day SMA |

Score 3 or 4 is `risk_on`, 2 is `neutral`, 0 or 1 is `risk_off`. If history is
insufficient, the affected check is false, which biases the system toward cash.

### 4.4 Sizing and allocation

1. Inverse-volatility weights among the selected instruments.
2. Estimate portfolio volatility from the 126-day covariance matrix; fall back
   to a weighted sum of 63-day vols when history is short.
3. Scale all weights by `min(1, 10% / estimated vol)`. The core never levers.
4. Apply sleeve caps for the current regime. Capital released by a capped
   sleeve is redistributed to sleeves with room, preserving total invested
   weight. This prevents a single low-volatility credit position from forcing
   a large idle cash balance.
5. Apply per-instrument caps. Excess is redistributed within the same sleeve;
   anything that cannot be placed remains in cash.
6. Scale down if invested weight exceeds 95%. Cash is the residual and is
   always at least 5% by construction.

Regime sleeve caps:

| Regime | Equity | Defensive | Real asset | Credit |
| --- | ---: | ---: | ---: | ---: |
| risk_on | 80% | 40% | 25% | 15% |
| neutral | 50% | 50% | 20% | 10% |
| risk_off | 20% | 60% | 30% | 0% |

### 4.5 Rebalancing and order construction

- Skip a trade if notional is below `max($500, 0.5% of NAV)`.
- For held positions with a positive target, skip if the weight gap is below
  20% of the larger of current and target weight. This is a relative drift band.
- Exits always trade in full; no band applies when the target is zero.
- Sells are emitted before buys and sorted by notional.
- Limit price is the last price plus 0.1% for buys and minus 0.1% for sells.
  The risk kernel rejects any limit more than 3% away from the last price.
- Buy-side notional for the day is capped at 50% of NAV. If the plan exceeds
  it, buy quantities are scaled proportionally. De-risking sells are exempt.
  This produces a deliberate two-day entry instead of forcing a full position
  in one session.

## 5. Risk policy

The kernel is strategy-agnostic: it evaluates order intents against account
state and policy, not against a particular strategy. All rules are evaluated
before an order is considered executable. Any breach blocks the order; there
is no override flag. Sells that reduce exposure remain allowed while buys are
blocked.

| Rule | Threshold | Behavior |
| --- | --- | --- |
| Account | ID matches `^SIM` | Reject |
| Market | US only | Reject |
| Universe | Must be configured | Reject |
| Price available | Last price > 0 | Reject |
| Minimum price | $0.50 | Reject |
| Limit deviation | 3% from last | Reject |
| Order notional | 30% of NAV | Reject |
| No shorting | Sell quantity <= held | Reject |
| Minimum order | $500 unless closing | Reject |
| Halt | Agent halted | Block buys |
| Soft drawdown | 4% from high-water NAV | Halve buy quantity |
| Hard drawdown | 6% from high-water NAV | Block buys |
| Daily loss | -2.5% versus prior close | Block buys |
| Position cap | 30% of NAV post-trade | Reject |
| Gross exposure | 95% of NAV post-trade | Reject |
| Minimum cash | 5% of NAV post-trade | Reject |
| Sleeve cap | Regime table | Reject |
| Daily order count | 6 orders | Reject |
| Daily turnover | 50% of NAV, buys only | Reject |

Position, gross, and sleeve caps apply to buys only. A sell that reduces
exposure is always permitted, even if the position is already above its cap;
otherwise the agent could be locked into an overweight position. Caps carry a
0.25% NAV tolerance to avoid false rejections from mark-to-market drift. The
minimum cash floor has no tolerance.

Drawdown is measured against the high-water NAV, not the prior close, so a
slow bleed is treated as seriously as a one-day shock. When the high-water
mark is unavailable, the prior close is the fallback.

## 6. Order lifecycle

1. **Ingest.** Load a long-format price CSV (`date,symbol,close`) and an
   account snapshot JSON. The snapshot includes positions, cash, and optional
   `prior_close_nav` and `high_water_nav`.
2. **Signal.** Run the strategy to turn price history into target weights.
3. **Intent.** Convert weight gaps into explicit limit orders.
4. **Budget.** Scale buy-side notional to the daily turnover cap.
5. **Risk.** Evaluate each intent in sequence, updating state for each approved
   order so that daily counts and turnover accumulate. Record every verdict.
6. **Artifact.** Write `plans/<date>-plan.json` and `.md`, then append a
   `plan.created` event to the journal.
7. **Review.** The LLM critique reads the plan and context and writes a
   pre-trade note. It cannot modify the plan.
8. **Execute.** A separate explicit step submits only approved orders to the
   paper account, after re-validating the account and prices.
9. **Reconcile.** Compare submitted orders with broker order history and
   positions. A submit is not a fill; unfilled orders expire or are canceled
   explicitly. Execution re-fetches quotes and the account list and rejects the
   whole batch before submitting anything if pre-flight fails.
10. **Report.** Write an end-of-day report with fills, P&L, exposure, drift,
    and any risk events, and journal it.

## 7. LLM perimeter contract

The LLM may:

- Summarize news, sector context, and macro events from Moomoo skills.
- Critique a plan against the regime and risk policy, flagging concerns.
- Draft the daily brief and end-of-day report in natural language.
- Propose research hypotheses for human review.

The LLM may not:

- Produce or modify order intents, quantities, prices, or targets.
- Approve, bypass, or reinterpret a risk breach.
- Submit orders or change configuration.
- Access tokens, credentials, or live account identifiers.

Every LLM output is text or a validated summary object. If a critique is empty
or malformed, the deterministic plan proceeds unchanged. The system does not
depend on LLM availability for safety or execution.

## 8. Qoder Cloud Agent automation

A scheduled run executes a fixed sequence:

1. Check data freshness and `moomoo auth status`.
2. Fetch the latest daily closes (or fail loudly if stale).
3. Run `tyche plan`.
4. Read the plan artifact and write the pre-trade critique using the critique
   template.
5. Execute approved orders only if a human operator has enabled execution for
   the run; otherwise stop at the plan.
6. After the close, fetch fills and positions and write the EOD report.
7. Verify the journal hash chain.

Failed steps stop the run and journal the failure. Automation never retries a
submit blindly; it reconciles broker state first.

## 9. Audit journal

`journal/events.jsonl` is append-only JSON Lines. Each record contains `ts`,
`type`, `payload`, the previous record's hash, and its own SHA-256 hash over a
canonical JSON encoding. Event types include `plan.created`, `order.approved`,
`order.blocked`, `order.submitted`, `order.filled`, `order.rejected`,
`report.published`, and `run.failed`. `tyche journal-verify` recomputes the
chain and reports the first broken record. Editing or deleting any record
breaks every subsequent hash.

## 10. Failure modes

| Failure | Detection | Response |
| --- | --- | --- |
| Stale prices | Last bar older than the decision date | Do not trade; journal and report |
| Missing instrument | No series or NaN signal | Exclude it; cash absorbs the weight |
| Moomoo CLI missing | `doctor` check | Plan only; no execution |
| Auth expired | `moomoo auth status` fails | Stop; require interactive re-login |
| Broker rejects order | Non-zero CLI exit | Journal rejection; do not retry blindly |
| Partial fill | Order history shows remaining quantity | Reconcile; cancel or re-plan next run |
| Risk breach | Kernel verdict | Block order; keep de-risking sells available |
| Drawdown limits | High-water NAV | Halve or block buys automatically |
| Journal tampering | Hash chain mismatch | Stop the run; require investigation |
| LLM unavailable | Missing critique | Continue with deterministic plan |

## 11. Evaluation mapping

| Criterion | Weight | Evidence |
| --- | ---: | --- |
| Risk-adjusted return | 25% | Volatility targeting, regime sleeves, drawdown controls, turnover cap, backtest and live paper results |
| Qoder and Cloud Agent usage | 30% | Scheduled Cloud Agent runs, research briefs, critiques, EOD reports, journaled automation |
| Strategy and risk design | 30% | This document, tested invariants, explicit thresholds, failure handling, a strategy-agnostic risk kernel |
| Reusability and documentation | 15% | README, operations runbook, ADRs, typed config, demo data, broker adapter, strategy layer separated from the shared pipeline |

## 12. Open work

- Backtest harness with transaction costs, slippage, and walk-forward splits.
- Automate the account snapshot from `moomoo sim account funds` and
  `moomoo sim position` instead of a hand-written JSON file.
- Cloud Agent deployment: built and running (desk, researcher, executor, risk
  auditor). The stale draft spec this bullet pointed at is archived to
  `archive/cloud-agent-draft-2026-11.md`; current rules live in
  `docs/agent-rules.md` and the topology in `docs/agent-engineering.md`.
  Remaining: the live prompts carry caps that have drifted from
  `config/risk.yaml` and need a re-pin.
- Parameter sensitivity and decay analysis before the trading window.
- Post-trade reconciliation report that matches order IDs to fills.
- Strategy protocol and strategy-agnostic plan schema so strategies other than
  target-weight rotation plug in without touching core models.
