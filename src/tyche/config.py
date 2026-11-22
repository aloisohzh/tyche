from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tyche.lanes import SOURCE_LABEL, effective

Sleeve = Literal["equity", "defensive", "real_asset", "credit"]
RegimeKey = Literal["risk_on", "neutral", "risk_off"]

# Which bytes freeze each playbook id, and which switch turns it on (ADR 0014).
#
# Only PB-001 follows the `config/strategies/<id>.yaml` convention; the tactical and scalp lanes keep
# their own parameter files, and a freeze must cover the bytes that actually govern trading rather
# than a documentation pointer (L-036, L-037). PB-002 and PB-003 share one file because they are one
# lane with one set of parameters, so editing tactical.yaml re-registers both - stated rather than
# discovered later.
#
# Rotation ids missing from this table fall back to the convention, so adding PB-007 needs no edit
# here as long as its config lands in config/strategies/.
PLAYBOOK_LANES: dict[str, tuple[str, str]] = {
    "PB-001": ("config/strategies/pb-001.yaml", "rotation"),
    "PB-002": ("config/tactical.yaml", "tactical"),
    "PB-003": ("config/tactical.yaml", "tactical_options"),
    "PB-004": ("config/scalp.yaml", "scalp"),
    # ADR 0017: a swing lane on its own daily-bar scanner; its yaml follows the convention and carries
    # `kind: fib_pullback`, so the rotation switch logic (the file's own `enabled`) applies unchanged.
    "PB-007": ("config/strategies/pb-007.yaml", "fib_pullback"),
}


def rules_path_for(config_root: Path, strategy_id: str) -> Path:
    """Resolve the file that freezes a playbook id, without loading the whole config."""
    lane = PLAYBOOK_LANES.get(strategy_id)
    if lane is not None:
        return config_root / lane[0]
    candidate = config_root / "config" / "strategies" / f"{strategy_id.lower()}.yaml"
    if candidate.is_file():
        return candidate
    raise ValueError(
        f"{strategy_id} has no rules file: add config/strategies/{strategy_id.lower()}.yaml "
        f"or map it in PLAYBOOK_LANES (src/tyche/config.py)"
    )


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
    """Rotation lane parameters (PB-001). `kind` defaults to rotation so existing files are unchanged."""
    id: str = Field(pattern=r"^PB-\d{3}$")
    kind: Literal["rotation"] = "rotation"
    allocation_cap: float = Field(default=0.95, gt=0, le=0.95)
    enabled: bool = True
    # Rotation trades the whole shared universe; the scope accessor returns it. Kept for symmetry
    # with lanes that own their own symbol set (ADR 0017).
    symbols: None = None
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
    initial_stop_pct: float = Field(default=0.08, gt=0.0, le=0.5)
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


class FibRegime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sma_fast: int = Field(default=50, ge=2)
    sma_slow: int = Field(default=200, ge=2)
    slope_bars: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _order(self) -> FibRegime:
        if self.sma_fast >= self.sma_slow:
            raise ValueError("sma_fast must be shorter than sma_slow")
        return self


class FibLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lookback: int = Field(default=30, ge=5)
    max_high_age: int = Field(default=15, ge=1)
    min_high_age: int = Field(default=2, ge=1)
    min_leg_atr: float = Field(default=3.0, gt=0)
    atr_period: int = Field(default=14, ge=2)

    @model_validator(mode="after")
    def _order(self) -> FibLeg:
        if not self.min_high_age <= self.max_high_age < self.lookback:
            raise ValueError("require min_high_age <= max_high_age < lookback")
        return self


class FibLevels(BaseModel):
    """Retracement ratios measured from the swing high: 0.5 = halfway back to the swing low."""
    model_config = ConfigDict(extra="forbid")
    entry: float = Field(default=0.5, gt=0, lt=1)
    zone_top: float = Field(default=0.382, gt=0, lt=1)
    zone_bottom: float = Field(default=0.618, gt=0, lt=1)
    stop_level: float = Field(default=0.786, gt=0, lt=1)
    stop_atr_buffer: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def _order(self) -> FibLevels:
        if not self.zone_top < self.entry <= self.zone_bottom < self.stop_level:
            raise ValueError("require zone_top < entry <= zone_bottom < stop_level")
        return self


