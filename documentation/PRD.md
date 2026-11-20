# tyche Product Requirements Document

| | |
|---|---|
| **Version** | 1.1 |
| **Last revised** | 2026-11-20 |
| **Supersedes** | [../DESIGN.md](../DESIGN.md) §2/§11 as the statement of current scope (DESIGN.md stays as the v0.1 baseline) |
| **How it is built** | [architecture.md](architecture.md) |
| **Why it is built this way** | [../docs/adr/](../docs/adr/) |
| **What is broken or unfinished** | §7 below, plus [../docs/lessons/LESSONS.md](../docs/lessons/LESSONS.md) |

This document describes **the platform as it exists**, not the platform as intended. Every capability
carries a status from the fixed vocabulary in [README.md](README.md): `implemented`, `partial`,
`experimental`, `planned`, `deprecated`. A sentence in the present tense that is not backed by code, a
test or a journal row is a defect in this file - report it, do not smooth it over.

## 1. Product statement

tyche is a **strategy-agnostic paper-trading desk** built for the Moomoo x Qoder AI Agent Paper Trading
Challenge (window 17-28 Nov 2026). It separates two jobs that are usually conflated in "AI trading":

- a **deterministic Python kernel** decides and executes: data, target weights, order construction, risk
  invariants, authorization gates, execution, audit trail;
- **LLM agents (Qoder Cloud Agents)** sit on the perimeter: they gather research, critique a plan before
  it runs, audit orders independently and write the daily narrative. They never size or submit an order.

The user-visible product is therefore three things: a **journal** that proves what happened and why, a
**desk** (local server plus a hosted snapshot) that makes the state legible, and a **paper P&L** produced
under hard, documented risk caps.

## 2. Who it is for

| Audience | What they need from tyche | Where it lives |
|---|---|---|
| Operator (one person, at the desk) | see state, arm/disarm an envelope, halt, review a plan before it runs | `dashboard/`, `tyche` CLI, Telegram digest |
| Cloud agent sessions | unambiguous inputs and outputs; no need to guess the clock, the account or the caps | [../docs/agent-rules.md](../docs/agent-rules.md), journaled artifacts |
| Judge / reviewer | risk-adjusted results **and** the evidence chain that produced them | `docs/performance/`, `journal/events.jsonl`, [../docs/competition/scoring-map.md](../docs/competition/scoring-map.md) |
| Reuser (someone running this without a Moomoo account) | a working vertical slice from synthetic data | `scripts/make_demo_data.py`, `tyche plan --prices data/demo_prices.csv` |

## 3. Scope

**In scope.** US equities and equity ETFs, plus **defined-risk single-leg options** (long calls/puts, no
spreads or nonstandard contracts - PB-005 is parked precisely because a vertical conflicts with desk
policy). Paper accounts only.

**Out of scope, by construction rather than by policy statement.** Live accounts (the guard is an
allowlist conjunction the code enforces, not a warning), shorting, crypto/futures/commodities/FX and any
non-equity asset class, and autonomous entry without a valid envelope. Removing irrelevant asset classes
from active configs and UIs was a refinement requirement; the classification vocabulary in
[../playbook/README.md](../playbook/README.md) is restricted to `Stocks` and `Options` and
`test_playbook_instruments_are_stocks_and_options_only` fails on anything else.

**Research is not trading.** The lanes under `research/` (LEAN, external video insights) and every agent
artifact are inputs to a human or to the kernel's own deterministic code. Nothing in `research/` is a
kernel input ([ADR 0015](../docs/adr/0015-external-research-perimeter.md)).

## 4. Product invariants

These are requirements in the strict sense: a change that breaks one is not a refactor.

1. **Determinism.** Same inputs, same plan, same hashes. `rules_hash()` binds a lane to the bytes that
   define it, and a plan records the inputs it was built from.
2. **The LLM cannot trade.** No agent output reaches the broker. Advisory text only
   ([ADR 0006](../docs/adr/0006-llm-perimeter.md)).
3. **Paper only, provably.** `env == paper` AND account id in `account_allowlist` AND
   `account_type in {1,2}` AND `market_id == 100`, checked against the sim account list; real broker
   accounts are hard-blocked in the local path (L-010).
4. **Nothing trades silently.** Every verdict, plan, submission, fill, veto, halt and gate wait is a
   hash-chained journal event; `verify_chain` runs in CI, in `doctor` and before every reservation.
5. **A submit is not a fill.** Position state is reconciled from broker order state, and an unresolved
   order blocks further writes on that symbol (L-012, L-015, L-016).
