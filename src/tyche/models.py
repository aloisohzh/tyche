from __future__ import annotations

import math
import re
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"


class Regime(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


OPTION_SYMBOL = re.compile(r"^US\.([A-Z]+)(\d{6})([CP])(\d+)$")


def looks_like_option(symbol: str) -> bool:
    return bool(re.search(r"\d{6}[CP]\d+$", symbol))


class OptionContract(BaseModel):
    """Verified standard-contract metadata, never inferred from premium alone."""

    model_config = ConfigDict(allow_inf_nan=False)
    underlying: str = Field(pattern=r"^US\.[A-Z]+$")
    expiry: date
    right: Literal["call", "put"]
    strike: float = Field(gt=0)
    multiplier: Literal[100] = 100

    def matches(self, symbol: str) -> bool:
        match = OPTION_SYMBOL.fullmatch(symbol)
        if not match:
            return False
        root, expiry, right, strike = match.groups()
        return (
            self.underlying == f"US.{root}"
            and self.expiry.strftime("%y%m%d") == expiry
            and right == ("C" if self.right == "call" else "P")
            and abs(int(strike) / 1000 - self.strike) < 1e-8
        )


class Instrument(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    symbol: str
    option: OptionContract | None = None

    @model_validator(mode="after")
    def _contract(self):
        if self.option is not None and not self.option.matches(self.symbol):
            raise ValueError("option symbol does not match verified standard contract metadata")
        if looks_like_option(self.symbol) and self.option is None:
            raise ValueError("option instrument requires verified contract metadata")
        return self

    @property
    def multiplier(self) -> int:
        return self.option.multiplier if self.option else 1

    @property
    def underlying(self) -> str:
        return self.option.underlying if self.option else self.symbol


class Position(Instrument):
    quantity: int = Field(ge=0)
    available_quantity: int | None = Field(default=None, ge=0)
    avg_cost: float = Field(ge=0.0)
    last_price: float = Field(ge=0.0)

    @property
    def sellable(self) -> int:
        return min(self.quantity, self.available_quantity) if self.available_quantity is not None else self.quantity

    @computed_field
    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price * self.multiplier


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    account_id: str
    cash: float = Field(ge=0.0)
    frozen_cash: float = Field(default=0.0, ge=0.0)
    broker_nav: float | None = Field(default=None, gt=0.0)
    prior_close_nav: float | None = Field(default=None, gt=0.0)
    high_water_nav: float | None = Field(default=None, gt=0.0)
    captured_at: datetime | None = None
    positions: list[Position] = Field(default_factory=list)
    env: Literal["paper", "live"] = "paper"
    account_type: int | None = None
    market_id: int | None = None
    source: Literal["demo", "sim_list", "manual"] = "demo"

    @model_validator(mode="after")
    def _snapshot_integrity(self):
        symbols = [p.symbol for p in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate position symbols")
        if self.captured_at is not None and self.captured_at.tzinfo is None:
            raise ValueError("snapshot timestamp must include timezone")
        return self

    def position(self, symbol: str) -> Position | None:
        return next((p for p in self.positions if p.symbol == symbol), None)

    @computed_field
    @property
    def gross_exposure(self) -> float:
        return sum(p.market_value for p in self.positions)

    @computed_field
    @property
    def nav(self) -> float:
        return self.cash + self.frozen_cash + self.gross_exposure


class OrderIntent(Instrument):
    strategy_id: str = "PB-001"
    setup_id: str | None = None
    side: Side
    quantity: int = Field(gt=0)
    order_type: OrderType = OrderType.LIMIT
    limit_price: float = Field(gt=0.0)
    stop_price: float | None = Field(default=None, gt=0.0)
    reason: str

    @computed_field
    @property
    def notional(self) -> float:
        return self.quantity * self.limit_price * self.multiplier


def apply_fill(
    snapshot: AccountSnapshot,
    intent: OrderIntent,
    quantity: int,
    fill_price: float | None = None,
) -> AccountSnapshot:
    """Project a fill into the snapshot so later orders see the post-trade book."""
    price = fill_price if fill_price is not None else intent.limit_price
    if not math.isfinite(price) or price <= 0:
        raise ValueError("fill price must be finite and positive")
    signed = quantity if intent.side == Side.BUY else -quantity
    positions = {position.symbol: position.model_copy() for position in snapshot.positions}
    held = positions.get(intent.symbol)
    if quantity <= 0 or quantity > intent.quantity:
        raise ValueError("invalid fill quantity")
    if held is not None and held.option != intent.option:
        raise ValueError("fill contract differs from held contract")
    if signed < 0 and (held is None or quantity > held.sellable):
        raise ValueError("sell exceeds available long position")
    if signed > 0 and quantity * price * intent.multiplier > snapshot.cash:
        raise ValueError("buy exceeds available cash")
    if held is None and signed > 0:
        positions[intent.symbol] = Position(
            symbol=intent.symbol,
            option=intent.option,
            quantity=signed,
            avg_cost=price,
            last_price=price,
        )
    elif held is not None:
        new_quantity = held.quantity + signed
        if new_quantity <= 0:
            positions.pop(intent.symbol)
        else:
            average = (
                (held.quantity * held.avg_cost + signed * price) / new_quantity
                if signed > 0
                else held.avg_cost
            )
            positions[intent.symbol] = held.model_copy(
                update={"quantity": new_quantity, "avg_cost": average, "last_price": price,
                        "available_quantity": None if held.available_quantity is None else held.sellable + signed}
            )
    return snapshot.model_copy(
        update={
            "cash": snapshot.cash - signed * price * intent.multiplier,
            "positions": list(positions.values()),
            "broker_nav": None,
        }
    )


class RiskBreach(BaseModel):
    rule: str
    detail: str


class RiskVerdict(BaseModel):
    allowed: bool
    breaches: list[RiskBreach] = Field(default_factory=list)
    adjusted_quantity: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class Outlook(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE = "range"


class InputsRef(BaseModel):
    prices_path: str
    prices_sha256: str
    brief: str | None = None


class PlanPipeline(BaseModel):
    """Research-to-execution context shared by every order in the plan."""

    thesis_ref: str
    rules_hash: str
    inputs_ref: InputsRef
    outlook: Outlook
    conviction: Literal["high", "medium-high", "medium", "low"]
    checks_score: int = Field(ge=0)
    checks_total: int = Field(gt=0)
    act_wait_rule: str


class EdgeEstimate(BaseModel):
    r: float | None = None
    pct: float | None = None
    label: str = "provisional — unvalidated"


class Sizing(BaseModel):
    quantity: int = Field(gt=0)
    effective_quantity: int = Field(ge=0)
    limit_price: float = Field(gt=0.0)
    notional: float = Field(ge=0.0)
    nav_pct: float = Field(ge=0.0)
    single_asset_cap_pct: float = Field(gt=0.0)
    sleeve_cap_pct: float | None = None


class OrderPipeline(BaseModel):
    """Per-trade contract fields (docs/dashboard.md) carried in plan + journal."""

    vehicle: Literal["etf", "stock_long", "option_call", "option_put", "option_vertical"]
    vehicle_rationale: str
    expected_edge: EdgeEstimate | None = None
    invalidation: str
    protection_type: Literal["synthetic_stop", "defined_risk", "time_exit", "rebalance"]
    roll_plan: str | None = None
    sizing: Sizing
    action: Literal["act", "wait"] = "act"


class PlannedOrder(BaseModel):
    intent: OrderIntent
    verdict: RiskVerdict
    pipeline: OrderPipeline | None = None

    @computed_field
    @property
    def effective_quantity(self) -> int:
        if not self.verdict.allowed:
            return 0
        return min(self.intent.quantity, self.verdict.adjusted_quantity)


class SignalRow(BaseModel):
    momentum: float
    volatility: float
    score: float
    selected: bool = False


class RotationResult(BaseModel):
    regime: Regime
    targets: dict[str, float]
    signals: dict[str, SignalRow]
    regime_checks: dict[str, bool]
    portfolio_vol: float
    vol_scale: float
    notes: list[str] = Field(default_factory=list)


class TradePlan(BaseModel):
    as_of: date
    account_id: str
    nav: float
    cash: float
    regime: Regime
    targets: dict[str, float]
    signals: dict[str, SignalRow]
    regime_checks: dict[str, bool]
    portfolio_vol: float
    vol_scale: float
    orders: list[PlannedOrder]
    pipeline: PlanPipeline | None = None
    notes: list[str] = Field(default_factory=list)


class OrderAck(BaseModel):
    order_id: str
    status: str
    raw: dict = Field(default_factory=dict)
