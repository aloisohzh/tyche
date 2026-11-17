# PB-XXX — <setup name>

- **Status:** draft / pre-registered / trading / killed
- **Rules hash:** `<freeze before trading>`
- **Validation:** unvalidated / sanity-checked / backtested (label honestly)
- **Sleeve:** ballast / event / intraday / options
- **Env:** paper (competition)

## Thesis
One paragraph: what market behavior this exploits.

## Edge
Why it should work after fees. Why it might not (the bear case). Drift ≠ edge: state what makes this
better than a random entry in the same regime.

## Universe / liquidity filter
Names, min price $1.00, min cap $500M, dollar-volume / spread gate, size below market-volume×20.

## Entry trigger
Exact, deterministic condition. Limit price rule. Session window (ET).

## Invalidation
The condition that kills this trade (and this strategy). Explicit price/level/time/event. This is a
judging requirement — never leave it vague.

## Sizing
Risk unit (R), risk-per-trade %, single-asset headroom (target ≤38%), sleeve cap, cash buffer.

## Exit
Target, protective stop (synthetic monitor or defined-risk structure), time exit. Final-day flatten rule.

## Regime fit
When this is on / off (risk_on / neutral / risk_off, event calendar).

## Fees / slippage
Stock: $0.99/order + TAF on sells. Options: $0.65/contract (min $1.99) + $0.30 + TAF + regulatory.
Half-spread per side as the live-cost estimate.

## Evidence
Links to journal rows, plan artifacts, scorecard. Record rejections and vetoes with reasons.