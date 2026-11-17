# End-of-day narrative

You are writing the closing note for a paper-trading agent. Use only the
provided data.

## Inputs

- As-of date: {{as_of}}
- NAV: {{nav}}
- Prior close NAV: {{prior_close_nav}}
- Positions and weights: {{positions}}
- Submitted orders: {{orders}}
- Fills and open orders: {{fills}}
- Blocked orders and risk events: {{risk_events}}

## Rules

- A submit is not a fill. Distinguish submitted, filled, partially filled, and
  open orders explicitly.
- Do not infer a fill from an order acknowledgement.
- Do not recommend tomorrow's trades. Describe what happened and what is
  unresolved.
- Do not mention credentials, tokens, or full account identifiers.
- Keep the note under 300 words.

## Output

### Day summary

Two or three sentences on P&L, exposure, and the regime.

### Execution

What filled, what remains open, and any order that was blocked by risk.

### Drift and risk

Portfolio drift from target, cash weight, gross exposure, and any drawdown or
turnover event.

### Follow-ups

At most three items for the next run. Write "none" if clean.
