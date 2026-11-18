# Cloud config export — 2026-11-18 (retrieved-at 02:49 UTC)

Live Forward configuration for the tyche desk, pinned for the challenge window.
Change summary: Collaboration conversion (operator-approved 2026-11-18): members
are Forward templates wired through the desk's Collaboration roster; the old
`Moomoo Paper Trader` shell was rewritten in place as the researcher member.
Repo mount completed by operator via console (PAT configured, mount
`/data/workspace/tyche`).

Amendment 2026-11-18 12:39 UTC (rehearsal-timeout remediation, operator-approved):
researcher system prompt → fast data path (one `num=370` kline call per symbol +
`scripts/mcp_prices.py`), compiled agent `agent_00vs9v3dg0rnkr4740x3` v4→**v5**, desk
roster re-pinned to v5 (verified via get_agent). `execution.timeout_ms` 1800000→**3600000**
on tyche-premarket / tyche-eod / tyche-eod-halfday (env/execution edits do not bump member
pins). Auditor v2 and executor v4 unchanged.

## Template (coordinator)

- id: `tmpl_004fa008901a6c256bd0ed3f` — name `tyche-desk`, status active
- model: `qmodel_latest` (Qwen4-Max), effort `high`, context_window 400000
- environment: `env_00vtsfiylf7czjlt4b82` (`tyche`)
- vault: `vault_00vs6gjsbcxkw661ka7o` (`moomoo-mcp`) enabled
- managed tools: drive, schedule; schedule_creation_enabled true
- tools: agent_toolset_20260401 (Bash, Read, Write, Edit, Glob, Grep, WebSearch,
  WebFetch, DeliverArtifacts); no browser, no media tools
- system prompt: Desk Head delegation contract (see template; mirrors
  docs/agent-engineering.md + .qoder/cloud-agent.md hard rules)

## Members (Forward templates) and roster (multiagent.agents, pinned)

The Collaboration roster stores console-compatible entries
(`{"type":"agent","template_id":...,"version":N}`) that resolve to each member
template's compiled agent (`metadata.created_by: forward`). Member templates
share the tyche environment;
researcher and executor bind the moomoo vault, the auditor binds none (least
privilege; unbound 2026-11-18 04:10 UTC). None has schedule creation or managed
drive/schedule tools; each prompt refuses standalone operation outside the desk.

| Role | Member template | Compiled agent (roster entry) | Pin | MCP | Trade tools |
|---|---|---|---|---|---|
| Researcher (scout) | `tmpl_875834770244a9e35c7f6499` (rewritten from Moomoo Paper Trader) | `agent_00vs9v3dg0rnkr4740x3` | 5 | moomoo (read; all order-write tools disabled) | none |
| Risk auditor | `tmpl_ae317cc0626a4fcc8fa8fad6` | `agent_00vtx8g7k1534t7w9eve` | 2 | none | none |
| Executor | `tmpl_bc25a5c313827d53894fd7ff` | `agent_00vtx8mfbxerk6vxmny5` | 4 | moomoo, default **always_deny**; sim reads + quotes allowed; `sim_trade_input_order` / `cancel` / `modify` = **always_ask** (per-order operator confirmation) | paper only |
| Advisor | — (model consult) | — | — | none | none |

Advisor model: `ultimate`. All member models: `qmodel_latest`, effort high.
Live (`trading_order_*`) and crypto order tools are denied/disabled everywhere.

Rollback: the pre-conversion standalone agents (`agent_00vtsgocscef4hvsj7y0`,
`agent_00vtshuefbgn4nnlwaxz`, `agent_00vtsma8hg5c01t932hw`), the old debug
session (`sess_00vscf514vaptrjtcu1t`) and the orphaned old environment
(`env_00vqj27b2b2m8zx4bngy`) were ARCHIVED 2026-11-18 ~04:30 UTC with operator
approval. The pinned Collaboration roster is the only live desk.

## Environment

- id: `env_00vtsfiylf7czjlt4b82`, type cloud
- pip preinstalled: pydantic, PyYAML, pandas, numpy, typer, rich, pytest, ruff
- setup_script: `python3 --version && pip --version`
- session bootstrap: `pip install -e <repo> --no-deps` (repo mounted or cloned)
- **networking: limited (allow_mcp_servers=false, allow_package_managers=false)** —
  platform default; not writable through the QCA MCP schema. **Smoke-verified
  2026-11-18: hosted Moomoo MCP reachable from a member thread (quote ret_code 0);
  `pip install -e . --no-deps` works (local, no index).** PyPI installs of new
  deps would still be blocked; env preinstalls cover current needs.

## Open items (operator)

0. Repo visibility: PUBLIC for the competition submission window (operator
   decision 2026-11-18); switch to private after submission. Sanitize gate is
   the protection: ids/tokens redacted before git, raw payloads Drive-only
   (identity-private).

