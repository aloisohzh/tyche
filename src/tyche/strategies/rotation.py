from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tyche.config import AppConfig, RegimeConfig, StrategyConfig, UniverseConfig
from tyche.models import (
    AccountSnapshot,
    OrderIntent,
    Regime,
    RotationResult,
    Side,
    SignalRow,
)

ANNUALIZATION = 252
VOL_FLOOR = 0.05


def _series(histories: dict[str, pd.Series], symbol: str) -> pd.Series | None:
    series = histories.get(symbol)
    if series is None:
        return None
    series = series.dropna().sort_index()
    return series if not series.empty else None


def realized_vol(prices: pd.Series, lookback: int) -> float:
    returns = prices.pct_change().dropna().tail(lookback)
    minimum = max(5, lookback // 4)
    if len(returns) < minimum:
        return float("nan")
    return float(returns.std(ddof=1) * math.sqrt(ANNUALIZATION))


def momentum_score(
    prices: pd.Series,
    lookbacks: list[int],
    weights: list[float],
    skip_days: int,
) -> float:
    contributions: list[float] = []
    used_weight = 0.0
    for lookback, weight in zip(lookbacks, weights):
        if len(prices) < lookback + skip_days + 1:
            continue
        end = prices.iloc[-(1 + skip_days)]
        start = prices.iloc[-(1 + skip_days + lookback)]
        if start <= 0:
            continue
        contributions.append(weight * (end / start - 1.0))
        used_weight += weight
    if used_weight == 0.0:
        return float("nan")
    return sum(contributions) / used_weight


def _sma_last(prices: pd.Series, window: int) -> float:
    if len(prices) < window:
        return float("nan")
    return float(prices.tail(window).mean())


def detect_regime(
    histories: dict[str, pd.Series], cfg: RegimeConfig
) -> tuple[Regime, dict[str, bool]]:
    checks: dict[str, bool] = {}

    spy = _series(histories, "US.SPY")
    if spy is not None and len(spy) > cfg.trend_sma:
        checks["equity_trend"] = float(spy.iloc[-1]) > _sma_last(spy, cfg.trend_sma)
        checks["golden_cross"] = _sma_last(spy, cfg.cross_fast) > _sma_last(spy, cfg.cross_slow)
    else:
        checks["equity_trend"] = False
        checks["golden_cross"] = False

    if spy is not None:
        short_vol = realized_vol(spy, cfg.vol_short)
        long_vol = realized_vol(spy, cfg.vol_long)
        calm = (
            not math.isnan(short_vol)
            and not math.isnan(long_vol)
            and long_vol > 0
            and short_vol <= long_vol * cfg.vol_ratio_limit
        )
    else:
        calm = False
    checks["vol_calm"] = calm

    hyg = _series(histories, "US.HYG")
    ief = _series(histories, "US.IEF")
    credit_up = False
    if hyg is not None and ief is not None:
        ratio = (hyg / ief).dropna()
        if len(ratio) >= cfg.credit_fast + 1:
            credit_up = float(ratio.iloc[-1]) > _sma_last(ratio, cfg.credit_fast)
    checks["credit_trend"] = credit_up

    score = sum(checks.values())
    if score >= 3:
        regime = Regime.RISK_ON
    elif score == 2:
        regime = Regime.NEUTRAL
    else:
        regime = Regime.RISK_OFF
    return regime, checks


def _portfolio_vol(histories: dict[str, pd.Series], weights: dict[str, float]) -> float:
    frame = pd.DataFrame(
        {symbol: _series(histories, symbol).pct_change() for symbol in weights}
    ).dropna()
    frame = frame.tail(126)
    if len(frame) < 20:
        return float(
            sum(
                weight * realized_vol(_series(histories, symbol), 63)
                for symbol, weight in weights.items()
            )
        )
    covariance = frame.cov().to_numpy() * ANNUALIZATION
    vector = np.array([weights[symbol] for symbol in frame.columns])
    variance = float(vector @ covariance @ vector)
    return math.sqrt(max(variance, 0.0))


def _cap_sleeves(
    weights: dict[str, float],
    universe: UniverseConfig,
    caps: dict[str, float],
) -> dict[str, float]:
    sleeves = universe.sleeve_by_symbol()
    target_total = sum(weights.values())
    for sleeve, cap in caps.items():
        symbols = [symbol for symbol in weights if sleeves.get(symbol) == sleeve]
        total = sum(weights[symbol] for symbol in symbols)
        if total > cap > 0:
            factor = cap / total
            for symbol in symbols:
                weights[symbol] *= factor

    for _ in range(10):
        released = target_total - sum(weights.values())
        if released <= 1e-9:
            break
        room: dict[str, float] = {}
        for sleeve, cap in caps.items():
            symbols = [symbol for symbol in weights if sleeves.get(symbol) == sleeve]
            if not symbols:
                continue
            room[sleeve] = max(0.0, cap - sum(weights[symbol] for symbol in symbols))
        if not room or sum(room.values()) <= 1e-9:
            break
        base = sum(
            sum(weights[symbol] for symbol in weights if sleeves.get(symbol) == sleeve)
            for sleeve in room
        )
        added = 0.0
        for sleeve, sleeve_room in room.items():
            symbols = [symbol for symbol in weights if sleeves.get(symbol) == sleeve]
            sleeve_total = sum(weights[symbol] for symbol in symbols)
            share = released * (sleeve_total / base) if base > 0 else released / len(room)
            addition = min(share, sleeve_room)
            if addition <= 0:
                continue
            for symbol in symbols:
                weights[symbol] += addition * (
                    weights[symbol] / sleeve_total if sleeve_total > 0 else 1 / len(symbols)
                )
            added += addition
        if added <= 1e-12:
            break
    return weights


def _apply_asset_caps(
    weights: dict[str, float],
    universe: UniverseConfig,
    strategy_max: float,
) -> dict[str, float]:
    sleeves = universe.sleeve_by_symbol()
    caps = {asset.symbol: min(asset.max_weight, strategy_max) for asset in universe.assets}
    for sleeve in {sleeves.get(symbol) for symbol in weights}:
        symbols = [symbol for symbol in weights if sleeves.get(symbol) == sleeve]
        for _ in range(10):
            excess = 0.0
            for symbol in symbols:
                cap = caps.get(symbol, strategy_max)
                if weights[symbol] > cap:
                    excess += weights[symbol] - cap
                    weights[symbol] = cap
            if excess <= 1e-9:
                break
            open_symbols = [
                symbol
                for symbol in symbols
                if weights[symbol] < caps.get(symbol, strategy_max) - 1e-12
            ]
            if not open_symbols:
                break
            open_total = sum(weights[symbol] for symbol in open_symbols)
            for symbol in open_symbols:
                weights[symbol] += excess * (
                    weights[symbol] / open_total if open_total > 0 else 1 / len(open_symbols)
                )
    return weights


def rotation_targets(
    histories: dict[str, pd.Series], config: AppConfig, strategy: StrategyConfig
) -> RotationResult:
    regime, checks = detect_regime(histories, strategy.regime)
    notes: list[str] = []

    required = max(strategy.lookbacks) + strategy.skip_days + 1
    signals: dict[str, SignalRow] = {}
    for asset in config.universe.assets:
        prices = _series(histories, asset.symbol)
        if prices is None or len(prices) < required:
            notes.append(f"{asset.symbol}: insufficient history")
            continue
        momentum = momentum_score(
            prices, strategy.lookbacks, strategy.lookback_weights, strategy.skip_days
        )
        volatility = realized_vol(prices, min(strategy.lookbacks))
        if math.isnan(momentum) or math.isnan(volatility):
            notes.append(f"{asset.symbol}: signal unavailable")
            continue
        signals[asset.symbol] = SignalRow(
            momentum=momentum,
            volatility=volatility,
            score=momentum / max(volatility, VOL_FLOOR),
        )

    eligible = {
        symbol: row for symbol, row in signals.items() if row.momentum > strategy.min_momentum
    }
    ranked = sorted(eligible, key=lambda symbol: eligible[symbol].score, reverse=True)[
        : strategy.top_n
    ]
    for symbol in ranked:
        signals[symbol].selected = True

    if not ranked:
        notes.append("no asset passed the absolute momentum filter; holding cash")
        return RotationResult(
            regime=regime,
            targets={config.universe.cash_symbol: 1.0},
            signals=signals,
            regime_checks=checks,
            portfolio_vol=0.0,
            vol_scale=0.0,
            notes=notes,
        )

    inverse = {symbol: 1.0 / max(signals[symbol].volatility, VOL_FLOOR) for symbol in ranked}
    total_inverse = sum(inverse.values())
    weights = {symbol: inverse[symbol] / total_inverse for symbol in ranked}

    portfolio_vol = _portfolio_vol(histories, weights)
    scale = (
        min(1.0, strategy.target_vol / portfolio_vol)
        if portfolio_vol > 0 and not math.isnan(portfolio_vol)
        else 1.0
    )
    weights = {symbol: weight * scale for symbol, weight in weights.items()}
    max_invested = 1.0 - strategy.min_cash_weight
    weights = _cap_sleeves(
        weights,
        config.universe,
        strategy.sleeve_caps[regime.value].as_dict(),
    )
    weights = _apply_asset_caps(weights, config.universe, strategy.max_weight)

    invested = sum(weights.values())
    if invested > max_invested > 0:
        factor = max_invested / invested
        weights = {symbol: weight * factor for symbol, weight in weights.items()}

    weights = {symbol: round(weight, 6) for symbol, weight in weights.items() if weight > 0}
    excess = sum(weights.values()) - max_invested
    if excess > 0:
        largest = max(weights, key=weights.get)
        weights[largest] = round(weights[largest] - excess, 6)
        if weights[largest] <= 0:
            weights.pop(largest)
    cash_weight = max(0.0, round(1.0 - sum(weights.values()), 6))
    targets = {**weights, config.universe.cash_symbol: cash_weight}

    notes.append(
        f"regime={regime.value} checks={sum(checks.values())}/{len(checks)} "
        f"portfolio_vol={portfolio_vol:.1%} vol_scale={scale:.2f}"
    )
    return RotationResult(
        regime=regime,
        targets=targets,
        signals=signals,
        regime_checks=checks,
        portfolio_vol=portfolio_vol,
        vol_scale=scale,
        notes=notes,
    )


def build_intents(
    result: RotationResult,
    snapshot: AccountSnapshot,
    last_prices: dict[str, float],
    config: AppConfig,
    strategy: StrategyConfig,
) -> list[OrderIntent]:
    nav = snapshot.nav
    if nav <= 0:
        return []
    cash_symbol = config.universe.cash_symbol
    positions = {position.symbol: position for position in snapshot.positions}
    symbols = set(result.targets) | set(positions)

    intents: list[OrderIntent] = []
    minimum_trade = max(strategy.min_trade_notional, 0.005 * nav)

    for symbol in sorted(symbols):
        if symbol == cash_symbol:
            continue
        price = last_prices.get(symbol)
        if not price or price <= 0:
            continue
        held = positions[symbol].quantity if symbol in positions else 0
        current_weight = held * price / nav
        target_weight = result.targets.get(symbol, 0.0)
        delta = target_weight - current_weight
        trade_value = abs(delta) * nav
        if trade_value < minimum_trade:
            continue
        if (
            held > 0
            and target_weight > 0
            and abs(delta) < strategy.drift_band * max(target_weight, current_weight)
        ):
            continue

        buy = delta > 0
        limit_price = round(price * (1.001 if buy else 0.999), 2)
        quantity = int(trade_value / limit_price)
        if not buy:
            quantity = min(quantity, held)
        if quantity <= 0:
            continue
        intents.append(
            OrderIntent(
                symbol=symbol,
                side=Side.BUY if buy else Side.SELL,
                quantity=quantity,
                limit_price=limit_price,
                reason=(
                    f"rebalance {current_weight:.1%} -> {target_weight:.1%} "
                    f"under {result.regime.value} regime"
                ),
            )
        )

    intents.sort(key=lambda intent: (intent.side == Side.BUY, -intent.notional))
    return intents


def fit_turnover_budget(
    intents: list[OrderIntent], nav: float, max_turnover_pct: float
) -> list[OrderIntent]:
    budget = max_turnover_pct * nav
    total_buys = sum(intent.notional for intent in intents if intent.side == Side.BUY)
    if budget <= 0 or total_buys <= budget:
        return intents
    factor = budget / total_buys
    fitted: list[OrderIntent] = []
    for intent in intents:
        if intent.side == Side.BUY:
            quantity = int(intent.quantity * factor)
            if quantity <= 0:
                continue
            intent = intent.model_copy(update={"quantity": quantity})
        fitted.append(intent)
    return fitted
