---
id: PB-001
title: Regime-aware ETF rotation (ballast)
# The four classification dimensions are independent (see playbook/README.md). Only playbook/INDEX.yaml
# and this block describe a playbook; nothing here is restated in an agent prompt (L-033).
classification:
  holding_period: Position          # rebalances on drift bands, multi-session horizon
  strategy_type: Momentum           # cross-asset momentum, inverse-vol weighted
  execution_style: Semi-automated   # deterministic kernel plans; entries need operator approval
  instruments: [Stocks]             # broad ETFs; no options in this sleeve
  regime_fit: [Any]                 # the regime gate itself chooses: risk_off rotates to cash
  direction: Long                   # long ETFs and cash only
  validation: Sanity-checked        # LEAN smoke 2026-11-19: positive return, no edge vs cash
---

# PB-001 - Regime-aware ETF rotation (ballast)

- **Status:** trading (ballast)
- **Rules hash:** `819ad06e35f0` (sha256 of `config/strategies/pb-001.yaml` + `config/universe.yaml`, CRLF normalized, first 12). Declared here, computed by the kernel, asserted equal in `tests/test_docs_consistency.py`.
- **Freeze history:**
  - `946b3ef31a3d` - frozen 2026-11-18 against `config/strategy.yaml` (pre-ADR 0014 layout).
  - `569eb2c341e0` - recorded in the ADR 0014 split as the post-migration hash and carried here until 2026-11-20. **It never matched the committed files.** Recomputing at `010cd9b` gives `6d991165fa64`, so the re-freeze was mis-recorded on arrival rather than drifted later (L-030).
  - `6d991165fa64` - actual hash at `010cd9b` (2026-11-19). File moved and `id`/`enabled`/`playbook` metadata added; trading parameters unchanged, so this one is genuinely "new hash, same rules".
  - `7799974f9fd0` - `43b85ca` (2026-11-19, ADR 0016). **A real rules change:** `initial_stop_pct: 0.08` added.
  - `4105d7a680a3` - `7f61baf` (2026-11-19). **A real rules change:** `allocation_cap: 0.25`, cutting the ballast ceiling to a quarter of NAV.
  - `becd112bcac8` - 2026-11-20, playbook relocations. **Not a rules change:** the `playbook:` pointer moved from `docs/playbooks/` to `playbook/`; every trading parameter is byte-identical. The pointer was inside the frozen bytes, so a doc move re-hashed the strategy - the defect corrected by the next entry (L-037).
  - `819ad06e35f0` - 2026-11-20. **Not a rules change:** the `playbook:` pointer left the hashed file altogether, and the id now maps to this document through `playbook/INDEX.yaml`, while `PLAYBOOK_LANES` resolves each lane's real rules file (L-036, L-037). Trading parameters are byte-identical to `becd112bcac8`; only the two comment lines that named the doc changed. From here a documentation move can never re-register a strategy, and `test_no_freeze_source_names_a_document` fails the build if a path creeps back in.
- **Registration gap:** the two 2026-11-19 changes altered sizing and stop rules and were never re-registered in the journal, and the chain's newest row for this lane still reads the mis-recorded `569eb2c341e0` (2026-11-18). The producer that closes the gap landed 2026-11-21: `tyche rules-freeze` (`src/tyche/freeze.py`) recomputes this lane from `config/strategies/pb-001.yaml` + `config/universe.yaml`, reads the previous hash **only** out of the journal, refuses to register anything this document does not declare, and appends `rules.refrozen` when given `--record --reason` (L-035). It cannot retro-date the entries above - those stay reconstructed from git blobs. With the operator's approval it ran on 2026-11-21 and appended the row this lane never had: `rules.refrozen` `569eb2c341e0` -> `819ad06e35f0`, journal event `5f1b2b82b48a`, with the reason naming which of the changes above were real rules edits and which were layout. **2026-11-22 correction (L-056):** that row went into the laptop drill copy of the journal, not the Drive ledger the desk reads; the ledger holds no freeze row for this lane until the 2026-11-24 runbook run ([freeze-on-ledger](../docs/runbooks/freeze-on-ledger.md)). The CI assertion remains what guarantees the declared hash matches the bytes; from now on, a parameter change without a journaled re-freeze is drift the desk will see.
- **Validation:** unvalidated - beta exposure, not an edge claim; Fortuna's gauntlet rejected every setup it tested
- **Sleeve:** ballast
- **Env:** paper (competition)

