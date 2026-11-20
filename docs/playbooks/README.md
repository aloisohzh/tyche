# Playbooks

One setup per file (`PB-001-*.md`). A playbook is the trading thesis a judge can read in one page.
**Pre-register before trading**: freeze the rules, record a hash, label validation status honestly.

Status of the current book: **no setup is validated**. Fortuna's gauntlet rejected every setup it
tested (see [validation/](../validation/)). tyche's window setups are small, event-driven, and
explicitly labeled unvalidated. The ETF rotation is low-vol **ballast**, not an edge claim.

## Required sections (see [_TEMPLATE.md](_TEMPLATE.md))

Thesis · Edge (why it should work, and why it might not) · Universe/liquidity filter · Entry trigger ·
**Invalidation** (the condition that kills the trade/strategy) · Sizing (risk unit, caps) · Exit
(target, stop, time) · Regime fit · Fees/slippage note · Validation status · Evidence links.

## Window playbooks

One row per playbook id, and an id is claimed once and kept forever (L-029). `planned` rows are
placeholders with no file and no trade behind them; the PRD is the register for those.

| id | Setup | Status | Note |
|---|---|---|---|
| PB-001 | ETF rotation ballast | **live** | rules `4105d7a680a3` (reconciled 2026-11-20; see the playbook's freeze history for the mis-recorded `569eb2c341e0` and the two unregistered rules changes); low-vol, regime-aware; beta not alpha |
| PB-002 | Event drift (FOMC minutes / PCE) | planned | defined-risk, small, time exit; needs pre-registration before any trade |
| PB-003 | First/last-hour liquidity | planned | intraday, limit orders, flat by close |
| PB-004 | Intraday momentum scalp | **live** | the deterministic breakout lane in `config/scalp.yaml`; no playbook file yet, so its rules are only written down in config. This id was previously double-listed as "sector rotation heat" - corrected 2026-11-20, closing L-029 |
| PB-005 | Defined-risk option vertical | parked | **conflicts with the instrument rules:** a vertical is a spread, and desk/auditor policy allows standard single-leg long calls and puts only. Do not trade without an ADR |
| PB-006 | Sector rotation heat | planned | relative-strength sleeve; renumbered from the PB-004 collision in L-029 |

Write a playbook only when you intend to trade it this window. Do not scaffold all five for show.