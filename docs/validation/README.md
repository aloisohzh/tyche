# Validation

## Convention (window-sized)

A setup is **pre-registered** before it trades: freeze rules, record a hash, write the playbook, label
validation status. In a ~7-session window we cannot run fortuna's full gauntlet (500 nulls, rotated
matched null, 30-trade checkpoints). So:

- Label every window setup **unvalidated** or **sanity-checked** — never "validated".
- Size small; define invalidation and a time exit; record every rejection/veto.
- A cheap historical sanity check on equities (MCP kline) is allowed if time permits; options history
  is unavailable via MCP.
- A re-tuned rule is a **new hypothesis** on data it has already seen — new hash, new playbook.

## NO-GO ledger (carried from fortuna, reference only)

| Setup | Verdict | Why |
|---|---|---|
| pead_jump | FAIL | +0.130R but random same-regime +0.103R (p 0.37); drift ≠ edge |
| RSI-2 | NO-GO | +0.018R, bootstrap LB −0.016, p 0.024 vs 0.0125, 3/5 folds |
| gap fade | NO-GO | −0.056R, worse than random |
| low-vol selection | NO-GO | Sharpe 0.87 vs universe 1.02, p 0.859 |

Lesson: governance worked, edge did not. Do not rebuild the gauntlet this window; build the discipline
and the evidence, and validate properly after the competition.

## Parked (post-window)

Full gauntlet: net-expectancy bootstrap LB > 0 · rotated matched null p < family alpha · ≥4/5 folds
incl. 2 recent · survivorship/QFQ caveats. See fortuna `docs/BACKTEST_RSI2_GAPFADE.md`.