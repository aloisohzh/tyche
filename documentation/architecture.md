# tyche architecture

**Status: current as of 2026-11-20.** This file describes how the system is built today. Product scope
and per-feature status live in [PRD.md](PRD.md); why a shape was chosen lives in
[../docs/adr/](../docs/adr/); how to operate it lives in [../docs/runbooks/](../docs/runbooks/).
[../DESIGN.md](../DESIGN.md) is the v0.1 baseline and is partially superseded.

## The one rule that organizes everything else

Money decisions are made by deterministic code. An LLM may read state, write prose, critique a plan and
be ignored - it may never size an order, approve a risk breach, or submit. This is
[ADR 0001](../docs/adr/0001-hybrid-architecture.md) (hybrid) plus
[ADR 0006](../docs/adr/0006-llm-perimeter.md) (perimeter), and it is the reason the diagram below has a
one-way boundary rather than a loop.

```text
  CONTROL PLANE (schedules, humans, notifications)
  +------------------------------------------+        +-------------------------------------+
  | Qoder Cloud Automation                   |        | Operator                            |
  |  one card per month                      |        |  desk console + browser             |
  |  cron 5 8,12,15 <trading days> ET        |        |  127.0.0.1:8765                     |
  |  08:05 plan | 12:05 watch-only | 15:05   |        +-----------------+-------------------+
  +-----+------------------------------------+                          |
        | delegates                                          GET /api/state, /api/automation
        v                                          POST /api/halt, /api/approvals/arm|disarm
  +-------------------------------------------------------+  +-------------------------------+
  | LLM PERIMETER  (Qoder Cloud Agents, no order sizing)  |  | Local desk                    |
  |  tyche-desk v28        coordinator, narrative         |  |  dashboard/server.py          |
  |  tyche-researcher v16  discovery, 24 moomoo reads     |  |  stdlib ThreadingHTTPServer   |
  |  tyche-executor v15    broker reads + paper submit    |-->  writes data/approvals.json,   |
  |  tyche-risk-auditor v6 per-order audit, no clock      |  |  data/halt.json; commits+pushes |
  +---------------------------+---------------------------+  +-------------------------------+
                              | text, proposals, audit verdicts (advisory)
                              v
  +=======================================================================================+
  | DETERMINISTIC KERNEL  src/tyche  (Python 3.13, Typer CLI, the only path to a trade)   |
  |                                                                                       |
  |  data          signals + regime            intents                verdict             |
  |  prices.csv -> rotation / tactical / scalp -> OrderIntent -------> risk.py            |
  |  account.json  (one lane per playbook id)                          |                  |
  |       ^                  |                                          v                  |
  |       |                  +--> pipeline.py: rules_hash, plan/order   approved|blocked   |
  |       |                        envelopes, conviction, act/wait           |              |
  |       |                                                                  v              |
  |       |                                             lifecycle.py decide/tick/reserve     |
  |       |                                             approvals.py envelope gate           |
  |       |                                                                  |              |
  |       |  accounts/cash/positions.json                                    v              |
  |       +---- broker/mcp_json.py  <--------- executor writes <---------  execution         |
  |                                                                                         |
  |  every step appends to journal/events.jsonl (SHA-256 hash chain, verify_chain)          |
  +=======================================================================================+
                    | paper only: env==paper AND id in allowlist AND type in {1,2} AND market 100
                    v
            Moomoo paper account  (MCP sim_trade_* in the cloud; moomoo CLI locally)

  SIDE CHANNELS (never a control path)
   scripts/telegram.py            outbound-only sentinel; no inbound approvals (L-003, L-006)
   tyche persist / persist.py     raw run -> Qoder Drive locker, sanitized -> git (ADR 0009)
   scripts/export_dashboard.py    dashboard/ -> desk-site/ snapshot + hosted function routes
```

## Layers and components

### 1. Configuration (typed, validated at load)

`src/tyche/config.py` loads `config/risk.yaml`, every `config/strategies/*.yaml`, `config/tactical.yaml`,
`config/scalp.yaml` and `config/universe.yaml` into Pydantic models with cross-field validation
(`AppConfig` at `config.py:238`, `load_config` at `:296`). Load-time checks enforce symbol-disjointness
between the universe and the short-horizon lanes and that allocation caps sum inside gross exposure
(`:323-331`). Account ids are injected from `TYCHE_ALLOWED_ACCOUNT_IDS` and never committed.

`PLAYBOOK_LANES` (`config.py:23`) is the contract that says which file freezes each playbook id and which
switch turns it on; `rules_path_for()` (`:31`) resolves it. Ids not in the table fall back to the
`config/strategies/<id>.yaml` convention, so a new rotation lane needs no code edit. Rationale and the
bug it fixed: [ADR 0014](../docs/adr/0014-per-strategy-isolation.md) and L-036/L-037.