6. **A gate that always blocks is not a gate.** Safety checks must be provably computing, not swallowing
   errors - the lesson behind L-036, now asserted by tests.
7. **No secrets, no full account ids in tracked files or journal payloads** (L-031).

## 5. Capability map

### 5.1 Data and market context

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Daily close fetch through the Moomoo CLI | implemented | `tyche fetch`, `cli.py:429` | bulk path is `scripts/mcp_prices.py` in the cloud (L-026) |
| Broker state capture (accounts, cash, positions, orders) | implemented | `broker/mcp_json.py:159,194` | executor writes the files; kernel never calls a broker API in the cloud |
| Session calendar, half-days, phases, gate | implemented | `market_calendar.py`, `tyche calendar --json` | trading-day filtering is applied at card generation (L-019) |
| NYSE published-calendar drift detection | partial | `nyse_calendar.py:74,152`, `tyche calendar-check` | the check clause is installed only on a **paused** schedule, so it does not run unattended |
| Event overlay (catalyst days) | implemented | `config/events.yaml`, `tyche events add` | fed by operator triage of research, not automatically |
| Two-sided quote capture for intraday entry | partial | `quote_order_book`, snapshot capture in card prompts | pre-market payloads lack bid/ask; entries require a fresh RTH capture (L-017) |
| Synthetic demo data | implemented | `scripts/make_demo_data.py` | the no-credentials on-ramp |

### 5.2 Strategy lanes

| Lane | Status | Evidence | Gap / note |
|---|---|---|---|
| PB-001 regime/vol-targeted rotation (ballast) | implemented, **unvalidated** | `strategies/rotation.py`, [../playbook/PB-001-etf-rotation-ballast.md](../playbook/PB-001-etf-rotation-ballast.md) | beta-not-alpha framing; low-vol regime sleeves |
| PB-002 tactical event lane | partial | `tactical.py:243`, `config/tactical.yaml` (`enabled: true`) | lane runs and stamps its id, but has **no thesis file**, so the roster keeps it `planned`; freeze shared with PB-003 |
| PB-003 tactical options lane | partial | `tactical.py:345` | off: `options_enabled: false`; option protections per ADR 0012 |
| PB-004 intraday breakout scalp | partial | `scalp.py`, [../playbook/PB-004-intraday-momentum-scalp.md](../playbook/PB-004-intraday-momentum-scalp.md) | rules now freeze (`72077d5d4808`); submission gated by the executor rollout hold; unvalidated |
| Backtest / walk-forward harness | planned | - | open item in [../DESIGN.md §12](../DESIGN.md); validation currently means a documented sanity check, labelled as such |
| Local LEAN sanity lane | experimental | `research/lean/PB001/`, `docs/validation/2026-11-19-lean-pb001-smoke.md` | research-only, one smoke run, never a kernel input |
| Strategy plug-in interface (one registry, strategy-agnostic plan schema) | planned | `strategies/__init__.py:12` exports a `REGISTRY` nothing imports | adding a lane is still a code change; see §7 |

### 5.3 Risk, authorization and execution

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Pre-trade risk kernel with named breaches | implemented | `risk.py:31`, `tests/test_risk.py` (29 tests) | caps in `config/risk.yaml`; published view [../docs/risk-card.md](../docs/risk-card.md) |
| Drawdown ladder, daily loss, turnover and order budgets | implemented | `risk.py:108-114,146-151` | soft halves buys, hard blocks them |
| Per-trade risk budget + R-multiple expectancy | implemented | `trade_risk.py:173`, ADR 0016 | needs canonically journaled fills; unattributed fills are reported, never guessed |
| Operator envelope (bounded same-day authorization) | implemented | `approvals.py`, `data/approvals.json`, desk arm/disarm | `sim_trade_input_order` executes immediately inside it - no platform popup (L-014) |
| Lifecycle decide/tick/reserve gate | implemented | `lifecycle.py:386,597`, `lifecycle_cli.py:242-333` | reservation is durable before one submit; largest test suite |
| Cloud execution via Moomoo MCP (paper) | implemented | executor v15 tool grants, `docs/agent-engineering.md` | submission is agent-side by design; Python never submits in the cloud |
| Local execution via `moomoo` CLI | implemented | `cli.py:516-668` | preview exits 2; real accounts blocked |
| In-memory paper broker | implemented (test/demo) | `broker/base.py:14` | explicitly not evidence of a broker fill |
| Intraday protection monitor (1-2 min) | planned | ADR 0013 (still `proposed`), runbook marked not deployed | the gap that makes the scalp lane's exits a manual watch today |

