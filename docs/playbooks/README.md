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

## Planned window playbooks

| id | Setup | Note |
|---|---|---|
| PB-001 | ETF rotation ballast | v0.1 reference; low-vol, regime-aware; beta not alpha |
| PB-002 | Event drift (FOMC minutes / PCE) | defined-risk, small, time exit; pre-register |
| PB-003 | First/last-hour liquidity | intraday, limit orders, flat by close |
| PB-004 | Sector rotation heat | relative-strength sleeve |
| PB-005 | Defined-risk option vertical | leg group; flatten before expiry close |

Write a playbook only when you intend to trade it this window. Do not scaffold all five for show.