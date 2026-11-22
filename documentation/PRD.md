# tyche Product Requirements Document

| | |
|---|---|
| **Version** | 1.15 |
| **Last revised** | 2026-11-22 |
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
| NYSE published-calendar drift detection | implemented | `nyse_calendar.py:74,152`, `tyche calendar-check`, `CALENDAR DRIFT` in `scripts/deploy_two_fire_automation.py` | alert-only and prompt-level: the 08:05 premarket fire of both live desk cards fetches the NYSE page, runs the diff and reports drift; it cannot edit a calendar, a cap or a cron, and the re-pin stays `scripts/refresh_calendar.py` under the operator |
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
| `rules.refrozen` journal producer | implemented | `src/tyche/freeze.py`, `tyche rules-freeze` (`src/tyche/cli.py:1360`), `tests/test_rules_freeze.py` (18 tests) | Records a lane's bytes, its playbook's declaration and its previous chain hash in one row. `old_hash` is taken **only** from the journal, a lane whose document disagrees with the kernel blocks the whole run, `--record` needs a `--reason`, and check mode writes nothing. Ran against the live chain on 2026-11-21: `rules.refrozen` PB-001 `569eb2c341e0` -> `819ad06e35f0` (event `5f1b2b82b48a`) and first-ever `rules.frozen` rows for PB-002/PB-003 (`1664156d6346` / `4f3e84d163ec`) and PB-004 (`5f6d8ab3cc1d`); chain 89 -> 93 events. What it still cannot do is invent provenance for the past: the pre-2026-11-20 lineage remains documented, not journaled |
| Config-change journaling with effective time | partial | L-032 records the requirement | a cap change is currently inferred from later plans |

### 5.5 Desk and reporting

| Capability | Status | Evidence | Gap / note |
|---|---|---|---|
| Local desk with overview/strategy/risk/automation/controls views | implemented | `dashboard/static/index.html`, `server.py:1505` (`build_state`), routes `server.py:2338-2400` | version + changelog in `app.js`, currently `0.10.0` |
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
| Four pinned cloud agents, authored on the Managed plane (coordinator 34, researcher 19, executor 19, auditor 12) | implemented | `scripts/deploy_managed_agents.py status` read of the platform on 2026-11-21, [../docs/agent-rules.md](../docs/agent-rules.md) | pins are restated in prose and **will drift**; the platform read is the authority. Coordinator v31 -> v34 moved as four guarded writes (stale caps, `sentinel-digest`, Trim A, Trim B), each printing the fields that moved (L-045/L-046/L-047/L-049) |

| One permanent weekday card, 08:05 / 12:05 watch-only / 15:05, holidays gated in-run | implemented | `scripts/deploy_two_fire_automation.py` (`DESK_CRON = "5 8,12,15 * * 1-5"`), `cloud_api.pick_card`; live card `dep_00w9n1b9mkb9cjkalhcv` on desk `agent_00w96vnmjp81t0rfdqun` v1, verified 2026-11-22 | the two monthly cards are paused as rollback until the first clean day, then archived; `scripts/telegram.py` `DESK_CARD_IDS` still names them (tracked by the Telegram approval thread). Script file name says "two fire"; script is truth |
| Least-privilege tool grants (deny-by-default MCP allowlists) | implemented | live read of the Managed agents 2026-11-21: researcher 25 enabled read-only tools, executor 14 of 15 with `quote_rt_data` disabled, coordinator 9 built-ins and no MCP server, auditor 4 | assert the allowlist after every re-pin (L-023). The surface is now unwritable from `scripts/`: the driver never sends `tools`/`mcp_servers`, and the Forward tool-policy writer is parked with a fence test, because a template write recompiles and can materialise a grant the running pin never had (L-046) |
| Independent per-order risk audit | implemented | auditor v12, `reports/<date>-audit.md`, `skills/auditor/exact-order-audit` | auditor has no clock or shell: its times/hashes are desk-head claims (L-024) |
| Scout (idea generation) | partial | researcher v19 role + premarket fire; manual trigger `server.py:2265`; `watchlist.py`, `reports/*-research.md` | the pinned arsenal now defers to the run brief's live lane ids, so a switched-off lane is research rather than a proposal; the manual run still starts the researcher alone, so it can propose nothing that reaches a broker |
| Ideas consumed downstream | partial | `tyche events add` → `config/events.yaml` → gate halves budget | operator triage is the link; nothing auto-promotes an idea into a plan |
| Telegram sentinel | implemented (outbound) | `scripts/telegram.py`, [../docs/runbooks/sentinel-telegram.md](../docs/runbooks/sentinel-telegram.md) | at-least-once semantics; inbound approvals stay the operator's local `listen` bridge, PC-required and stopped by decision (L-003/L-006). Its session discovery was re-based on the cloud API so it can bind a card-fired run (L-051); posting a confirmation or interrupt against a **live** fire is still undrilled |
| CI (ruff + pytest) | implemented | `.github/workflows/ci.yml` | 607 tests; a red pipeline blocks every later phase (L-034) |

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

