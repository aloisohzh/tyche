from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"


class Regime(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


class Position(BaseModel):
    symbol: str
    quantity: int = Field(ge=0)
    avg_cost: float = Field(ge=0.0)
    last_price: float = Field(ge=0.0)

    @computed_field
    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price


class AccountSnapshot(BaseModel):
    account_id: str
    cash: float = Field(ge=0.0)
    positions: list[Position] = Field(default_factory=list)
    env: Literal["paper", "live"] = "paper"
    account_type: int | None = None
    market_id: int | None = None
    source: Literal["demo", "sim_list", "manual"] = "demo"

    def position(self, symbol: str) -> Position | None:
        return next((p for p in self.positions if p.symbol == symbol), None)

    @computed_field
    @property
    def gross_exposure(self) -> float:
        return sum(p.market_value for p in self.positions)

    @computed_field
    @property
    def nav(self) -> float:
        return self.cash + self.gross_exposure


class OrderIntent(BaseModel):
    symbol: str
    side: Side
    quantity: int = Field(gt=0)
    order_type: OrderType = OrderType.LIMIT
    limit_price: float = Field(gt=0.0)
    reason: str

    @computed_field
    @property
    def notional(self) -> float:
        return self.quantity * self.limit_price


def apply_fill(
    snapshot: AccountSnapshot,
    intent: OrderIntent,
    quantity: int,
    fill_price: float | None = None,
) -> AccountSnapshot:
    """Project a fill into the snapshot so later orders see the post-trade book."""
    price = fill_price if fill_price is not None else intent.limit_price
    signed = quantity if intent.side == Side.BUY else -quantity
    positions = {position.symbol: position.model_copy() for position in snapshot.positions}
    held = positions.get(intent.symbol)
    if held is None and signed > 0:
        positions[intent.symbol] = Position(
            symbol=intent.symbol,
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
                update={"quantity": new_quantity, "avg_cost": average}
            )
    return snapshot.model_copy(
        update={
            "cash": snapshot.cash - signed * price,
            "positions": list(positions.values()),
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

    vehicle: Literal["etf", "stock_long", "option_vertical"]
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
