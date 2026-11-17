# Daily brief - {{as_of}}

- Regime: **{{regime}}** ({{checks_passed}}/4 checks)
- Portfolio volatility estimate: {{portfolio_vol}}
- Volatility scale: {{vol_scale}}
- Cash target: {{cash_weight}}

## Research context

{{research_brief}}

## Plan

- Plan artifact: `{{plan_path}}`
- Approved orders: {{approved_count}}
- Blocked orders: {{blocked_count}}
- Buy notional: {{buy_notional}}
- Sell notional: {{sell_notional}}

| Side | Symbol | Qty | Limit | Notional | Status |
| --- | --- | ---: | ---: | ---: | --- |
{{orders_table}}

## Pre-trade critique

{{critique}}

## Decision

- [ ] Proceed with approved orders
- [ ] Hold; re-plan next session
- [ ] Flag for human review

Operator note:

{{operator_note}}
