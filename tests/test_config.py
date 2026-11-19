from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tyche.config import (
    AppConfig,
    RiskPolicy,
    SleeveCaps,
    StrategyConfig,
    TacticalConfig,
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
    assert config.strategy_by_id("PB-001").top_n == 4
    assert config.strategy_by_id("PB-001").enabled is True
    assert config.enabled_strategies() == config.strategies
    with pytest.raises(KeyError):
        config.strategy_by_id("PB-999")


def test_paper_allocation_profile_preserves_risk_limits() -> None:
    config = load_config(ROOT)
    ballast = sum(strategy.allocation_cap for strategy in config.enabled_strategies())
    assert ballast == pytest.approx(0.25)
    assert config.tactical.stock_allocation_cap == pytest.approx(0.45)
    assert config.risk.max_option_premium_pct == pytest.approx(0.25)
    assert ballast + config.tactical.stock_allocation_cap + config.risk.max_option_premium_pct == pytest.approx(0.95)
    assert config.risk.max_gross_exposure == pytest.approx(0.95)
    assert config.risk.min_cash_weight == pytest.approx(0.05)
    assert config.risk.option_risk_per_trade_pct == pytest.approx(0.0075)
    assert config.risk.risk_per_trade_pct == pytest.approx(0.01)
    assert config.risk.daily_loss_limit_pct == pytest.approx(0.025)
    assert config.risk.soft_drawdown_pct == pytest.approx(0.04)
    assert config.risk.hard_drawdown_pct == pytest.approx(0.06)
    assert config.tactical.enabled and config.tactical.options_enabled
    assert not config.tactical.execution_enabled
    assert not config.risk.allow_short


def test_hourly_tactical_cadence_keeps_freshness_and_default_gate() -> None:
    config = load_config(ROOT)
    assert config.tactical.monitor_interval_seconds == 3600
    assert config.tactical.max_quote_age_seconds == 60
    assert config.tactical.max_snapshot_age_seconds == 120
    assert not TacticalConfig().execution_enabled
    with pytest.raises(ValidationError):
        TacticalConfig(monitor_interval_seconds=3601)


def test_option_allocation_ceiling_is_bounded() -> None:
    assert RiskPolicy(max_option_premium_pct=0.25).max_option_premium_pct == 0.25
    with pytest.raises(ValidationError):
        RiskPolicy(max_option_premium_pct=0.2501)


def test_account_allowlist_merges_env_ids(monkeypatch) -> None:
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "9000001, 9000002")
    config = load_config(ROOT)
    assert "9000001" in config.risk.account_allowlist
    assert "9000002" in config.risk.account_allowlist
    assert "SIM-DEMO-US" in config.risk.account_allowlist


def test_lookback_weights_must_match() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig(
            id="PB-001",
            playbook="docs/playbooks/PB-001-etf-rotation-ballast.md",
            lookbacks=[63, 126],
            lookback_weights=[1.0],
            sleeve_caps=CAPS,
        )


def test_lookback_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig(
            id="PB-001",
            playbook="docs/playbooks/PB-001-etf-rotation-ballast.md",
            lookbacks=[63, 126],
            lookback_weights=[0.5, 0.2],
            sleeve_caps=CAPS,
        )


def test_duplicate_strategy_ids_rejected() -> None:
    config = load_config(ROOT)
    payload = config.model_dump()
    payload["strategies"].append(payload["strategies"][0])
    with pytest.raises(ValidationError, match="duplicate strategy ids"):
        AppConfig.model_validate({**payload, "root": ROOT})


def test_strategy_filename_must_match_id(tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "strategies"
    config_dir.mkdir(parents=True)
    (config_dir / "pb-002.yaml").write_bytes(
        (ROOT / "config" / "strategies" / "pb-001.yaml").read_bytes()
    )
    (tmp_path / "config" / "risk.yaml").write_bytes(
        (ROOT / "config" / "risk.yaml").read_bytes()
    )
    (tmp_path / "config" / "universe.yaml").write_bytes(
        (ROOT / "config" / "universe.yaml").read_bytes()
    )
    with pytest.raises(ValueError, match="does not match id"):
        load_config(tmp_path)


def test_shorting_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskPolicy(allow_short=True)


def test_drawdown_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        RiskPolicy(soft_drawdown_pct=0.08, hard_drawdown_pct=0.06)
