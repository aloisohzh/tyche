# Platform refinement audit - 2026-11-20

Scope of this review: the whole repository (deterministic core, agents, dashboard, scheduler, docs,
playbooks, lessons) against the operator's refinement brief - organization, architecture,
maintainability, usability, and a stocks-and-options-only trading scope.

**Nothing was modified to produce this audit.** Findings are evidence-linked. Test baseline at the
time of writing: `432 passed in 19.01s`, but **`ruff` fails and CI has been red on `main`** - see §3.0.

Repo shape: 286 tracked files, 16 top-level directories, 30 Python modules (7,545 LOC in `src/`),
4 dashboard files (5,527 LOC), 144 tracked docs files, 16 ADRs, 32 lessons, 11 cloud-deploy scripts.

---

## 1. Verdict

The platform is not a mess of broken code - it is a **working system with an accreted surface**. The
deterministic core, the risk kernel, the journal and the docs spine are in good shape and should be
preserved as-is. The mess is concentrated in four places:

1. **Two generations of the same mechanism running side by side.** Three scheduler designs, two
   dashboard UI trees, three parallel CLI modules, and 11 one-shot deploy scripts whose hardcoded
   ids disagree with the docs that describe them.
2. **Docs drift, not doc absence.** The spine (`docs/README.md` → ADRs → playbooks → lessons →
   validation) is a strong asset, but its index now points at a deleted file and its agent doc
   describes a cadence that was superseded on 2026-11-20.
3. **Strategy identity is split across three conventions.** Only PB-001 obeys the documented
   "one playbook + one `config/strategies/pb-xxx.yaml` + one registry module" contract. The two
   strategies that actually trade intraday (scalp, tactical) live outside it, and PB-004's id is
   double-claimed (L-029).
4. **The requested operator controls do not exist.** There is no strategy toggle, no manual scout
   trigger, and no schedule switch on any dashboard surface. The read paths for all three already
   do exist, which makes this additive work rather than a rebuild.
5. **The CI gate is currently red** (§3.0), so "tests pass" has not actually been proven by the
   pipeline for the last three commits. Fix this before building on the validation signal.

Reuse-heavy, rewrite-light is the right call here. See §5.

---

## 2. Capability matrix

### 2.1 Implemented and working - preserve

| Capability | Where | Evidence |
|---|---|---|
| Typed, validated config with a real strategy enable flag | `src/tyche/config.py:67-232` | `StrategyConfig.enabled`, `AppConfig.enabled_strategies()`, cross-lane symbol-overlap guards at `config.py:271-276` |
| Deterministic pre-trade risk kernel | `src/tyche/risk.py`, `trade_risk.py`, `fees.py` | `docs/risk-card.md` doc-as-test; `tests/test_risk.py`, `test_fees.py`, `test_trade_risk.py` |
| Hash-chained audit journal | `src/tyche/journal.py` | `verify_chain`, asserted in `tests/test_journal.py`, surfaced in the dashboard header |
| Kill switch + approval envelope | `src/tyche/halt.py`, `approvals.py` | `POST /api/halt`, `/api/approvals/arm|disarm` in `dashboard/server.py:1814-1910`; kill-switch drill recorded in `docs/validation/2026-11-18-kill-switch-drill.md` |
| Paper-only broker guard | `src/tyche/broker/` | allowlist conjunction per ADR 0002 / L-010; `tests/test_broker.py` |
| Market calendar + session-phase gate | `src/tyche/market_calendar.py` (517), `nyse_calendar.py` | `tyche calendar --json`; drives run/no-run and is unit-tested |
| Scout idea schema (rich) | `src/tyche/watchlist.py` | thesis / synthesis / edge / bear case / invalidation / factor axes / entry zone / stop / target / `confirmation_ticks`; options-aware |
| Journal-derived dashboard state + honest derived/gap labelling | `dashboard/server.py:128-333` (`derive_contract`, `build_instrumentation`) | `tests/test_cloud_feed.py`, `test_desk_thesis.py`, `test_docs_consistency.py` |
| Hosted desk published from the same code | `scripts/export_dashboard.py` → `desk-site/` | reuses `server.py` builders; redacts ids; hard secret guard refuses the write |
| Multi-agent topology with least privilege | 4 live cloud agents | `tyche-desk` v28, `tyche-researcher` v16, `tyche-executor` v15, `tyche-risk-auditor` v6 (QCA `list_agents`) |
| Lessons ledger | `docs/lessons/LESSONS.md` | 32 evidence-linked rows, append-only, category tables, row template |

