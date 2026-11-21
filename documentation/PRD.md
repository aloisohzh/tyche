# tyche Product Requirements Document

| | |
|---|---|
| **Version** | 1.6 |
| **Last revised** | 2026-11-21 |
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
| Two-sided quote capture for intraday entry | partial | Moomoo MCP read tool `quote_order_book`, enabled on the executor (`plans/live-executor.json`; the platform, not that capture, is the authority), plus snapshot capture in card prompts | pre-market payloads lack bid/ask; entries require a fresh RTH capture (L-017) |
| Synthetic demo data | implemented | `scripts/make_demo_data.py` | the no-credentials on-ramp |

### 5.2 Strategy lanes

| Lane | Status | Evidence | Gap / note |
|---|---|---|---|
| PB-001 regime/vol-targeted rotation (ballast) | implemented, **unvalidated** | `strategies/rotation.py`, [../playbook/PB-001-etf-rotation-ballast.md](../playbook/PB-001-etf-rotation-ballast.md) | beta-not-alpha framing; low-vol regime sleeves |
| PB-002 tactical event lane | partial | `tactical.py:241-243` (exit intent) and `:342-345` (entry intent) stamp the id, `config/tactical.yaml` (`enabled: true`) | lane runs and stamps its id, but has **no thesis file**, so the roster keeps it `planned`; freeze shared with PB-003 |
| PB-003 tactical options lane | partial | `config.py:182,275` (`options_enabled`) and its gate at `tactical.py:302`; the id ternary it shares with PB-002 is `tactical.py:345` | off: `options_enabled: false`; option protections per ADR 0012 |
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
| Exit-note drafting from the open book (propose, then arm) | implemented (local desk + CLI) | `envelope.py` (`propose_exit_envelope`, `exit_levels`), `tyche propose-envelope` (`cli.py:1231`), `server.py` (`propose_envelope`, `arm_envelope({"use_draft": true})`, `_draft_summary`), route `/api/approvals/propose`; `tests/test_envelope_proposal.py`, drafting block in `tests/test_desk_controls.py` | Rung 1.5 of ADR 0013 (see [runbook §0](../docs/runbooks/intraday-protection-monitor.md)). Floors come from the journaled stop widened by `risk.exit_collar_pct`; `setup_hash` is copied verbatim (it folds in the account id and config hash, `tactical.py:72`), so a line that cannot be bound is flagged unbound instead of passed off as bound. Options and bearish puts are refused; the draft file is gitignored and only Arm writes `data/approvals.json`. Detection is untouched: this shortens the confirm leg, not the gap between checks |
| Lifecycle decide/tick/reserve gate | implemented | `lifecycle.py:386,597`, `lifecycle_cli.py:241-332` | reservation is durable before one submit; largest test suite |
| Cloud execution via Moomoo MCP (paper) | implemented | executor v15 tool grants, `docs/agent-engineering.md` | submission is agent-side by design; Python never submits in the cloud |
| Local execution via `moomoo` CLI | implemented | `cli.py:516-668` | preview exits 2; real accounts blocked |
| In-memory paper broker | implemented (test/demo) | `broker/base.py:14` | explicitly not evidence of a broker fill |
| Intraday protection monitor (Level 0 tick) | partial (rung 0 built 2026-11-21; the bounded exit at rung 1.5 is shipped; rungs 1 and 2 are not) | `src/tyche/monitor.py`, `src/tyche/monitor_cli.py`, registered at `src/tyche/cli.py:55`; `tests/test_monitor_tick.py` (23 tests); drill [../docs/validation/2026-11-21-synthetic-breach-drill.md](../docs/validation/2026-11-21-synthetic-breach-drill.md); [ADR 0013](../docs/adr/0013-protection-monitor.md) (still `proposed`) + its contract [../docs/runbooks/intraday-protection-monitor.md](../docs/runbooks/intraday-protection-monitor.md) | The tick is a pure function over files: a runner must write `quotes.json` and invoke it, and **no schedule does that yet**, so detection on an open lot is still the three desk fires. It evaluates `synthetic_stop` and `defined_risk` level crosses (a bearish put is watched on its underlying, upwards) and types PB-001 ballast `rebalance` so an alert is never read as an exit; `time_exit` (scalp flatten) is not a monitor row. Nothing is journaled without `--record`, `--at` replay cannot record, and a tick that could not judge exits `2` rather than reporting "no breaches". Per-tick Telegram routing needs its own approval (§7) |

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
| Local desk with overview/strategy/risk/automation/controls views | implemented | `dashboard/static/index.html`, `server.py:1505` (`build_state`), routes `server.py:2338-2400` | version + changelog in `app.js`, currently `0.8.0` |
| Halt and envelope arm/disarm from the desk | implemented | `server.py` (`halt_control`, `arm_envelope`, `disarm_envelope`, `propose_envelope`) + their `/api/*` routes | path-limited commit + push; the kill switch and envelope keep one intent path each. Arm has three doors - fresh bounds, re-arm the last note, or arm the drafted exit note - and remains the only writer of `data/approvals.json` |
| Exit-note card on the desk (drafted lines, sources, refusals) | implemented (local desk only) | `renderApproval` in `dashboard/static/app.js`, `_draft_summary` in `server.py`, `.draft-block` rules in `style.css` | the hosted console shows no Propose/Arm buttons: the Sites Function has no Python and no journal to read them from. A draft not dated today cannot be armed, and an empty proposal deletes the previous draft |
| Hosted desk snapshot + control proxy | implemented | `desk-site/`, `scripts/export_dashboard.py`, `handler.ts` | `functions/` is authored inside the export target; refresh-on-load, no polling (L-022). Republished 2026-11-21 with the `/schedule` route live; the three Secrets the Function declares are present and synced, but the console's runtime behaviour is unverified from here (§7 item 11) |
| Per-strategy enable/disable control in the UI | implemented | `src/tyche/lanes.py:82` (`set_enabled`), `server.py:1966` (`toggle_strategy`) + route `2386`, `handler.ts:298` (`action === "strategy"`), `tests/test_strategy_switches.py`; state lives in `data/strategies.json` | local and hosted desks both write the same unhashed switch file; a toggle blocks entries but never an exit, and moves no rules hash (L-037). The file is created on the first toggle, and its absence is normal: `read_overrides` (`lanes.py:44`) falls back to the lane config rather than to "everything on" |
| Scheduled daily checks: see the cadence, switch it, fire one now | implemented (times read-only by decision) | `server.py:2047` (`build_schedule`), `2102` (`schedule_control`), routes `2338`/`2392`; `scripts/cloud_api.py:119,135,143,148`; `app.js:1179,1237` | pause/resume/run-now are journaled and the pause is re-read from the platform before it is reported as done; fire times and timezone are shown but not editable, because they live in the card's cron and again in its prompt (operator decision, Phase 4b) |
| "Run Scout" trigger in the UI | implemented | `server.py:2155` (`scout_brief`), `2265` (`start_scout`), routes `2344`/`2398`; `scripts/cloud_api.py:209,231`; `app.js:1270,1313` | starts the researcher session alone - no executor, no auditor, no envelope, nothing that can submit; a second concurrent run is refused and the start is journaled as `scout.requested`. The session has no repo mount, so the brief carries the clock, the live lane ids and their hashes |
| Daily brief / pre-trade critique / EOD narrative | implemented | card prompts, `reports/*` | journaled; advisory only |

