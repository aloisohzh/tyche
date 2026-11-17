# ADR 0012: Defined-risk options and synthetic protection on a limit/market-only sim

Status: Accepted, 18 November 2026.

## Context

The sim MCP `order_type` enum is Limit/Market only — no stops, trailing stops, or
algo orders on paper. Multi-leg options can be entered but each leg is managed
independently afterward, and there is no historical options data via MCP. Direct
shorting is out of scope. Broker-side protection therefore cannot be assumed.

## Decision

- **Defined-risk structures only.** Downside expression uses long puts or put
  spreads (debit, capped loss); no naked shorts and no undefined-risk legs.
- **Leg groups.** A multi-leg thesis is tracked as one group with a shared
  thesis, invalidation, and roll plan, while each leg is a separate order that
  counts against the daily allowance and is reconciled independently.
- **Synthetic protection.** Because broker stops are unavailable, an intraday
  monitor (1–2 minute cadence during regular hours) watches invalidation and
  stop levels and emits de-risking sell intents when they breach. Protection is
  agent-driven and journaled, not broker-guaranteed.
- **Rolling** follows the playbook `roll_plan`; a roll is a new leg group entry
  plus closes, each through the kernel and the auditor gate.

Options are P2: they ship only after the stock adapter, allowlist, persistence,
and kill-switch drill are proven on the personal paper account.

## Consequences

- Protection depends on the monitor running; a missed cadence is an open risk
  and must be journaled and surfaced, not silently ignored.
- Each leg consumes order allowance and must be reconciled on its own; the group
  is an accounting convenience, not a broker construct.
- No historical options backtest is possible; options edge is validated forward
  on paper with small size and a provisional expectancy label.

## Alternatives considered

- Rely on broker stop orders: rejected — the sim does not support them.
- Naked shorts or undefined-risk spreads for cheaper downside: rejected —
  violates the defined-risk mandate and the no-short policy.