## Thesis
Diversified asset sleeves trend and mean-revert at different horizons; a regime gate
(risk_on / neutral / risk_off) plus cross-asset momentum keeps capital in the strongest
risk-adjusted sleeves while a volatility target and cash floor cap the drawdown path.
This is systematic beta harvesting, not alpha.

## Edge
Why it should work after fees: momentum + inverse-vol weighting is a documented risk-premium
harvest; low turnover (drift band 20%, min trade $500) keeps modeled fees small.
Why it might not: momentum crashes on regime whipsaws; 7-session competition n is far too
small to validate anything. Drift ≠ edge: no claim of beating a random entry in the same
regime - the value is the risk path, not the return.

## Universe / liquidity filter
config/universe.yaml: 11 broad ETFs (SPY/QQQ/IWM/EFA/EEM/TLT/IEF/GLD/DBC/VNQ/HYG),
min market cap $500M, min price $1.00; all large liquid funds.

## Entry trigger
Deterministic kernel (`tyche plan`): weighted 63/126/252-day momentum (0.5/0.3/0.2, 5-day
skip) > min_momentum, top 4 by momentum/vol score, inverse-vol weights scaled to 10%
portfolio vol, regime sleeve caps, 5% cash floor. Limit = last ±0.1%. Session: RTH only.

## Invalidation
Per position: rotation target drops to 0 when the symbol's momentum ≤ 0 or the regime
flips to risk_off (<2 of 4 checks: SPY>200-SMA, golden cross, vol calm, HYG/IEF credit
trend); exit at next rebalance. Strategy-level: hard drawdown 6% blocks all buys;
daily loss 2.5% blocks buys. No broker-native stop on sim - protection is rebalance +
risk kernel (protection_type=rebalance), synthetic monitor is P2.

## Sizing
Risk unit = vol-targeted weight; single-asset cap 40% (desk target ≤38%), per-order
notional ≤30% NAV, sleeve caps per regime, daily turnover ≤50%, ≤6 orders/day.

## Exit
The base strategy exits by rebalance-to-target (drift band 20%); a halt blocks
new exposure, not protective sells, although broker/account checks and the
competition order ceiling still apply. The rolling-ballast signal has no time
exit of its own; final-day flattening is an intention, not a guaranteed order.

Unattended execution additionally requires an approved **complete lifecycle**:
entry bounds and quantity, stop and its basis (last price or completed daily
close), profit target, entry expiry, explicit holding deadline, and sourced
thesis-invalidation conditions. Review the thesis and relevant material events
each hour and immediately before reserving an entry. Missing/stale/uncertain
research blocks entries without disabling already-approved protective exits.
Changing the contract requires a new preview and approval; a positive research
refresh cannot silently rearm a previously invalidated lifecycle.

The [hourly lifecycle workflow](../docs/runbooks/protection-monitor.md) is deployed
in observe-only mode as of 2026-11-19; automatic orders remain unarmed pending
storage/risk integration checks and reviewed adoption approvals. Neither the
sizing stop nor an old research level
constitutes that approval. Synthetic hourly checks do not guarantee stop prices
or liquidation at the deadline; choose deadlines within the deployed schedule.

## Regime fit
All regimes - the sleeve caps are the regime expression (risk_off: equity ≤20%,
defensive ≤60%, credit 0).

## Fees/slippage note
Modeled per src/tyche/fees.py; limits accept non-fill, never chase; batch-atomic 3%
drift pre-flight rejects the whole batch on stale prices → re-plan, never override.

## Act/wait gate
New non-defensive entries wait at low conviction (≤1 of 4 regime checks); sells and
defensive entries always act. Carried per order as `pipeline.action`; enforced by
`tyche execute` and journaled as `gate.wait` on the MCP path.

## Evidence links
- Kernel: src/tyche/strategies/rotation.py, src/tyche/risk.py, src/tyche/pipeline.py
- ADRs: 0003 (risk kernel), 0004 (regime rotation), 0012 (options/protection context), 0014 (per-strategy isolation)
- Validation: docs/validation/README.md (re-tuned rule = new hypothesis, new hash)