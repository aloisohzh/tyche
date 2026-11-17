# ADR 0011: Three-role topology with a separate auditor, plus coordinator and advisor

Status: Accepted, 18 November 2026.

## Context

The handbook rewards a researcher / executor / risk-auditor topology with the
auditor in a separate session so it cannot be talked into agreeing, and states
the orchestrator rule: never let the executor act on the researcher's output
without the auditor's approval. QCA Forward Mode supports a coordinator with
depth-1 children, isolated history, a shared sandbox, ≤20 ordinary threads plus
one model-only advisor, and version pins fixed at save.

## Decision

Adopt the handbook topology rather than an invented six-agent design:

- **Coordinator** — owns the run, delegates by explicit criteria and output
  formats written into its prompt (selecting agents does not force delegation).
  Holds no trading credentials.
- **Researcher** — produces thesis, multi-factor inputs, outlook, vehicle and
  expected edge; writes research artifacts. No order authority.
- **Risk auditor** — a separate session/thread; reviews the plan and risk
  verdicts and approves or rejects. Cannot be persuaded by the researcher.
- **Executor** — submits only auditor-approved orders verbatim via MCP, then
  reconciles. The only role holding trading credentials.
- **Advisor** — model-only critique (≤1), advisory; its failure does not block.

Pin every child agent and skill version (no `latest`). Schedules start a new
session per run (no carry-over), concurrency 1, dedupe by stable ids, and carry
an explicit end time for monitoring. Instructions are self-contained and name
the exact files each role owns.

## Consequences

- Matches the scored topology and the approval gate exactly.
- More threads to manage, but each is narrowly scoped with file ownership.
- A pinned version means an update affects new sessions only; tuning is a
  deliberate re-pin plus a re-run of the fixed eval prompts, diffed.

## Alternatives considered

- Six-agent/six-plane design: rejected as over-engineered for the window (0007).
- Auditor in the same session as the researcher: rejected — it defeats the
  independence the handbook explicitly rewards.