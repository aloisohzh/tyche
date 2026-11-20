# Evaluation map

How the project addresses each judging criterion, and where the evidence lives.

## Scoring criteria

| Criterion | Weight | What judges look for | Evidence |
| --- | ---: | --- | --- |
| Risk-adjusted return | 25% | Returns relative to drawdown and volatility | Volatility targeting, regime sleeves, drawdown ladder, turnover cap, paper results |
| Qoder and Cloud Agent usage | 30% | Meaningful, repeated use of Qoder and Cloud Agents | Scheduled runs, research briefs, pre-trade critiques, EOD narratives, journaled automation |
| Strategy and risk design | 30% | Coherent thesis, explicit rules, credible risk controls | DESIGN.md, ADRs, 43 tests, risk kernel, failure-mode table |
| Reusability and documentation | 15% | Another person can run and extend it | README, operations runbook, typed config, demo data, broker adapter |

## Risk-adjusted return

Controls that directly affect the ratio:

- 10% annualized volatility target, never levered.
- Regime score reduces equity exposure before drawdowns deepen.
- 4% soft and 6% hard drawdown blocks; 2.5% daily loss block.
- 95% gross, 30% position, 5% cash, 20% order notional.
- Buy-side turnover capped at 50% of NAV per day; exits are exempt.
- 20% relative drift band and a minimum trade size suppress noise.

Metrics to report daily: NAV, daily and cumulative return, realized volatility,
Sharpe (annualized), maximum drawdown, gross and net exposure, cash weight,
turnover, number of orders, blocked orders, and risk events. The backtest
harness will report the same metrics with costs and slippage.

## Qoder and Cloud Agent usage

Each scheduled run produces:

1. A pre-market brief from Moomoo news and quote skills, limited to a template.
2. A deterministic plan artifact produced by the Python core.
3. A pre-trade critique that reads the plan and flags concerns without changing
   it.
4. An end-of-day report with fills, P&L, exposure, and risk events.

Every step appends to the hash-chained journal. The Cloud Agent configuration
and prompt templates live in `.qoder/` and `templates/`, so the automation is
reproducible rather than a one-off chat session.

## Strategy and risk design

- [DESIGN.md](../../DESIGN.md) states the thesis, rules, and thresholds.
- Six ADRs record the architectural decisions and rejected alternatives.
- `tests/test_risk.py` covers each kernel invariant, including projected fills,
  the de-risking sell exemption, halt behavior, soft drawdown halving, and
  sleeve caps.
- `tests/test_strategy.py` covers momentum, regime detection in both directions,
  allocation constraints, cash fallback, and turnover scaling.
- `tests/test_execution.py` covers kline parsing, the confirmation gate,
  paper-account refusal, pre-flight rejection, and approved-only submission.
- `tests/test_journal.py` proves tamper detection.
- `tests/test_cli.py` runs the full plan pipeline end to end.

## Reusability and documentation

- Configuration is YAML with validation; no strategy parameter is hard-coded.
- The broker interface is a protocol with an in-memory implementation, so the
  core can be tested or reused without Moomoo.
- `scripts/make_demo_data.py` generates deterministic synthetic prices and an
  account snapshot; no credentials are needed to explore the system.
- The operations runbook covers installation, authentication, the daily
  routine, troubleshooting, and security.

## Five-minute verification

```bash
python scripts/make_demo_data.py
tyche doctor
tyche plan --prices data/demo_prices.csv --as-of 2026-11-16 \
  --account data/demo_account.json
tyche journal-verify
.venv/Scripts/python.exe -m pytest -q
```

Expected: a risk-on plan with four approved buys, a Markdown plan under
`plans/`, an intact journal, and a passing test suite.

## Claims we do not make

- No claim of live profitability. The competition window is paper-only.
- No claim that default parameters are optimal; they are documented priors and
  will be checked with walk-forward analysis.
- No claim that the LLM improves returns. Its role is context and
  documentation, not alpha.
