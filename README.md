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

> **Current state (20 Nov 2026):** the paper desk is running end to end - deterministic kernel, MCP
> execution behind the paper-only allowlist, hash-chained journal, Telegram sentinel, and four pinned
> Qoder Cloud Agents (desk, researcher, executor, risk auditor). 496 tests pass. What is real, partial
> and planned is itemised in the [refinement audit](docs/reviews/2026-11-20-platform-refinement-audit.md)
> and the [playbook roster](playbook/INDEX.yaml); the live rules are in
> [docs/agent-rules.md](docs/agent-rules.md). Known open defects are tracked as lessons, not hidden:
> the auditor prompt quotes caps that no longer match `config/risk.yaml` (L-033), and no producer writes
> the `rules.refrozen` journal event the freeze contract assumes (L-035). Every lane's rules hash is now
> computable and asserted in CI (L-036, L-037 closed 20 Nov 2026). DESIGN.md is the v0.1 baseline,
> partially superseded.

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
  (id, enabled, parameters - the thesis link goes in `playbook/INDEX.yaml`, never in the frozen
  file), and one module registered in `src/tyche/strategies/` keeping `OrderIntent` as the output, so
  the risk kernel, turnover budget, order construction, broker adapter, journal, and
  LLM perimeter apply unchanged (ADR 0014). Each lane's rules hash is frozen independently from the
  file named in `PLAYBOOK_LANES` (`src/tyche/config.py`); an id that resolves to no file is a build
  failure, not a silent block. Generalizing the strategy contract is tracked in
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
| `tyche strategies [--json]` | Show which playbook lanes are live, what decides each one, and its frozen rules hash |
| `python dashboard/server.py` | Local operator desk on <http://127.0.0.1:8765> (loopback only, no auth) |

## Layout

```text
documentation/   the product description: PRD (status per capability), architecture, changelog
config/          universe, risk policy and the tactical/scalp lanes (YAML);
                 strategies/ holds one frozen yaml per playbook id
playbook/        one thesis file per setup + INDEX.yaml roster; agent-loadable
src/tyche/
  config.py      typed, validated configuration
  models.py      domain models and enums
  strategies/    registry + one module per algorithm (rotation.py is the reference)
  risk.py        deterministic pre-trade risk kernel
  journal.py     SHA-256 hash-chained JSONL audit log
  broker/        broker protocol, in-memory paper broker, Moomoo CLI + MCP adapters
  cli.py         Typer entry point
dashboard/       local desk server + static UI (the authored copy)
desk-site/       the hosted site: web/ is exported from dashboard/ by scripts/export_dashboard.py,
                 functions/ is authored here, and web/data/*.json is the feed the site serves (L-039)
scripts/         cloud agent deploys, price/feed fetches, dashboard and site exports
tests/           unit and end-to-end tests
docs/            ADRs, lessons, runbooks, validation, performance, competition, reviews
                 (index: docs/README.md)
archive/         superseded artifacts, one MANIFEST.md row each
runs/  journal/  plans/  reports/    runtime evidence and scratch, gitignored
```

## Safety model

- Only paper accounts are accepted. The guard is an **allowlist** conjunction: `env == paper`,
  id in `account_allowlist` (real ids injected from vault/env, never committed), and for non-demo
  sources `account_type ∈ {1,2}` ∧ `market_id == 100` verified against the sim account list.
- Shorting is disabled and oversells are rejected.
- Hard caps: 95% gross, 40% per position (target ≤38%), 100 positions, 5% minimum cash, 30% per order,
  $1.00 minimum price. Internal order budget is 120/day (competition ceiling 200).
- Drawdown control: 4% soft (buy quantities halved), 6% hard (buys blocked).
- Daily loss limit 2.5%; daily turnover 300% of NAV on the buy side.
- Every verdict, plan, and execution is appended to the audit journal.

Product scope, per-capability status and the open defect list are in [documentation/PRD.md](documentation/PRD.md); how the system is wired is in [documentation/architecture.md](documentation/architecture.md).

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
- [x] Cloud Agent roster deployed and pinned (desk, researcher, executor, risk auditor)
- [ ] Backtest harness with costs and walk-forward validation
- [ ] Strategy protocol and strategy-agnostic plan schema
