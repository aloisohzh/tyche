# Performance (generated)

Artifacts here are **readings of the journal**, never hand-edited. Raw journal/events persist to a
bucket; sanitized summaries commit to git.

## Daily metrics (fee-net)

NAV · daily + cumulative return · realized vol · Sharpe (annualized, with the ~7-mark caveat) ·
max drawdown · gross/net exposure · cash weight · turnover · orders executed (vs 200 cap) ·
blocked orders + reasons · risk events · fees (modeled) vs account cash delta (`fees.unreconciled`).

## Per-sleeve scorecard

Ballast vs each event sleeve: closed trades, win/loss, expectancy (R and %), avg edge vs SPY over the
same windows, conviction calibration if tiers are used. Attribute a trade to the sleeve that armed it.

## Reconciliation

EOD: submitted orders ↔ broker order history ↔ positions ↔ fills. A submit is not a fill. Unfilled
DAY orders cancelled/expired explicitly; nothing left working overnight without intent. Fees modeled
per fill; financing accrued daily after close; reconcile modeled cash to broker cash.

## Generator

`scripts/` performance report (to write, P1) reads `journal/events.jsonl` + archive and emits
`docs/performance/<date>-metrics.md` and the dashboard feed. Deterministic; the LLM only narrates.