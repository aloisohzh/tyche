# End-of-day report - {{as_of}}

## Account

- Account: `{{account_id}}`
- NAV: {{nav}}
- Prior close NAV: {{prior_close_nav}}
- Daily return: {{daily_return}}
- High-water NAV: {{high_water_nav}}
- Drawdown: {{drawdown}}

## Exposure

| Sleeve | Weight | Cap | Status |
| --- | ---: | ---: | --- |
{{sleeve_table}}

- Gross exposure: {{gross_exposure}}
- Cash weight: {{cash_weight}}
- Largest position: {{largest_position}}

## Execution

| Side | Symbol | Qty | Limit | Order ID | Status | Fill |
| --- | --- | ---: | ---: | --- | --- | ---: |
{{execution_table}}

Unfilled or canceled orders: {{unfilled}}

## Risk events

{{risk_events}}

## Performance

- Turnover today (buy side): {{turnover}}
- Orders submitted: {{orders_submitted}}
- Orders blocked: {{orders_blocked}}
- Realized volatility estimate: {{realized_vol}}
- Cumulative return since inception: {{cumulative_return}}

## Narrative

{{eod_narrative}}

## Follow-ups

{{follow_ups}}