### 5.6 Agents and automation

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Four pinned cloud agents (desk 28, researcher 16, executor 15, auditor 6) | implemented | `list_agents` on 2026-11-20, [../docs/agent-rules.md](../docs/agent-rules.md) | pins are restated in prose and **will drift**; `list_agents` is the authority |
| Monthly trading-day-gated card, 08:05 / 12:05 watch-only / 15:05 | implemented | `scripts/deploy_two_fire_automation.py:53-63` | name says "two fire", prompt says three; script is truth |
| Least-privilege tool grants (deny-by-default MCP allowlists) | implemented | `deploy_token_policy.py`; live: researcher 24 enabled, executor 14 + `quote_rt_data` disabled | assert the allowlist after every re-pin (L-023) |
| Independent per-order risk audit | implemented | auditor v6, `reports/<date>-audit.md` | auditor has no clock or shell: its times/hashes are desk-head claims (L-024) |
| Scout (idea generation) | partial | researcher role + premarket fire; manual trigger `server.py:2265`; `watchlist.py`, `reports/*-research.md` | scheduled and manual discovery both work; the researcher prompt still does not consult the live lane id set, and changing that prompt is a re-pin needing operator approval. The manual run starts the researcher alone, so it can propose nothing that reaches a broker |
| Ideas consumed downstream | partial | `tyche events add` → `config/events.yaml` → gate halves budget | operator triage is the link; nothing auto-promotes an idea into a plan |
| Telegram sentinel | implemented (outbound only) | `scripts/telegram.py`, runbook | at-least-once semantics; no inbound approvals (L-003/L-006) |
| CI (ruff + pytest) | implemented | `.github/workflows/ci.yml` | 553 tests; a red pipeline blocks every later phase (L-034) |

