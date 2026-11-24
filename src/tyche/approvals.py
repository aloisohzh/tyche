"""Operator authorization for paper orders: two modes, one deterministic gate.

"Within my bounds": the operator arms a bounded same-day envelope from the desk
(data/approvals.json, synced to the cloud mount via git). The executor may
submit inside those bounds with no Telegram ask.

"Ask me": no envelope. During a fire the desk previews each proposal on
Telegram and waits for ``/approve N``; the approval is journaled
(``approval.telegram``) and ``telegram_batch`` turns today's journaled
approvals into an ``ApprovalBatch`` of exactly the approved orders, so the same
``authorize_order`` gate runs with no envelope file. The cloud desk cannot write
data/approvals.json (push-back is 403), but it can and does write the journal.

``resolve_batch`` picks the mode: a same-day envelope wins, otherwise today's
Telegram approvals, otherwise nothing is authorized. The kill-switch overrides
both. Usage is counted from the journal (order.requested events carrying an
operator authorization), so budgets survive ephemeral sessions via the
Drive-persisted journal. Symbols, sides, quantities and limit bounds only -
never account ids or tokens.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tyche.execution_state import request_notional
from tyche.journal import read_events

# Journal event type for one operator yes given on Telegram during a fire.
TELEGRAM_APPROVAL_EVENT = "approval.telegram"
# Authorization kinds an order.requested may carry that count against the operator's budget.
OPERATOR_AUTHORIZATION_KINDS = frozenset({"envelope", "telegram"})
MODE_ASK = "ask"
MODE_BOUNDS = "bounds"
# A kernel-triggered exit (stop, target, invalidation, time, option expiry) of a lot the desk holds:
# it only removes risk, so it needs no operator line that day (operator direction 2026-11-24).
MODE_PROTECTIVE = "protective"


def cancelled_request_ids(events: list[dict]) -> set[str]:
    """Requests whose broker order was cancelled (the desk's own resting take-profit, pulled for a stop).

    A cancelled order never traded, so it hands its quantity and its order-budget slot back.
    """
    return {str(e.get("payload", {}).get("request_id")) for e in events
            if e.get("type") == "order.cancelled" and e.get("payload", {}).get("request_id")}


class ApprovalLine(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    max_total_qty: int | None = Field(default=None, gt=0)
    multiplier: Literal[1, 100] = 1
    setup_hash: str | None = None
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
    model_config = ConfigDict(allow_inf_nan=False)
    max_notional: float | None = Field(default=None, gt=0)
    as_of: date
    # Optional last day a standing envelope covers (inclusive). Absent means as_of only: the daily
    # envelope stays same-day. The PB-004 scalp's standing envelope (data/scalp-approvals.json) uses it.
    valid_until: date | None = None
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
        if self.valid_until is not None and self.valid_until < self.as_of:
            raise ValueError("valid_until is before as_of")
        return self

    def valid_on(self, today: date) -> bool:
        if self.valid_until is None:
            return self.as_of == today
        return self.as_of <= today <= self.valid_until

    def line_for(self, symbol: str, side: str) -> ApprovalLine | None:
        return next((o for o in self.orders if o.symbol == symbol and o.side == side), None)


class TelegramApproval(BaseModel):
    """One journaled ``/approve N``: the exact order the operator said yes to.

    The desk writes it from the proposal's ``order`` block after ``wait-for-reply`` lists the
    number under ``approved``. A buy carries the exit floor it was approved with, so the
    protective sell is authorized by the same yes.
    """
    model_config = ConfigDict(allow_inf_nan=False)
    as_of: date
    ref: str = Field(min_length=4, max_length=16)
    n: int = Field(ge=1, le=999)
    symbol: str = Field(min_length=1, max_length=24)
    side: Literal["buy", "sell"]
    qty: int = Field(gt=0)
    limit: float = Field(gt=0)
    multiplier: Literal[1, 100] = 1
    setup_hash: str | None = None
    exit_floor: float | None = Field(default=None, gt=0)
    decided_at: str = ""

    @model_validator(mode="after")
    def _exit_floor_side(self) -> TelegramApproval:
        if self.side == "sell" and self.exit_floor is not None:
            raise ValueError("a sell proposal carries no exit_floor")
        return self

    def lines(self) -> list[ApprovalLine]:
        bound = {"limit_max": self.limit} if self.side == "buy" else {"limit_min": self.limit}
        out = [ApprovalLine(symbol=self.symbol, side=self.side, max_qty=self.qty, max_total_qty=self.qty,
                            multiplier=self.multiplier, setup_hash=self.setup_hash, **bound)]
        if self.side == "buy" and self.exit_floor is not None:
            out.append(ApprovalLine(symbol=self.symbol, side="sell", max_qty=self.qty, max_total_qty=self.qty,
                                    multiplier=self.multiplier, setup_hash=self.setup_hash,
                                    limit_min=self.exit_floor))
        return out


def telegram_approvals(events: list[dict], today: date) -> list[TelegramApproval]:
    """Today's journaled Telegram approvals, in journal order; malformed rows are skipped, never guessed at."""
    out: list[TelegramApproval] = []
    for record in events:
        if record.get("type") != TELEGRAM_APPROVAL_EVENT:
            continue
        try:
            approval = TelegramApproval.model_validate(record.get("payload") or {})
        except ValueError:
            continue
        if approval.as_of == today:
            out.append(approval)
    return out


def _decided_at(text: str, today: date) -> datetime:
    """The approval's own time when it parses, else the start of its day; always tz-aware."""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        moment = datetime.combine(today, datetime.min.time())
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def authorization_record(mode: str, today: date) -> dict:
    """The authorization stamp an order.requested carries: which yes let it through."""
    if mode == MODE_PROTECTIVE:
        return {"kind": MODE_PROTECTIVE, "as_of": today.isoformat()}
    return {"kind": "telegram" if mode == MODE_ASK else "envelope", "as_of": today.isoformat()}


def telegram_batch(events: list[dict], today: date) -> ApprovalBatch | None:
    """The "Ask me" authority: an envelope made of exactly today's approved proposals.

    Each approval is one line (plus its exit line for a buy). The same symbol and side
    approved twice adds up: quantities sum and the bound is the one the operator accepted
    last, which is what two separate yeses mean. ``max_orders`` is the number of lines, so
    the budget is one order per approved line and nothing more.
    """
    approvals = telegram_approvals(events, today)
    if not approvals:
        return None
    merged: dict[tuple[str, str], ApprovalLine] = {}
    for approval in approvals:
        for line in approval.lines():
            key = (line.symbol, line.side)
            prior = merged.get(key)
            if prior is None:
                merged[key] = line
                continue
            total = (prior.max_total_qty or prior.max_qty) + (line.max_total_qty or line.max_qty)
            merged[key] = line.model_copy(update={"max_qty": max(prior.max_qty, line.max_qty),
                                                  "max_total_qty": total})
    refs = ", ".join(f"#{a.n}@{a.ref}" for a in approvals)
    return ApprovalBatch(
        as_of=today,
        approved_at=_decided_at(approvals[-1].decided_at, today),
        approved_by="operator (Telegram /approve)",
        max_orders=len(merged),
        orders=list(merged.values()),
        note=f"Ask me: journaled Telegram approvals {refs}"[:400],
    )


def resolve_batch(envelope_path: Path | None, events: list[dict], today: date) -> tuple[ApprovalBatch | None, str, str]:
    """Pick today's authority: (batch, mode, reason).

    A same-day envelope file means "Within my bounds" and wins. Otherwise today's journaled
    Telegram approvals form the batch ("Ask me"). An envelope dated another day or unreadable
    is ignored with its reason stated; it never falls through to a stale authority.
    """
    if envelope_path is not None and envelope_path.is_file():
        try:
            batch = ApprovalBatch.model_validate_json(envelope_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            envelope_note = f"envelope invalid ({str(exc)[:120]})"
        else:
            if batch.valid_on(today):
                # An envelope covers only its own lines. Today's Telegram yeses still count for
                # everything else, so a sell-only exit note never silences "Ask me" for entries
                # (the 24 Nov premarket fire sent no approval cards for exactly that reason).
                asked = telegram_batch(events, today)
                if asked is not None:
                    extra = [line for line in asked.orders if batch.line_for(line.symbol, line.side) is None]
                    if extra:
                        batch = batch.model_copy(update={
                            "orders": [*batch.orders, *extra],
                            "max_orders": batch.max_orders + len(extra),
                            "note": (batch.note + " | plus " + asked.note)[:400],
                        })
                        return batch, MODE_BOUNDS, (f"within my bounds for {today}, plus {len(extra)} "
                                                    "Telegram-approved line(s)")
                return batch, MODE_BOUNDS, f"within my bounds: envelope armed for {today}"
            envelope_note = f"envelope dated {batch.as_of} is not valid today"
    else:
        envelope_note = "no envelope"
    batch = telegram_batch(events, today)
    if batch is not None:
        return batch, MODE_ASK, f"ask me: {len(batch.orders)} journaled Telegram-approved line(s) for {today} ({envelope_note})"
    return None, MODE_ASK, f"ask me: no Telegram approval journaled today ({envelope_note}); nothing may be submitted"


def envelope_usage(journal_path: Path, today: date) -> int:
    """Count today's operator-authorized order.requested events in the journal (both modes)."""
    count = 0
    events = read_events(journal_path)
    cancelled = cancelled_request_ids(events)
    for record in events:
        if record.get("type") != "order.requested":
            continue
        payload = record.get("payload", {})
        auth = payload.get("authorization") or {}
        if (auth.get("kind") in OPERATOR_AUTHORIZATION_KINDS and auth.get("as_of") == today.isoformat()
                and str(payload.get("request_id")) not in cancelled):
            count += 1
    return count


def envelope_totals(events: list[dict], today: date, symbol: str, side: str) -> tuple[int, float]:
    cancelled = cancelled_request_ids(events)
    rows = [e.get("payload", {}) for e in events if e.get("type") == "order.requested"
            and e.get("payload", {}).get("authorization", {}).get("kind") in OPERATOR_AUTHORIZATION_KINDS
            and e.get("payload", {}).get("authorization", {}).get("as_of") == today.isoformat()
            and str(e.get("payload", {}).get("request_id")) not in cancelled]
    qty = sum(int(r.get("quantity", r.get("qty", 0))) for r in rows
              if r.get("symbol") == symbol and r.get("side") == side)
    return qty, sum(request_notional(r) for r in rows)


def authorize_order(
    batch: ApprovalBatch,
    *,
    symbol: str,
    side: str,
    qty: int,
    limit: float | None,
    today: date,
    used: int,
    used_qty: int = 0,
    used_notional: float = 0.0,
    multiplier: int = 1,
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
    if limit is None or not 0 < limit < float("inf"):
        return False, "envelope requires a finite positive limit; no market orders"
    if line.multiplier != multiplier:
        return False, "instrument multiplier differs from approved product"
    if used_qty + qty > (line.max_total_qty or line.max_qty):
        return False, "cumulative quantity exceeds daily symbol-side approval"
    if batch.max_notional is not None and used_notional + qty * limit * multiplier > batch.max_notional:
        return False, "cumulative envelope notional budget exhausted"
    if side == "buy" and limit > line.limit_max:
        return False, f"limit {limit} above approved ceiling {line.limit_max} for {symbol}"
    if side == "sell" and limit < line.limit_min:
        return False, f"limit {limit} below approved floor {line.limit_min} for {symbol}"
    if used >= batch.max_orders:
        return False, f"envelope order budget exhausted ({used}/{batch.max_orders} used today)"
    bound = line.limit_max if side == "buy" else line.limit_min
    return True, f"within operator envelope {batch.as_of}: {symbol} {side} <= {line.max_qty} @ {bound} ({used + 1}/{batch.max_orders})"