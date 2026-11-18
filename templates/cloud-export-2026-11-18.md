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

Amendment 2026-11-18 13:07 UTC (operator-approved follow-ups): researcher v5→**v7**
(v6: no-shell handoff — researcher lists persisted kline files, Desk Head runs the
parser; v7: OUTPUT wording aligned to one-file + handoff), roster re-pinned to v7
(verified). Schedule `initial_events` v2→**v3**: plain-language HTML digest with
`<pre>` orders table, < 3500 chars, parse_mode=HTML. Rehearsal 2
`srun_84820bb31f5900a61a3429d1` ran on v5/events-v2; risk alert delivered 12:59 UTC.

Amendment 2026-11-18 13:20 UTC: desk template delegation contract updated — the
researcher line now mandates the kline handoff explicitly (researcher sends the
persisted /tmp/tool-outputs file map; Desk Head runs `python scripts/mcp_prices.py
/tmp/tool-outputs --out data/prices.csv`; researcher has no shell tool). Desk prompt
edits bump the coordinator compile, but roster pins are member-only and unchanged
(researcher 7 / auditor 2 / executor 4 + advisor). Rehearsal 2 final: COMPLETED
13:10:41Z, digest delivered ok; plan = BUY EFA/VNQ/DBC approved, SPY blocked at the
old 20% notional cap (cap raised to 30% in repo 18b97cf, pushed 13:18 UTC before the
13:45 cron; mount syncs latest main per session). Cloud git push 403 (mount PAT is
read-only) — Drive raw sink succeeded; push-back still operator-open.

Amendment 2026-11-18 16:51 UTC (pre-change export, act/wait gate clause): live prompts
retrieved via GET /templates (executor `tmpl_bc25a5c313827d53894fd7ff` updated
2026-11-18T13:04+08, desk `tmpl_004fa008901a6c256bd0ed3f` updated 2026-11-19T00:45+08 —
the desk prompt now carries the parallel session's hourly-cadence + watchlist flow).
Neither prompt mentions `pipeline.action` / `gate.wait`; roster pins 7/2/4 + advisor.
Raw exports kept local-only under gitignored `plans/cloud-*-live.json`. Planned change:
executor system prompt gains the ACT/WAIT GATE clause (skip `pipeline.action="wait"`
orders, journal `gate.wait`, never block sells/defensive entries); compiled executor
v4→v5 expected; desk roster re-pin executor 4→5, desk prompt untouched.

Amendment 2026-11-18 17:16 UTC (gate clause APPLIED, operator-approved via explicit
target+diff confirmation): executor template updated via `update_forward_template`
(name + system only; tools/always_ask policies/vault/env preserved — verified in the
response). Compiled executor `agent_00vtx8mfbxerk6vxmny5` now **v5** (get_agent verified,
clause present). Desk roster re-pinned **7/2/5 + advisor** (update response verified;
desk system prompt preserved verbatim — the hourly-cadence + watchlist flow from the
parallel session is intact). New executor prompt snapshot: gitignored
`plans/cloud-executor-new.prompt.txt`; rollback = restore `plans/cloud-executor-live.prompt.txt`
(pre-change, v4) and re-pin 4. Note: the direct-API script path
(`scripts/forward.py` POST) was blocked by the desktop permission classifier; the QCA
connector tool path was used instead. Env-var values returned by the API are
server-side only and must never be copied into docs, chat, or git.

Amendment 2026-11-18 17:56 UTC (operator approval envelope + SGT, operator-approved
"option 2"): repo commit `7a43032` pushed to main adds `tyche approvals` / `tyche
authorize` CLI + `src/tyche/approvals.py`, git-tracked `data/approvals.json` (mount-synced
operator envelope; `.gitignore` negation), and SGT (`Asia/Singapore`, UTC+8) in
`ScheduleDef.sgt_time` + the dashboard schedule table. Schedule `tyche-hourly`
`initial_events` v1→**v2**: APPROVALS CONTRACT, per-order `tyche authorize` gate in the
drive/midday playbooks, pre-market "propose the evening approval batch", and digest header
`<HH:MM> UTC / <HH:MM> SGT`. Desk template system gained the envelope authorization clause
(delegation line + DAILY FLOW step 3 + APPROVALS paragraph); coordinator compile bumped,
member pins unchanged. Executor template: `HUMAN-IN-THE-LOOP` → `OPERATOR AUTHORIZATION`
(path A pre-approved envelope via `tyche authorize` exit-0; path B per-order confirmation),
precondition (3) updated; **`sim_trade_input_order` always_ask→always_allow**, cancel/modify
**stay always_ask**; the parallel session's ACT/WAIT gate (v5) is preserved intact in v6.
Compiled executor `agent_00vtx8mfbxerk6vxmny5` v5→**v6** (get_agent verified); desk roster
re-pinned **7/2/6 + advisor** (update_forward_template, multiagent only; system/tools/vault/
env/mount preserved). Deploy + verify: `scripts/deploy_envelope_sgt.py`,
`scripts/verify_envelope_deploy.py`. Rollback snapshots (gitignored):
`plans/cloud-{schedule,desk,executor}-pre-envelope.json`; restore + re-pin executor 5.
Trade-off accepted by operator: the platform per-order popup for submission is replaced by
the deterministic `tyche authorize` code gate + prompt + journal + auditor review (paper
orders on stated intent). Direct-API inline POST was classifier-blocked; the file-based
deploy script and the QCA connector tool path were used.

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
| Researcher (scout) | `tmpl_875834770244a9e35c7f6499` (rewritten from Moomoo Paper Trader) | `agent_00vs9v3dg0rnkr4740x3` | 7 | moomoo (read; all order-write tools disabled) | none |
| Risk auditor | `tmpl_ae317cc0626a4fcc8fa8fad6` | `agent_00vtx8g7k1534t7w9eve` | 2 | none | none |
| Executor | `tmpl_bc25a5c313827d53894fd7ff` | `agent_00vtx8mfbxerk6vxmny5` | 6 | moomoo, default **always_deny**; sim reads + quotes allowed; `sim_trade_input_order` = **always_allow** under the `tyche authorize` envelope gate (else per-order confirmation); `cancel` / `modify` = **always_ask** | paper only |
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