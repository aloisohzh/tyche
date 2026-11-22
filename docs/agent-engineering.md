# Agent engineering

Topology aligned to the handbook §8.2/§9 (researcher / executor / risk auditor + coordinator + advisor).
The platform is the source of truth for what runs; this file says where to look and how to change it.

## What lives where (one plane)

The desk is authored on the **Managed** API (`api.qoder.com/api/v1/cloud`) and nowhere else. Forward still
holds objects, but they are residue: no control or execution path reads or writes them, and the only readers
left are two display-only panels that show a desk which no longer runs there ([PRD §7 item 14](../documentation/PRD.md)).

| Object | Where it lives | How it changes |
|---|---|---|
| Four agents: coordinator, researcher, auditor, executor | Managed `agents` | `scripts/deploy_managed_agents.py apply-system` / `attach` / `roster`, one field group per write |
| Three skills | Managed `skills`, each with immutable versions | `publish-skill` mints a version, `attach` pins it - deliberately two steps |
| One permanent desk card (two monthly cards until the cut-over) | Managed `deployments` | `scripts/deploy_two_fire_automation.py` owns the brief, `pin-card` owns the agent version |
| Environment (repo mount, Drive bucket, `setup_script`) | Managed `environments` | read-only in practice: a `config` write replaces the object wholesale and the bucket credential is write-only |
| Vault, memory store, sessions / threads / events | Managed | not authored from this repo |
| 4 templates, 8 archived schedules, 1 identity | Forward only, and they fire nothing | **never authored, by design.** A template write recompiles the Managed agent and can materialise a `managed_tool_config` grant the running pin never had (L-046), so the writers are in [../archive/MANIFEST.md](../archive/MANIFEST.md) and `test_no_live_script_authors_a_forward_template` keeps them out of `scripts/` |

The Forward identity `idn_1d7b9ab60a1bcc934d4a1d8f` stays even though it is Forward: the environment's OSS
bucket prefix embeds it, so retiring it could orphan the journal lineage under `/data/drive/tyche-raw` that
the prompts treat as authoritative.

## Roles and scoping (least privilege)

| Role | Tools / MCP | Vault | Owns (files) | May not |
|---|---|---|---|---|
| Coordinator (Desk Head) | orchestration, read artifacts | none | `reports/` narrative, delegation | size, submit, hold trade tools |
| Researcher | quote/news MCP (read-only) incl. `quote_order_book`, so a thesis can cite a two-sided executable quote (L-017) | none | `reports/<date>-research.md` | submit, write journal |
| Risk auditor | read-only (plan, journal, quotes) | none | `reports/<date>-audit.md`, drawdown report | agree under pressure; submit |
| Executor | **sim trade tools + moomoo MCP** | moomoo vault | `plans/`, `journal/` (single writer) | act without auditor approval + human arm |
| Advisor | model-only consult | none | advice in coordinator context | tools, files |

Handbook rule in the coordinator prompt: *"never let the executor act on the researcher's output
without the auditor's approval."* Auditor runs in a separate thread so it cannot be talked into agreeing.

## Skills (procedures, loaded on demand)

Procedure text lives in `skills/<role>/<name>/SKILL.md` in this repo, version-controlled and guarded by
[tests/test_skills.py](../tests/test_skills.py); the prompts keep permissions and hard rules only. The
cloud copies, pinned on the Managed **agent** that loads them (re-pinned 2026-11-21 after two of them
were found contradicting the code they describe, L-048):

| Skill | Cloud id | Pinned version | Pinned on | Loaded by |
|---|---|---|---|---|
| `sentinel-digest` | `skill_00w5eiyk0bl6o8wz2yd8` | `1795250714818439` | coordinator | the 12:05 watch fire |
| `exact-order-audit` | `skill_00w5ej0prnz0h36xnfvm` | `1795256506833674` | auditor | before an exact-order verdict |
| `paper-submit-protocol` | `skill_00w5ej2wczbb5vfl1bq9` | `1795256578842546` | executor | before any broker write |

Mechanics that are not obvious from either API's docs:

- **Content and attachment are two different surfaces.** The body only moves through
  `POST /api/v1/cloud/skills` (multipart zip, one top-level directory named exactly like the
  `name:` field); no MCP tool writes skill content. Attachment is an ordinary Managed agent write -
  `skills: [{type: custom, skill_id, version, enabled}]` - which is why the driver keeps them as two
  subcommands instead of one "deploy the skill" action.