## 6. Non-functional requirements

| Requirement | How it is met | Verification |
|---|---|---|
| Reproducibility | config-driven lanes, input pins in the plan, CRLF-insensitive rule hashing | `tests/test_pipeline.py` |
| Auditability | hash chain + reservations + advisory-forever LLM outputs | `tyche journal-verify` in CI and pre-submit |
| Fail-safe defaults | unknown → blocked; envelope required for autonomous entry; halt stops buys | `tests/test_halt.py`, `test_desk_controls.py` |
| Least privilege | per-agent tool allowlists; no MCP mount on desk/auditor; paper-only ids injected from env | verified against the live platform, re-asserted after re-pins |
| Privacy | no credentials or full account ids in tracked files, journals or chat; secret guard in the site export | `test_no_live_code_reaches_into_the_archive`, export guard in `export_dashboard.py` |
| Runway | internal order budget below the competition ceiling so the desk cannot exhaust its own limits | `config/risk.yaml` + `docs/risk-card.md` |
| Documentation as test | published caps, playbook hashes, roster ids, classification vocabulary and local links all fail the build when they rot | `tests/test_docs_consistency.py` (17 tests) |
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
9. **`dashboard/` sits outside the lint set.** `ruff check dashboard` reports 18 findings (14 auto-fixable)
   while CI lints `src scripts tests` only, so the operator-facing server and its UI have no style or
   correctness gate - the same class of blind spot that let a JS parse error blank the whole desk while every
   Python test stayed green (L-040). Fix: clear the 18, then add `dashboard` to the CI lint command.
10. **Approval cards clip horizontally below ~390 px.** Pre-existing `.approval-*` / `.mode-*` / `.tbl` rules,
    not introduced by the Phase 4 cards (verified by diff); the new schedule and Scout cards are
    overflow-safe at the same width. Fix: stack the approval grid at a narrow breakpoint.
11. **PB-001 computes a stop it never journals, so ballast lots cannot be pre-armed.**
    `rotation.py:351-353` derives `stop_price` from `initial_stop_pct: 0.08` and puts it on the intent, but the
    rotation path does not journal a `protected_setup` and the ballast has no watchlist entry, so
    `exit_levels` (`src/tyche/envelope.py:93`) finds nothing to protect and the drafting card reports those
    positions as refused with a reason. This matches ADR 0013's alert-only stance for `rebalance` protection -
    ballast is meant to exit at the next rebalance, not at a stop - but it was undocumented until rung 1.5 made
    the absence visible on today's book (SPY + EFA both refused). Fix if ballast stops are ever wanted: journal
    the computed stop as the entry's protective level, which is a freeze-relevant change to PB-001's contract.
12. **The hosted desk is only as fresh as its last feed publish.** The Controls view reads and writes the live
    cloud card directly, but the hosted page serves `desk-site/web/data/*.json` from `main`, and those files are
    a snapshot of whenever `scripts/publish_desk_data.py` last ran (2026-11-21). Nothing refreshes them by
    itself, and that is by design: `handler.ts:8-10` keeps the cloud token off the server so only one path can
    change cadence, which means the hosted snapshot advances on push rather than pretending to be live.
    **Not a gap, and this was claimed wrongly once:** all three Secrets the Function declares
    (`TYCHE_FORWARD_PAT`, `TYCHE_GITHUB_PAT`, `TYCHE_OPERATOR_PASSPHRASE`) are present with
    `sync_state: synced`, so the operator console is configured. A Function's `required_secret_names` is a
    *dependency list*, not a gap report - presence and sync only come from the secrets detail. **Still
    unverified:** the console's live behaviour, because the site gateway answers 401 to unauthenticated
    requests; the `operator_configured` read has to be done from a signed-in browser.

### Blocked on an operator decision, with what each one needs