`config/events.yaml` is the one exception: not part of `AppConfig`, read ad hoc by
`market_calendar.load_overlay()` and written by `events_cli.py`.

### 2. Strategy lanes (three, one output type)

Every lane emits `OrderIntent` ([`models.py:133`](../src/tyche/models.py)) so everything downstream is
shared. Lanes are not pluggable through one interface yet - see "Known debt".

| Lane | Id | Module | What it does |
|---|---|---|---|
| Rotation ballast | PB-001 | `strategies/rotation.py` | momentum + regime detection + volatility targeting + sleeve allocation over the ETF universe; low turnover |
| Tactical | PB-002 stock, PB-003 option | `tactical.py` | event/catalyst setups, `plan_tick` state machine, `setup_hash`/`order_hash` identity; option leg behind `options_enabled` |
| Scalp | PB-004 | `scalp.py` | 1-minute breakout, hard 0.25% stop, 20-minute timeout, flat before close, deterministic thesis text |

Theses, classification and validation status are in [../playbook/](../playbook/README.md); the roster is
`playbook/INDEX.yaml`.

### 3. Risk and authorization (deterministic, three separate gates)

1. **`risk.py`** - pre-trade invariants per intent (`evaluate_intent` at `:31`): paper-only account,
   price floor, position and gross caps, order notional, turnover, daily loss, drawdown ladder
   (soft halves buys, hard blocks them). Returns `RiskVerdict` with named breaches; it adjusts quantity,
   it does not veto silently.
2. **`approvals.py`** - the operator envelope: a bounded, same-day, git-tracked authorization
   (`data/approvals.json`) that lets paper orders proceed without per-order clicking. Removing it is
   `POST /api/approvals/disarm` or `tyche halt`.
3. **`lifecycle.py` + `lifecycle_cli.py`** - the live decision core for held positions: `decide` at `:386`
   computes exit/hold actions from a `MarketSnapshot`, `tick` advances state, `reserve` performs the
   pre-submit sequence (journal chain verify, NAV reconcile, re-run of the tick, approval and rules-hash
   match, unresolved-order check, daily cap, deadlines) and writes a durable reservation *before* one
   submit is authorized. A submit is never treated as a fill (L-012, L-015, L-016).

`trade_risk.py` computes R-multiple expectancy from journaled fills so round trips close
([ADR 0016](../docs/adr/0016-per-trade-risk-budget.md)); `strategy_ledger.py` scores a lane for
mount/retire decisions.

### 4. Execution

There is exactly one exit per environment, and no code path can reach a live account
([ADR 0002](../docs/adr/0002-paper-only.md), [ADR 0008](../docs/adr/0008-mcp-adapter-allowlist.md), L-011):

- **Cloud (scored path):** the executor agent calls Moomoo MCP `sim_trade_input_order` verbatim with
  plan values. Broker *reads* come back as `accounts.json` / `cash.json` / `positions.json` files that
  `broker/mcp_json.py` normalizes into kernel types. Submission is not implemented in Python at all.
- **Local:** `MoomooCli` (`broker/moomoo_cli.py:104`) shells out to the official binary for `fetch`,
  `quote`, `accounts` and `execute`; `execute` re-validates and hard-blocks real broker accounts.
- **`broker/base.py` `PaperBroker`:** an in-memory instant-fill simulator used by tests and the offline
  demo. It is not evidence of a broker fill and is not a production path.
- `execute-exit` is read-only by design: a local command may check, never submit (L-011).

### 5. Evidence

`journal.py` appends a hash-chained JSONL event for plans, verdicts, submissions, fills, halts, config
changes and gate waits; `verify_chain` (`:91`) is run by `tyche journal-verify`, CI, and the `reserve`
gate. Two kill-switch flags (journal-dir and repo-level) are merged by `halt.py:effective_halt`, so a
halt from either location stops buys. `execution_state.py` reconciles cumulative budgets with what the
broker actually holds, and `unresolved_symbols()` blocks writes on a symbol with an open order.

`persist.py` splits evidence: raw payloads to the Qoder Drive locker, sanitized summaries to git
([ADR 0009](../docs/adr/0009-persistence.md), L-025) - the cloud sandbox is ephemeral, and the run is
worthless as evidence if it is not written out. Account ids are masked at journal write time (L-031).

### 6. Desk and hosting