1. **Nothing re-checks the live prompts between re-pins** (L-033 closed 2026-11-21; the residue is the check).
   Auditor v6 used to say "40 daily entry orders" and "150% buy turnover" and desk v28 "<=40 entry orders/day"
   while `config/risk.yaml` enforced 120 and 300% - two authorities, and the wrong one read as permission. The
   three prompts now name the config and the kernel and quote no number (auditor v12, researcher v19, desk v34
   as of 2026-11-21, four pins later than the ones that closed the defect), applied from
   [the reviewed diff](../docs/reviews/2026-11-21-prompt-repin-proposal.md) by
   `archive/repin_stale_caps.py`, which fails a write if any of six recited-cap strings survives. The same
   class reappeared in a *skill* rather than a prompt, and was fixed the same way (L-048). What is
   still true is that this runs at deploy time only: a cap raised in config cannot make a prompt stale again
   now (no number is in one), but a future hand-edit in the hosted console can, and no CI job reads the cloud.
   Fix: fold the live-agent read (`scripts/deploy_managed_agents.py verify`) into a scheduled `tyche`-side
   check, or accept the console as the drift point.
2. **Two live lanes now have bytes on the chain and no document to review them** (L-035's residue).
   `tyche rules-freeze` recorded all four hashable lanes on 2026-11-21 - PB-001 re-frozen from the mis-recorded
   `569eb2c341e0` to `819ad06e35f0`, and first-ever `rules.frozen` rows for PB-002/PB-003 (`b6bc571033ac`) and
   PB-004 (`72077d5d4808`), chain 89 -> 93 events - so a re-registration is now a record rather than git
   archaeology. What those rows expose is the older gap: PB-002 and PB-003 carry `declared: null`, because no
   playbook declares their hash. That is item 4's missing thesis, now with provenance attached to it.
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
7. **The calendar drift check runs, but nothing proves a fire ran it** (wiring closed 2026-11-21; the
   residue is the proof). The clause used to live only in a paused schedule, so the code had no trigger.
   It is now in the live desk card brief, and the first unattended run is Mon 23 Nov 13:05Z. What is still
   true is that a prompt is not a kernel: a fire that skips the check leaves no trace except the absent
   `calendar.check` event, and only the operator's `scripts/refresh_calendar.py` can re-pin the tables.
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
    itself, and that is by design: `handler.ts` spends its cloud credential on GETs only (`/deployments`,
    `/sessions`) and `/schedule` serves the committed `schedule.json` rather than calling a card, so only one
    path can change cadence and the hosted snapshot advances on push instead of pretending to be live.
    **Not a gap, and this was claimed wrongly once:** all three Secrets the published Function declares
    (`TYCHE_CLOUD_PAT`, `TYCHE_GITHUB_PAT`, `TYCHE_OPERATOR_PASSPHRASE`) are present with
    `sync_state: synced`, so the operator console is configured. That list took the cloud name when item 14's
    republish landed on 22 Nov; the secrets detail still carries a fourth, `TYCHE_FORWARD_PAT`, which no
    published Function declares and the platform refuses to delete (item 14). A Function's
    `required_secret_names` is a *dependency list*, not a gap report - presence and sync only come from the
    secrets detail. **Still unverified:** the console's live behaviour, because the site is
    `access_mode: private` and its gateway answers 401 `sites_gateway_login_required` to unauthenticated
    requests, this agent's browser included; the `operator_configured` read has to be done from a signed-in
    session.
13. **The bridge's write side is proven only against a finished session** (L-051). `/approve`, `/deny` and
    `/interrupt` now POST to `/sessions/{id}/events` on the cloud base, and the endpoint plus the
    `user.message` envelope are proven by `cloud_api.start_scout_run`; posting `user.tool_confirmation` or
    `user.interrupt` against a fire in progress has not been exercised, because doing so against a closed
    session is itself a live write. The drill is scheduled and written up - Mon 23 Nov, the 12:05 ET
    monitor-phase fire, chosen because stopping that run cannot leave an order half-submitted: see
    [../docs/runbooks/sentinel-telegram.md](../docs/runbooks/sentinel-telegram.md).
14. **The hosted desk reads the Managed base in code, and the site now publishes that code.** The local half
    landed on 21 Nov: `dashboard/server.py`'s automation panel lists the cadence through `cloud_api.cards()` and
    the runs through `cloud_api.sessions()`, and `tests/test_forward_fence.py` forbids the desk's own code from
    naming that base again. The hosted `desk-site` Function followed on 22 Nov: `/automation` now fetches
    `/deployments` and `/sessions` under `TYCHE_CLOUD_PAT` and projects every row through `cardView` and
    `sessionView` - the hosted twins of `cloud_api.card_view`/`session_view`, so a raw row's plaintext
    `environment_variables` cannot reach a browser (L-050) - and `session_origin` moved with it, so a run opened
    elsewhere is still labelled as one. The Forward-only fields (`trigger_policy`, `template_id`,
    `source_type`) left the payload, the fence now names `desk-site/functions/handler.ts` among the readers it
    guards, and `dev/test-handler.mjs` proves the live read against the two active cards plus a leak check.
    **The publish landed 22 Nov 05:44Z; the secret removal did not.** Preparation action
    `accb4d5e-0ab6-4946-bd8a-b29ad27b7939` and publish operation `01a201c8-f742-7e59-a2ae-9b8d809e8fc2`
    committed release `01a201c8-9fed-795c-a489-9682b6d1ea6a` with `published: true`, and the active Function's
    declared set is the three names in item 12 - so the hosted card list and the cadence table beside it now
    describe the same two cards instead of one archived and one real. `delete_secret` for `TYCHE_FORWARD_PAT`
    then returned `sites_secret_in_use` on all three attempts, each one preceded by a fresh
    `get_site(include: ["functions", "secrets"])` that did not name it in the active Function: a Secret an
    earlier release declared stays on the books until the platform stops counting it, and no tool argument
    overrides that. It is inert - nothing this project publishes reads it - so what is left is a console entry
    to clear, not a live defect. **The one acceptance check this session cannot do** is the signed-in read of
    the hosted Orchestration pill (item 12): the gateway answers 401 `sites_gateway_login_required` to the
    automated browser, so "the deployed edge authenticates `TYCHE_CLOUD_PAT` and reports the live cloud cards"
    is proven in code and by the local harness, not yet observed in the hosted page.

### Blocked on an operator decision, with what each one needs

| Item | Closing condition |
|---|---|
| Intraday protection monitor (§5.3) | decided 2026-11-21: rung 1.5 (pre-armed bounded exit) is built, Level 2 stays declined; rung 0 (`tyche monitor tick`) was approved and is built, with a pinned-clock synthetic-breach rehearsal recorded. Still open: a runner that feeds the tick a quote file on a schedule, the live-session drill leg that needs the operator, and a separate decision on rung 1 Telegram bark routing. **The tick is deliberately unscheduled for now:** a cloud card that fires outside the session would judge overnight holds on stale quotes, and the challenge book is intraday. Trigger to revisit: the first overnight holding, or a decision to run it as a local cron only while the desk is open |
| Roster child pins: `latest` or numeric (W6b) | not applied, and reversible either way. Today the coordinator's roster pins its children at `version: "latest"`, so a child write is live at the next fire; numeric pins would move that to "next deliberate re-pin", which trades surprise for the opposite failure - a forgotten pin. The children are still changing while strategies are being tested, so the current semantics are the safer ones. Trigger: after Mon 23 Nov, once one clean fire has run on the trimmed brief and the children have stopped moving |
| The two Phase 0 probe sessions | kept, not deleted, on the operator's decision. They are the only surviving evidence that a published skill actually loads in a running session, and a session delete is not reversible. They show up in the panel as "opened elsewhere", which is honest. Trigger: the first skill change whose loading is proven by a scheduled fire - after that the evidence is reproducible and they are ordinary history |
| Hosted `TYCHE_FORWARD_PAT` removal (14) | no decision and no code left. The site republished 22 Nov 05:44Z and the active `app` Function declares only `TYCHE_CLOUD_PAT`, `TYCHE_GITHUB_PAT`, `TYCHE_OPERATOR_PASSPHRASE`; `delete_secret` then refused the orphan three times with `sites_secret_in_use`, each attempt after a fresh functions-plus-secrets read that did not name it. The platform is holding a Secret against a release that is no longer current, and no argument on that call overrides it. The Secret is inert - nothing published reads it - so this is a console entry to clear, not a live defect. Closing condition: the platform stops counting the superseded release, or the operator clears it in the Sites console. A fourth identical call is not a plan |
| Hosted operator console proven unattended (11) | one signed-in browser read of `control/status` and one arm/disarm round trip; the Secrets themselves are present and synced, and the gateway 401s any check from here. The same session is what proves item 14's deployed half: that the live Orchestration pill authenticates `TYCHE_CLOUD_PAT` on the edge runtime instead of falling back to the committed export |
| Telegram bot token | the deployments/sessions API returns `environment_variables` in plaintext, which is why `cloud_api.py` whitelists every payload before it reaches a browser (L-038); rotating the token itself is an operator action outside the repo |

Closed during this refinement and kept off the list: the desk server had no documented launch command
(it is in the README command table now) and the site export deleted hosted assets it could not rebuild
(L-039). Also closed: `docs/dashboard.md` described the act/wait gate on the MCP path as prompt-honored when
`lifecycle.py:485` blocks it in code; the doc now states the mechanism and the prompt is labelled a backstop.
Also closed on 2026-11-21, on the operator's approval: the recited risk caps (L-033) and the Scout's
live-lane clause, both re-pinned into auditor v7 / researcher v17 / desk v31 with the two scheduled cards
moved off v28 - and the desk's platform-managed `drive`/`schedule` tool group taken back out, because the
grant the template carried was never part of the pin that had been running (L-046). The same day the
calendar-drift check (7) moved from the paused schedule's `initial_events` into that card brief, so the
trigger the code had been waiting for is the fire that already runs.

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
- **Deferred, needs a decision:** the backtest harness, the monitor's bark (ADR 0013
  rung 1) and narrowing the ETF universe further to equity-only. The `rules.refrozen` writer is no longer on this
  list - it shipped in v1.7 as `tyche rules-freeze` and recorded all four hashable lanes on 2026-11-21.

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
| **v1.7** | 2026-11-21 | L-035's missing writer landed: `src/tyche/freeze.py` + `tyche rules-freeze` (`src/tyche/cli.py:1360`) compare one lane's bytes, the hash its playbook declares and the hash the journal last recorded, and can append the `rules.frozen` (first row for a lane) or `rules.refrozen` (each one after) event the freeze contract assumes - with `old_hash` taken only from the chain, the two source files' full sha256 alongside the 12-hex lane hash, and a required `--reason`. Check-only by default; a lane whose document disagrees with the kernel blocks the whole run rather than quietly registering the healthy neighbours, and an invalid chain or a missing reason exits `2` having written nothing (exit `1` means drift, not failure). Against this repo it read the truth the docs already suspected - PB-001's chain said `569eb2c341e0` where the bytes say `819ad06e35f0`, and PB-002/PB-003/PB-004 had never been recorded - and on the operator's approval it then recorded all four: `rules.refrozen` PB-001 (event `5f1b2b82b48a`) and first-ever `rules.frozen` rows for PB-002 (`1664156d6346`), PB-003 (`4f3e84d163ec`) and PB-004 (`5f6d8ab3cc1d`), chain 89 -> 93 events and verified. §5.4 moves to `implemented`, and §7 item 2 shrinks to what those rows expose: PB-002/PB-003 carry `declared: null` because no playbook declares their hash. `tests/test_docs_consistency.py` now reads the declared hashes through the same parser, so CI and the tool cannot disagree about the same line. Suite 553 -> 571; CI then caught a test that had been asserting on rich's line-wrapped output and passed here only because this terminal is wider (L-044). No cloud object changed. |
| **v1.8** | 2026-11-21 | L-033 closed on the operator's approval. `scripts/repin_stale_caps.py` applied the reviewed byte-exact diff ([the proposal](../docs/reviews/2026-11-21-prompt-repin-proposal.md)): the auditor stopped reciting "40 daily entry orders / 150% buy turnover / <=100 positions", the desk stopped reciting "<=40 entry orders/day", and the researcher's arsenal paragraph now defers to the run brief's live lane ids. Both authority edits end at `config/risk.yaml` and the kernel's verdict rather than at a number, so the next cap raise cannot rot a prompt. Pins moved as a chain, because a template edit alone changes nothing that runs: auditor v6 -> v7 (system sha `895754b43589`), researcher v16 -> v17 (`6b9bce87ed03`), desk v28 -> v29 carrying the prompt *and* the roster re-pin 7/17/15 in one write (`d3ee24f78f05`), then both scheduled cards off v28. Two findings the platform handed back, both recorded as lessons: the desk template carried a `managed_tool_config` of `drive` + `schedule` that v28 never materialised and v29 did - ten always-allow tools including `delete_forward_schedule` and `delete_drive_entry`, against a card that says the paused schedule must stay paused - so the operator had the grant stripped and the pin rebuilt to desk v30 (L-046); and rebuilding that roster from the rows that carry a `template_id` silently dropped the model-only advisor row ADR 0011 names, which was restored as v31 with the child pins and prompt byte-identical (L-045). Verified against the compiled agents, not the templates: desk v31 has 9 built-ins and no MCP server, auditor v7 4 and none, researcher v17 6 plus 24 read-only moomoo tools, executor v15 untouched. `dep_00vzb9h4ezawwl4thnva` and `dep_00vzd8d5rdfr4w0denqh` pin v31, each card's 11,972-char prompt, cron and env keys asserted byte-identical before and after the move, so the first run under the new authority is Mon 23 Nov 13:05Z. No config value, cap, schedule or order path changed; suite stays 571 because the writer is an ops script, not kernel code. |
| **v1.10** | 2026-11-21 | The desk is authored on one plane. Three role skills (`skills/<role>/<name>`) now carry procedures the four prompts used to restate, and the prompts were trimmed twice through a new Managed driver (`scripts/deploy_managed_agents.py`: `status`/`export`/`diff`/`apply-system`/`publish-skill`/`attach`/`roster`/`pin-card`/`verify`, one field group per write, a guard that prints every field that moved). Pins after the work: coordinator v34, researcher v19, auditor v12, executor v19, and both scheduled cards re-pinned to v34 with cron, `initial_events` hash and env *key names* asserted unmoved. The trim found two defects it was not looking for: two skills contradicted the kernel that enforces them (L-048, corrected versions pinned on auditor and executor), and the driver's own guard was blind to a skill re-pin because it keyed skills by id only (L-049). The Telegram bridge's session discovery moved off the eight paused Forward schedules that had made `/status`, `/approve` and `/interrupt` dead for card-fired runs (L-051), and reads now retry a transient 404 where writes deliberately do not (L-052). Forward residue was retired the careful way: eight template/schedule writers moved to [../archive/MANIFEST.md](../archive/MANIFEST.md) with rows, [../tests/test_forward_fence.py](../tests/test_forward_fence.py) fails if anything under `scripts/` authors a template again, the four Forward templates stay untouched because a template write recompiles (L-046), and the eight paused schedules were archived the same day - `POST /forward/schedules/{id}/archive`, eight calls, each re-read as `archived_at` and with the Managed projection (agent versions, prompt lengths, skill pins, both cards' pin/events hash/env keys) asserted unmoved between calls, so the default Forward schedule list is now empty. §5.6 re-read from the platform, [../docs/agent-engineering.md](../docs/agent-engineering.md) now says what lives where, and the ledger grows L-048 through L-053. Suite 607, ruff clean. Items 13 and 14 record what the cutover did not finish: the bridge's write path undrilled against a live fire, and two display-only readers still pointed at Forward. |
| **v1.11** | 2026-11-21 | The desk's Orchestration panel now describes the plane the desk runs on. `dashboard/server.py` does not import the Forward client any more: the cadence comes from `cloud_api.cards()` - cron, timezone, window, status, agent pin and `next_runs` per card - and the run history from `cloud_api.sessions()`, each row reduced by `cloud_api.session_view()`, the same whitelist the bridge uses. That is what keeps a session's plaintext `environment_variables` out of the panel (L-050) while still supplying credits and wall time without an extra GET per run. The Forward-shaped shim is deleted rather than renamed (`slim_schedule`, `slim_session`, `sentinel_fallback`, and the `template_id`/`trigger_policy`/`initial_events_version`/`source_type` fields), each session is labelled by what is provable about its origin (cadence card, Research Scout, or opened elsewhere), and an unreachable cloud **blinds** the panel with the problem stated instead of refilling it from a committed export. `desk-site/web/` was re-exported from the same source and the desk UI is v0.9.0. [../tests/test_forward_fence.py](../tests/test_forward_fence.py) gained `test_the_desk_itself_does_not_read_the_forward_base` and [../tests/test_desk_schedule.py](../tests/test_desk_schedule.py) four tests for the new payload, so the panel cannot drift back to the archived base. §7 item 14 shrinks to its hosted half: `desk-site/functions/handler.ts` still lists `/forward/schedules` and `/forward/sessions` with `TYCHE_FORWARD_PAT` - present and synced, so the hosted live overlay reports zero schedules while the baked export shows the cards - and repointing it needs a Managed PAT in Sites secrets, which is its own approval. Suite 607 -> 612. |
| **v1.12** | 2026-11-22 | The Strategy view's cadence table now describes the fires that exist. `build_calendar()` had kept emitting `generate_hourly_schedules()` - the retired six-run hourly design's schedule model - so beside a correct Orchestration panel the desk still listed 09:05, 10:05 and 16:05 ET fires no card makes. The rows are now derived from the cards themselves: `card_cadence()` expands each card's own cron into one row per fire time, takes cron/timezone/window/day-count off that expression, and asks the kernel gate (`phase_at` -> `strategy_for`) what that wall-clock hour routes to on the first session day inside the card's window (`_cadence_reference_day`), which is why a weekend never labels a healthy card's whole table CLOSED. Against the two live cards it reads 08:05 pre_market/plan, 12:05 midday/monitor, 15:05 closing_drive/active for both, with 7 dated days on the November card and 22 on the December one. Blind is blind here too: unreadable cards give an empty table that says so. The kernel function and its gate semantics were left alone - `tyche schedule --hourly` and `tests/test_market_calendar.py` still describe that model, which is honest for a generator but was never honest as a status report. Desk UI v0.9.0 -> v0.10.0, hosted export re-baked, §5.5's desk row re-pointed at the current version, and [../docs/dashboard.md](../docs/dashboard.md) names the cards as the table's only source. Suite 612 -> 616 (four tests in [../tests/test_desk_schedule.py](../tests/test_desk_schedule.py) pin the derivation, the routing labels, the reference-day rule and the single answerer). No cloud object, cron, cap or gate changed. |
| **v1.15** | 2026-11-22 | The desk cadence becomes one permanent card instead of one card per month. `scripts/deploy_two_fire_automation.py` now authors cron `5 8,12,15 * * 1-5` in `America/New_York` with an open-ended `metadata.window` (`YYYY-MM-DD..`), and relies on the in-run `tyche calendar --json` gate for NYSE holidays instead of a per-month trading-day list - the monthly design's failure mode was a month nobody regenerated. `cloud_api.pick_card` reads both window shapes and, when a paused monthly card sits beside the permanent one during the cut-over, picks the card that still fires; `dashboard/server.py` judges an open window on the next fortnight of sessions and counts weekdays off the cron's last field. A prompt update (`--apply-update`) now re-sends the live card's own cron and metadata so the "only `initial_events` moved" guard is honest, and the create path refuses a second active desk card without `--allow-overlap` (two cards that fire are two writers). **Not done, and not to be done before Mon 23 Nov's 08:05 and 12:05 ET fires and the operator's explicit approval:** creating the live card, pausing the Nov/Dec cards and archiving them after the new card's first clean fire. §5.6's cadence row is reworded; no cap, gate, risk policy, agent pin or live card touched; `scripts/telegram.py`'s `DESK_CARD_IDS` still names the two monthly cards and gains the new id only once it exists. Suite 644 -> 651. |
| **v1.14** | 2026-11-22 | Status correction after the two hosted writes, no code change. §7 item 14's headline is now true: the published `desk-site` `app` Function serves the Managed `/automation` read (preparation action `accb4d5e-0ab6-4946-bd8a-b29ad27b7939`, publish operation `01a201c8-f742-7e59-a2ae-9b8d809e8fc2`, release `01a201c8-9fed-795c-a489-9682b6d1ea6a`, `published: true` at 05:44Z), so the hosted card list and the cadence table beside it describe the same two cards instead of one archived read and one real table. Item 12's Secret list is corrected from the Forward name to the three the active Function actually declares, and its `handler.ts:8-10` claim - that the cloud token stays off the server - is replaced by what is now true and what the code enforces: the credential is present server-side, spent on GETs only, with `/schedule` serving the committed `schedule.json` so cadence still has exactly one writer. The third step did not land: `delete_secret` refused `TYCHE_FORWARD_PAT` three times with `sites_secret_in_use`, each after a fresh functions-plus-secrets read that did not name it in the active Function, so the orphan is a platform-held entry against a superseded release rather than a live exposure, and the blocked row now says that instead of promising a removal. The acceptance read that closes item 14's last inch is also recorded as *not done*: the site gateway answers 401 `sites_gateway_login_required` to an automated browser, so the live-cloud pill has to be seen from the operator's signed-in session. Credential *roles* are stated without values anywhere in this repo: `QODER_PAT` in the gitignored local `.env` is what the desk, the bridge and the deploy drivers authenticate with, `TYCHE_CLOUD_PAT` is what the hosted Function reads with, and which console token sits behind each name is the operator's to confirm in the console - an inference from a 18 Nov `.env` write time is not a record, and no token is to be revoked on this document's say-so (the earlier advice to revoke the older one was wrong and is withdrawn). Suite unchanged at 616; desk UI unchanged at v0.10.0; no card, cron, cap, gate, risk policy or Secret *value* touched. |
| **v1.13** | 2026-11-22 | The hosted `/automation` read moved to the Managed plane in code. `desk-site/functions/handler.ts` fetched `/forward/schedules` and `/forward/sessions` under `TYCHE_FORWARD_PAT`; since the eight schedules were archived that overlay returned nothing, and because its cadence rows ride in on the baked `base.calendar` the hosted desk showed live-but-empty cards next to a cadence table describing two real ones. It now fetches `/deployments` and `/sessions` under `TYCHE_CLOUD_PAT` (mounted in Site Settings by the operator, the same credential the local desk already authenticates with - a read-only probe through `cloud_api.cards()` confirmed it works on `/api/v1/cloud`) and projects each row through `cardView`/`sessionView`, the hosted twins of `cloud_api.card_view`/`session_view`, with `sessionOrigin` ported from `dashboard/server.py` and the Scout tag as the `SCOUT_KIND` literal: identity, state, cadence and credits leave the function, and a raw row's plaintext `environment_variables` cannot (L-050). `forward.py`-era fields `trigger_policy`, `template_id`, `source_type` and the `template` object are gone from the payload. `tests/test_forward_fence.py` now guards `desk-site/functions/handler.ts` alongside the local panel, so the retired base has no reader left in anything this project publishes, and `dev/test-handler.mjs` grew a live-token block - cards as cadence, origins proven, cadence rows still riding the overlay, and explicit checks that neither `environment_variables`/`vault_ids` nor any token-shaped string reaches the response. All 21 harness checks pass against the real API. **No hosted write happened:** the published Function still declares `TYCHE_FORWARD_PAT`, so republish and then remove that secret remain two separately approved steps (§7 items 12 and 14, and the blocked-row that tracks them). No cap, gate, cron, card or risk policy changed; desk UI stays v0.10.0 because no `dashboard/static/` file moved, and the suite count is unchanged at 616. |
| **v1.9** | 2026-11-21 | §7 item 7's wiring gap closed: the NYSE drift check moved out of the paused `tyche-hourly` schedule's `initial_events` - where nothing could ever execute it - into the authored desk card brief (`CALENDAR DRIFT` in `scripts/deploy_two_fire_automation.py`), and both scheduled cards were rewritten onto it: `dep_00vzb9h4ezawwl4thnva` and `dep_00vzd8d5rdfr4w0denqh`, `initial_events` sha `de2f4907f7378b87` / `b172199383602dae`, still pinned to desk v31 with cron, status, vaults, resources and env keys asserted unmoved and 14 prompt lines added / none removed. The clause stays alert-only: fetch the page, run `tyche calendar-check --source data/nyse-calendar.txt --json`, put a non-zero exit's `changes`/`warnings` in the digest's Problems section, journal `calendar.check`, and never edit config, a cap or a cron day list - re-pinning remains `scripts/refresh_calendar.py` under the operator. Verified against the live page rather than a fixture: today's nyse.com output parses to `changed: false, uncertain: false`, exit 0, so Monday 23 Nov 13:05Z is the first unattended run. The card update path inherited the re-pin's discipline and now refuses a card whose pin is not an exact version, refuses any field move beyond `initial_events`, and no longer demands local copies of secrets an update never sends. §5.1 moves `partial` -> `implemented`; item 7's residue is proof, not wiring: a fire that skips the check leaves only an absent event. `scripts/deploy_calendar_check.py` is marked superseded rather than deleted, because the paused schedule still carries its wording. Suite 571 -> 572. |

**Maintenance rule.** A change to a capability's status, a new lane, a new agent or a new external
integration is a PRD edit with a version bump and a [CHANGELOG.md](CHANGELOG.md) row, landed in the same
commit as the code. Prose-only edits do not bump the version.