### 2.2 Partially implemented - complete, do not reinvent

**Strategy registry (PB-001 only).**
`src/tyche/strategies/__init__.py` is `REGISTRY = {"PB-001": rotation_targets}`. `config/strategies/`
holds exactly one file. Meanwhile the two strategies that actually trade are configured outside the
contract: `config/scalp.yaml` (flat `enabled: true`, no `id`, no `playbook` ref) and
`config/tactical.yaml` (`enabled`, `execution_enabled`, `options_enabled`). The README's stated
onboarding path (playbook + yaml + registry module, ADR 0014) is therefore aspirational for 2 of 3
live lanes. `DESIGN.md §12` already tracks "strategy protocol and strategy-agnostic plan schema" as
open work - this is the same gap, and it is the direct blocker for dashboard toggles.

**Playbooks.** `docs/playbooks/` = `README.md`, `_TEMPLATE.md`, `PB-001-etf-rotation-ballast.md`.
PB-002…PB-005 exist only as rows in the README table. PB-004 is *live* (scalp) with no playbook file.
There are **no classification dimensions anywhere** - nothing encodes holding period, strategy type,
execution style or instrument. `tests/test_strategy_ledger.py` grades results per strategy, so a
per-id ledger key already exists to hang classifications beside.

**Scheduler - three coexisting generations.**
&nbsp;&nbsp;a. `docs/agent-engineering.md:61-72` documents **six fires** (`tyche-hourly`, 08:05…16:05 ET).
&nbsp;&nbsp;b. `plans/live-schedule.json` + `desk-site/web/data/automation.json` show that hourly card, `status: "paused"`, plus five gate-routed siblings (`tyche-closing-drive`, `tyche-midday-monitor`, `tyche-opening-drive`, `tyche-eod-halfday`, `tyche-closing-drive-halfday`) and six archived payloads under `plans/sentinel/sched_*.json`.
&nbsp;&nbsp;c. `scripts/deploy_two_fire_automation.py` - the live mechanism per commits `1430300`…`e53d045` - creates **three-fire** Cloud Automation cards (08:05 premarket / 12:05 midday watch-and-shout / 15:05 close), one per month, targeting `agent_00vtt1wjgm22o20s8ykz`.
The dashboard reads schedules read-only through `build_automation()` (`server.py:1780`) and can
neither switch them nor change their time. `slim_schedule()` already returns `trigger_policy`
including `cron`, `timezone` and `upcoming_runs_at`, so the read side of "next scheduled run" is done.

**Run history / observability.** `load_cloud_runs()` (`server.py:1023`), `sentinel_fallback()`,
`slim_session()` and the Orchestration view give sessions, status, usage and credits. What is
missing is only the *manual-trigger* record - no run can be started from the desk today, so there is
nothing to key that history on.

**Agent rules.** `docs/agent-engineering.md` is a strong topology contract, and the agents' hard rules
are enforced server-side in each agent's `system` prompt (verified via `list_agents`). But the
repo-side rule file the docs index points to was archived on 2026-11-19 (§3.1), leaving nothing in the
repo that states the hard rules - and **no rule anywhere requires an agent to consult lessons before
significant work.**

### 2.3 Missing entirely - build new

| Requested | Current state |
|---|---|
| `archive/` at repo root | absent; only `docs/archive/` (5 frozen artifacts) exists |
| `documentation/` with versioned PRD | absent; no PRD exists in any form |
| `playbook/` as an agent-loadable strategy library | absent; playbooks live in `docs/playbooks/` and carry no machine-readable front matter |
| Dashboard strategy enable/disable + persistence | absent - toggling a strategy means editing YAML and committing |
| Dashboard "Run Scout" | absent - no POST route triggers any agent or workflow |
| Scheduled daily-check toggle / time / timezone UI | absent (read-only list only) |
| Stocks-and-options-only scoping | violated - see §4 |

---

## 3. Technical debt and inconsistencies

### 3.0 CI is red on `main`

`pytest` is green (432 passed) but CI also runs `ruff check src scripts tests`, and that fails:

```
I001 [*] Import block is un-sorted or un-formatted  --> src/tyche/cli.py:1:1
-from tyche.strategy_ledger import StrategyPolicy, score as score_strategy
+from tyche.strategy_ledger import StrategyPolicy
+from tyche.strategy_ledger import score as score_strategy
```