### 5.4 Evidence and audit

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Hash-chained journal + verify | implemented | `journal.py:86,91`, `tyche journal-verify` | account ids masked at write time |
| Two-flag kill switch | implemented | `halt.py:56`, `tyche halt-status --json` | drill recorded in `docs/validation/2026-11-18-kill-switch-drill.md` |
| Run evidence persistence split (raw → Drive, sanitized → git) | implemented | `persist.py`, ADR 0009 | the cloud sandbox is ephemeral; without this, 60% of the score evaporates |
| `rules.refrozen` journal producer | planned (no writer exists) | nothing in the codebase emits it | the freeze is *asserted* in CI but not *recorded* when it happens (L-035) |
| Config-change journaling with effective time | partial | L-032 records the requirement | a cap change is currently inferred from later plans |

### 5.5 Desk and reporting

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Local desk with overview/strategy/risk/automation/controls views | implemented | `dashboard/static/index.html`, `server.py:1501-1673` | version + changelog in `app.js:8`, currently `0.5.0` |
| Halt and envelope arm/disarm from the desk | implemented | `server.py:1957-1974` | the only two write actions; path-limited commit + push |
| Hosted desk snapshot + control proxy | implemented | `desk-site/`, `scripts/export_dashboard.py`, `handler.ts` | `functions/` is authored inside the export target; refresh-on-load, no polling (L-022) |
| Per-strategy enable/disable control in the UI | **planned** | toggling means editing YAML and committing | Phase 4 |
| "Run Scout" trigger in the UI | **planned** | no `/api/scout/run` route exists | Phase 4; must reuse the existing card workflow |
| Schedule configuration in the UI | **planned** | automation view is read-only (`app.js:1502-1514`) | Phase 4; manual trigger must work with the schedule off |
| Daily brief / pre-trade critique / EOD narrative | implemented | card prompts, `reports/*` | journaled; advisory only |

### 5.6 Agents and automation

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Four pinned cloud agents (desk 28, researcher 16, executor 15, auditor 6) | implemented | `list_agents` on 2026-11-20, [../docs/agent-rules.md](../docs/agent-rules.md) | pins are restated in prose and **will drift**; `list_agents` is the authority |
| Monthly trading-day-gated card, 08:05 / 12:05 watch-only / 15:05 | implemented | `scripts/deploy_two_fire_automation.py:53-63` | name says "two fire", prompt says three; script is truth |
| Least-privilege tool grants (deny-by-default MCP allowlists) | implemented | `deploy_token_policy.py`; live: researcher 24 enabled, executor 14 + `quote_rt_data` disabled | assert the allowlist after every re-pin (L-023) |
| Independent per-order risk audit | implemented | auditor v6, `reports/<date>-audit.md` | auditor has no clock or shell: its times/hashes are desk-head claims (L-024) |
| Scout (idea generation) | partial | researcher role + premarket fire; `watchlist.py`, `reports/*-research.md` | scheduled discovery works; **no manual trigger** and it **cannot see which strategies are enabled** |
| Ideas consumed downstream | partial | `tyche events add` → `config/events.yaml` → gate halves budget | operator triage is the link; nothing auto-promotes an idea into a plan |
| Telegram sentinel | implemented (outbound only) | `scripts/telegram.py`, runbook | at-least-once semantics; no inbound approvals (L-003/L-006) |
| CI (ruff + pytest) | implemented | `.github/workflows/ci.yml` | 447 tests; a red pipeline blocks every later phase (L-034) |

## 6. Non-functional requirements

| Requirement | How it is met | Verification |
|---|---|---|
| Reproducibility | config-driven lanes, input pins in the plan, CRLF-insensitive rule hashing | `tests/test_pipeline.py` |
| Auditability | hash chain + reservations + advisory-forever LLM outputs | `tyche journal-verify` in CI and pre-submit |
| Fail-safe defaults | unknown → blocked; envelope required for autonomous entry; halt stops buys | `tests/test_halt.py`, `test_desk_controls.py` |
| Least privilege | per-agent tool allowlists; no MCP mount on desk/auditor; paper-only ids injected from env | verified against the live platform, re-asserted after re-pins |
| Privacy | no credentials or full account ids in tracked files, journals or chat; secret guard in the site export | `test_no_live_code_reaches_into_the_archive`, export guard in `export_dashboard.py` |
| Runway | internal order budget below the competition ceiling so the desk cannot exhaust its own limits | `config/risk.yaml` + `docs/risk-card.md` |
| Documentation as test | published caps, playbook hashes, roster ids, classification vocabulary and local links all fail the build when they rot | `tests/test_docs_consistency.py` (10 tests) |
| Offline usability | demo data + in-memory broker means a full plan/journal cycle with no credentials | `README.md` quick start |