class FibPullbackConfig(BaseModel):
    """PB-007 fib 50% pullback: a swing lane on daily bars, planned through the lifecycle contract.

    Carries the same cap fields the lifecycle gate reads from the rotation model
    (`allocation_cap`, `max_weight`, `sleeve_caps`) so one `decide()` serves both kinds.
    """
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    id: str = Field(pattern=r"^PB-\d{3}$")
    kind: Literal["fib_pullback"]
    enabled: bool = False
    sleeve: Sleeve = "equity"
    symbols: list[str] = Field(min_length=1)
    allocation_cap: float = Field(default=0.20, gt=0, le=0.95)
    max_weight: float = Field(default=0.10, gt=0, le=0.38)
    regime: FibRegime = FibRegime()
    leg: FibLeg = FibLeg()
    fib: FibLevels = FibLevels()
    min_reward_risk: float = Field(default=1.5, ge=1)
    risk_per_trade_pct: float = Field(default=0.005, gt=0, le=0.01)
    max_notional_pct: float = Field(default=0.10, gt=0, le=0.38)
    max_open: int = Field(default=4, ge=1)
    max_hold_sessions: int = Field(default=10, ge=1, le=60)
    max_spread_pct: float = Field(default=0.003, gt=0, le=0.01)
    min_avg_dollar_volume: float = Field(default=50_000_000.0, ge=0)
    min_bars: int = Field(default=260, ge=50)
    no_entry_event_kinds: list[str] = Field(default_factory=lambda: ["FOMC", "CPI", "PCE"])

    @model_validator(mode="after")
    def _consistent(self) -> FibPullbackConfig:
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("duplicate fib_pullback symbols")
        if any(not re.match(r"^[A-Z]{2}\.[A-Z0-9.]+$", symbol) for symbol in self.symbols):
            raise ValueError("fib_pullback symbols must look like US.XXXX")
        if self.max_open > len(self.symbols):
            raise ValueError("max_open exceeds the fib_pullback universe")
        if self.max_notional_pct > self.max_weight + 1e-9:
            raise ValueError("max_notional_pct must not exceed max_weight")
        if self.min_bars < self.regime.sma_slow + self.regime.slope_bars:
            raise ValueError("min_bars must cover sma_slow plus slope_bars")
        return self

    @property
    def sleeve_caps(self) -> dict[RegimeKey, SleeveCaps]:
        """The lane's own sleeve is capped at its allocation in every regime; it owns nothing else."""
        caps = {"equity": 0.0, "defensive": 0.0, "real_asset": 0.0, "credit": 0.0}
        caps[self.sleeve] = self.allocation_cap
        one = SleeveCaps(**caps)
        return {"risk_on": one, "neutral": one, "risk_off": one}


AnyStrategyConfig = StrategyConfig | FibPullbackConfig