Reproduces with the pinned `ruff==0.17.5` (`constraints.txt:34`), on the committed tree. `gh run list`
shows the last three `main` pushes each completed **failure** in ~22 s (`44685671254`, `44680531206`,
`44676118035`) - the runs die at the lint step, before `pytest`, so nothing has been CI-verified since.

One line, zero behavioural risk, and it is the gate every later phase depends on. It belongs at the top
of P0 and should land as its own commit so the validation signal is clean from Phase 3 onward. This
also fits the repo's own convention of asserting the tool contract after any change (L-023).

### 3.1 Dangling references, and no repo home for agent hard rules

`.qoder/` is an **empty directory**. Two living docs still cite a file that is no longer there:

- `docs/README.md:25` - links `[.qoder/cloud-agent.md]` against `../.qoder/cloud-agent.md`, labelled
  "(agent hard rules)"
- `DESIGN.md §12` - "Create and validate the Cloud Agent deployment described in `.qoder/cloud-agent.md`"

**This is not lost work.** Commit `6ee2b28` records it as a pure rename -
`.qoder/cloud-agent.md => docs/archive/cloud-agent-draft-2026-11.md`, 0 insertions, 0 deletions, and
the archived copy diffs byte-identical against the original. The move was deliberate: that file is a
stale v0.1 draft whose own header says the CLI + OAuth path does not work in a cloud sandbox and
"Do not deploy from it as-is." Restoring it would resurrect a superseded spec - see the recorded
pattern in L-011 and L-020.

Two real defects follow from the move:

1. **The index lines were never repointed**, so `docs/README.md` - the doc spine's entry point -
   404s on its own "agent hard rules" row.
2. **Nothing in the repo states the agent hard rules any more.** They survive only inside the four
   live cloud system prompts (verified via `list_agents`: the executor prompt carries the allowlist
   conjunction, the no-blind-retry rule, cancel/modify `always_ask` and the never-reset-the-account
   guard). Those rules were also written down in the archived draft's "Hard rules" block. With the
   file archived, the repo-side statement of them went with it, and `docs/agent-engineering.md` covers
   topology and permissions but is not framed as rules an agent must obey.

Fix: repoint both references at `docs/archive/cloud-agent-draft-2026-11.md` labelled *superseded*, and
add a short authoritative rules doc - recommended `docs/agent-rules.md`, not a second file under the
vacant `.qoder/` - that carries the hard rules plus the new **lessons-review-before-significant-work**
requirement the brief asks for. Making the live agents actually read it is a prompt change, and
therefore a new version pin that only applies to new sessions (L-021): schedule it with the Scout
prompt work in P2 rather than treating the doc alone as enforcement.

**Correction and status (2026-11-20).** The count above is wrong: there were **three** dangling
references, not two. `docs/runbooks/operations.md` §6 also cited `.qoder/cloud-agent.md`, and the move
of the playbook library to `/playbook` produced two more (`PB-001`'s own runbook link, plus stale
archive links to `../docs/agent-engineering.md` and `../DESIGN.md`). All are repointed, and
`docs/agent-rules.md` now exists. The durable fix is the guard, not the hunt:
`test_markdown_links_resolve` fails on any local markdown link whose target is missing, so a future
move cannot leave rot behind. It ignores anchors, URLs and fenced templates.

### 3.2 Stale documentation

| Doc | Claim | Reality |
|---|---|---|
| `docs/agent-engineering.md:61-72` | six-fire hourly cadence | three-fire monthly card, `deploy_two_fire_automation.py` |
| `README.md:16-21` | "**Current state (18 Nov 2026)**" | 2 days stale; PB-004 scalp, tactical lane, desk v0.5.0 and the three-fire card all postdate it |
| `README.md:125-139` status checklist | "[ ] Cloud Agent deployment" | 4 agents are live and version-pinned |
| `docs/playbooks/README.md:16-25` | PB-004 = "Sector rotation heat" | PB-004 = live intraday momentum scalp (`config/scalp.yaml`) - L-029, still **open** |
| `pyproject.toml:4` | description "Regime-aware ETF rotation agent" | platform is strategy-agnostic per ADR 0007/0014 |

### 3.3 Generated artifacts tracked in git

