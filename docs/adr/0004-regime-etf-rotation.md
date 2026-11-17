# ADR 0004: Regime-aware, volatility-targeted ETF rotation

Status: Accepted, 17 November 2026.

## Context

The competition rewards risk-adjusted return over roughly two weeks of paper
trading, with a US$100,000 account and a small set of liquid instruments. A
single-asset bet is too fragile for a short window. High-turnover signals are
expensive and hard to validate. The strategy must also be explainable to judges
in one page.

## Decision

Use multi-horizon momentum to select up to four ETFs, classify the market into
three regimes with four observable checks, and size with inverse volatility and
a 10% annualized portfolio volatility target. Express the regime through sleeve
caps rather than through discretionary overrides.

Allocation order: inverse-vol weights, volatility scale capped at 1.0, sleeve
caps with redistribution of released capital, then per-instrument caps with
within-sleeve redistribution. Residual weight stays in cash, subject to a 5%
minimum. Rebalancing uses a 20% relative drift band and a minimum trade size.

Momentum skips the most recent five trading days to reduce short-term reversal
exposure. The regime combines trend, cross-over, volatility, and credit
conditions so that no single indicator controls exposure.

## Consequences

- Low turnover, typically a handful of orders per week.
- The portfolio can hold 20-35% cash when selected instruments hit their caps,
  which is a feature in risk-off regimes but a drag in strong risk-on markets.
- Momentum and regime parameters need walk-forward validation; the current
  values are documented defaults, not optimized results.
- The universe is US-listed ETFs only, which keeps data and execution simple.

## Alternatives considered

- Static 60/40: rejected as too little strategy content.
- Single-asset trend following: rejected for concentration and path dependence.
- Mean reversion: rejected for turnover and adverse selection in a short window.
- LLM-selected holdings: rejected under ADR 0001.
