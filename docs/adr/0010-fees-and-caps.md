# ADR 0010: Model fees, reconcile at EOD, and encode the competition caps

Status: Accepted, 18 November 2026.

## Context

The handbook mandates recording commissions and slippage, and the scored return
is fee-net. The sim MCP exposes no fee fields, so fees cannot be read from the
broker. The v0.1 risk defaults also differ from the competition rulebook
(min price, single-asset cap, position and order ceilings).

## Decision

Model fees from the handbook schedule and label them `source: model`:

- Stocks: commission $0; platform $0.99/order; TAF $0.000166/share on sells,
  capped at $8.30.
- Options: commission $0.65/contract (premium > $0.10) or $0.15 (≤ $0.10),
  minimum $1.99/order; platform $0.30/contract; TAF $0.00279/contract;
  regulatory $0.015/contract.

Each fill produces a `FeeRecord`. At end of day, reconcile modeled fees plus
fill cash against the actual cash delta from MCP funds; the residual is recorded
and investigated, not hidden. Modeled fees stay provisional until reconciled.

Encode the competition caps in the risk policy and config:

- `min_price` 1.00 (was 0.50);
- single-asset hard cap 0.40, with a tyche target ≤ 0.38 for headroom;
- `max_positions` 100;
- competition order ceiling 200/day — tyche keeps a stricter internal budget
  (6/day) to avoid churn;
- minimum market cap $500M as a research-stage universe gate (the kernel has no
  market-cap feed, so this is enforced when the universe is built, not per order).

## Consequences

- The fee-net equity curve, not gross, is the scored artifact.
- Internal discipline is stricter than the competition maxima, leaving headroom
  for mark drift and event-sleeve concentration.
- A persistent reconcile residual means the fee model or a fill is wrong; it
  blocks the next plan until explained.

## Alternatives considered

- Ignore fees because sim shows none: rejected — the handbook explicitly scores
  fee-net and requires the record.
- Wait for broker fee fields: rejected — they do not exist on the sim MCP; a
  labeled model plus reconcile is the honest, available path.