| Item | Closing condition |
|---|---|
| Stale caps in prompts (1) and Scout honoring the live lane ids (§5.6) | one re-pin of the researcher/auditor prompts, which is a new build and needs approval |
| `rules.refrozen` producer (2) | a kernel writer plus a journal assertion; deferred by decision while the freeze-source fix is verified in use |
| Calendar drift trigger (7) | a live schedule object to attach the check to; `scripts/deploy_calendar_check.py` already builds it |
| Intraday protection monitor (§5.3) | decided 2026-11-21: rung 1.5 (pre-armed bounded exit) is built, Level 2 stays declined; rung 0 (`tyche monitor tick`) was approved and is built, with a pinned-clock synthetic-breach rehearsal recorded. Still open: a runner that feeds the tick a quote file on a schedule, the live-session drill leg that needs the operator, and a separate decision on rung 1 Telegram bark routing |
| Hosted operator console proven unattended (11) | one signed-in browser read of `control/status` and one arm/disarm round trip; the Secrets themselves are present and synced, and the gateway 401s any check from here |
| Telegram bot token | the deployments/sessions API returns `environment_variables` in plaintext, which is why `cloud_api.py` whitelists every payload before it reaches a browser (L-038); rotating the token itself is an operator action outside the repo |

Closed during this refinement and kept off the list: the desk server had no documented launch command
(it is in the README command table now) and the site export deleted hosted assets it could not rebuild
(L-039). Also closed: `docs/dashboard.md` described the act/wait gate on the MCP path as prompt-honored when
`lifecycle.py:485` blocks it in code; the doc now states the mechanism and the prompt is labelled a backstop.

## 8. Roadmap

Named here so the desk's next steps are auditable; the first bullet is now part code, part plan.

- **Phase 4 (dashboard controls).** Landed in v1.2: per-strategy enable/disable persisted to
  `data/strategies.json` (git-synced, outside the freeze), on both the local and hosted desk, with the
  rules hash shown next to each lane. Landed in v1.3: the Controls view now shows the cloud cadence card
  that owns today - fire times, next runs, recent runs with their errors - and can pause it, resume it and
  fire one check immediately, plus a **Run Scout** button that starts the researcher alone with today's
  live lane ids in its brief, refuses a second concurrent run, and journals the request. Fire times and
  timezone are deliberately read-only (operator decision): they live in the card's cron and again in its
  prompt, so retuning them is a card rebuild, not a setting. Still open: Scout honoring the live id set in
  the researcher prompt (a re-pin, so it needs operator approval), and giving the hosted desk a cadence
  write path - it reads the published snapshot only, because the Sites Function holds no verified cloud
  token for deployments and two write paths to one switch is how cadence drifts.
  Each change bumps `app.js` `VERSION` and adds a `CHANGELOG` entry.
- **Phase 5 (validation).** End-to-end rehearsal of the new controls, honest status re-audit, and a
  residual-debt list folded into this file's §7.
- **Phase 6 (protection, in pieces).** The operator chose the pre-armed bounded exit over an alert-only
  watchdog (ADR 0013 runbook §0). Shipped in v1.5: the kernel drafts a sell-only note from the open book and the
  stops it journaled, and the desk arms it in one click (desk v0.8.0). Shipped in v1.6: rung 0 - `tyche monitor
  tick` evaluates every journaled level against a quote file at a 5-minute tier, journals
  `monitor.heartbeat` / `.breach` / `.clear` / `.gap` / `.error`, de-duplicates by transition and fails closed when
  it could not judge; the synthetic-breach drill runs it end to end on a pinned clock and its record is under
  [../docs/validation/](../docs/validation/2026-11-21-synthetic-breach-drill.md). Still open in the same ladder: a
  scheduled runner that supplies fresh quotes (the tick reads files, so this is a card/schedule decision, not a
  kernel one), the wall-clock drill leg with the operator present, the bark, and only then any queueing behaviour.
- **Deferred, needs a decision:** the `rules.refrozen` writer, the backtest harness, the monitor's bark (ADR 0013
  rung 1) and narrowing the ETF universe further to equity-only.

