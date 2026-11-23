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

`tyche performance report` (`src/tyche/performance.py`, `performance_cli.py`) reads the journal, the
published desk feed and the researcher's `date,symbol,close` CSVs and writes `docs/performance/<date>-metrics.md`
(and `--json-out`). Deterministic: no network, no wall clock, the same inputs give the same bytes, and the
chain is verified before it is read. It produces the daily marks against a **SPY buy-and-hold baseline**
(same cash into SPY at the start day's close), realized vol, Sharpe with its n and a provisional label,
max drawdown, orders per day against the 200 cap, the rejection log by rule, and modelled fees against
the broker's cash. A day with no account mark is left out, never carried; a day with no SPY close is
listed as missing, never interpolated.

```bash
tyche performance report --journal journal/events.jsonl --feed desk-site/web/data/state.json \
  --prices "data/prices.csv" --out docs/performance/$(date +%F)-metrics.md
```

From a public checkout without the live journal, the sanitized run bundles under this folder are the
inputs: `--journal docs/performance/<newest run>/journal/events.jsonl --skip-verify` (the redaction breaks
the hash chain by design) and `--prices "docs/performance/*/data/prices.csv"`. SPY closes come from
whichever price file covers the day; `tyche fetch US.SPY` refreshes `data/prices.csv` on a machine with
the moomoo CLI.