## 7. Known defects and technical debt

Ordered by how much they can cost, not by effort.

1. **Stale numeric caps inside agent prompts** (L-033). Auditor v6 still says "40 daily entry orders"
   and "150% buy turnover"; desk v28 says "<=40 entry orders/day". `config/risk.yaml` enforces 120 orders
   and 300% turnover. Two authorities disagree and a prompt reads as authority. Fix: strip the numbers
   from both prompts, re-pin, assert the tool allowlist. **Needs operator approval** (a re-pin is a new
   build).
2. **No `rules.refrozen` producer** (L-035). The freeze contract is provable in CI but has no journal
   provenance, so every historical re-registration is git archaeology.
3. **Strategy identity is a default value, not a required argument.** `OrderIntent.strategy_id` defaults
   to `PB-001` while `tyche strategy-score` defaults to `PB-004`. A lane that forgets to set the id books
   its trades under the wrong strategy, and ledger/expectancy filter on that field.
4. **PB-002 runs without a thesis file.** The tactical stock lane is enabled and stamps its id; the
   roster keeps it `planned` because `status: live` requires a playbook, which is the guard working as
   intended - but the underlying mismatch is real.
5. **`REGISTRY` is aspirational.** The strategy-agnostic dispatch the README implies does not exist; the
   CLI calls the rotation function directly.
6. **`desk-site/` is one directory with four provenances** (exporter output, another script's output, the
   published data feed, hand-authored functions). Nothing destructive remains - a full export preserves
   what it cannot rebuild (L-039) - but the tracked `data/*.json` is a snapshot of the last publish, which
   reads as live state to anyone who finds it in a clone.
7. **Calendar drift checking is not wired to a live trigger**; the code and CLI exist.
8. **Duplicate domain names** (`Outlook` enum vs model) invite the wrong import.
9. **No launch command documented for the desk server** in README or runbooks; only the audit references
   it, so a new operator cannot start it from the docs.

## 8. Roadmap

Named here so the desk's next steps are auditable; none of it is code yet.

- **Phase 4 (dashboard controls).** Per-strategy enable/disable persisted to a git-synced state file and
  respected by Scout; a "Run Scout" action that triggers the existing card workflow with status, history
  and duplicate-run protection; a scheduled-daily-check toggle with time/timezone, next-run and previous
  runs, and a manual trigger that works with the schedule off. Ordering constraint: toggles must land
  together with Scout honoring them, before the Scout button. Each change bumps `app.js` `VERSION` and
  adds a `CHANGELOG` entry.
- **Phase 5 (validation).** End-to-end rehearsal of the new controls, honest status re-audit, and a
  residual-debt list folded into this file's §7.
- **Deferred, needs a decision:** the `rules.refrozen` writer, the backtest harness, the protection
  monitor (ADR 0013), and narrowing the ETF universe further to equity-only.

## 9. Version history

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-11-16 | `DESIGN.md` written as the v0.1 baseline: rotation strategy, risk caps, LLM perimeter, journal. Still the reference for the safety core; §2/§11 no longer describe the platform. |
| v0.2 | 2026-11-18/19 | Window scope lifted to stocks + defined-risk options (L-001 cut), MCP execution path (ADR 0008), tactical and scalp lanes, envelope and lifecycle gates, persistence split, four-agent topology, hosted desk. Never written up as a PRD - the gap this document closes. |
| **v1.0** | 2026-11-20 | First PRD. Written from an audit of the code and the live platform rather than from the README: capability statuses, the §7 defect list, and an updated architecture in [architecture.md](architecture.md). Simultaneously: `playbook/` became the strategy library, `archive/` became the only superseded-work dump, the per-lane freeze source was fixed (L-036/L-037), and five superseded cadence scripts were retired. |
| **v1.1** | 2026-11-20 | Hosted-desk claims corrected after checking what the exporter actually does: `desk-site/` is not uniformly generated (the Sites Function and the tracked data feed are load-bearing), and a full export used to delete assets it cannot rebuild (L-039, fixed). Capability statuses are now asserted against the vocabulary in [README.md](README.md) by `test_prd_capability_statuses_use_the_fixed_vocabulary`. |

**Maintenance rule.** A change to a capability's status, a new lane, a new agent or a new external
integration is a PRD edit with a version bump and a [CHANGELOG.md](CHANGELOG.md) row, landed in the same
commit as the code. Prose-only edits do not bump the version.
