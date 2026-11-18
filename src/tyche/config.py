from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Sleeve = Literal["equity", "defensive", "real_asset", "credit"]
RegimeKey = Literal["risk_on", "neutral", "risk_off"]


class Asset(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]{2}\.[A-Z0-9.]+$")
    name: str
    sleeve: Sleeve
    max_weight: float = Field(gt=0.0, le=1.0)


class UniverseConfig(BaseModel):
    cash_symbol: str = "CASH"
    min_market_cap_usd: float = 500_000_000.0
    assets: list[Asset]

    @model_validator(mode="after")
    def _unique_symbols(self) -> UniverseConfig:
        symbols = [asset.symbol for asset in self.assets]
        if len(symbols) != len(set(symbols)):
            raise ValueError("universe contains duplicate symbols")
        if not self.assets:
            raise ValueError("universe must contain at least one asset")
        return self

    def by_symbol(self) -> dict[str, Asset]:
        return {asset.symbol: asset for asset in self.assets}

    def sleeve_by_symbol(self) -> dict[str, Sleeve]:
        return {asset.symbol: asset.sleeve for asset in self.assets}


class RegimeConfig(BaseModel):
    trend_sma: int = 200
    cross_fast: int = 50
    cross_slow: int = 200
    vol_short: int = 20
    vol_long: int = 252
    vol_ratio_limit: float = 1.25
    credit_fast: int = 63


class SleeveCaps(BaseModel):
    equity: float = Field(ge=0.0, le=1.0)
    defensive: float = Field(ge=0.0, le=1.0)
    real_asset: float = Field(ge=0.0, le=1.0)
    credit: float = Field(ge=0.0, le=1.0)

    def as_dict(self) -> dict[Sleeve, float]:
        return {
            "equity": self.equity,
            "defensive": self.defensive,
            "real_asset": self.real_asset,
            "credit": self.credit,
        }


class StrategyConfig(BaseModel):
    id: str = Field(pattern=r"^PB-\d{3}$")
    enabled: bool = True
    playbook: str
    lookbacks: list[int] = [63, 126, 252]
    lookback_weights: list[float] = [0.5, 0.3, 0.2]
    skip_days: int = 5
    min_momentum: float = 0.0
    top_n: int = 4
    target_vol: float = 0.10
    max_weight: float = 0.25
    min_cash_weight: float = 0.05
    min_trade_notional: float = 500.0
    drift_band: float = 0.20
    regime: RegimeConfig = RegimeConfig()
    sleeve_caps: dict[RegimeKey, SleeveCaps]

    @model_validator(mode="after")
    def _consistent(self) -> StrategyConfig:
        if len(self.lookbacks) != len(self.lookback_weights):
            raise ValueError("lookbacks and lookback_weights must have equal length")
        if not self.lookbacks or any(lookback <= 0 for lookback in self.lookbacks):
            raise ValueError("lookbacks must be positive")
        if abs(sum(self.lookback_weights) - 1.0) > 0.01:
            raise ValueError("lookback_weights must sum to 1.0")
        if self.top_n < 1:
            raise ValueError("top_n must be at least 1")
        if not 0.0 < self.min_cash_weight < 1.0:
            raise ValueError("min_cash_weight must be between 0 and 1")
        if not 0.0 < self.target_vol < 1.0:
            raise ValueError("target_vol must be between 0 and 1")
        for key in ("risk_on", "neutral", "risk_off"):
            if key not in self.sleeve_caps:
                raise ValueError(f"sleeve_caps missing regime '{key}'")
        return self


class RiskPolicy(BaseModel):
    account_allowlist: list[str] = Field(default_factory=lambda: ["SIM-DEMO-US", "SIM-TEST"])
    sim_account_types: list[int] = Field(default_factory=lambda: [1, 2])
    sim_market_id: int = 100
    allowed_markets: list[str] = ["US"]
    max_gross_exposure: float = 0.95
    max_position_weight: float = 0.40
    max_positions: int = 100
    cap_tolerance_pct: float = 0.0025
    min_cash_weight: float = 0.05
    max_order_notional_pct: float = 0.30
    max_daily_turnover_pct: float = 0.50
    max_orders_per_day: int = 6
    max_limit_deviation_pct: float = 0.03
    min_order_notional: float = 500.0
    min_price: float = 1.00
    soft_drawdown_pct: float = 0.04
    hard_drawdown_pct: float = 0.06
    daily_loss_limit_pct: float = 0.025
    allow_short: bool = False

    @model_validator(mode="after")
    def _drawdown_order(self) -> RiskPolicy:
        if self.soft_drawdown_pct >= self.hard_drawdown_pct:
            raise ValueError("soft_drawdown_pct must be below hard_drawdown_pct")
        if not 0.0 < self.max_gross_exposure <= 1.0:
            raise ValueError("max_gross_exposure must be in (0, 1]")
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")
        if self.min_price <= 0.0:
            raise ValueError("min_price must be positive")
        if self.allow_short:
            raise ValueError("shorting is out of scope for this agent")
        return self


class AppConfig(BaseModel):
    universe: UniverseConfig
    strategies: list[StrategyConfig]
    risk: RiskPolicy
    root: Path = Field(exclude=True)

    @model_validator(mode="after")
    def _unique_strategy_ids(self) -> AppConfig:
        if not self.strategies:
            raise ValueError("at least one strategy config is required")
        ids = [strategy.id for strategy in self.strategies]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate strategy ids in config/strategies")
        return self

    def strategy_by_id(self, strategy_id: str) -> StrategyConfig:
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                return strategy
        raise KeyError(f"unknown strategy id: {strategy_id}")

    def enabled_strategies(self) -> list[StrategyConfig]:
        return [strategy for strategy in self.strategies if strategy.enabled]


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"missing config file: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"config file is not a mapping: {path}")
    return payload


def load_config(root: Path) -> AppConfig:
    root = Path(root).resolve()
    config_dir = root / "config"
    risk = RiskPolicy.model_validate(_read_yaml(config_dir / "risk.yaml"))
    extra = os.environ.get("TYCHE_ALLOWED_ACCOUNT_IDS", "")
    injected = [item.strip() for item in extra.split(",") if item.strip()]
    if injected:
        risk = risk.model_copy(
            update={"account_allowlist": [*risk.account_allowlist, *injected]}
        )
    strategy_paths = sorted((config_dir / "strategies").glob("*.yaml"))
    if not strategy_paths:
        raise FileNotFoundError(f"no strategy configs in {config_dir / 'strategies'}")
    strategies = []
    for path in strategy_paths:
        strategy = StrategyConfig.model_validate(_read_yaml(path))
        if path.stem != strategy.id.lower():
            raise ValueError(
                f"strategy file {path.name} does not match id {strategy.id} "
                f"(expected {strategy.id.lower()}.yaml)"
            )
        strategies.append(strategy)
    return AppConfig(
        universe=UniverseConfig.model_validate(_read_yaml(config_dir / "universe.yaml")),
        strategies=strategies,
        risk=risk,
        root=root,
    )