`dashboard/static/` and `desk-site/web/` carry the same UI. `app.js` is byte-identical; `style.css` is
identical modulo CRLF↔LF; `index.html` differs by exactly one generated line
(`window.TYCHE_LIVE=…`, injected by `scripts/export_dashboard.py`). So ~1,200 LOC of UI is duplicated
in a directory that is a build output, `desk-site/` is not gitignored, and the CRLF split is evidence
of independent hand-editing. `desk-site/web/vendor/lightweight-charts-…js` accounts for most of the
1.2 MB. Risk: the two trees silently diverge and the published desk stops matching the desk the
operator tests.

### 3.4 Naming collision - "strategy" means two unrelated things

- `market_calendar.strategy_for()` / `gate.strategy` = **session-phase cadence directive** (activity,
  sleeves, `new_entries`, `max_orders`).
- `config.strategies` / `StrategyConfig` / `REGISTRY` = **trading playbook** (PB-xxx).

Both are exposed through `/api/state` and `/api/automation` and both render under a "Strategy" nav
item. Any toggle work must resolve this before it writes code, or the control will be ambiguous.

### 3.5 Root sprawl and unclear ownership

`data/` (64 files) mixes three roles with no separator: operator inputs that must reach git
(`approvals.json`, `halt.json`), transient broker captures (`feed-*/`, `work-*/`, `capture-*/`, all
gitignored), and demo fixtures (`demo_prices.csv`, `prices.csv`). `plans/` (701 KB) mixes plan
artifacts, cloud schedule exports, sentinel payloads and agent prompt `.txt` files. The `.gitignore`
carries a 12-line comment to explain exactly this fragility. `runs/` is **new, untracked and not
gitignored** (`sentinel-preview.html`) - it will show up in every `git status` until it is either
ignored or given a purpose. `dev/` (3 `.mjs` harnesses) is unlabelled dev tooling. `.scratch/`
contains only a stale `__pycache__/old_card.cpython-313.pyc`.

### 3.6 Structural smells (record, do not churn)

The `Sleeve` literal is declared twice - `src/tyche/config.py:10` and `src/tyche/watchlist.py:11` -
with identical members. Two definitions of one vocabulary is how the sleeve blast radius in §7 gets
missed. One shared `models.py` type is the cheap fix; it should move with the next change that touches
sleeves rather than as a standalone commit. Related: `TacticalConfig.etf_symbols` (`config.py:153`,
defaulting to `["US.SMH"]`) is a second, less obvious ETF entry point that decision 1 also reaches.

Four CLI entry modules - `cli.py` (1,260), `lifecycle_cli.py` (522), `tactical_cli.py` (493),
`events_cli.py` (103) - each registered separately in `pyproject` per-file lint ignores; and 11
`deploy_*/verify_*` scripts each hardcoding its own `AGENT_ID` / `ENVIRONMENT_ID` / `VAULT_ID`
constants. `L-011` ("never maintain parallel broker paths") is the project's own lesson applied to
broker code; the same principle argues for a single `deploy` surface, but consolidating 11 one-shot
scripts mid-competition is a rewrite with no functional payoff. Recommend a documented pattern plus
one shared ids module, not a merger.

### 3.7 Open lessons that are live correctness bugs

Not bookkeeping items - both directly affect the playbook/strategy work requested here:

- **L-029** - `PB-004` names both a planned rotation sleeve and the live scalp. Attribution across
  docs, journal and strategy ledger is currently unreliable.
- **L-030** - PB-001's playbook and its `rules.refrozen` row say `569eb2c341e0`; the kernel computes
  `4105d7a680a3`. The freeze hash no longer proves the rules it froze, and no test asserts it does.
  Any playbook-format change made without closing this leaves the pre-registration contract broken.

**Status after P0 items 2-3 landed (2026-11-20):** L-029 applied (PB-004 stays the live scalp, the
planned sleeve became PB-006); L-030 partially applied - the playbook now declares the real hash and
`test_docs_consistency.py` asserts it, but no `rules.refrozen` producer exists (L-035).

### 3.8 The per-strategy freeze contract only covers one of three live lanes

Found while starting P0 #4. `config/strategies/` contains `pb-001.yaml` and nothing else, but every
running lane stamps a playbook id onto its intents:

| Lane | Ids stamped in code | `config/strategies/<id>.yaml` |
|---|---|---|
| Ballast rotation (`pipeline.py`) | `PB-001` | exists |
| Tactical (`tactical.py:243,345`) | `PB-002` stock / `PB-003` option | missing |
| Scalp (`scalp.py:163,215`) | `PB-004` | missing |

