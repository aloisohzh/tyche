# Prompt re-pin proposal - 2026-11-21 - PROPOSAL, nothing written to the cloud

Two of the four pinned agents quote risk caps that `config/risk.yaml` no longer carries, and the researcher's
pinned arsenal names lanes that are not what the desk runs today. [PRD §7 item 1](../../documentation/PRD.md)
records this as **L-033**, and it needs the operator's approval to fix: a prompt edit is a new pin, and a new
pin is a new build ([agent-rules](../agent-rules.md), L-021).

This file is the exact diff. No `update_agent` call has been made, no deployment was touched, and no existing
pin was modified. The live configs are captured (gitignored, local-only) in `data/capture-2026-11-21-repin/` so
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

Restore the captured `system` string for the affected agent with the same `update_agent` call
(`data/capture-2026-11-21-repin/*.json`, local-only). Version numbers move forward only; a rolled-back pin is a
new pin again, which is why the capture is the rollback, not the previous version id.

## Separate approval sitting next to this one

`tyche rules-freeze` now exists and reports four unregistered lanes against the real chain (PB-001
`rules.refrozen` `569eb2c341e0` -> `819ad06e35f0`; PB-002/PB-003/PB-004 `rules.frozen`). Appending them is a
provenance claim in the audit chain, so it has not been run. Say the word and it executes as
`tyche rules-freeze --record --reason "..."`; the check-only run writes nothing and is safe to repeat.
