"""Operator pre-approved order envelope (option 2: bounded evening batch).

The operator approves a bounded batch before the US drives (evening SGT) by
committing data/approvals.json; the cloud mount syncs it per session. The
executor may submit an order WITHOUT a per-order confirmation popup only when
``authorize_order`` passes against a same-day envelope; everything else stays
always_ask. Usage is counted from the journal (order.requested events carrying
an envelope authorization), so the budget survives ephemeral sessions via the
Drive-persisted journal. Symbols, sides, quantities and limit bounds only —
never account ids or tokens.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from tyche.journal import read_events


class ApprovalLine(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    max_qty: int = Field(gt=0)
    limit_max: float | None = None
    limit_min: float | None = None

    @model_validator(mode="after")
    def _side_bounds(self) -> ApprovalLine:
        if self.side == "buy":
            if self.limit_max is None or self.limit_max <= 0 or self.limit_min is not None:
                raise ValueError("buy line requires a positive limit_max and no limit_min")
        elif self.limit_min is None or self.limit_min <= 0 or self.limit_max is not None:
            raise ValueError("sell line requires a positive limit_min and no limit_max")
        return self


class ApprovalBatch(BaseModel):
    as_of: date
    approved_at: datetime
    approved_by: str = "operator"
    max_orders: int = Field(ge=1)
    orders: list[ApprovalLine] = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def _unique_lines(self) -> ApprovalBatch:
        keys = [(o.symbol, o.side) for o in self.orders]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate symbol+side lines in envelope")
        return self

    def valid_on(self, today: date) -> bool:
        return self.as_of == today

    def line_for(self, symbol: str, side: str) -> ApprovalLine | None:
        return next((o for o in self.orders if o.symbol == symbol and o.side == side), None)


def envelope_usage(journal_path: Path, today: date) -> int:
    """Count today's envelope-authorized order.requested events in the journal."""
    count = 0
    for record in read_events(journal_path):
        if record.get("type") != "order.requested":
            continue
        auth = record.get("payload", {}).get("authorization") or {}
        if auth.get("kind") == "envelope" and auth.get("as_of") == today.isoformat():
            count += 1
    return count


def authorize_order(
    batch: ApprovalBatch,
    *,
    symbol: str,
    side: str,
    qty: int,
    limit: float | None,
    today: date,
    used: int,
) -> tuple[bool, str]:
    """Deterministic envelope gate: (authorized, plain-words reason)."""
    if not batch.valid_on(today):
        return False, f"envelope dated {batch.as_of} is not valid today ({today}); operator must re-approve"
    line = batch.line_for(symbol, side)
    if line is None:
        return False, f"no operator-approved line for {symbol} {side}"
    if qty <= 0:
        return False, "quantity must be positive"
    if qty > line.max_qty:
        return False, f"qty {qty} exceeds approved max {line.max_qty} for {symbol} {side}"
    if limit is None:
        return False, "envelope authorizes limit orders only; no market orders"
    if side == "buy" and limit > line.limit_max:
        return False, f"limit {limit} above approved ceiling {line.limit_max} for {symbol}"
    if side == "sell" and limit < line.limit_min:
        return False, f"limit {limit} below approved floor {line.limit_min} for {symbol}"
    if used >= batch.max_orders:
        return False, f"envelope order budget exhausted ({used}/{batch.max_orders} used today)"
    bound = line.limit_max if side == "buy" else line.limit_min
    return True, f"within operator envelope {batch.as_of}: {symbol} {side} <= {line.max_qty} @ {bound} ({used + 1}/{batch.max_orders})"