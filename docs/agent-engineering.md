# Agent engineering

Topology aligned to the handbook §8.2/§9 (researcher / executor / risk auditor + coordinator + advisor).
This file is the source of truth for the cloud configuration; export and pin the actual template here.

## Roles and scoping (least privilege)

| Role | Tools / MCP | Vault | Owns (files) | May not |
|---|---|---|---|---|
| Coordinator (Desk Head) | orchestration, read artifacts | none | `reports/` narrative, delegation | size, submit, hold trade tools |
| Researcher | quote/news MCP (read-only) | none | `reports/<date>-research.md` | submit, write journal |
| Risk auditor | read-only (plan, journal, quotes) | none | `reports/<date>-audit.md`, drawdown report | agree under pressure; submit |
| Executor | **sim trade tools + moomoo MCP** | moomoo vault | `plans/`, `journal/` (single writer) | act without auditor approval + human arm |
| Advisor | model-only consult | none | advice in coordinator context | tools, files |

Handbook rule in the coordinator prompt: *"never let the executor act on the researcher's output
without the auditor's approval."* Auditor runs in a separate thread so it cannot be talked into agreeing.

## Delegation contract (coordinator prompt must state)

- When to delegate, to whom, and the **expected artifact + schema** per child.
- What the coordinator keeps: journal write, submit decision, halt, final narrative.
- **File ownership** (shared filesystem): each child writes only its own paths.
- Every delegation message is **self-contained**: date/session clock, plan path + hash, config hash,
  caps snapshot, output path. Children do not inherit context.
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

- Pin **numeric** child agent + skill versions for the whole window; no `latest`.
- Omitted version pins at save; updates affect **new sessions only**.
- Export the working config locally with a timestamped comment (retrieved-at, agent id, cloud version,
  change summary) before every change; verify after; keep the exact submission version.

## Cadence (what is deployed, 2026-11-20)

One Qoder **Managed card per month**, built by `scripts/deploy_two_fire_automation.py`:
cron `5 8,12,15 <trading-day list> <month> *` in `America/New_York`, trading days filtered at
generation time by `is_trading_day` (L-019). Live cards: `dep_00vzb9h4ezawwl4thnva` (Nov,
2026-11-19..30) and `dep_00vzd8d5rdfr4w0denqh` (Dec, 2026-12-01..31), both `active`, agent pin v28.

- **08:05 pre-market** and **15:05 close** are decision fires. **12:05 is watch-and-shout only**: it
  may open, change or close nothing, and messages only on a breach or an exit-less lot
  ([sentinel runbook](runbooks/sentinel-telegram.md)). The name still says "two fire" and the prompt
  says "THREE-FIRE"; the script is the source of truth, not either label.
- Each fire is a new session that starts by running `tyche calendar --json`; exit 1 means skip
  (weekend, holiday, outside 04:00-20:00 ET) and finish read-only. On a 13:00 early close the 15:05
  fire is AFTER_HOURS and may reconcile only, never submit. Halt is checked with
  `tyche halt-status --json`; a halted run submits no buys.
- The hourly and six-fire cadences are **cut** (L-019, L-020). Their `tyche-hourly` and phase schedules
  remain in the platform as `paused` objects, and the deploy scripts that used to drive them are in
  [../archive/MANIFEST.md](../archive/MANIFEST.md).
- **Gap:** the calendar drift check is alert-only and is carried in a *paused* schedule's
  `initial_events`, so on the card path it does not run. `scripts/deploy_calendar_check.py` builds it;
  wiring it to a live trigger is open work.
- The 1-2 min protection monitor remains a draft prerequisite for the options lane
  ([ADR 0013](adr/0013-protection-monitor.md) + [protection-monitor runbook](runbooks/protection-monitor.md));
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

## Export

`templates/` holds the reference prompts. The live cloud config export (pinned versions, permission
matrix, schedule ids) lands here before submission. No credentials in the export.

Change control: `scripts/deploy_token_policy.py` (default read-only diff, `--apply` to mutate) owns the
MCP allowlists, and `scripts/verify_envelope_deploy.py` re-reads the executor's envelope state without
printing secrets. Verified against the live platform via `list_agents` on 2026-11-20: both
MCP-connected agents run `permission_policy: always_deny` at the toolset level with per-tool enables -
researcher 24 tools, executor 14 enabled and `quote_rt_data` explicitly disabled. Desk (v28) and
auditor (v6) mount no MCP server at all.

The `plans/live-*.json` captures in the gitignored scratch tree are **not** the pin or permission
authority: `plans/live-desk.json` still records researcher 13 / auditor 5 / executor 12 and an
`always_allow` researcher, all of which predate the token policy. Read the platform, then re-export.