`rules_hash()` reads that path unconditionally, so for the other lanes it raises
`FileNotFoundError` rather than returning a hash. Verified: PB-001 → `4105d7a680a3`; PB-002/003/004 →
`FileNotFoundError`. Two consequences, in ascending order of seriousness:

- **The runtime guard is inert but fail-safe.** `lifecycle.decide()` calls `rules_hash()` at
  `lifecycle.py:477`; the `except (ValueError, OSError, KeyError)` at `:621` turns it into
  `action="blocked"`, "invalid lifecycle inputs or unavailable strategy; operator review required".
  So a PB-004 plan can never have its frozen rules verified - and can never be approved to run.
- **The operator approval path raises.** `lifecycle_cli.py:166` calls the same function outside any
  handler, so approving a tactical or scalp lifecycle plan surfaces a traceback instead of the
  intended `ValueError`.

This is why P0 #4 is not cosmetic. Toggling a strategy off from the dashboard, and binding an
approval to the rules that were approved, both need a config object per lane that actually exists.
The fix is a design choice, not a mechanical one: either the lane configs move under
`config/strategies/` (which means `load_config`'s `StrategyConfig` validation and the
file-stem-must-equal-id check have to accept three different parameter shapes), or `rules_hash()`
resolves each id to the file that genuinely defines it (`config/tactical.yaml`,
`config/scalp.yaml`). The second keeps PB-001's bytes - and therefore `4105d7a680a3` - untouched,
which matters because that hash was only just reconciled. It also means `PB-002` and `PB-003` share
one hash source, which reflects today's reality: they are one parameter file. Recorded as L-036.

**Resolved 2026-11-20 (option 2, as recommended above).** `PLAYBOOK_LANES` maps each id to its rules
file and enabling switch; `rules_hash()` and `AppConfig.strategy_enabled()` resolve through it, and
`lifecycle.decide()` asks the latter instead of `strategy_by_id()`, which only ever knew rotation
configs. All four ids now hash: PB-001 `819ad06e35f0`, PB-002/PB-003 `b6bc571033ac` (shared),
PB-004 `72077d5d4808` - the scalp and tactical lanes' first ever freeze hash.

One prediction in this section was wrong and is worth keeping visible: the second option was credited
with leaving PB-001's bytes untouched. It did not, because doing it properly also meant deleting the
`playbook:` pointer from the hashed file (L-037). PB-001 re-froze anyway, to `819ad06e35f0` with every
trading parameter byte-identical. The lesson is general: when a guard's input set is wrong, fixing the
set re-baselines the value, so budget for one honest re-registration instead of assuming you can avoid
it. What the extra hash bought is that no documentation move can cause one again.

Still open after this fix: no `rules.refrozen` producer exists (L-035), so the freeze lineage above is
git archaeology rather than journal provenance.

---

## 4. Stocks-and-options-only scope

This is the one requirement that conflicts with working, scoring functionality, so it needs an
explicit decision rather than a silent edit.

In scope already: `config/scalp.yaml` (NVDA, AMD, AVGO, MU, SMH) and `config/tactical.yaml` (MSFT) -
single names, plus an options-capable planner whose lane is switched off
(`tactical.yaml:3 options_enabled: false`). `watchlist.py` supports long calls / long puts and
rejects shorts and non-standard contracts at the schema level.

Out of scope under a literal reading: `config/universe.yaml` - PB-001's universe is **11 broad ETFs**
(SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ, HYG). PB-001 is the documented v0.1 reference
strategy, the account's ballast, and the only registry-registered strategy. GLD and DBC are
commodity-fund exposure, and TLT/IEF/HYG are bond/credit-fund exposure - these are the parts furthest
from "stocks and options", and the sleeve model (`real_asset`, `credit`, `defensive`) exists to serve
them.

There is also one non-trading artifact whose description strays: `scripts/deploy_two_fire_automation.py`
`DESCRIPTION` says "ETF ballast plus catalyst stocks and standard long options". No crypto or
futures were found in active configs or in the UI - the drift is ETF-vs-stock, and it is concentrated
in PB-001.

Options are second-class rather than out of scope: the planner, schema and risk paths exist
(`tactical.py`, `watchlist.py`, ADR 0012), but the lane is disabled and ADR 0013's protection monitor -
the stated hard prerequisite - is undeployed. Per the recorded backlog, the intraday protection
monitor is what unlocks the options lane; it should be reflected as *experimental*, not as a feature.