`dashboard/server.py` is a stdlib `ThreadingHTTPServer` on `127.0.0.1:8765` with four API routes and
static files:
read-only `GET /api/state` and `GET /api/automation`, and `POST /api/halt` and
`POST /api/approvals/arm|disarm` as the only writes. A write commits the specific JSON path and pushes
(`_git_push_paths`), which is how the cloud mount sees operator intent without a shared database. UI
state in the browser is `localStorage` theme/view only; the operator passphrase is in memory.
`app.js:8` carries `VERSION` plus a `CHANGELOG`, and any control change must bump both.

`scripts/export_dashboard.py` regenerates `desk-site/` from `dashboard/` (it imports the same builders,
so the hosted view cannot drift in logic, only in freshness) and refuses to write if a secret, a full
account id or a PAT appears in the output. `desk-site/web/data/*.json` is refreshed by
`scripts/publish_desk_data.py`; the hosted function serves `/state`, `/automation`, `/control` and
`/control/status`. `desk-site/` is generated output: author in `dashboard/`, never in place.

### 7. Market context and calendar

`market_calendar.py` owns session phases, the trading-day gate (`is_trading_day`), half-days, the
event overlay from `config/events.yaml` and `evaluate()`/`--json` used by the cards to decide whether to
run at all. `nyse_calendar.py` parses the published NYSE calendar and diffs it against the pinned one so
drift is detected rather than assumed; the drift *check job* is currently attached only to a paused
schedule, so it does not run unattended (open work).

### 8. Notifications

`scripts/telegram.py` renders and sends the digest through a deterministic Markdown-to-Telegram-HTML
normalizer. Delivery is at-least-once: a socket timeout exits `2` (UNCONFIRMED) rather than claiming
failure, so a retry cannot silently duplicate (L-004), and there is no inbound path (L-003, L-006).

## Data and control flow of one trading day

1. 08:05 card fires a new `tyche-desk` session; `tyche calendar --json` decides whether to proceed.
2. Desk delegates: researcher gathers catalysts and quotes, executor captures broker state to a run dir.
3. Kernel builds the plan: lane -> intents -> `risk.py` -> `pipeline.py` -> `plans/<date>-plan.json|.md`,
   hash-chained into the journal.
4. Risk auditor reviews each approved order independently and writes `reports/<date>-audit.md`. Its
   verdict is advisory to the kernel and blocking only through the operator's envelope decision.
5. `tyche lifecycle reserve` re-validates everything and writes a reservation; the executor submits one
   order per reservation via MCP; each outcome is journaled.
6. 12:05 watch-only fire checks protection levels and may shout, never trade.
7. 15:05 close fire reconciles fills, records `order.filled` events, runs expectancy, writes the EOD
   narrative, then `tyche persist` exports evidence.
8. Sentinel pushes the digest to Telegram.

## Deployment topology

| Where | Runs | State it holds |
|---|---|---|
| Desk PC (Windows, Git Bash) | kernel CLI, desk server, telegram helper, exports, deploy scripts | git checkout, `data/*.json`, `journal/`, `plans/`, `.venv` |
| Qoder cloud sandbox | four agents, one session per fire | ephemeral mount of `main`; nothing persistent |
| GitHub `main` | the shared truth for config, docs, journal chain, desk JSON | tracked files only |
| Moomoo | quotes + paper accounts via MCP and CLI | positions, orders, fills |
| Qoder Sites | hosted desk snapshot + control proxy | generated `desk-site/` output |
| Qoder Drive locker | raw run evidence | `/data/drive/tyche-raw/<run>/` |
| GitHub Actions | `ruff check src scripts tests` then `pytest -q` | none |

## Known architectural debt

- **The strategy "registry" is not a dispatch path.** `strategies/__init__.py:12` exports `REGISTRY` and
  nothing imports it; `cli.py:41` calls `rotation_targets` directly. A new lane is still a code change in
  the CLI, not a registration. This is the open item in [../DESIGN.md §12](../DESIGN.md).
- **Two `Outlook` types** (`models.py:213` enum vs `watchlist.py:27` model) and
  **`OrderIntent.strategy_id` defaulting to `"PB-001"`** (`models.py:134`) while `tyche strategy-score`
  defaults to `PB-004` (`cli.py:1231`). Both are misattribution hazards: a lane that forgets to set the id
  books its trades under the ballast strategy, and ledger scoring filters on that field.
- **Act/wait is enforced in code on both paths** (`pipeline.py:148`, `lifecycle.py:485`), but
  `docs/dashboard.md` still describes the MCP path as prompt-honored. The doc understates the kernel.
- **No `rules.refrozen` producer** exists, so a re-registration is provable in CI (declared hash ==
  kernel hash) but not journaled at the moment it happens (L-035).
- **`desk-site/` is generated but tracked**, so a hand-edit there is silently overwritten on the next
  export. Decide: track the export as a release artifact with a "do not edit" header, or ignore it and
  publish from the pipeline.
