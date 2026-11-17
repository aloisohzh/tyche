# ADR 0001: Deterministic core with an LLM perimeter

Status: Accepted, 17 November 2026.

## Context

The competition rewards both Qoder and Cloud Agent usage (30%) and strategy and
risk design (30%). An LLM given direct order authority is hard to test, hard to
audit, and prone to inconsistent sizing. A purely rule-based system, on the
other hand, leaves the LLM contribution superficial and forfeits the research
and narrative value an agent can add.

## Decision

Split responsibilities. The Python core owns data ingestion, signals, regime
classification, position sizing, order construction, risk checks, execution,
and the audit journal. The LLM operates at the perimeter: research synthesis,
pre-trade critique, and daily reporting. Its outputs are text or validated
summary objects and never mutate a plan.

## Consequences

- Every money-losing decision is deterministic and covered by unit tests.
- The system remains fully functional when the LLM is unavailable.
- Qoder usage is visible and journaled without being load-bearing for safety.
- The LLM cannot react to breaking news by changing a position intraday. This
  is accepted: the strategy is daily and regime-based, not event-driven.

## Alternatives considered

- LLM as trader: rejected for auditability and reproducibility.
- No LLM: rejected because it weakens the Qoder criterion and the daily brief.
- LLM with veto power: rejected because a hallucinated veto is indistinguishable
  from a legitimate one and adds no safety over hard rules.
