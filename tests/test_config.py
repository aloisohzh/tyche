from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from tyche.config import (
    PLAYBOOK_LANES,
    AppConfig,
    RiskPolicy,
    SleeveCaps,
    StrategyConfig,
    TacticalConfig,
    load_config,
    rules_path_for,
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
    assert config.enabled_strategies() == [config.strategy_by_id("PB-001")]  # PB-007 ships disabled
    assert config.rotation_strategies() == [config.strategy_by_id("PB-001")]
    assert config.strategy_by_id("PB-007").kind == "fib_pullback"
    with pytest.raises(KeyError):
        config.strategy_by_id("PB-999")


def test_paper_allocation_profile_preserves_risk_limits() -> None:
    config = load_config(ROOT)
    ballast = sum(strategy.allocation_cap for strategy in config.enabled_strategies())
    assert ballast == pytest.approx(0.25)
    assert config.tactical.stock_allocation_cap == pytest.approx(0.25)
    assert config.risk.max_option_premium_pct == pytest.approx(0.05)
    # 2026-11-23: the tactical cap came down from 0.45 so PB-007's 0.20 fits when its switch is on.
    # 2026-11-24: the PB-003 option premium slice came down from 0.25 to 0.05 for the long-options test,
    # so yaml-enabled lanes sum to 0.55 and every switch on sums to 0.75, under the 0.95 gross cap.
    yaml_enabled_sum = ballast + config.tactical.stock_allocation_cap + config.risk.max_option_premium_pct
    assert yaml_enabled_sum == pytest.approx(0.55)
    pb007 = config.strategy_by_id("PB-007").allocation_cap
    assert yaml_enabled_sum + pb007 == pytest.approx(0.75)
    assert yaml_enabled_sum + pb007 <= config.risk.max_gross_exposure
    assert config.risk.max_gross_exposure == pytest.approx(0.95)
    assert config.risk.min_cash_weight == pytest.approx(0.05)
    assert config.risk.option_risk_per_trade_pct == pytest.approx(0.0075)
    assert config.risk.risk_per_trade_pct == pytest.approx(0.01)
    assert config.risk.daily_loss_limit_pct == pytest.approx(0.025)
    assert config.risk.soft_drawdown_pct == pytest.approx(0.04)
    assert config.risk.hard_drawdown_pct == pytest.approx(0.06)
    # PB-004 is the live lane. From 2026-11-25 its five chips are shared with the tactical lane, one
    # lane per run (tyche.leases); the scalp still never shares a ticker with the ballast universe.
    assert config.scalp.enabled
    assert set(config.scalp.symbols) <= set(config.tactical.symbols)
    assert not set(config.scalp.symbols) & set(config.universe.by_symbol())
    assert config.scalp.max_round_trips_per_day == 50
    assert TacticalConfig().execution_enabled is False  # model default stays closed
    assert not config.risk.allow_short


def test_intraday_tactical_cadence_keeps_freshness_bounds() -> None:
    config = load_config(ROOT)
    # Agent runs come 15 minutes apart and take minutes to read the broker (2026-11-25): the clocks
    # match that cadence. They still exist and are still bounded; they are no longer a 30-second daemon's.
    assert config.tactical.monitor_interval_seconds == 900
    assert config.tactical.max_quote_age_seconds == 900
    assert config.tactical.max_snapshot_age_seconds == 900
    assert config.scalp.max_quote_age_seconds == 900
    assert config.tactical.submit_window_seconds == 600
    with pytest.raises(ValidationError):
        TacticalConfig(max_quote_age_seconds=1801)
    assert not TacticalConfig().execution_enabled
    assert TacticalConfig(monitor_interval_seconds=5).monitor_interval_seconds == 5
    with pytest.raises(ValidationError):
        TacticalConfig(monitor_interval_seconds=4)
    with pytest.raises(ValidationError):
        TacticalConfig(monitor_interval_seconds=86401)


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
            lookbacks=[63, 126],
            lookback_weights=[1.0],
            sleeve_caps=CAPS,
        )


def test_lookback_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig(
            id="PB-001",
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


def test_every_id_the_code_can_emit_has_a_lane() -> None:
    """An unmapped id has no rules file and no switch, so its lane is unregistrable (L-036)."""
    literal = re.compile(r"""["'](PB-\d{3})["']""")
    stamped = {
        match.group(1)
        for path in (ROOT / "src" / "tyche").rglob("*.py")
        for match in literal.finditer(path.read_text(encoding="utf-8"))
    }
    assert stamped, "no playbook id is stamped in src: the guard would pass vacuously"
    unmapped = stamped - set(PLAYBOOK_LANES)
    assert not unmapped, f"{sorted(unmapped)} stamped onto intents but absent from PLAYBOOK_LANES"


def test_enabled_playbook_ids_reads_each_lanes_own_switch() -> None:
    """`strategy_by_id` only knows rotation configs; the other lanes would raise (L-036).

    The operator switch file (data/strategies.json) wins where it names a lane, so each expectation is
    the lane's own config unless the committed switch file overrides it (L-037).
    """
    from tyche.lanes import read_overrides

    config = load_config(ROOT)
    overrides, problem = read_overrides(ROOT)
    assert problem is None, problem

    def expected(pid: str, lane_default: bool) -> bool:
        return overrides.get(pid, lane_default)

    assert config.strategy_enabled("PB-001") is expected("PB-001", config.strategy_by_id("PB-001").enabled)
    assert config.strategy_enabled("PB-002") is expected("PB-002", config.tactical.enabled)
    assert config.strategy_enabled("PB-003") is expected(
        "PB-003", config.tactical.enabled and config.tactical.options_enabled
    )
    assert config.strategy_enabled("PB-004") is expected("PB-004", config.scalp.enabled)
    enabled = config.enabled_playbook_ids()
    assert [pid for pid in PLAYBOOK_LANES if config.strategy_enabled(pid)] == enabled
    assert config.tactical.options_enabled is False, "options stay switch-gated; the yaml is not the switch"
    assert config.options_live is (config.tactical.enabled and config.strategy_enabled("PB-003"))


def test_unmapped_strategy_id_says_how_to_fix_it() -> None:
    with pytest.raises(ValueError, match="PLAYBOOK_LANES"):
        rules_path_for(ROOT, "PB-999")
