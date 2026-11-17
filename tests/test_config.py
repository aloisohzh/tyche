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
    assert config.universe.min_market_cap_usd == 500_000_000.0
    assert config.risk.allow_short is False
    assert config.risk.min_price == 1.00
    assert config.risk.max_positions == 100
    assert "SIM-DEMO-US" in config.risk.account_allowlist
    assert config.strategy.top_n == 4


def test_account_allowlist_merges_env_ids(monkeypatch) -> None:
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "9000001, 9000002")
    config = load_config(ROOT)
    assert "9000001" in config.risk.account_allowlist
    assert "9000002" in config.risk.account_allowlist
    assert "SIM-DEMO-US" in config.risk.account_allowlist


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
