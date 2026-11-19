from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tyche.config import load_config
from tyche.models import OrderIntent, Side
from tyche.strategies.rotation import (
    _cap_sleeves,
    detect_regime,
    fit_turnover_budget,
    momentum_score,
    rotation_targets,
)

ROOT = Path(__file__).resolve().parents[1]


def make_series(daily_drift: float, daily_vol: float, seed: int, days: int = 500) -> pd.Series:
    rng = np.random.default_rng(seed)
    returns = rng.normal(daily_drift, daily_vol, days)
    prices = 100.0 * np.cumprod(1.0 + returns)
    index = pd.bdate_range("2024-01-01", periods=days)
    return pd.Series(prices, index=index)


def base_histories() -> dict[str, pd.Series]:
    specs = {
        "US.SPY": (0.0006, 0.008, 1),
        "US.QQQ": (0.0008, 0.012, 2),
        "US.IWM": (0.0004, 0.012, 3),
        "US.EFA": (0.0003, 0.010, 4),
        "US.EEM": (0.0002, 0.014, 5),
        "US.TLT": (-0.0001, 0.008, 6),
        "US.IEF": (0.00005, 0.004, 7),
        "US.GLD": (0.0003, 0.008, 8),
        "US.DBC": (0.0001, 0.012, 9),
        "US.VNQ": (0.0002, 0.010, 10),
        "US.HYG": (0.0003, 0.004, 11),
    }
    return {symbol: make_series(drift, vol, seed) for symbol, (drift, vol, seed) in specs.items()}


def test_momentum_uses_skip_window() -> None:
    prices = pd.Series(np.linspace(100, 200, 300), index=pd.bdate_range("2024-01-01", periods=300))
    score = momentum_score(prices, [63, 126], [0.5, 0.5], skip_days=5)
    assert score > 0


def test_risk_on_regime_from_trending_market() -> None:
    config = load_config(ROOT)
    histories = base_histories()
    regime, checks = detect_regime(histories, config.strategy_by_id("PB-001").regime)
    assert regime.value == "risk_on"
    assert checks["equity_trend"]
    assert checks["golden_cross"]


def test_target_weights_respect_constraints() -> None:
    config = load_config(ROOT)
    histories = base_histories()
    result = rotation_targets(histories, config, config.strategy_by_id("PB-001"))

    invested = sum(weight for symbol, weight in result.targets.items() if symbol != "CASH")
    assert invested <= 1.0 - config.strategy_by_id("PB-001").min_cash_weight + 1e-6
    cap = config.strategy_by_id("PB-001").allocation_cap
    assert invested <= cap + 1e-6
    assert invested >= cap - 1e-6  # bullish fixture uses its ballast budget
    assert result.targets["CASH"] >= 1 - cap - 1e-6
    caps = {asset.symbol: asset.max_weight for asset in config.universe.assets}
    assert all(
        weight <= caps[symbol] + 1e-6
        for symbol, weight in result.targets.items()
        if symbol != "CASH"
    )
    assert len([row for row in result.signals.values() if row.selected]) <= config.strategy_by_id("PB-001").top_n
    assert result.vol_scale <= 1.0

    sleeves = config.universe.sleeve_by_symbol()
    for sleeve, cap in config.strategy_by_id("PB-001").sleeve_caps[result.regime.value].as_dict().items():
        sleeve_weight = sum(
            weight
            for symbol, weight in result.targets.items()
            if symbol != "CASH" and sleeves.get(symbol) == sleeve
        )
        assert sleeve_weight <= cap + 1e-6


def trend_series(
    start: float, end: float, seed: int, days: int = 500, noise: float = 0.0015
) -> pd.Series:
    rng = np.random.default_rng(seed)
    path = start * (end / start) ** np.linspace(0.0, 1.0, days)
    path = path * np.exp(np.cumsum(rng.normal(0.0, noise, days)))
    return pd.Series(path, index=pd.bdate_range("2024-01-01", periods=days))


def test_risk_off_regime_caps_equity() -> None:
    config = load_config(ROOT)
    histories = {
        "US.SPY": trend_series(100, 65, 21, noise=0.0008),
        "US.QQQ": trend_series(100, 60, 22),
        "US.IWM": trend_series(100, 55, 23),
        "US.EFA": trend_series(100, 70, 24),
        "US.EEM": trend_series(100, 60, 25),
        "US.TLT": trend_series(100, 120, 26),
        "US.IEF": trend_series(100, 110, 27, noise=0.0003),
        "US.GLD": trend_series(100, 110, 28),
        "US.DBC": trend_series(100, 90, 29),
        "US.VNQ": trend_series(100, 65, 30),
        "US.HYG": trend_series(100, 80, 31, noise=0.0003),
    }
    result = rotation_targets(histories, config, config.strategy_by_id("PB-001"))
    assert result.regime.value == "risk_off"
    sleeves = config.universe.sleeve_by_symbol()
    equity_weight = sum(
        weight
        for symbol, weight in result.targets.items()
        if symbol != "CASH" and sleeves.get(symbol) == "equity"
    )
    assert equity_weight <= config.strategy_by_id("PB-001").sleeve_caps["risk_off"].equity + 1e-6


def test_sleeve_cap_releases_capital_to_open_sleeves() -> None:
    config = load_config(ROOT)
    weights = {"US.SPY": 0.18, "US.QQQ": 0.17, "US.EFA": 0.20, "US.HYG": 0.40}
    capped = _cap_sleeves(
        weights,
        config.universe,
        config.strategy_by_id("PB-001").sleeve_caps["risk_on"].as_dict(),
    )
    sleeves = config.universe.sleeve_by_symbol()
    credit = sum(weight for symbol, weight in capped.items() if sleeves[symbol] == "credit")
    assert credit == pytest.approx(0.15, abs=1e-6)
    assert sum(capped.values()) == pytest.approx(0.95, abs=1e-6)


def test_sleeve_redistribution_preserves_vol_scaled_total() -> None:
    config = load_config(ROOT)
    weights = {"US.SPY": 0.144, "US.QQQ": 0.136, "US.EFA": 0.16, "US.HYG": 0.32}
    capped = _cap_sleeves(
        weights,
        config.universe,
        config.strategy_by_id("PB-001").sleeve_caps["risk_on"].as_dict(),
    )
    assert sum(capped.values()) == pytest.approx(sum(weights.values()), abs=1e-6)


def test_insufficient_history_falls_back_to_cash() -> None:
    config = load_config(ROOT)
    histories = {
        asset.symbol: pd.Series([100.0] * 20, index=pd.bdate_range("2026-01-01", periods=20))
        for asset in config.universe.assets
    }
    result = rotation_targets(histories, config, config.strategy_by_id("PB-001"))
    assert result.targets == {"CASH": 1.0}
    assert result.notes


@pytest.mark.parametrize("symbol", ["US.SPY", "US.HYG"])
def test_signal_present_for_full_history(symbol: str) -> None:
    config = load_config(ROOT)
    result = rotation_targets(base_histories(), config, config.strategy_by_id("PB-001"))
    assert symbol in result.signals


def test_turnover_budget_scales_buys_and_spares_sells() -> None:
    intents = [
        OrderIntent(symbol="US.SPY", side=Side.BUY, quantity=600, limit_price=100.0, reason="test"),
        OrderIntent(symbol="US.QQQ", side=Side.SELL, quantity=10, limit_price=100.0, reason="test"),
    ]
    fitted = fit_turnover_budget(intents, nav=100_000.0, max_turnover_pct=0.5)
    assert fitted[0].quantity == 500
    assert fitted[1].quantity == 10