**Resolved (operator, 2026-11-20): narrow PB-001 to equity ETFs plus stocks.** The non-equity legs and
their sleeves come out of the active book (§7.1), the `etf_symbols` field in `TacticalConfig` is
reviewed in the same pass, and `deploy_two_fire_automation.py`'s `DESCRIPTION` line drops "ETF ballast"
for wording that matches the surviving book. Removing asset classes from the *UI* is the easy half;
the config/kernel/test blast radius is the part that needs the increment budget.

---

## 5. Proposed target structure

Moves only what is genuinely misplaced. `src/`, `tests/`, `config/`, `docs/adr/`, `docs/lessons/` and
`docs/validation/` do not move.

```
tyche/
├── README.md                  # entry point; status banner generated from the PRD, not hand-dated
├── DESIGN.md                  # v0.1 baseline, clearly marked superseded where the PRD differs
├── documentation/             # NEW - project documentation and the versioned PRD
│   ├── PRD.md                 # current state, versioned; single source of truth for "what exists"
│   ├── changelog/             # PRD v1.0, v1.1 … previous versions kept verbatim
│   └── architecture.md        # the live diagram + narrative (PRD links here)
├── playbook/                  # NEW - agent-loadable strategy library (built 2026-11-20)
│   ├── README.md              # contract, lifecycle, classification vocabulary
│   ├── INDEX.yaml             # machine-readable roster: id, file, config, status
│   ├── PB-001-*.md            # front matter = classification; body = existing template
│   ├── PB-004-*.md            # the live scalp lane, previously documented only in config
│   └── _TEMPLATE.md           # migrated from docs/playbooks/, which is now a pointer
├── archive/                   # NEW - superseded work with a MANIFEST.md entry each
│   ├── MANIFEST.md            # why each artifact died, what replaced it, how to revive it
│   ├── bridge-site/           # dead per L-003, documented as an experiment
│   └── cloud_bridge.py        # the bridge's wiring, kept as the only Sites-webhook example
├── config/
│   ├── strategies/            # PB-001 today; scalp + tactical normalisation is blocked on L-036
│   └── …
├── src/tyche/                 # unchanged; strategies/ registry widened
├── dashboard/                 # the one authored UI tree (source of truth)
├── build/desk-site/           # generated; gitignored
├── scripts/                   # ops scripts; deploy ids consolidated into one module
├── data/                      # split: inputs/ (tracked) vs cache/ (ignored) vs fixtures/
├── tests/  research/  docs/   # docs/ keeps adr, lessons, runbooks, reviews, validation,
│                              # performance, competition, agent-rules.md - the living spine
```

Two corrections to this plan, made while building it. **There is one archive, not two:** the tree above
previously listed `archive/` at the root *and* `archive` under `docs/`, which would have left two
superseded-work dumps to reconcile. `docs/archive/` moved into `/archive`, so `docs/` is now only the
living spine. And `.scratch/` needed no archiving - it holds nothing but `__pycache__`, already ignored.
`test_no_archived_code_is_imported` keeps `/archive` unreachable from live code, so consolidation
cannot quietly reverse itself.

Consolidations, in the order that keeps each step independently verifiable:

1. **Playbooks → `playbook/` with front matter; keep `docs/playbooks/` as a pointer.** The
   classification vocabulary the brief specifies (holding period × strategy type × execution style ×
   instrument) goes into YAML front matter plus `INDEX.yaml`, so the dashboard, the registry and the
   Scout prompt all read one list instead of three. The existing `_TEMPLATE.md` sections
   (thesis/edge/invalidation/sizing/exit/validation status) are kept unchanged - they are good and
   PB-001 proves the format.
2. **Strategy config normalisation.** Give `config/scalp.yaml` and `config/tactical.yaml` the same
   `id` / `enabled` / `playbook` header PB-001 has, so `enabled_strategies()` is the single answer to
   "what is on". No behaviour change; the modules keep reading their own parameters.
3. **Toggle persistence = a tracked state file, not a YAML rewrite.** The cloud reads the repo through
   its mount, and `_git_push_paths()` (`server.py:1839`) already proves the pattern for
   `approvals.json`. A `config/strategies/state.yaml` written by the desk and pushed through the same
   path-bound helper makes the toggle visible to the next Scout run and keeps one auditable writer -
   and it inherits L-025's persistence lesson for free.
4. **One scheduler doc.** Rewrite the `agent-engineering.md` §Schedules section against the live card,
   and move the two superseded generations (hourly `plans/*.json`, six `plans/sentinel/sched_*.json`)
   into `archive/` with manifest entries. This also fixes the stale `docs/README.md:25` index line.