1. DONE (operator, console): GitHub repo mounted with PAT at
   `/data/workspace/tyche`; push-back of sanitized artifacts now possible.
2. DONE (2026-11-18 ~04:39 UTC, via API at operator request):
   `TYCHE_ALLOWED_ACCOUNT_IDS` set on tyche-desk AND tyche-executor = challenge
   account only (titled "Moomoo x Qoder AI Paper Trading Agent Challenge", US,
   account_type 2, market_id 100, id ends ...598; identified via
   sim_trade_account_list). The personal "US Margin Account [Paper Trading]"
   (type 1, id ends ...748) is for local drills only via gitignored local .env —
   NOT in the cloud allowlist. Full ids live server-side in template env vars
   only; never committed or pasted in chat/reports. Env-var edits do not bump
   the compiled agent version, so the executor pin (v2) stayed valid.
3. DONE (operator decision 2026-11-18): raw sink = Qoder Drive locker
   `/data/drive/tyche-raw` (identity-private, persistent across sessions, zero
   provisioning); OSS bucket mount deferred post-competition. Desk prompt,
   runbook and ADR 0009 amended; `tyche persist --bucket` unchanged (any mounted
   path). EOD additionally DeliverArtifacts the raw run bundle + EOD report to
   console Files. Drive is NOT the console Files tab: Files shows uploaded
   inputs and delivered artifacts; Drive is session-mounted storage.
4. DONE (smoke 1 + smoke 2, 2026-11-18, see below): bootstrap, journal-verify,
   Collaboration delegation, Moomoo market-data AND account-scope OAuth
   (executor snapshot queries ret_code 0 first attempt, no authorization
   prompts). Kill-switch drill DONE 2026-11-18 09:45 UTC on the PERSONAL paper
   account (…748) via the MCP-only variant — PASS, see
   docs/validation/2026-11-18-kill-switch-drill.md.
5. DONE (2026-11-18 04:46–04:47 UTC): three cron schedules created, all active,
   new_session per run, max_concurrent_runs 1, stop 2026-11-28T00:00Z:
   - `sched_52f7a8a04e4bf656e25fac47` tyche-premarket — `45 13 18-20,23-25,27 11 *`
     UTC (13:45 on session days; planning phase, no orders without per-order
     operator confirmation).
   - `sched_f522c892f2a72e77dd7c590f` tyche-eod — `15 22 18-20,23-25 11 *` UTC
     (22:15 regular days; reconcile, fees, persist, DeliverArtifacts).
   - `sched_7d7dcb7101f048b8b4df159f` tyche-eod-halfday — `15 18 27 11 *` UTC
     (27 Nov half-day close 18:00). 26 Nov (Thanksgiving) excluded by the
     day-of-month lists.

## Smoke results — 2026-11-18 03:36–03:40 UTC (PASS)

Session `sess_00vtxkszw6ccgsqzxzwo` (tyche-desk v9, operator identity), 14.6
credits, ~90 s of work. Read-only: no plan/audit/execution/orders/persistence.

- Bootstrap: repo found at `/data/workspace/tyche` (PAT mount, no clone);
  `pip install -e . --no-deps` OK; `tyche journal-verify` → "Journal OK: 0
  events, chain intact."
- Delegation: coordinator `create_agent` → researcher thread
  `sthr_00vtxw7d54ydcw11yw55`; self-contained message honored; member replied
  via `agent.thread_message_received`; both threads idled with `end_turn`.
- Moomoo MCP: `quote_stock_quote` US.SPY ret_code 0, no OAuth/network wall
  (market-data scope of the vault token is valid). Last 732.44, data_time
  2026-11-17 21:00 UTC close + extended-session sections.
- Artifacts (sandbox-local only, NOT pushed): `reports/2026-11-18-smoke.md`,
  `reports/2026-11-18-smoke-research.md`.
- Caveats: (a) researcher has no Bash, so no wall-clock `date` — coordinator
  must put HH:MM UTC in delegation messages (contract already says session
  clock; enforce time, not just date); (b) `quote_stock_quote` returns no
  bid/ask — use `quote_order_book` for spreads; (c) executor account-scope
  tools untested (blocked on TYCHE_ALLOWED_ACCOUNT_IDS).

Follow-up 04:09-04:12 UTC: desk delegation contract now mandates HH:MM UTC
(coordinator runs `date -u +%H:%M` and pastes it; members have no clock tool);
auditor vault unbound; roster pins re-asserted 3/2/2 + advisor and confirmed on
the template.

## Smoke results 2 — 2026-11-18 04:40–04:44 UTC (PASS)

