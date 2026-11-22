# Playbooks

One setup per file (`PB-001-*.md`). A playbook is the trading thesis a judge can read in one page, and
the unit an agent loads when it needs to know what the desk actually believes. **Pre-register before
trading**: freeze the rules, record a hash, label validation status honestly.

Status of the current book: **no setup is validated**. Fortuna's gauntlet rejected every setup it
tested (see [validation/](../docs/validation/)). tyche's window setups are small, event-driven, and
explicitly labeled unvalidated. The ETF rotation is low-vol **ballast**, not an edge claim.

## This directory is the strategy library, not part of the kernel

`src/tyche/` never imports anything here. The three artifacts a playbook id links stay separate
(ADR 0014): the thesis (this folder), the rules (`config/strategies/<id>.yaml` for a rotation lane;
whatever `PLAYBOOK_LANES` in `src/tyche/config.py` names for the others) and the code
(`src/tyche/strategies/`). Nothing in this folder is inside a freeze hash - moving a thesis must never
re-register a strategy (L-037). An agent that needs the current roster reads [INDEX.yaml](INDEX.yaml).

## Classification vocabulary

Every playbook carries YAML front matter with seven **independent** dimensions, so a request like
"swing options trades" can be answered without reading prose. The vocabulary is fixed; a new value is
a decision, not a typo.

| Dimension | Values |
|---|---|
| Holding period | Scalping · Intraday · Swing · Position · Long-term |
| Strategy type | Trend following · Mean reversion · Momentum · Breakout · Arbitrage · Market making · Event-driven · Statistical/quantitative |
| Execution style | Manual · Semi-automated · Fully automated |
| Instrument | Stocks · Options |
| Regime fit | Bull · Bear · Range · Any (a list: a setup may suit more than one) |
| Direction | Long · Long puts · Both |
| Validation | Unvalidated · Sanity-checked · Validated |

The desk may hold long stocks/ETFs and single-leg long calls or puts only (agent-rules.md), so
"bearish" can only mean cash or `Long puts`; there is no short direction to tag. `Regime fit` says where
the setup is *meant* to run, not where it is proven: `validation` carries that, and must match the
playbook body. Rows without a file carry the same tags in [INDEX.yaml](INDEX.yaml) under `tags:`.

Arbitrage and market making are in the vocabulary but have no live setup, and both are constrained by
the fill assumptions in [agent-rules.md](../docs/agent-rules.md): no strategy may assume liquidity it
has not observed.

## Required sections (see [_TEMPLATE.md](_TEMPLATE.md))

Thesis · Edge (why it should work, and why it might not) · Universe/liquidity filter · Entry trigger ·
**Invalidation** (the condition that kills the trade/strategy) · Sizing (risk unit, caps) · Exit
(target, stop, time) · Regime fit · Fees/slippage note · Validation status · Evidence links.

## Window playbooks

One row per playbook id, and an id is claimed once and kept forever (L-029). [INDEX.yaml](INDEX.yaml)
is the machine-readable roster; this table is the human-facing copy of it, and
`test_playbook_ids_are_claimed_once` reads both. `planned` rows are placeholders with no file and no
trade behind them.

| id | Setup | Status | Regime fit | Direction | Note |
|---|---|---|---|---|---|
| PB-001 | [ETF rotation ballast](PB-001-etf-rotation-ballast.md) | **live** | Any | Long | rules `819ad06e35f0` (see the playbook's freeze history for the mis-recorded `569eb2c341e0` and the two unregistered 2026-11-19 rules changes); low-vol, regime-aware; beta not alpha |
| PB-002 | Event drift (FOMC minutes / PCE) | planned | Bull, Range | Long | defined-risk, small, time exit; needs a thesis file before it can be called live. `tactical.py` already stamps this id on stock intents from the **enabled** `config/tactical.yaml`, which freezes PB-002 and PB-003 together at `b6bc571033ac` |
| PB-003 | First/last-hour liquidity | planned | Range | Both | intraday, limit orders, flat by close. `tactical.py` stamps this id on option intents, and `options_enabled: false` today |
| PB-004 | [Intraday momentum scalp](PB-004-intraday-momentum-scalp.md) | **live** | Bull | Long | the deterministic breakout lane in `config/scalp.yaml`; rules `72077d5d4808`, the lane's first computable hash (L-036 fixed 2026-11-20). Submission still gated by the executor's rollout hold |
| PB-005 | Defined-risk option vertical | parked | Any | Both | **conflicts with the instrument rules:** a vertical is a spread, and desk/auditor policy allows standard single-leg long calls and puts only. Do not trade without an ADR |
| PB-006 | Sector rotation heat | planned | Bull | Long | relative-strength sleeve; renumbered from the PB-004 collision in L-029 |
| PB-007 | [Fib 50% pullback](PB-007-fib50-pullback.md) | **live** (disabled) | Bull, Range | Long | swing mean reversion with an SMA50/200 regime filter on daily bars; `kind: fib_pullback` in `config/strategies/pb-007.yaml`, plans through the lifecycle lane (ADR 0017); ships `enabled: false`, first run is a plumbing test |

Write a playbook only when you intend to trade it this window. Do not scaffold all seven for show.
