# Protection guard: plan awaiting operator decision (2026-11-20)

Status: **proposal for approval, not a decision record.** No code, config, card or schedule was
changed to write this. [ADR 0013](../adr/0013-protection-monitor.md) stays `Proposed` until the
operator picks the three options marked DECIDE below. Author: Qoder, from a live inspection of the
cloud state and the repo at 04:30-04:45 UTC.

## What is actually true today

- The only active execution owners are the two Cloud Automation cards: `dep_00vzb9h4ezawwl4thnva`
  (Nov, fires 08:05 and 15:05 ET) and `dep_00vzd8d5rdfr4w0denqh` (Dec). Verified by
  `list_deployments` - it returned exactly these two, both `active`.
- All eight Forward schedules are `paused`, including `tyche-hourly` and `tyche-midday-monitor`.
  Verified by `scripts/forward.py get /schedules`.
- The guard code exists and is not the missing piece: `tyche lifecycle tick` and its read-only
  `execute-exit` (`src/tyche/lifecycle_cli.py`, `monitoring_book` at line 57), the tactical monitor
  with `monitor_interval_seconds: 30` (`src/tyche/tactical_cli.py:113`, `config/tactical.yaml:14`),
  heartbeat-gap detection (`src/tyche/tactical.py:153-157`) and the 75-minute coverage-gap string
  (`src/tyche/lifecycle.py:603`).
- But no live instruction runs any of it between the two fires: searching the two-fire card prompt for
  `lifecycle tick`, `tactical monitor` or `monitor tick` returns zero matches. So today's intraday
  protection is two checks a day, and nothing at all between 15:05 ET and 08:05 ET next day.
- The ADR's own `tyche monitor tick` (heartbeat / breach / clear events) is still unimplemented; the
  pieces above are the lifecycle and tactical lanes, which a run must be told to invoke.

## Doc and test drift found while checking (reported, not fixed)

- [../runbooks/protection-monitor.md](../runbooks/protection-monitor.md) line 5 pins the cloud
  workflow to release `1e902cf57c...`. That commit is **not an ancestor of `main`** and no branch
  contains it, and `scripts/deploy_hourly_workflow.py:97` says "Do not use old lifecycle-hourly-release
  1e902cf". The pin is stale and points at a deprecated build.
- The same runbook line 27 says the 2026-11-19 follow-up (strategy, asset and sleeve caps, CRLF rule
  hashing) "is not committed or deployed". That is now wrong: the caps are on `main`, asserted at
  `src/tyche/lifecycle.py:556-574`.
- `tests/test_scalp.py::test_state_rebuilds_lots_cooldown_and_today_round_trips` **fails**. It is a
  clock bomb, not a broker bug: the file hardcodes `NOW = 2026-11-19 15:30 UTC` (line 24) while
  `append_event` stamps the real wall clock, so the ET-date filter in `src/tyche/scalp.py:114-117`
  drops the request and `last_request` comes back empty. It has been failing every day since 19 Nov.
  It must be green before guard work, because it is the test for the lane whose state the guard reads.
- Full suite otherwise passes; this is the single failure.

## Three decisions

### 1. Cadence. DECIDE

| Option | Blind window after a breach | Cloud cost | Notes |
|---|---|---|---|
| a. keep two fires | up to ~6h intraday, ~17h overnight | none | current state, honestly labelled |
| b. add a midday fire (12:05 ET) | ~4h | 1 extra LLM run/day | smallest real improvement; no new schedule family, no new writer |
| c. dedicated deterministic guard every 5 min | ~5 min | ~78 thin runs/session day | ADR 0013's alert-only tier; 1-2 min tiers are irrelevant while `options_enabled: false` |

Recommendation: **b now, then c** as the real build. Do not start at 1-2 min; nothing on the book needs
that speed yet, and the cost is ~195 runs a day.

### 2. Where it runs. DECIDE

Cloud card is the only option consistent with unattended operation - the operator PC is not always on,
which is exactly why the inbound listener was stopped (`docs/lessons/LESSONS.md` L-006). A local
runner is cheaper and can tick at 30s, but a switched-off PC is a silent protection gap, and the
competition requires automation that survives it.

Recommendation: **cloud, as a separate card, never an execution owner**, `max_concurrent_runs: 1`,
`max_attempts: 1`, calendar-gated so holidays and weekends cost nothing, and skipped when the
watchlist is empty. The two-fire card keeps sole execution ownership and its "never run two writers"
rule stays intact.

### 3. What it may do unattended. DECIDE

- Level 0: journal a heartbeat, and on breach send one urgent Telegram alert. No orders, no intent.
- Level 1: additionally queue a defensive exit intent that a human confirms in the console.
- Level 2: submit an approved exit automatically under an existing lifecycle grant.

Recommendation: **ship Level 0, then Level 1. Keep Level 2 off** until options are enabled and a
synthetic-breach drill has passed. This matches the standing rule that an order needs a preview and an
explicit confirmation, and that paper submission still needs an approved exact grant.

## Build order once approved

0. Fix the scalp test's clock dependence so the suite is trustworthy evidence again.
1. Implement `tyche monitor tick` per ADR 0013: watchlist plus fresh quote JSON in,
   `monitor.heartbeat` / `monitor.breach` / `monitor.clear` out, no broker access, `--dry-run` default,
   unit-tested. This is the piece that removes the LLM from the breach decision.
2. Wire the quote fetch to the existing fast path (`scripts/mcp_prices.py`, one kline call per symbol)
   so a tick stays cheap and bounded.
3. New guard card instruction: run the tick, deliver an alert through
   `scripts/telegram.py send-digest` with `urgent: true`, record delivery failure and keep going.
4. Confirm the cross-process journal lock before the first scheduled tick - the guard appends to the
   same hash chain as desk runs, so this is a prerequisite, not a follow-up (ADR 0005, ADR 0013).
5. Alert de-duplication by transition: alert on clear-to-breach once per symbol per episode, not every
   tick, or a volatile day buries the operator.
6. Drill, recorded under `docs/validation/`: synthetic breach end to end, measuring detection-to-alert
   and alert-to-confirmation latency, with zero broker writes proven.
7. Report heartbeat coverage in every EOD digest, and make both fires state the age of the last tick,
   because a schedule that never ran cannot alert about its own failure.

## Risks the operator is accepting

Protection stays synthetic: detection, alert, queued intent, human confirmation. It is not a resting
broker stop and the honest latency must appear in every drill report. A 5-minute guard on a volatile
day can still alert repeatedly if transition de-duplication is skipped. Cloud spend rises with each
tick, so cadence is the first knob to turn down if runs cost more than expected. None of this enables
options; that still waits on ADR 0012 and 0013 both closing.

## Out of scope

Options trading. Broker-native stops. Reopening the inbound Telegram bridge or the paused Forward
schedules. Any change to the two-fire cards' trading gates, envelopes, caps or approval rules.
