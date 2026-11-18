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

## Version pins

- Pin **numeric** child agent + skill versions for the whole window; no `latest`.
- Omitted version pins at save; updates affect **new sessions only**.
- Export the working config locally with a timestamped comment (retrieved-at, agent id, cloud version,
  change summary) before every change; verify after; keep the exact submission version.

## Schedules (EST November; regular 14:30–21:00 UTC)

- Pre-market plan: ~13:45 UTC (08:45 ET). New session each run; self-contained instructions.
- Intraday monitor: every 1–2 min **during the regular session only**, with an end time; short tasks
  (concurrency 1); dedupe by stable order/trade id.
- EOD reconcile + report + **persist**: after 21:00 UTC; on the 27 Nov half day, after 18:00 UTC.
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