class RiskPolicy(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    option_risk_per_trade_pct: float = Field(default=0.0075, gt=0, le=0.02)
    max_option_premium_pct: float = Field(default=0.05, gt=0, le=0.25)
    competition_order_cap: int = Field(default=200, ge=1, le=200)
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
    # How far below the journaled stop a proposed exit floor may sit (envelope drafts).
    exit_collar_pct: float = Field(default=0.05, gt=0.0, le=0.20)
    min_order_notional: float = 500.0
    min_price: float = 1.00
    soft_drawdown_pct: float = 0.04
    hard_drawdown_pct: float = 0.06
    daily_loss_limit_pct: float = 0.025
    risk_per_trade_pct: float = Field(default=0.01, gt=0.0, le=0.05)
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


class TacticalConfig(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    enabled: bool = False
    options_enabled: bool = False
    execution_enabled: bool = False  # rollout gate; enable only after cloud/broker drill
    symbols: list[str] = Field(default_factory=lambda: ["US.NVDA", "US.AMD", "US.AVGO", "US.MU", "US.SMH"])
    etf_symbols: list[str] = Field(default_factory=lambda: ["US.SMH"])
    stock_allocation_cap: float = Field(default=0.65, gt=0, le=0.8)
    max_name_weight: float = Field(default=0.20, gt=0, le=0.38)
    min_reward_risk: float = Field(default=1.5, ge=1)
    max_quote_age_seconds: int = Field(default=60, ge=5, le=120)
    max_snapshot_age_seconds: int = Field(default=120, ge=5, le=300)
    monitor_interval_seconds: int = Field(default=120, ge=5, le=86400)
    stock_spread_pct: float = Field(default=0.003, gt=0, le=0.01)
    option_spread_pct: float = Field(default=0.05, gt=0, le=0.10)
    min_option_open_interest: int = Field(default=100, ge=0)
    min_option_volume: int = Field(default=50, ge=0)
    min_option_dte: int = Field(default=2, ge=1)
    max_option_dte: int = Field(default=30, ge=2)
    option_exit_minutes_before_close: int = Field(default=45, ge=15, le=120)
    session_exit_minutes_before_close: int = Field(default=10, ge=5, le=60)
    max_new_orders_per_tick: int = Field(default=3, ge=1, le=10)
    max_entries_per_setup: int = Field(default=1, ge=1, le=3)

    @model_validator(mode="after")
    def _bounds(self):
        if self.min_option_dte > self.max_option_dte:
            raise ValueError("invalid option DTE range")
        if len(self.symbols) != len(set(self.symbols)) or not set(self.etf_symbols) <= set(self.symbols):
            raise ValueError("invalid tactical universe")
        return self


class ScalpConfig(BaseModel):
    """PB-004: one intraday momentum-scalp strategy, many small round trips."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    enabled: bool = False
    symbols: list[str] = Field(default_factory=lambda: ["US.NVDA", "US.AMD", "US.AVGO", "US.MU", "US.SMH", "US.SPY"])
    breakout_bars: int = Field(default=5, ge=2, le=30)
    stop_pct: float = Field(default=0.0025, gt=0, le=0.01)
    target_r: float = Field(default=2.0, ge=1, le=5)
    risk_per_trade_pct: float = Field(default=0.001, gt=0, le=0.005)
    max_notional_pct: float = Field(default=0.05, gt=0, le=0.15)
    max_open: int = Field(default=4, ge=1, le=10)
    cooldown_seconds: int = Field(default=600, ge=60, le=3600)
    timeout_minutes: int = Field(default=20, ge=2, le=60)
    max_round_trips_per_day: int = Field(default=50, ge=1, le=200)
    max_spread_pct: float = Field(default=0.001, gt=0, le=0.01)
    flatten_minutes_before_close: int = Field(default=10, ge=5, le=30)
    # A blocked exit must stay retryable; an entry can expire quickly.
    exit_submit_window_seconds: int = Field(default=900, ge=60, le=3600)

    @model_validator(mode="after")
    def _bounds(self):
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("duplicate scalp symbols")
        if self.max_open > len(self.symbols):
            raise ValueError("max_open exceeds scalp universe")
        return self


class AppConfig(BaseModel):
    tactical: TacticalConfig = Field(default_factory=TacticalConfig)
    scalp: ScalpConfig = Field(default_factory=ScalpConfig)
    universe: UniverseConfig
    strategies: list[AnyStrategyConfig]
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

    def strategy_by_id(self, strategy_id: str) -> AnyStrategyConfig:
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                return strategy
        raise KeyError(f"unknown strategy id: {strategy_id}")

    def rotation_strategies(self) -> list[StrategyConfig]:
        """The strategies `tyche plan` can run; scoped lanes plan through their own command."""
        return [s for s in self.strategies if isinstance(s, StrategyConfig)]

    def scope_symbols(self, strategy_id: str) -> set[str]:
        """The symbols a strategy may buy (ADR 0017): its own scope, else the shared universe."""
        strategy = self.strategy_by_id(strategy_id)
        if strategy.symbols:
            return set(strategy.symbols)
        return set(self.universe.by_symbol())

    def sleeve_map(self, strategy_id: str | None = None) -> dict[str, Sleeve]:
        """symbol -> sleeve. For a scoped strategy only its own symbols; otherwise the universe
        plus every scoped lane, which is what fill attribution and the scorecard need."""
        if strategy_id is not None:
            strategy = self.strategy_by_id(strategy_id)
            if strategy.symbols:
                return {symbol: strategy.sleeve for symbol in strategy.symbols}
            return self.universe.sleeve_by_symbol()
        sleeves: dict[str, Sleeve] = dict(self.universe.sleeve_by_symbol())
        for strategy in self.strategies:
            if strategy.symbols:
                sleeves.update({symbol: strategy.sleeve for symbol in strategy.symbols})
        return sleeves

    def rules_path(self, strategy_id: str) -> Path:
        """The file whose bytes freeze this playbook id (see PLAYBOOK_LANES)."""
        return rules_path_for(self.root, strategy_id)

    def _lane_label(self, strategy_id: str) -> str:
        lane = PLAYBOOK_LANES.get(strategy_id)
        if lane is not None:
            return lane[1]
        try:
            return self.strategy_by_id(strategy_id).kind
        except KeyError:
            return "rotation"

    def _lane_enabled(self, strategy_id: str) -> bool:
        """Whether the lane owning this id is on, across all three config shapes."""
        lane = PLAYBOOK_LANES.get(strategy_id, (None, "rotation"))[1]
        if lane in ("rotation", "fib_pullback"):
            # Every config/strategies/<id>.yaml lane, whatever its kind, is switched by its own file.
            return self.strategy_by_id(strategy_id).enabled
        if lane == "tactical":
            return self.tactical.enabled
        if lane == "tactical_options":
            return self.tactical.enabled and self.tactical.options_enabled
        if lane == "scalp":
            return self.scalp.enabled
        raise ValueError(f"{strategy_id}: unknown lane {lane}")

    def strategy_switch(self, strategy_id: str) -> tuple[bool, str, str | None]:
        """(enabled, what decided it, switch-file problem) - the operator override wins over the lane."""
        return effective(strategy_id, self._lane_enabled(strategy_id), self.root)

    def strategy_enabled(self, strategy_id: str) -> bool:
        """Effective enablement: the desk's switch file if it names this id, else the lane config."""
        return self.strategy_switch(strategy_id)[0]

    def playbook_switches(self) -> list[dict]:
        """Every claimable playbook id with what the desk and Scout should treat as live (L-036)."""
        claimed = sorted({strategy.id for strategy in self.strategies} | set(PLAYBOOK_LANES))
        rows = []
        for strategy_id in claimed:
            lane_default = self._lane_enabled(strategy_id)
            enabled, source, problem = self.strategy_switch(strategy_id)
            rows.append(
                {
                    "strategy_id": strategy_id,
                    "lane": self._lane_label(strategy_id),
                    "rules_file": self.rules_path(strategy_id).relative_to(self.root).as_posix(),
                    "lane_config_enabled": lane_default,
                    "operator_override": enabled if source == SOURCE_LABEL else None,
                    "enabled": enabled,
                    "source": source,
                    "switch_file_problem": problem,
                }
            )
        return rows

    def enabled_playbook_ids(self) -> list[str]:
        """What Scout and the desk should treat as live right now (L-036)."""
        return sorted(row["strategy_id"] for row in self.playbook_switches() if row["enabled"])

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
        raw = _read_yaml(path)
        model = FibPullbackConfig if raw.get("kind") == "fib_pullback" else StrategyConfig
        strategy = model.model_validate(raw)
        if path.stem != strategy.id.lower():
            raise ValueError(
                f"strategy file {path.name} does not match id {strategy.id} "
                f"(expected {strategy.id.lower()}.yaml)"
            )
        strategies.append(strategy)
    tactical_path = config_dir / "tactical.yaml"
    tactical = TacticalConfig.model_validate(_read_yaml(tactical_path)) if tactical_path.is_file() else TacticalConfig()
    scalp_path = config_dir / "scalp.yaml"
    scalp = ScalpConfig.model_validate(_read_yaml(scalp_path)) if scalp_path.is_file() else ScalpConfig()
    universe = UniverseConfig.model_validate(_read_yaml(config_dir / "universe.yaml"))
    if tactical.enabled and set(tactical.symbols) & set(universe.by_symbol()):
        raise ValueError("tactical and ballast symbols must not overlap; separate position ownership")
    if scalp.enabled and set(scalp.symbols) & (
            set(universe.by_symbol()) | (set(tactical.symbols) if tactical.enabled else set())):
        raise ValueError("scalp symbols must not overlap ballast/tactical ownership")
    owned: dict[str, str] = {symbol: "ballast universe" for symbol in universe.by_symbol()}
    if tactical.enabled:
        owned.update({symbol: "tactical lane" for symbol in tactical.symbols})
    if scalp.enabled:
        owned.update({symbol: "scalp lane" for symbol in scalp.symbols})
    for strategy in strategies:
        if not strategy.symbols or not strategy.enabled:
            continue
        clash = sorted(set(strategy.symbols) & set(owned))
        if clash:
            raise ValueError(
                f"{strategy.id} symbols {clash} already belong to the {owned[clash[0]]}; "
                "one lane owns a symbol (ADR 0014/0017)"
            )
        owned.update({symbol: f"{strategy.id} scope" for symbol in strategy.symbols})
    if tactical.enabled and (sum(s.allocation_cap for s in strategies if s.enabled)
                             + tactical.stock_allocation_cap + risk.max_option_premium_pct
                             > risk.max_gross_exposure + 1e-8):
        raise ValueError("strategy allocation caps exceed gross exposure cap")
    return AppConfig(
        tactical=tactical,
        scalp=scalp,
        universe=universe,
        strategies=strategies,
        risk=risk,
        root=root,
    )
