# Runbook: intraday protection monitor (design draft)

Status: **design only — nothing here is implemented yet.** Decision record:
[ADR 0013](../adr/0013-protection-monitor.md). This monitor is the hard
prerequisite for enabling options (ADR 0012, P2).

## What it is

The sim has no broker stops. Protection is a scheduled agent loop that, during
the regular session, compares fresh quotes against each open position's
journaled invalidation and queues a de-risking exit when a level breaches.
It is detection + alert + queued intent — **not** an instant stop; the
breach-to-fill path includes auditor review and per-order operator
confirmation. That latency is only acceptable because options are
defined-risk (loss capped by structure) and ballast exits are
rebalance-tolerant.

## Watchlist contract

Written by the executor at plan/execute time to `plans/<date>-watchlist.json`
(raw copy to the Drive locker; sanitized summary may go to git). One entry per
open position or option leg group:

```json
{
  "as_of": "2026-11-18",
  "account": "...598",
  "entries": [
    {
      "symbol": "US.SPY",
      "group_id": null,
      "side": "long",
      "qty": 28,
      "entry_price": 733.17,
      "playbook": "PB-001",
      "rules_hash": "569eb2c341e0",
      "protection_type": "rebalance",
      "invalidation": {
        "kind": "rule",
        "expr": "momentum <= 0 or regime risk_off (<2 of 4 checks)",
        "level": null,
        "deadline": null
      },
      "roll_plan": null
    }
  ]
}
```

- `kind: price` — `level` is the stop/trigger price; breach when last price
  crosses it in the adverse direction (long: `last <= level`).
- `kind: rule` — deterministic expression over the regime/momentum inputs the
  kernel already computes; evaluated by the kernel, never by the LLM.
- `kind: time` — `deadline` (UTC timestamp); breach at/after it while open.
- `group_id` — option leg group (ADR 0012): one thesis, one invalidation, one
  roll plan; a breach closes **all legs** of the group, each leg a separate
  order against the daily allowance.
- Entries are derived from `order.pipeline` (invalidation, protection_type,
  roll_plan) plus reconciled fills. No entry may be invented by the monitor.

## Cadence

| Strictest protection on watchlist | Tick interval | Mode |
|---|---|---|
| `synthetic_stop` | 1 min (2 min acceptable) | full |
| `defined_risk` (options) | 2 min | full |
| `time_exit` / `rebalance` only | 5 min | alert-only |
| empty watchlist | schedule gate skips | — |

- Regular session only, DST-aware: `tyche calendar --phase intraday --json`
  runs first in every tick (same MARKET GATE pattern as the desk schedules);
  exit 1 → journal `run.skip`, stop. Half day (27 Nov): ticks end 18:00 UTC.
- Schedule: `tyche-protection`, cron `*/2 14-20 * * 1-5` UTC as the base
  (tightened/loosened per tier at deploy), `new_session`,
  `max_concurrent_runs: 1`, `max_attempts: 1`, window-bound
  (stop 2026-11-28T00:00Z), same template/environment/identity as the desk.

## Tick flow

1. MARKET GATE (calendar + `tyche journal-verify`). Skip → one-line notice, stop.
2. Executor reads broker positions + fresh quotes for watchlist symbols
   (read-only MCP), writes `quotes.json` into the run dir.
3. `tyche monitor tick --watchlist ... --quotes ...` (kernel, deterministic):
   - appends `monitor.heartbeat` `{ts, cadence_s, watched, gaps}`;
   - evaluates each entry; appends `monitor.breach` or `monitor.clear`
     per entry with the triggering value;
   - exits non-zero if any breach, so the perimeter cannot miss it.
4. On breach: executor builds defensive sell/close intents (group → all legs),
   routes through kernel sizing/caps → auditor → `sim_trade_submit_order`
   with `always_ask` per-order confirmation. Telegram alert fires **before**
   confirmation, not after — the operator must know even if they never confirm.
5. Persist per the PERSIST step (raw → Drive locker; sanitized → git only if
   the sanitize gate passes).

The monitor **never initiates new entries**. The act/wait gate never blocks
its defensive exits. Under halt, ticks continue (defensive exits are allowed)
and alerts carry the halt state.

## Contention (single-writer journal)

Desk phase runs and monitor ticks share the hash-chained journal (ADR 0005):

- Kernel journal appends take a cross-process lock (implementation item).
- `max_concurrent_runs: 1` on the protection schedule; ticks are short
  (target < 60 s) so overlap with a desk run resolves by lock, not by loss.
- A tick that cannot acquire the lock within its budget journals nothing,
  sends a `monitor.gap` alert, and exits — a skipped tick is a surfaced risk,
  never a silent one.

## Heartbeat, gaps, EOD coverage

- Gap rule: `now - last_heartbeat > 2 × cadence` → `monitor.gap` event +
  Telegram alert on the next tick (or by the next desk run, whichever first).
- EOD reconcile reports coverage: heartbeats vs expected session ticks;
  coverage < 95% is an audit finding, not a footnote.
- Telegram formats (masked ids only, no tokens):
  - `TYCHE PROTECTION BREACH — <HH:MM UTC> <symbol> <kind> <value> vs <level>; exit queued, confirm in executor thread`
  - `TYCHE PROTECTION GAP — <n> missed ticks (<minutes> min blind); positions: <list>`

## Pre-options drill (required before P2 flips on)

Record under `docs/validation/` like the kill-switch drill:

1. Seed a watchlist entry with a `price` invalidation just above the market.
2. Run a tick; verify `monitor.breach` journaled, Telegram alert received,
   defensive intent queued with `always_ask`, group legs all included.
3. Confirm one leg; verify submit → receipt → reconcile; deny another; verify
   it stays unsubmitted and the alert still fired.
4. Kill a tick mid-window; verify the next tick journals `monitor.gap` and
   alerts.
5. Measure and record breach→alert and breach→confirm latency; state the
   residual unprotected window explicitly.

## Implementation items (not done)

- [ ] `tyche monitor tick` kernel command + event types + tests
- [ ] Watchlist writer in plan/execute path (from `order.pipeline` + fills)
- [ ] Cross-process journal lock
- [ ] `tyche-protection` schedule deploy script (tiered cron, calendar gate)
- [ ] Executor template clause: monitor tick flow + breach path (operator-
      approved template edit + version re-pin, per agent-engineering.md)
- [ ] Drill executed and recorded; only then options allowlist expands