- A skill is read from `/data/.agent/skills/<name>/SKILL.md` with the `Read` tool when the agent decides
  it applies, so every role bound to a skill must keep `Read`, and a skill can never carry a rule that
  must hold on a turn where it does not load. Those rules stay verbatim in the prompt.
- `latest_version` is an opaque epoch-microsecond string, not a sequence number, and it is `null` once
  every version is deleted. Pin it verbatim; `PUT /skills/{id}` is deprecated, a change means creating a
  new version and re-pinning.
- The agent's own skill list is what runs, so verify the agent after every write (L-021/L-047), not the
  repo file. Deleting a skill deletes all of its versions.

## Delegation contract (coordinator prompt must state)

- When to delegate, to whom, and the **expected artifact + schema** per child.
- What the coordinator keeps: journal write, submit decision, halt, final narrative.
- **File ownership** (shared filesystem): each child writes only its own paths.
- Every delegation message is **self-contained**: date/session clock, plan path + hash, config hash,
  caps snapshot, the playbook ids live for this run (`tyche strategies --json`), output path. Children
  do not inherit context.
- Selecting agents does not force delegation — the prompt does.

## Snapshot file contract (executor → deterministic core)

The core cannot call MCP directly. The executor fetches read JSON and writes three
files into the run directory; `tyche.broker.mcp_json.snapshot_from_dir` consumes them:

| File | MCP tool | Shape used |
|---|---|---|
| `accounts.json` | `sim_trade_account_list` | `data.accounts[]` → `account_id`, `account_type`, `market_id` |
| `cash.json` | `sim_trade_cash_info` | `data.balance` = cash; `data.total_asset` = NAV |
| `positions.json` | `sim_trade_position_list` | `data.positions[]` → bare `symbol` (prefix `US.`), `qty`, `cost_price`, `cur_price` |

`build_snapshot` sets `source="sim_list"`, `env="paper"`, and carries `account_type`/`market_id`
from the matching account entry so the kernel can verify them. A missing account entry yields
`None` types and fails closed. Quotes/klines reuse the payload-agnostic `extract_last_price` /
`extract_daily_bars` walkers.

Execution flow: plan → auditor approval → human arm → executor submits each approved order
**verbatim** via `sim_trade_submit_order` (limit/market only) → executor writes order/receipt JSON →
core reconciles fills and fees (`tyche.fees.reconcile_cash`). Submit is non-idempotent: on timeout,
query today's orders before any further write; never retry blindly.

**Act/wait gate:** every planned order carries `pipeline.action` (`act`/`wait`). The executor must
skip `wait` orders on both paths — `tyche execute` withholds them automatically; on the MCP path
the executor journals `tyche record-order gate.wait` and does not submit. The gate only ever
withholds new non-defensive entries at low conviction; sells and defensive entries always act.

## Version pins

- Pin **numeric** agent + skill versions for the whole window; no `latest`. **Live exception, stated
  because it changes what goes live when:** the coordinator's roster currently pins its three children at
  `version: "latest"`, so a write to auditor / researcher / executor is live at the next fire with no
  re-pin, while a write to the coordinator is inert until both cards move. Making the roster numeric
  flips that to "next deliberate re-pin" and is a separate reviewed change, not something to smuggle into
  a prompt trim.
- Verify the **agent object** after every write, with the same reducer you used before it. A template
  recompile can materialise a `managed_tool_config` group the running pin never had (L-046), which is the
  whole reason this repo no longer authors templates.
- Omitted version pins at save; updates affect **new sessions only**.
- Export the working config locally with a timestamped comment (retrieved-at, agent id, cloud version,
  change summary) before every change; verify after; keep the exact submission version.
- When a script writes back a nested object it did not author (a roster, a tool matrix), deep-copy the whole
  object and mutate only the named rows - a filtered rebuild deletes rows (L-045).
- A before/after guard only works if **both sides go through the same projection**. Capturing a template
  through one reducer and verifying it through another reported a changed field that had not changed,
  which is worse than no guard: it trains you to wave the alarm past (L-047).
- Skill pins live in `latest_version` form (an epoch-microsecond string) while roster and card pins are
  integers; the two never convert into each other, so record both verbatim.

## Cadence (what is deployed, 2026-11-22)

