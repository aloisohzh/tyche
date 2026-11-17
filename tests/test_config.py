from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tyche.config import (
    RiskPolicy,
    SleeveCaps,
    StrategyConfig,
    load_config,
)

ROOT = Path(__file__).resolve().parents[1]
CAPS = {
    key: SleeveCaps(equity=0.8, defensive=0.5, real_asset=0.3, credit=0.2)
    for key in ("risk_on", "neutral", "risk_off")
}


def test_load_repo_config() -> None:
    config = load_config(ROOT)
    assert len(config.universe.assets) == 11
    assert config.universe.cash_symbol == "CASH"
    assert config.risk.allow_short is False
    assert config.strategy.top_n == 4


def test_lookback_weights_must_match() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig(
            lookbacks=[63, 126],
            lookback_weights=[1.0],
            sleeve_caps=CAPS,
        )


def test_lookback_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig(
            lookbacks=[63, 126],
            lookback_weights=[0.5, 0.2],
            sleeve_caps=CAPS,
        )


def test_shorting_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskPolicy(allow_short=True)


def test_drawdown_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        RiskPolicy(soft_drawdown_pct=0.08, hard_drawdown_pct=0.06)
