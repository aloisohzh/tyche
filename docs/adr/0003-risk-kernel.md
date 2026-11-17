# ADR 0003: A sequential, fail-closed risk kernel

Status: Accepted, 17 November 2026.

## Context

Risk limits spread across strategy code and broker calls are easy to bypass
and hard to test. The strategy already sizes conservatively, but sizing is not
a control: bugs, stale prices, and surprising account state can still produce
an unacceptable order.

## Decision

Route every order intent through `evaluate_intent` before it can be executed.
The kernel is pure, deterministic, and independent of the strategy. It returns
a verdict with breaches, an adjusted quantity, and notes. An order is allowed
only if there are no breaches and the adjusted quantity is positive. There is
no override argument.

Orders are evaluated in sequence against a projected account that includes
earlier approved fills, so daily counts, turnover, cash, and exposure accumulate
within the batch. Exits that reduce exposure are exempt from turnover, halt,
position, gross, and sleeve restrictions, so the system can always de-risk. The
planning command applies each allowed fill to its working snapshot rather than
reusing the opening book for every check.

Drawdown uses a high-water NAV reference. A 4% drawdown halves buy quantities;
6% blocks buys. A 2.5% daily loss blocks buys. Caps on position, gross, and
sleeve exposure allow a 0.25% NAV tolerance for mark drift; the minimum cash
floor does not.

## Consequences

- Every invariant has a focused unit test.
- A blocked order does not block the rest of the plan unless state is consumed.
- The kernel must be updated deliberately when a new instrument type or order
  type is introduced.
- Sequential evaluation means order order matters for count and turnover; the
  plan emits de-risking sells first.

## Alternatives considered

- Validation inside the strategy: rejected because it conflates intent with
  permission and cannot guard execution of a hand-edited plan.
- Broker-side checks only: rejected because paper brokers may accept orders the
  policy should refuse, and rejection messages are not a risk budget.