**One permanent Qoder Managed card**, built by `scripts/deploy_two_fire_automation.py`: cron
`5 8,12,15 * * 1-5` in `America/New_York` - 08:05, 12:05 and 15:05 every Monday to Friday, no end date,
`metadata.window` open-ended (`YYYY-MM-DD..`). The cron carries no holiday list on purpose: the in-run
`tyche calendar --json` gate is the holiday filter, so a holiday fire costs one read-only session that ends
at its first step. This replaces the one-card-per-month design (cron `5 8,12,15 <trading-day list>
<month> *`, days filtered by `is_trading_day` at generation time), whose weakness was that a month nobody
regenerated was a desk that silently stopped. The monthly cards `dep_00vzb9h4ezawwl4thnva` (Nov,
2026-11-19..30) and `dep_00vzd8d5rdfr4w0denqh` (Dec, 2026-12-01..31) stay live until the cut-over, which
is operator-approved and lands between fires: pause both monthly cards, `--apply --start <first day>`
(the create path refuses to add a second *active* desk card without `--allow-overlap`, because two cards
that fire are two writers), `--verify <new id>`, then watch the new card's first 08:05 fire before the old
cards are archived. Agent pin **v34** (v28 -> v31 stale-caps re-pin, v31 -> v32 when the desk took
`sentinel-digest`, v32 -> v33 -> v34 the two prompt trims done through the Managed driver on 2026-11-21).
Each card's prompt, cron, env *keys* and `initial_events` hash were asserted byte-identical through every
move and only the `agent` block was sent.

- **08:05 pre-market** and **15:05 close** are decision fires. **12:05 is watch-and-shout only**: it
  may open, change or close nothing, and messages only on a breach or an exit-less lot
  ([sentinel runbook](runbooks/sentinel-telegram.md)). The name still says "two fire" and the prompt
  says "THREE-FIRE"; the script is the source of truth, not either label.
- Each fire is a new session that starts by running `tyche calendar --json`; exit 1 means skip
  (weekend, holiday, outside 04:00-20:00 ET) and finish read-only. On a 13:00 early close the 15:05
  fire is AFTER_HOURS and may reconcile only, never submit. Halt is checked with
  `tyche halt-status --json`; a halted run submits no buys.
- The hourly and six-fire cadences are **cut** (L-019, L-020), and the eight Forward schedules that used to
  own them were **archived on 21 Nov 2026** - one reviewed write, `POST /forward/schedules/{id}/archive`,
  eight calls, nothing else, through `plans/managed-migration/archive_schedules.py`. That writer reads the
  list first and refuses anything outside exactly those eight ids or not already `paused`, never retries a
  POST, re-reads `archived_at` per call, and between calls re-reads the Managed projection it must not
  disturb (four agent versions and prompt lengths, three `skill@version` pins, each card's pin,
  `initial_events` hash and env *key names*), aborting if any of it moves. The deploy scripts that used to
  drive the cadence are in [../archive/MANIFEST.md](../archive/MANIFEST.md). Objects are archived, not
  deleted, so platform history stays where it happened; what the archive removes is the risk that an object
  nobody can name gets mistaken for the cadence. An archived schedule still reports `status: "paused"` with
  `archived_at` set and drops out of the default list, so the desk prompts' "the paused Forward schedules
  must remain paused" is still literally true after the write - no prompt depended on it either way.
- **The live card is operator-switchable from the desk, not from the hosted page.** Controls reads the card
  that owns today (`scripts/cloud_api.py` `pick_card` selects by `metadata.window`; a bounded window is a
  monthly card, an open one the permanent card, and when both cover the day the card that still fires wins,
  because pausing an already-paused card would look like success), and `POST /api/schedule/control`
  pauses, resumes or fires one run. Every action is journaled and the pause is **re-read** from the platform
  before the desk calls it done (`verified`). Fire times and timezone are shown read-only on purpose: they
  live in the card's cron and again in its prompt, so retuning them means rebuilding the card
  (`scripts/deploy_two_fire_automation.py`) and re-pinning the cadence doc in the same commit. The hosted
  Sites Function publishes `/schedule` from the desk's snapshot and holds no cadence write path.
- **Scout can also be started by hand.** `POST /api/scout/run` opens a researcher session directly
  (`cloud_api.start_scout_run`) rather than through the card, with no executor, auditor or envelope in
  reach. The session has no repository mount, so the desk puts everything it needs in the message: the
  clock, the calendar phase, and the live playbook ids with their frozen rules hashes - and no numeric
  caps, because agent-rules forbids restating them anywhere a prompt could drift (L-033). A run already in
  flight is refused, and the request is journaled as `scout.requested`.