5. **Stop tracking the generated site.** `desk-site/` becomes `build/desk-site/` and gitignored;
   `export_dashboard.py` keeps writing the same files plus its secret guard. Vendored charts move to
   the build so the authored tree holds one copy.
6. **Close L-029 and L-030 before touching playbook formatting**, then add the assertion L-030 asks
   for (playbook hash == `rules_hash()`) to `tests/test_docs_consistency.py` so it cannot recur.
   Reclassify the planned-but-never-built PB-002/PB-003/PB-005 rows as `planned` in the PRD rather than
   leaving them in the playbook README, and resolve the PB-004 id collision with a decision the
   operator makes, not one the code infers.

Not recommended: splitting the four `*_cli.py` modules, merging the 11 deploy scripts, or restructuring
`src/`. All three are cosmetic against a green 432-test suite, and L-001 plus L-020 are this project's
own warnings against spending the window on machinery.

---

## 6. Prioritized implementation plan

### P0 - correctness and safety of the controls (do first)

| # | Work | Reuse | Breaking risk |
|---|---|---|---|
| 0 | Make CI green again: sort the one import block in `cli.py`, land it alone, confirm the `ci` run passes | existing `ruff`/`pytest` CI job | none - lint only, no behaviour change |
| 1 | Repoint the two dangling refs at the archived draft (labelled superseded) and add `docs/agent-rules.md`: hard rules + lessons-review-before-significant-work. **Do not** restore `.qoder/cloud-agent.md` - it is an archived stale draft (§3.1) | live cloud system prompts for the rule text; `docs/lessons/` as the required reading list | none in repo; binding it to the agents needs a prompt pin → P2 #12 |
| 2 | Close L-030: reconcile PB-001 rules hash, journal `rules.refrozen`, add playbook-hash assertion test | `pipeline.rules_hash()`, `test_docs_consistency.py` | low - a red test until the re-freeze is recorded |
| 3 | Close L-029: settle the PB-004 id | playbook README table, `strategy_ledger` keys | **medium** - changes attribution keys in the ledger and journal; needs an operator decision |
| 4 | Normalise scalp/tactical into the strategy-config contract (§3.8: without a config object per lane, `rules_hash()` cannot run, so 2 of 3 lanes have an inert freeze guard and approval raises) | `config.py:StrategyConfig`, `enabled_strategies()` | medium - approval identity changes; hold until the operator picks the hash-source shape |

Dependencies: 0 gates everything after it - there is no point building on a validation signal the
pipeline is not actually running. 4 depends on nothing; 3 should precede 5 (classification is filed
per id); 2 gates any playbook format change.

**Status 2026-11-20.** 0, 1, 3 and 4 are landed. 2 is landed except for its journal half: the playbook
hash is reconciled and asserted in CI, but no `rules.refrozen` producer exists, so freeze provenance
remains open as L-035. Item 4's own prediction that the hash source could be fixed without moving
PB-001's hash did not hold - see §3.8.

### P1 - strategy and playbook foundation

| # | Work | Reuse | Breaking risk |
|---|---|---|---|
| 5 | `playbook/` + `INDEX.yaml` + classification front matter; migrate template | `docs/playbooks/_TEMPLATE.md`, `ADR 0014` | none if `docs/playbooks/` keeps a pointer |
| 6 | Write the missing PB-004 scalp playbook; mark PB-002/003/005 planned in the PRD | ledger + scalp.yaml rules | none |
| 7 | `archive/` + `MANIFEST.md`; move `bridge-site/`, superseded schedules, `.scratch/` | existing `docs/archive/` convention | low - verify no live import (`dev/serve-live.mjs` imports `desk-site/functions/handler.ts`) |
| 8 | `documentation/PRD.md` v1.0 + architecture diagram, statuses honest (implemented / partial / experimental / planned / deprecated) | `DESIGN.md`, `docs/README.md`, `docs/reviews/` | none |

**Status (2026-11-20):** 5, 6 and 7 are built - `/playbook` with front matter, `INDEX.yaml` and the
missing PB-004 playbook; `/archive` with a manifest, consolidating `docs/archive/`, `bridge-site/` and
`cloud_bridge.py`. 8 is the remaining Phase 3 item.

### P2 - dashboard controls (the user-visible half)

