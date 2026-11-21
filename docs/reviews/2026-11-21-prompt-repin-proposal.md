# Prompt re-pin proposal - 2026-11-21 - APPROVED AND APPLIED the same day, see "Applied" at the end

Two of the four pinned agents quote risk caps that `config/risk.yaml` no longer carries, and the researcher's
pinned arsenal names lanes that are not what the desk runs today. [PRD §7 item 1](../../documentation/PRD.md)
records this as **L-033**, and it needs the operator's approval to fix: a prompt edit is a new pin, and a new
pin is a new build ([agent-rules](../agent-rules.md), L-021).

This file is the exact diff. As written at approval time it described an untouched cloud: no `update_agent`
call had been made, no deployment had been touched, and no existing pin had been modified. The applied state,
including the two things the platform handed back, is recorded at the end. The live configs are captured (gitignored, local-only) in `data/capture-2026-11-21-repin/` so
any change is reversible byte-for-byte.

## Why numbers in a prompt are the problem, not these numbers

| Claim in a pinned prompt | `config/risk.yaml` today | Consequence |
|---|---|---|
| "40 daily entry orders" (auditor v6), "<=40 entry orders/day" (desk v28) | `max_orders_per_day: 120` | An auditor that believes the budget is 40 raises a false blocker on the 41st order, or an operator believes the prompt over the config |
| "150% buy turnover" (auditor v6) | `max_daily_turnover_pct: 3.00` (300%) | Same, on a cap that was raised for PB-004's ~100-order scalp day |
| "200 competition total orders", "<=100 positions" | `competition_order_cap: 200`, `max_positions: 100` | Correct today; correct for exactly as long as nobody changes them |

The kernel re-reads the config on every run and is the only thing that can actually block an order, so a recited
number can only ever be a stale copy of the truth. The two correct-looking numbers are the argument for removing
all four: the prompt is wrong in the way that is invisible until it matters (L-033 is the second time this has
happened, after the 6-orders/50% caps went stale the same way).

So the fix deletes the figures and points at the authority, rather than re-typing today's values.

## Edit 1 - `tyche-risk-auditor` (v6 -> v7)

```text
OLD:
Enforce current exact YAML/kernel limits including pending buys and held positions, 40 daily entry orders,
200 competition total orders, 150% buy turnover and <=100 positions.

NEW:
Enforce the current exact YAML/kernel limits including pending buys and held positions, read from
config/risk.yaml on this run - the daily order budget, competition order ceiling, turnover cap and position
count are configured there, never recited from memory. Those values have already been raised twice as lanes
landed, and a stale number in this prompt reads as authority while the kernel's verdict is the real one (L-033).
```

## Edit 2 - `tyche-desk` (v28 -> v29)

```text
OLD:
5%, soft/hard DD 4%/6%, <=40 entry orders/day, <=200 total competition orders/day, turnover and underlying
concentration per exact config.

NEW:
5%, soft/hard DD 4%/6%. The daily order budget, competition order ceiling, turnover and underlying
concentration come from config/risk.yaml and the kernel's verdict on this run, never from a number quoted
here: the caps move when a lane lands, and a stale figure in a prompt is a second, wrong authority (L-033).
```

## Edit 3 - `tyche-researcher` (v16 -> v17), the Scout lane-id clause

The desk's manual Scout brief already says `Playbooks live for this run: {lanes}` and "propose only inside
these" (`dashboard/server.py:2351`), but the researcher's pinned arsenal paragraph still describes the
2026-11-18 line-up, so a Scout that trusts its system prompt over its brief proposes for a lane the desk may
have switched off. One appended sentence makes the brief the authority:

```text
OLD:
ARSENAL: keep PB-001 ETF rotation as ballast (25% ceiling); add catalyst-driven long stocks (45% ceiling) and
standard single-leg long calls/long puts (25% premium ceiling), cash >=5%. These are maximum allocations, never
mandatory investment targets.

NEW:
ARSENAL: keep PB-001 ETF rotation as ballast (25% ceiling); add catalyst-driven long stocks (45% ceiling) and
standard single-leg long calls/long puts (25% premium ceiling), cash >=5%. These are maximum allocations, never
mandatory investment targets. Which lanes are actually mounted is not stated here: the run brief names the live
playbook ids and it wins - propose only inside the ids the brief reports, and treat a lane missing from it as
research, not as a proposal. A switched-off lane still runs its exits, stops and targets, so its holdings stay
relevant even though its entries are not.
```

## Mechanics of applying it

