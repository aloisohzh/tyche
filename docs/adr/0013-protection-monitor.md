# ADR 0013: Intraday protection monitor

Status: Proposed, 18 November 2026 (rung 0 - the detector - implemented 2026-11-21 and not yet scheduled; the
alert routing below still needs its own approval. Hard prerequisite for options per
[0012](0012-options-protection.md)).

## Context

The sim broker accepts Limit/Market orders only (ADR 0012): no stops, trailing
stops, or brackets. Once a position is open, nothing broker-side protects it.
The per-trade pipeline contract (`order.pipeline.invalidation`,
`protection_type`, `roll_plan`) now journals what *should* protect each trade,
but nothing currently watches those levels intraday. The phase schedules
(opening/midday/closing) are hours apart — far too coarse to be protection.
Options (P2) cannot ship until a monitor exists, because defined-risk
structures cap the loss but do not manage exits or rolls.

## Decision

- **Agent-driven synthetic protection.** A dedicated `tyche-protection`
  Forward schedule runs short monitor ticks during the regular session only
  (DST-aware via `tyche calendar`), evaluating each watched position against
  its journaled invalidation. Cadence is set by the strictest protection type
  on the watchlist: `synthetic_stop` → 1–2 min; `defined_risk` → 2 min;
  `time_exit`/`rebalance` only → 5 min alert-only. No watchlist, no schedule
  fire (gate skips).
- **Deterministic trigger evaluation.** A new kernel command
  (`tyche monitor tick`, implemented 2026-11-21) consumes the watchlist + fresh
  quote JSON and emits `monitor.heartbeat` / `monitor.breach` /
  `monitor.clear` events. The LLM perimeter fetches quotes and relays events;
  it never decides whether a level breached. What is built is the evaluation and
  the journaling only: no schedule runs the tick, and the defensive-intent and
  Telegram legs below are still unapproved.
- **Breach → de-risk path, never new entries.** A breach queues a defensive
  sell/close intent through the kernel → auditor → executor `always_ask`
  confirmation, plus an immediate Telegram sentinel alert. The act/wait gate
  never blocks defensive exits. For `rebalance`-protected ballast the monitor
  alerts only; the exit happens at the next rebalance unless halt is set.
- **Honest latency.** Protection is detection + alert + queued intent, not an
  instant stop: breach-to-fill includes human confirmation time. This is
  acceptable only because options are defined-risk (max loss capped by
  structure) and ballast exits are rebalance-tolerant. The design must state
  this latency in every drill report.
- **Heartbeat and gap surfacing.** Every tick journals a heartbeat. A gap
  larger than 2× the active cadence is an open risk: the next tick journals
  `monitor.gap` and sends a Telegram alert; EOD reports heartbeat coverage
  against session minutes. A missed cadence is never silently ignored.
- **Single-writer journal.** Monitor ticks share the hash-chained journal
  (ADR 0005) with desk runs, so journal appends take a cross-process lock
  (`journal_lock` at `src/tyche/journal.py:35` - nonblocking and local-filesystem
  only, already implemented as of 2026-11-21, so a contended tick skips rather than
  waits) and the schedule keeps `max_concurrent_runs: 1`.
  Ticks are read-only against broker state; they submit nothing themselves.

The full contract — watchlist schema, trigger kinds, tick flow, contention
rules, alert formats, and the pre-options drill — lives in
[docs/runbooks/intraday-protection-monitor.md](../runbooks/intraday-protection-monitor.md),
whose §2-§3 and §8 now describe rung 0 as built, and whose §9 build order lists what is still open: the quote
path, per-tick alert routing, the scheduled-tick lock demonstration, the live-session drill run and heartbeat
coverage in the EOD digest. Nothing is scheduled. [docs/runbooks/protection-monitor.md](../runbooks/protection-monitor.md)
is what runs today: the lifecycle checks inside the three desk fires.

## Consequences

- Options remain blocked until the monitor is implemented **and** passes a
  synthetic-breach drill (alert + intent + confirmation + journal evidence,
  latency measured), recorded under `docs/validation/`.
- Cadence costs cloud runs: ~195 ticks/day at 2 min over a full session.
  Tiered cadence and the empty-watchlist skip keep ballast-only days cheap.
- The monitor adds a second schedule family overlapping desk phase runs;
  the journal lock and skip-if-busy rules are load-bearing, not optional.
- `expected_edge` for stop-protected trades stays provisional until forward
  evidence exists; the monitor journals exits so realized R can be computed.

## Alternatives considered

- **Broker-native stops**: unavailable on the sim (ADR 0012).
- **One long-running session looping with sleeps**: cloud session timeouts
  (~1 h) force chaining anyway; a missed restart is a silent protection gap,
  and it burns a session slot for hours. Rejected.
- **Hourly phase runs as protection**: cadence too coarse; a 60-minute blind
  window defeats the purpose of a stop level. Rejected.
- **Local deterministic poller on the operator PC**: works technically, but
  the desk must run without a PC (competition automation requirement), and
  submission still needs the cloud executor's per-order confirmation path.
  Rejected as the primary mechanism.