| # | Work | Reuse | Breaking risk |
|---|---|---|---|
| 9 | Strategy toggles: read `INDEX.yaml` + state file; `GET /api/strategies`, `POST /api/strategies/toggle`; persist + push | `_git_push_paths()`, Controls view, `test_desk_controls.py` | low - additive route; **must** bump desk version per the standing rule |
| 10 | **Run Scout**: `POST /api/scout/run` → one Cloud Automation / Forward run of `tyche-researcher`, guarded against concurrent runs; status + run history on the desk | `forward.req()`, `deploy_two_fire_automation.py` card, `slim_session()`, `load_cloud_runs()` | **medium** - this is a write to a cloud system; needs a dry-run mode and explicit confirmation |
| 11 | Scheduled daily checks: enable/disable, time + timezone, next run, run history; manual run independent of the schedule | `slim_schedule().trigger_policy`, `market_calendar` for trading-day gating | **medium** - mutates a live schedule |
| 12 | Scout consumes enabled strategies: the run message carries the enabled set and loads only those playbooks | existing delegation contract (`agent-engineering.md:19-26`) | low in repo, **high in prompt** - a prompt change is a new pin and applies to new sessions only (L-021) |
| 13 | Version bump + changelog entry, per the standing desk rule | existing `CHANGELOG` array + version modal | none |

Ordering constraint: 9 → 12 → 10 → 11. Toggles are inert until Scout honours them, so landing 12
before advertising 9 would show a control that does nothing. 10 and 11 are the two steps that touch
live cloud state and should each be verified in dry-run first, then applied.

### P3 - follow-on, documented not done in this pass

Options lane enablement behind ADR 0013's protection monitor (experimental today); the unattended
intraday loop that moves PB-004 ticks out of the LLM session; ladder entries/exits from the recorded
playbook backlog; deploy-script id consolidation; `data/` split.

---

## 7. Decisions - resolved by the operator, 2026-11-20

These are now constraints on the plan, not open questions.

1. **Stocks-and-options scope → narrow to equity ETFs + stocks.** PB-001 keeps trading, but
   `config/universe.yaml` drops TLT, IEF, GLD, DBC and HYG, and the `defensive` / `real_asset` /
   `credit` sleeves collapse to equity-only. Consequences to handle deliberately:
   - the 4-check regime gate loses its HYG/IEF credit-trend leg and becomes SPY>200SMA, golden cross,
     vol calm - a **rules change, not a parameter change**, so it needs an honest re-freeze and a new
     validation-status line in the playbook (L-030 discipline);
   - `PB-001-etf-rotation-ballast.md` is written around cross-asset sleeves; its thesis, universe and
     sizing sections need rewriting rather than trimming;
   - `sleeve_caps` per regime, the `Sleeve` literal in `config.py:10` **and again** in
     `watchlist.py:11`, the sleeve lists in `market_calendar.py:279-294` (the session-phase
     directives name `defensive` / `real_asset` / `credit` too), `SLEEVE_MAP` →
     `compute_expectancy`, the dashboard allocation donut and `docs/risk-card.md` all name the
     removed sleeves - so this is a five-file semantic change plus tests, not a config trim;
   - `tests/test_config.py` and `test_strategy.py`, plus the LEAN PB-001 study under
     `research/lean/PB001/` (backtested on the 11-ETF set), go stale against the new universe.
   This is a **strategy re-registration**, and it should land after L-030 is closed so the hash
   lineage stays auditable.
2. **Controls → local `dashboard/` server, toggles persisted to a tracked state file and pushed via
   the existing `_git_push_paths()`**, so the cloud mount - and therefore Scout - sees the enabled set.
   The hosted `desk-site/` stays a read-only baked view; its Sites Function is not extended.
3. **PB-004 id → the live intraday scalp keeps PB-004**; the never-built "sector rotation heat"
   planned setup is renumbered to PB-006 in the playbook index. Journal, ledger and report attribution
   stay valid with no back-mapping.
4. **Run Scout → trigger the existing three-fire Cloud Automation card** from
   `scripts/deploy_two_fire_automation.py`, so manual and scheduled runs share one prompt, one
   mount/secrets set, and one run-history source already read by `slim_session()` /
   `load_cloud_runs()`.
5. **`docs/agent-rules.md` is the new home for hard rules** (P0 #1); `.qoder/cloud-agent.md` is not
   resurrected.

One caveat carried forward: decision 1 is the only item in this plan that changes what the account
actually trades. Everything else is structure, documentation and control surface. It gets its own
increment, its own re-freeze record, and its own PRD version.
