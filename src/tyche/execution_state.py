"""Cumulative paper budgets and conservative broker-order reconciliation."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from tyche.market_calendar import ET
from tyche.models import OptionContract, OrderIntent, Side


def day_requests(events: list[dict], today) -> list[dict]:
    rows = []
    for event in events:
        if event.get("type") != "order.requested":
            continue
        payload = event.get("payload", {})
        as_of = payload.get("authorization", {}).get("as_of")
        if not as_of:
            stamp = datetime.fromisoformat(event["ts"])
            as_of = stamp.astimezone(ET).date().isoformat()
        if as_of == today.isoformat():
            rows.append(payload)
    return rows


def request_notional(row: dict) -> float:
    quantity = float(row.get("quantity", row.get("qty", 0)))
    price = float(row.get("limit_price", row.get("price", 0)))
    option = row.get("option") or {}
    multiplier = int(row.get("multiplier", option.get("multiplier", 1)))
    return quantity * price * multiplier


def daily_usage(events: list[dict], today) -> tuple[int, float]:
    rows = day_requests(events, today)
    # Requested orders reserve the budget even after a timeout/rejection; never retry blind.
    return len(rows), sum(request_notional(row) for row in rows if row.get("side") == "buy")


def combined_usage(events: list[dict], rows: list[dict], today, contracts: dict) -> tuple[int, float]:
    """Broker orders plus unmatched journal requests, without double counting."""
    requested = day_requests(events, today)
    receipts = {e.get("payload", {}).get("request_id"): str(e.get("payload", {}).get("order_id"))
                for e in events if e.get("type") == "order.submitted"}
    ids = {str(r["order_id"]) for r in rows}
    remarks = {r.get("text") for r in rows if r.get("text")}
    unmatched = [r for r in requested if not (
        receipts.get(r.get("request_id")) in ids
        or (r.get("request_id") and r["request_id"] in remarks)
        or (r.get("remark") and r["remark"] in remarks)
        or str(r.get("order_id")) in ids
    )]
    current = [r for r in rows if datetime.fromtimestamp(
        int(r["create_time"]) / 1_000_000, UTC).astimezone(ET).date() == today]
    notional = sum(request_notional(r) for r in unmatched if r.get("side") == "buy")
    from tyche.models import looks_like_option
    for row in current:
        if row.get("side") == 1:
            symbol = order_symbol(row)
            contract = contracts.get(symbol)
            if looks_like_option(symbol) and contract is None:
                raise ValueError("daily option budget requires verified contract metadata")
            notional += float(row["qty"]) * float(row["price"]) * (contract.multiplier if contract else 1)
    return len(current) + len(unmatched), notional


# Broker status 2 is the one verified "still working" state. Everything else with zero fills that
# was created before today's US session (ET) is a DAY order the broker has expired: the operator
# ruled on 2026-11-24 (VNQ ...597, SMH ...500) that this counts as finished, not "unresolved".
WORKING_STATUS = 2


def expired_unfilled(status, quantity, cum_qty, created_us, today: date) -> bool:
    """True for a zero-fill order from an earlier session that is not shown as working."""
    try:
        if float(cum_qty) != 0 or float(quantity) <= 0 or status in (4, WORKING_STATUS):
            return False
        created = datetime.fromtimestamp(int(created_us) / 1_000_000, UTC).astimezone(ET).date()
    except (TypeError, ValueError, OverflowError):
        return False  # unparseable stays blocking: never guess an order finished
    return created < today


def order_finished(row: dict, today: date | None = None) -> bool:
    """Full verified fill, or a zero-fill order from a past session (see expired_unfilled)."""
    if row.get("status") == 4 and float(row.get("cum_qty", 0)) == float(row.get("qty", 0)):
        return True
    today = today or datetime.now(UTC).astimezone(ET).date()
    return expired_unfilled(row.get("status"), row.get("qty"), row.get("cum_qty", 0),
                            row.get("create_time"), today)


def broker_orders(payload: Any) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("ret_code") != 0:
        raise ValueError("successful broker order-list payload required")
    if payload.get("pagination", {}).get("has_more"):
        raise ValueError("order list incomplete: fetch all pages before planning")
    rows = payload.get("data", {}).get("orders")
    if not isinstance(rows, list):
        raise TypeError("broker orders array missing")
    ids = [str(r["order_id"]) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate broker order IDs")
    return rows


def order_symbol(row: dict) -> str:
    symbol = str(row.get("symbol", ""))
    return symbol if "." in symbol else f"US.{symbol}"


def pending_intents(rows: list[dict], contracts: dict[str, OptionContract]) -> list[OrderIntent]:
    out = []
    for row in rows:
        quantity, cumulative = float(row["qty"]), float(row["cum_qty"])
        if not quantity.is_integer() or not cumulative.is_integer() or not 0 <= cumulative <= quantity or quantity <= 0:
            raise ValueError("invalid broker quantity or cumulative fill")
        qty, filled = int(quantity), int(cumulative)
        # FILLED (4) is verified terminal; a zero-fill order from a past session is expired.
        if order_finished(row):
            continue
        remaining = qty - filled
        if remaining <= 0:
            raise ValueError("inconsistent broker order status/quantity")
        symbol = order_symbol(row)
        side = row.get("side")
        if side not in (1, 2):
            raise ValueError("unknown broker order side")
        out.append(OrderIntent(
            symbol=symbol, option=contracts.get(symbol), side=Side.BUY if side == 1 else Side.SELL,
            quantity=remaining, limit_price=float(row["price"]), reason="resting/unresolved broker order",
        ))
    return out


def unresolved_symbols(events: list[dict], rows: list[dict]) -> set[str]:
    """Atomic reservations remain blocked until their broker receipt is reconciled."""
    submitted = {e.get("payload", {}).get("request_id"): e.get("payload", {}).get("order_id")
                 for e in events if e.get("type") == "order.submitted"}
    filled_ids = {str(r.get("order_id")) for r in rows if order_finished(r)}
    pending = set()
    for event in events:
        p = event.get("payload", {})
        if event.get("type") == "order.requested" and p.get("request_id"):
            matches = [r for r in rows if str(r.get("order_id")) == str(submitted.get(p["request_id"]))
                       or r.get("text") == p["request_id"]]
            if len(matches) > 1:
                raise ValueError("ambiguous reservation receipt")
            if matches:
                r = matches[0]
                if (order_symbol(r) != p["symbol"]
                        or r.get("side") != (1 if p["side"] == "buy" else 2)
                        or float(r["qty"]) != p["quantity"]
                        or float(r["price"]) != p["limit_price"]):
                    raise ValueError("broker receipt does not match reserved order")
            if not matches or str(matches[0]["order_id"]) not in filled_ids:
                pending.add(p["symbol"])
    return pending
