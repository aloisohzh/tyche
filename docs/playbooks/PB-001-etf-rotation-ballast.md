# PB-001 — Regime-aware ETF rotation (ballast)

- **Status:** trading (ballast)
- **Rules hash:** `569eb2c341e0` (sha256 of config/strategies/pb-001.yaml + config/universe.yaml bytes, first 12; re-frozen 2026-11-19)
- **Freeze history:** `946b3ef31a3d` frozen 2026-11-18 against config/strategy.yaml. ADR 0014 migration (2026-11-19) moved the file to config/strategies/pb-001.yaml and added id/enabled/playbook metadata; every trading parameter is byte-identical. New hash, same rules — not a re-tune.
- **Validation:** unvalidated — beta exposure, not an edge claim; Fortuna's gauntlet rejected every setup it tested
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
regime — the value is the risk path, not the return.

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
daily loss 2.5% blocks buys. No broker-native stop on sim — protection is rebalance +
risk kernel (protection_type=rebalance), synthetic monitor is P2.

## Sizing
Risk unit = vol-targeted weight; single-asset cap 40% (desk target ≤38%), per-order
notional ≤30% NAV, sleeve caps per regime, daily turnover ≤50%, ≤6 orders/day.

## Exit
Rebalance-to-target (drift band 20%); de-risking sells always allowed, even halted.
Time exit: none (rolling ballast). Final-day flatten per competition rules at EOD.

## Regime fit
All regimes — the sleeve caps are the regime expression (risk_off: equity ≤20%,
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