## 9. Version history

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-11-16 | `DESIGN.md` written as the v0.1 baseline: rotation strategy, risk caps, LLM perimeter, journal. Still the reference for the safety core; §2/§11 no longer describe the platform. |
| v0.2 | 2026-11-18/19 | Window scope lifted to stocks + defined-risk options (L-001 cut), MCP execution path (ADR 0008), tactical and scalp lanes, envelope and lifecycle gates, persistence split, four-agent topology, hosted desk. Never written up as a PRD - the gap this document closes. |
| **v1.0** | 2026-11-20 | First PRD. Written from an audit of the code and the live platform rather than from the README: capability statuses, the §7 defect list, and an updated architecture in [architecture.md](architecture.md). Simultaneously: `playbook/` became the strategy library, `archive/` became the only superseded-work dump, the per-lane freeze source was fixed (L-036/L-037), and five superseded cadence scripts were retired. |
| **v1.1** | 2026-11-20 | Hosted-desk claims corrected after checking what the exporter actually does: `desk-site/` is not uniformly generated (the Sites Function and the tracked data feed are load-bearing), and a full export used to delete assets it cannot rebuild (L-039, fixed). Capability statuses are now asserted against the vocabulary in [README.md](README.md) by `test_prd_capability_statuses_use_the_fixed_vocabulary`. |
| **v1.2** | 2026-11-20 | Phase 4a: operator strategy switches. `src/tyche/lanes.py` owns `data/strategies.json`, the kernel resolves enablement through it after the freeze check, `tyche strategies` prints it, and both desks can flip a lane (desk v0.6.0). A toggle is deliberately not a rules change: no hash moves, no lineage entry, and exits keep running while entries block (L-037). Scout honoring the live set is still open because it is a prompt change, hence a re-pin. |
| **v1.3** | 2026-11-21 | Phase 4b: scheduled daily checks and Run Scout (desk v0.7.0-v0.7.1). `scripts/cloud_api.py` is a whitelisting cloud client - it drops `environment_variables`, `initial_events`, mounts and vault ids before anything reaches a browser (L-038) - and the desk reads the cadence card that owns a date, pauses and resumes it and fires one run, with the pause re-read from the platform before it is reported. Run Scout starts the researcher session alone; no envelope, halt or approval path is touched. Two defects this increment found and fixed: `evaluate()` was handed a `date` where it needs a `datetime`, and a raw newline inside a JS string made the whole desk fail to parse while every Python test stayed green (L-040, now a test). |
| **v1.4** | 2026-11-21 | Phase 5 close-out: no capability changed status, the **evidence** behind them was re-checked against the code. 40 of 42 §5 rows held; six defects were fixed - PB-002/PB-003 cited a shared id ternary rather than the `options_enabled` gate, the lifecycle `reserve` range overshot by a line, `quote_order_book` read like repo code when it is an MCP read tool enabled on the executor, two test counts were stale, and the header still said 1.2 under a v1.3 table (now a test). §7 gained the unlinted `dashboard/` tree, the narrow-viewport approval clip, the publish-on-hold truth and a gated-items table naming each closing condition. [../docs/dashboard.md](../docs/dashboard.md) no longer calls the act/wait gate prompt-honored: `lifecycle.py:485` blocks it in code. ADR 0013 finally has the contract it promised: [../docs/runbooks/intraday-protection-monitor.md](../docs/runbooks/intraday-protection-monitor.md), a draft for review with nothing deployed. |
| **v1.5** | 2026-11-21 | ADR 0013's rung 1.5 built: `src/tyche/envelope.py` drafts the operator's exit note from the book the desk shows plus the stops the plans journaled, `tyche propose-envelope` and the desk's Propose/Arm card turn it into a same-day sell-only envelope only when the operator clicks, and `risk.exit_collar_pct` (5%) became the single exit number the operator owns (desk v0.8.0). Nothing in it detects a breach - the tick is still unbuilt - and nothing in it can write `data/approvals.json` except the arm click. §7 gained the reason PB-001 ballast gets no drafted line (the rotation stop is computed at `rotation.py:351-353` and never journaled). |
| **v1.6** | 2026-11-21 | ADR 0013's rung 0 built. `src/tyche/monitor.py` + `tyche monitor tick` (`src/tyche/cli.py:55`) evaluate every journaled or entered protective level against a quote file at the 5-minute tier and journal `monitor.heartbeat` / `.breach` / `.clear` / `.gap` / `.error`: nothing is written without `--record`, `--at` replay cannot record, an unjudgeable tick exits `2` instead of saying "no breaches", and episodes de-duplicate by transition. `scripts/drill_synthetic_breach.py` rehearses runbook §8 on a pinned clock ([record](../docs/validation/2026-11-21-synthetic-breach-drill.md)) and caught a real defect on the way: exposure and coverage were being measured from the journal's append stamp rather than the payload's market time, which reported 386,832 s of naked risk for a 135 s breach. Fixed and guarded (L-043). Suite 530 → 553. Not claimed: a schedule that runs the tick, per-tick alert routing, or the operator-present live-session drill leg. |

**Maintenance rule.** A change to a capability's status, a new lane, a new agent or a new external
integration is a PRD edit with a version bump and a [CHANGELOG.md](CHANGELOG.md) row, landed in the same
commit as the code. Prose-only edits do not bump the version.