- **Calendar drift runs on the fire that fires.** The clause started life in the paused `tyche-hourly`
  Forward schedule (`archive/deploy_calendar_check.py`), where nothing would ever execute it; since
  2026-11-21 it is part of the authored card brief (`CALENDAR DRIFT` in
  `scripts/deploy_two_fire_automation.py`), so the 08:05 premarket fire WebFetches the NYSE page, runs
  `tyche calendar-check --source data/nyse-calendar.txt --json` once a day, and turns a non-zero exit into
  a Problems line plus a `calendar.check` event. It stays alert-only on purpose: re-pinning the calendar is
  `scripts/refresh_calendar.py` under the operator's hand, never a run step.
- The 1-2 min protection monitor remains a draft prerequisite for the options lane
  ([ADR 0013](adr/0013-protection-monitor.md) + [its draft contract](runbooks/intraday-protection-monitor.md));
  it is not deployed.
- Skip holidays; window-bound; archive after the deadline.

## Persistence (every run)

Raw journal/plans/reports → Drive locker (`/data/drive/tyche-raw`; OSS deferred post-competition). Sanitized summaries → git push with a
least-privilege PAT (server-side only, `.env` gitignored). The sandbox is ephemeral; without this the
evidence is lost.

## Tuning loop

Keep 3–4 fixed evaluation prompts; after any prompt/skill change, re-run and **diff** before promoting.
Log malformed child outputs and missed delegations; revise as a versioned change; pin; new sessions only.
Log decisions **and rejections** as first-class artifacts.

## Export and change control

`templates/prompts/live/*.md` is the as-retrieved record of the four prompts, written by
`scripts/deploy_managed_agents.py export --prompts`; its header names the agent and its version, not a
template. `tests/test_skills.py` re-checks the hard rules against that text, so a trim that quietly drops
a rule fails CI instead of shipping it.

One driver, one field group per write, and every write prints what moved. Full agent objects land in the
gitignored `plans/managed-migration/agents-live.json` as the baseline `verify` compares against.

| Command | Body it sends | What it proves afterwards |
|---|---|---|
| `status` | read | all four agents plus both cards, in the same projection the guards use |
| `export [--prompts]` | read | the baseline and the as-retrieved prompt files |
| `diff <role> --file <path>` | read | the exact line-level difference before anything is written |
| `apply-system <role> --file <path>` | `{version, system}` | only `system_chars`/`system_sha256` moved; roster rows and card pins untouched |
| `publish-skill <name>` | multipart zip | a new immutable version exists; nothing is pinned by it |
| `attach <role> --skill ...` | `{version, skills}` | the pin reads back as `id@version`, which is what a re-pin has to be visible as (L-047) |
| `roster` | `{version, multiagent}` | four rows, the model-only advisor row carried verbatim (L-045) |
| `pin-card <deployment id>` | `{agent: {id, type, version}}` | nine card fields plus the `initial_events` hash and the env *key names* unmoved |
| `verify` | read | no drift on any of the four |

Nothing in the driver sends `tools`, `mcp_servers`, `model`, `metadata`, vaults or
`environment_variables`, so a prompt trim cannot widen a grant by accident - the failure L-046 recorded
came from the template step, and the template step is gone. [tests/test_forward_fence.py](../tests/test_forward_fence.py)
fails if anything under `scripts/` imports `forward` or names `/templates`.

Capability, re-read from the Managed agents on 2026-11-21: researcher v19 and executor v19 both run the
moomoo toolset at `permission_policy: always_deny` with per-tool enables - researcher 25 read-only tools
and 6 built-ins (`Read`/`Write`/`Glob`/`Grep`/`WebSearch`/`WebFetch`), executor 14 of 15 enabled with
`quote_rt_data` explicitly disabled and 6 built-ins. Coordinator v34 (9 built-ins) and auditor v12 (4)
mount no MCP server at all, and the coordinator's `managed_tool_config` is empty, which is what its pin has
always run with (L-046). On the executor pin only `sim_trade_cancel_order` and `sim_trade_modify_order`
carry `always_ask`, while `sim_trade_input_order` carries `always_allow`: `/approve` governs cancels and
modifies, and the paper submit stays gated by the preview-and-confirm protocol rather than by the platform
(see the sentinel runbook).

The `plans/live-*.json` captures in the gitignored scratch tree are **not** the pin or permission
authority: `plans/live-desk.json` still records researcher 13 / auditor 5 / executor 12 and an
`always_allow` researcher, all of which predate the token policy. Read the platform, then re-export.