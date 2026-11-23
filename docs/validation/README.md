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

## Tuning versus evaluation (the out-of-sample claim, stated plainly)

The competition window is the evaluation set; nothing in it is used to tune a rule that then trades in it.
The line is the rules freeze on the Drive ledger, the journal the desk actually reads (L-056):

- **Frozen 23 Nov 2026** on `/data/drive/tyche-raw/2026-11-23-operator-freeze` (41 events, verified): PB-001
  `819ad06e35f0`, PB-002/PB-003 `a1d9df1c687c` (one shared parameter file), PB-004 `72077d5d4808`, PB-007
  `e26f006da28a`. Each hash is the sha256 of the lane's parameter file plus the universe, declared in the
  playbook and asserted equal to the kernel's computation in CI (`tests/test_docs_consistency.py`).
- **After that line, a rule change is a new hypothesis**: new hash, new playbook line, `tyche rules-freeze
  --record` from a console session, PR in the same commit. The operator switches in `data/strategies.json`
  (PB-007 on, PB-004 off, 23 Nov) change which lanes may enter; they move no hash and no parameter.
- **Before that line, be honest**: PB-001 traded on 18 Nov under earlier bytes. Its hash moved `6d99` →
  `7799` → `4105` → `819a` between 19 and 21 Nov while the allocation cap was cut to 25% after the buys
  (L-030, L-035), so PB-001's first two sessions are not a clean out-of-sample test and are labelled
  sanity-checked, not validated. The three closed PB-004 scalps of 19 Nov traded under the bytes that were
  frozen on 21 Nov; the lane was switched off on 23 Nov for fit, not re-tuned.
- **What a judge can replay**: `tyche strategies --json` prints each live lane's hash; `tyche rules-freeze`
  (check mode) compares bytes, playbook and ledger and exits `1` on drift; `tyche performance report`
  renders the fee-net marks against SPY from the same journal. None of the three can be made to agree by
  editing a document.

No parameter in any lane was fitted to prices from 17 Nov onward. The reference strategy's parameters
(PB-001) predate the window and were sanity-checked on the local LEAN lane below; the others are
pre-registered hypotheses with written invalidation and a time exit, sized small, as the convention above
requires.

## Local LEAN lane (ADR 0015)

Hypotheses may also be sanity-checked on the local LEAN engine (research-only,
never a kernel input). Notes must state venue, engine version, data source and
fill/cost model. First run:
[2026-11-19 LEAN lane smoke + PB-001](2026-11-19-lean-pb001-smoke.md) — lane
PASS, hypothesis NO-GO as alpha (sanity-checked).

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