"""Fee model for the Moomoo paper challenge.

The sim MCP exposes no fee fields, so fees are modeled from the handbook
schedule and labeled ``source="model"`` until reconciled against the EOD cash
delta. TAF and regulatory components are applied on sells, matching the equity
TAF-on-sell convention; this assumption is provisional and surfaced by reconcile.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AssetClass = Literal["stock", "option"]

STOCK_PLATFORM_PER_ORDER = 0.99
STOCK_TAF_PER_SHARE = 0.000166
STOCK_TAF_CAP = 8.30

OPTION_PREMIUM_THRESHOLD = 0.10
OPTION_COMMISSION_HIGH = 0.65
OPTION_COMMISSION_LOW = 0.15
OPTION_COMMISSION_MIN = 1.99
OPTION_PLATFORM_PER_CONTRACT = 0.30
OPTION_TAF_PER_CONTRACT = 0.00279
OPTION_REGULATORY_PER_CONTRACT = 0.015


class FeeRecord(BaseModel):
    order_id: str = ""
    symbol: str
    side: str
    quantity: int = Field(gt=0)
    price: float = Field(ge=0.0)
    asset_class: AssetClass = "stock"
    components: dict[str, float] = Field(default_factory=dict)
    total: float = Field(ge=0.0)
    source: Literal["model", "broker"] = "model"


def stock_fees(side: str, quantity: int) -> dict[str, float]:
    components = {"platform": STOCK_PLATFORM_PER_ORDER}
    if side == "sell":
        components["taf"] = round(min(quantity * STOCK_TAF_PER_SHARE, STOCK_TAF_CAP), 4)
    return components


def option_fees(side: str, contracts: int, premium: float) -> dict[str, float]:
    per_contract = (
        OPTION_COMMISSION_HIGH if premium > OPTION_PREMIUM_THRESHOLD else OPTION_COMMISSION_LOW
    )
    components = {
        "commission": round(max(per_contract * contracts, OPTION_COMMISSION_MIN), 4),
        "platform": round(OPTION_PLATFORM_PER_CONTRACT * contracts, 4),
    }
    if side == "sell":
        components["taf"] = round(OPTION_TAF_PER_CONTRACT * contracts, 4)
        components["regulatory"] = round(OPTION_REGULATORY_PER_CONTRACT * contracts, 4)
    return components


def estimate_fees(
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    asset_class: AssetClass = "stock",
    order_id: str = "",
) -> FeeRecord:
    components = (
        stock_fees(side, quantity)
        if asset_class == "stock"
        else option_fees(side, quantity, price)
    )
    return FeeRecord(
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        asset_class=asset_class,
        components=components,
        total=round(sum(components.values()), 4),
    )


class CashReconciliation(BaseModel):
    expected_cash_delta: float
    actual_cash_delta: float
    fee_total: float
    residual: float
    tolerance: float
    ok: bool


def reconcile_cash(
    cash_before: float,
    cash_after: float,
    fills: list[tuple[int, float] | tuple[int, float, int]],
    fees: list[FeeRecord],
    tolerance: float = 1.0,
) -> CashReconciliation:
    """Compare modeled fill+fee cash impact against the observed cash delta.

    ``fills`` are (signed quantity, price[, multiplier]); a buy is positive.
    Compare TOTAL cash (available + frozen), not free cash alone, when orders rest.
    Options must carry their verified contract multiplier.
    """
    fill_delta = 0.0
    for fill in fills:
        signed, price = fill[:2]
        multiplier = fill[2] if len(fill) == 3 else 1
        if multiplier not in (1, 100):
            raise ValueError("only stock shares or standard 100-share options supported")
        fill_delta -= signed * price * multiplier
    fee_total = sum(fee.total for fee in fees)
    expected = fill_delta - fee_total
    actual = cash_after - cash_before
    residual = actual - expected
    return CashReconciliation(
        expected_cash_delta=round(expected, 4),
        actual_cash_delta=round(actual, 4),
        fee_total=round(fee_total, 4),
        residual=round(residual, 4),
        tolerance=tolerance,
        ok=abs(residual) <= tolerance,
    )