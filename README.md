# tyche

A strategy-agnostic paper-trading platform for the **Moomoo x Qoder AI Agent Paper Trading Challenge**.

tyche splits trading into two layers. The strategy layer turns market data
into target weights and order intents; v0.1 ships a regime-aware,
volatility-targeted ETF rotation as the reference strategy. The platform layer
is strategy-independent: a deterministic Python core owns data, order
construction, risk, and execution. An LLM (Qoder Cloud Agent) sits on the
perimeter: it synthesizes research, critiques plans before execution, and
writes the daily narrative. The LLM never sizes or submits an order.

> Paper trading only. The agent refuses live accounts by policy and is not
> investment advice.

> **Current state (18 Nov 2026):** v0.1 safety core is built and tested. An adversarial review
> ([docs/reviews/2026-11-18-design-review.md](docs/reviews/2026-11-18-design-review.md)) cut scope for
> the ~7-session competition window and flagged critical fixes (MCP execution, account allowlist,
> artifact persistence, fees, competition caps). The competition contract is persisted in
> [docs/competition/rules.md](docs/competition/rules.md); the doc spine is indexed in
> [docs/README.md](docs/README.md). DESIGN.md is the v0.1 baseline, partially superseded.

## Why this design

Judging weights risk-adjusted return (25%), Qoder usage (30%), strategy and
risk design (30%), and reusability/documentation (15%). The architecture is
built for those weights:

- **Risk-adjusted return**: the reference strategy is low-turnover,
  volatility-targeted rotation with regime sleeves, and every strategy trades
  through the same hard risk kernel.
- **Qoder usage**: scheduled Cloud Agent runs produce a daily brief, a
  pre-trade critique, and an end-of-day report, all journaled.
- **Strategy and risk design**: every rule is explicit, configurable, tested,
  and documented in [DESIGN.md](DESIGN.md) and the ADRs; strategies inherit
  the shared risk policy instead of reimplementing it.
- **Reusability**: typed interfaces, a broker adapter, config-driven universe
  and policy, and synthetic demo data so anyone can run it without
  credentials. A new strategy reuses the entire pipeline.

## Strategies

tyche is built around a strategy layer rather than a single trading idea. A
strategy reads price history plus YAML configuration and emits target weights
and order intents; everything downstream is shared.

- **Reference strategy (v0.1)**: regime-aware, volatility-targeted rotation
  across a configurable ETF universe. Parameters live in
  `config/strategies/pb-001.yaml` and `config/universe.yaml`.
- **Adding a strategy**: one playbook md, one `config/strategies/pb-xxx.yaml`
  (id, enabled, playbook ref, parameters), and one module registered in
  `src/tyche/strategies/` keeping `OrderIntent` as the output, so the risk
  kernel, turnover budget, order construction, broker adapter, journal, and
  LLM perimeter apply unchanged (ADR 0014). Each strategy's rules hash is
  frozen independently. Generalizing the strategy contract is tracked in
  [DESIGN.md §12](DESIGN.md#12-open-work).

## Quick start (no Moomoo account needed)

Use Python 3.13 (see `.python-version`). `.venv` is the only supported kernel
environment; the optional research venv is regenerable and never used by the kernel.

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
pip install -e ".[dev]" -c constraints.txt

python scripts/make_demo_data.py
tyche doctor
tyche plan --prices data/demo_prices.csv --as-of 2026-11-16 \
  --account data/demo_account.json
tyche journal-verify
```

The plan command writes `plans/<date>-plan.json` and `.md`, prints approved and
blocked orders, and appends a hash-chained event to `journal/events.jsonl`.

## Commands

| Command | Purpose |
| --- | --- |
| `tyche doctor` | Validate config, Moomoo CLI, skills, and journal |
| `tyche fetch [symbols...]` | Fetch daily closes through `moomoo kline` |
| `tyche plan --prices ... [--as-of ...] [--account ...]` | Compute targets, build orders, run risk kernel |
| `tyche execute --plan ... --account-id SIM-... [--yes]` | Re-validate and submit approved paper orders |
| `tyche accounts` | List simulated Moomoo accounts |
| `tyche quote US.SPY US.QQQ` | Read-only quotes through the Moomoo CLI |
| `tyche journal-verify` | Verify the audit journal hash chain |
| `tyche halt-status --json` | Report the effective kill-switch state across both flags |

## Layout

```text
config/          universe and risk policy (YAML); strategies/ one yaml per playbook
src/tyche/
  config.py      typed, validated configuration
  models.py      domain models and enums
  strategies/    registry + one module per algorithm (rotation.py is the reference)
  risk.py        deterministic pre-trade risk kernel
  journal.py     SHA-256 hash-chained JSONL audit log
  broker/        broker protocol, in-memory paper broker, Moomoo CLI adapter
  cli.py         Typer entry point
tests/           unit and end-to-end tests
scripts/         demo data generator
docs/            competition contract, scoring map, reviews, ADRs, playbooks,
                 runbooks, validation, performance, agent-engineering (see docs/README.md)
```

## Safety model

- Only paper accounts are accepted. The guard is an **allowlist** conjunction: `env == paper`,
  id in `account_allowlist` (real ids injected from vault/env, never committed), and for non-demo
  sources `account_type ∈ {1,2}` ∧ `market_id == 100` verified against the sim account list.
- Shorting is disabled and oversells are rejected.
- Hard caps: 95% gross, 40% per position (target ≤38%), 100 positions, 5% minimum cash, 30% per order,
  $1.00 minimum price. Internal order budget is 40/day (competition ceiling 200).
- Drawdown control: 4% soft (buy quantities halved), 6% hard (buys blocked).
- Daily loss limit 2.5%; daily turnover 150% of NAV on the buy side.
- Every verdict, plan, and execution is appended to the audit journal.

See [config/risk.yaml](config/risk.yaml), [config/universe.yaml](config/universe.yaml), and the
[ADRs](docs/adr/) for the current policy, and [docs/runbooks/operations.md](docs/runbooks/operations.md)
for setup and the daily runbook. [DESIGN.md](DESIGN.md) is the v0.1 baseline.

## Status

- [x] Config-driven universe, strategy, and risk policy
- [x] Strategy layer isolated from the shared risk, execution, and journal pipeline
- [x] Signals, regime detection, volatility targeting, sleeve allocation
- [x] Risk kernel with tests for every invariant
- [x] Moomoo CLI adapter and in-memory paper broker
- [x] Trade plans (JSON + Markdown) and hash-chained journal
- [x] Synthetic demo data and end-to-end test
- [x] Order execution with pre-flight revalidation and receipts
- [x] Price fetch through `moomoo kline`
- [x] Cloud Agent prompt templates and deployment spec
- [ ] Cloud Agent deployment in the Qoder workspace
- [ ] Backtest harness with costs and walk-forward validation
- [ ] Strategy protocol and strategy-agnostic plan schema
