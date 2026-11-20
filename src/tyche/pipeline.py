"""Per-trade pipeline contract derivation (docs/dashboard.md).

Every field is derived from kernel outputs, pinned config or the price input —
nothing is fabricated. Expected edge stays None until a playbook has a
validated expectancy model; ballast is beta, not an edge claim.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from tyche.config import AppConfig, Sleeve, StrategyConfig, rules_path_for
from tyche.models import (
    AccountSnapshot,
    EdgeEstimate,
    InputsRef,
    OrderIntent,
    OrderPipeline,
    Outlook,
    PlanPipeline,
    Regime,
    RiskVerdict,
    Side,
    Sizing,
)

OUTLOOK_BY_REGIME = {
    Regime.RISK_ON: Outlook.BULLISH,
    Regime.NEUTRAL: Outlook.RANGE,
    Regime.RISK_OFF: Outlook.BEARISH,
}

ACT_WAIT_RULE = (
    "new non-defensive entries wait at low conviction (<=1 of 4 regime checks); "
    "sells and defensive entries always act — the gate never blocks de-risking"
)


def rules_hash(config_root: Path, strategy_id: str) -> str:
    """Per-strategy freeze identifier (ADR 0014): that lane's rules yaml + universe.

    Editing another strategy's file can never invalidate this hash; a universe
    edit re-freezes every strategy and must be journaled. The rules file is
    resolved through PLAYBOOK_LANES, because only the rotation lane follows the
    config/strategies/<id>.yaml convention (L-036).
    """
    digest = hashlib.sha256()
    paths = (
        rules_path_for(config_root, strategy_id),
        config_root / "config" / "universe.yaml",
    )
    for path in paths:
        # Git checkout newline conversion must not change approval identity.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:12]


def conviction_tier(score: int, total: int) -> str:
    if score >= total:
        return "high"
    if score == total - 1:
        return "medium-high"
    if score == total - 2:
        return "medium"
    return "low"


def act_wait(
    side: Side, sleeve: Sleeve | None, conviction: str, held: bool
) -> str:
    if side == Side.SELL or sleeve == "defensive" or held:
        return "act"
    return "wait" if conviction == "low" else "act"


def build_plan_pipeline(
    config_root: Path,
    strategy: StrategyConfig,
    regime: Regime,
    regime_checks: dict[str, bool],
    prices_path: Path,
    brief: str | None,
) -> PlanPipeline:
    score = sum(1 for passed in regime_checks.values() if passed)
    total = len(regime_checks)
    rh = rules_hash(config_root, strategy.id)
    return PlanPipeline(
        thesis_ref=f"{strategy.id} · rules {rh}",
        rules_hash=rh,
        inputs_ref=InputsRef(
            prices_path=str(prices_path),
            prices_sha256=hashlib.sha256(prices_path.read_bytes()).hexdigest(),
            brief=brief,
        ),
        outlook=OUTLOOK_BY_REGIME[regime],
        conviction=conviction_tier(score, total),
        checks_score=score,
        checks_total=total,
        act_wait_rule=ACT_WAIT_RULE,
    )


def build_order_pipeline(
    intent: OrderIntent,
    verdict: RiskVerdict,
    snapshot: AccountSnapshot,
    config: AppConfig,
    strategy: StrategyConfig,
    regime: Regime,
    conviction: str,
) -> OrderPipeline:
    symbol = intent.symbol
    asset = config.universe.by_symbol().get(symbol)
    sleeve = asset.sleeve if asset else None
    held = snapshot.position(symbol) is not None
    effective = min(intent.quantity, verdict.adjusted_quantity) if verdict.allowed else 0
    notional = effective * intent.limit_price * intent.multiplier
    sleeve_cap = (
        strategy.sleeve_caps[regime.value].as_dict().get(sleeve)
        if sleeve is not None
        else None
    )
    min_momentum = strategy.min_momentum
    return OrderPipeline(
        vehicle="etf",
        vehicle_rationale=(
            f"{sleeve or 'unassigned'} sleeve ETF; {intent.reason}"
        ),
        expected_edge=EdgeEstimate(
            label="provisional — ballast beta, no validated expectancy"
        ),
        invalidation=(
            f"rotation target drops to 0 if {symbol} momentum <= {min_momentum:g} "
            f"or regime flips to risk_off (<2 of 4 checks); exit at next rebalance — "
            f"no broker-native stop on sim"
        ),
        protection_type="rebalance",
        roll_plan=None,
        sizing=Sizing(
            quantity=intent.quantity,
            effective_quantity=effective,
            limit_price=intent.limit_price,
            notional=notional,
            nav_pct=notional / snapshot.nav if snapshot.nav > 0 else 0.0,
            single_asset_cap_pct=config.risk.max_position_weight,
            sleeve_cap_pct=sleeve_cap,
        ),
        action=act_wait(intent.side, sleeve, conviction, held),
    )