Session `sess_00vu3ba5amhhcshqh5u1`, 18.03 credits, ~4 min. Read-only: no plan,
no orders, no journal writes, no persistence, no push.

- Executor thread `sthr_00vu3f3tfnv28c3bfwye`: account-scope OAuth CLEAN —
  sim_trade_account_list / cash_info / position_list all ret_code 0 first
  attempt, no authorization prompts. Challenge account ***598 (title matched),
  account_type 2, market_id 100, total_asset 100,000, 0 positions. Snapshots at
  runs/2026-11-18-smoke2/{accounts,cash,positions}.json (sandbox-local).
- Auditor thread `sthr_00vu3hnknfev4gfe67o3`: all executor claims verified
  against files; file-visible guards confirmed (sim account checks, universe,
  price floor, caps, fee schedule vs fees.py). Zero APPROVE/REJECT verdicts
  (no plan/orders exist). Report reports/2026-11-18-smoke2-audit.md.
- Desk report reports/2026-11-18-smoke2.md. Findings to fix before first
  trading plan: F2 `universe.min_market_cap_usd` cited in risk-card but absent
  from config/universe.yaml; F3 snapshots carry no env=paper field; F4
  cash/positions snapshots carry no account_id linkage. Allowlist is
  env/kernel-enforced (not file-visible) — auditor correctly flagged it as
  unverifiable-from-files rather than approving it.

Follow-up 04:50–04:58 UTC: F2–F4 fixed locally — `min_market_cap_usd: 500000000`
now explicit in config/universe.yaml (F2); new `tyche snapshot --dir --account-id`
command writes run-dir snapshot.json with env/account_type/market_id/account
linkage (F3/F4); executor prompt (compile v3) mandates the snapshot step and the
desk roster was re-pinned 3/2/3 + advisor. Full suite 82 passed, ruff clean.
These changes must be committed + pushed BEFORE the 13:45 UTC pre-market run,
which mounts the repo from origin.

Follow-up 05:00–05:05 UTC (MCP-only cloud path): the moomoo CLI binary is absent
in the cloud sandbox, so `tyche execute`/`tyche fetch` are local-only. Executor
prompt now submits via MCP sim_trade_input_order and journals order events via
the new `tyche record-order` CLI (order.requested/submitted/rejected, halt.skip);
researcher prompt now also produces data/prices.csv via MCP klines (the plan
kernel's input); desk DAILY FLOW wires `tyche plan --prices data/prices.csv
--account <run-dir>/snapshot.json`. Roster re-pinned researcher 4 / auditor 2 /
executor 4 + advisor. Halt-kill runbook gained an MCP drill variant (no CLI
install needed).

Follow-up 09:45–09:50 UTC (kill-switch drill PASS): live MCP drill on the personal
paper account …748 — seed buy 3115432 filled 10 SPY @735.99; halt engaged; 3 buys
withheld + journaled (halt.skip); operator-authorized sell 3115472 filled 10 @737.04
while halted; broker day-history shows no drill buys; resume + journal-verify OK
(20 events). Record: docs/validation/2026-11-18-kill-switch-drill.md. Planning
inputs were a labeled synthetic fixture (disclosed in the record); broker state real.

## API quirks observed (connector)

- `update_forward_template` returns 400 unless `name` is included, despite the
  schema marking it optional.
- `github_repositories` entries 400 without a non-empty `authorization_token`.
- Failed writes do not change state; probes are safe but keep idempotency keys distinct.
- Roster entry shapes: the console writes `{"type":"agent","template_id":...}`
  WITHOUT pins; the API also accepts `{"type":"agent","id":<agent id>,"version":N}`.
  A template id under `id` resolves to not-found; `{"type":"template"}` 400s.
  Console checkboxes map only `template_id` entries, so agent-id entries run but
  render unticked. Hybrid `{"type":"agent","template_id":...,"version":N}` gives
  ticks AND pins (verified in session effective config 2026-11-18 04:22 UTC:
  researcher 3, auditor 2, executor 2, advisor ultimate). Console Save strips
  version pins: re-apply them via API after any console Save on that tab.
- Member template edits bump the compiled agent version; re-pin the roster
  after any member change (version-pin governance, docs/agent-engineering.md).
- The compiled coordinator agent stores roster refs as `"latest"`; the integer
  pins live on the TEMPLATE and are resolved into the session effective config
  at session creation. Verify pins via the session's `session.updated` agent
  block (or effective config), not `get_agent` on the coordinator.
- Vault bindings are template-level (`vault_ids` on update; null clears; the
  read shape is `vaults`). Vault-only edits do NOT bump the compiled agent
  version, so no roster re-pin is needed for them. `vaults` is not an update
  parameter (400). Same for `environment_variables` edits (verified on the
  executor allowlist change 2026-11-18: compile stayed v2).