Each replacement is applied programmatically to the captured `system` string, with an assertion that the old text
occurs **exactly once** before anything is sent: if a pin has drifted since this file was written, the edit aborts
instead of writing a prompt nobody reviewed. The OLD blocks above are wrapped for reading; the byte-exact strings
come from the capture.

## What a re-pin does not do

- Only **new sessions** pick up a new pin; anything already running keeps the old text (L-021). The next
  scheduled desk/researcher/auditor run is the first one that sees it.
- It changes no config, no cap, no tool grant and no schedule. The risk numbers stay wherever they are today -
  `config/risk.yaml` is untouched by this proposal.
- It grants no new capability to any agent, and nothing here touches order submission, the approvals envelope
  or the kill switch.

## Re-assert the least-privilege grants afterwards (L-023)

A recompile has silently dropped a needed tool before, so after each `update_agent` the returned config is
diffed against the capture and must still show exactly:

| Agent | Built-in tools | MCP tools |
|---|---|---|
| `tyche-risk-auditor` | Read, Glob, Grep, Write | none (`mcp_servers: []`) |
| `tyche-desk` | Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, DeliverArtifacts | none; children reached through `multiagent` |
| `tyche-researcher` | Read, Write, Glob, Grep, WebSearch, WebFetch | 24 moomoo read-only tools enabled, 0 disabled, no order-write tool |

## Rollback

Restore the captured `system` string for the affected agent. Written before the mechanics were understood,
this said `update_agent`; what actually carries a prompt is the Forward **template**, so a rollback is
`POST /templates/{id}` with the captured text, followed by the same chain this document's "Mechanics" section
now describes: compiled version, roster pin, card pin. `plans/cloud-*-pre-repin.json` holds every pre-change
object, and version numbers move forward only - a rolled-back pin is a new pin again, which is why the capture
is the rollback, not the previous version id.

## Applied (2026-11-21, operator approval "Apply all three")

`scripts/repin_stale_caps.py` sent the three diffs exactly as reviewed - each one asserted to match its OLD
text exactly once before anything was written, so a drifted pin aborts instead of shipping prose nobody read.

| Object | Before | After | What moved |
|---|---|---|---|
| `tyche-risk-auditor` | v6 | v7 (`895754b43589`) | Edit 1; 4 built-ins, no MCP |
| `tyche-researcher` | v16 | v17 (`6b9bce87ed03`) | Edit 3; 6 built-ins, 24 read-only moomoo tools |
| `tyche-desk` | v28 | v29 -> v30 -> v31 (`d3ee24f78f05`) | Edit 2 + roster 7/17/15 in one write, then the two findings below |
| Desk roster | researcher 16 / auditor 6 / executor 15 | 17 / 7 / 15 + advisor | pinned, not left to resolve |
| Scheduled cards | both v28 | both v31 | prompts, crons and env keys asserted byte-identical |

Two things the platform handed back that no prose review would have caught:

- **A recompile materialises latent grants (L-046).** The desk template carried
  `managed_tool_config: {enabled_tools: ["drive", "schedule"]}`, which v28 had never honoured and v29 did:
  ten always-allow tools, including `delete_forward_schedule` and `delete_drive_entry`, on the pin an
  unattended card runs - against a card that states the paused Forward schedule must stay paused and never
  have two writers. The operator chose to clear the grant; the desk compiled again as v30 with 9 built-ins and
  no MCP server, which is the surface the reviewed table described and what v28 actually ran with.
- **A filtered roster rebuild deletes rows (L-045).** Rebuilding `multiagent.agents` from the entries that
  carry a `template_id` dropped the model-only advisor row `{model: qmodel_38max, type: advisor}` - part of
  the topology ADR 0011 names deliberately. It was restored verbatim as v31 with the child pins and the prompt
  byte-identical, and the script now refuses a roster write whose non-agent rows changed.

Verified against the compiled agents rather than the templates: no recited cap string survives in any prompt,
the three allowlists match the table above, and the first run under the new authority is the Monday 23 Nov
13:05Z pre-market fire.

## The separate approval, also applied

`tyche rules-freeze --record` ran on the operator's approval and appended all four rows: PB-001
`rules.refrozen` `569eb2c341e0` -> `819ad06e35f0` (event `5f1b2b82b48a`) and first-ever `rules.frozen` rows for
PB-002 (`1664156d6346`), PB-003 (`4f3e84d163ec`) and PB-004 (`5f6d8ab3cc1d`); chain 89 -> 93 events, verified,
and a re-check exits 0. The residual finding it exposed - PB-002/PB-003 record with `declared: null` because no
playbook declares their hash - lives on as PRD §7 item 4.
