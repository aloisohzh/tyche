# ADR 0007: Cut scope to what the window can actually deliver

Status: Accepted, 18 November 2026.

## Context

The trading window is 17–28 November with roughly seven usable sessions left
from the 18th. Judging weights Qoder/Cloud Agent usage (30%) and strategy/risk
design (30%) plus documentation (15%) — 75% that does not depend on raw return.
The prior project (fortuna, reference only) built elaborate governance and
validation machinery but never produced a durable edge; the machinery consumed
the time that should have gone into a working, fee-net-positive process.

## Decision

Park, for after the window: the strategy gauntlet and rotated-null tests, Docker
"USB" strategy containers, the six-agent/six-plane topology, golden-set Outcome
rubrics, the four-key live-flip governance, fee calibration against broker
statements, and a full historical backtest.

Keep the seams that make those cheap to add later: an `Env` paper/live enum, a
broker adapter protocol, and pinned agent/skill versions. Build instead the
smallest thing that scores: a deterministic ballast rotation, small event-driven
sleeves, a fee-net equity curve, and impeccable journaled evidence.

## Consequences

- Less breadth of "platform" features, but a far higher chance of a working,
  well-documented agent inside the clock.
- Parked items are recorded in the 2026-11-18 review, not silently dropped.
- Every kept component must earn its place against the scoring map; anything
  that does not produce evidence is cut.

## Alternatives considered

- Build the full platform now: rejected — it repeats fortuna's failure mode and
  cannot be finished and validated in seven sessions.
- Cut all strategy work and only document: rejected — the 25% return criterion
  and the "genuine edge" requirement still need a live, fee-net process.