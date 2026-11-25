"""Cumulative paper budgets and conservative broker-order reconciliation."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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
            # An option row with no chain metadata to hand is still a standard 100-share contract here;
            # counting it at 100 is the conservative budget, and a missing chain never stops the run.
            multiplier = contract.multiplier if contract else (100 if looks_like_option(symbol) else 1)
            notional += float(row["qty"]) * float(row["price"]) * multiplier
    return len(current) + len(unmatched), notional


# Broker status 2 is the one verified "still working" state. Everything else with zero fills that
# was created before today's US session (ET) is a DAY order the broker has expired: the operator
# ruled on 2026-11-24 (VNQ ...597, SMH ...500) that this counts as finished, not "unresolved".
WORKING_STATUS = 2
FILLED_STATUS = 4
# Status 5 is terminal: the order is cancelled or expired and can never trade again. Seen going 2 -> 5
# twice, SMH ...500 two minutes after it was placed (a cancel) and VNQ ...597 at the end of its DAY,
# and still 5 on every later read. Treating a same-day 5 as "unresolved" blocked its symbol until the
# next session (2026-11-25 review), so a cancelled order is finished the moment the broker says so.
DEAD_STATUS = 5
# Remark prefixes of the desk's own orders: the request_id each one carries as its broker text.
SCALP_PREFIX, TACTICAL_PREFIX, EXIT_PREFIX = "tyche-scl-", "tyche-tac-", "tyche-exit-"
# How long a reserved request may still be on its way to the broker when it names no submit_before.
DEFAULT_SUBMIT_WINDOW_SECONDS = 900


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
    """Nothing more can trade on it: a full fill, a cancelled/expired order, or a stale zero-fill row."""
    if row.get("status") == FILLED_STATUS and float(row.get("cum_qty", 0)) == float(row.get("qty", 0)):
        return True
    if row.get("status") == DEAD_STATUS:
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


def _broker_time(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000, UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _request_rows(events: list[dict], rows: list[dict]) -> list[tuple[dict, dict, list[dict]]]:
    """Every reserved request with the broker order(s) that carry it: (event, payload, matching rows)."""
    submitted = {e.get("payload", {}).get("request_id"): e.get("payload", {}).get("order_id")
                 for e in events if e.get("type") == "order.submitted"}
    out = []
    for event in events:
        payload = event.get("payload", {})
        if event.get("type") != "order.requested" or not payload.get("request_id"):
            continue
        receipt = submitted.get(payload["request_id"])
        matches = [r for r in rows if r.get("text") == payload["request_id"]
                   or (receipt is not None and str(r.get("order_id")) == str(receipt))]
        out.append((event, payload, matches))
    return out


def _window_open(event: dict, payload: dict, now: datetime) -> bool:
    """Whether the executor may still be about to send this request."""
    try:
        deadline = datetime.fromisoformat(payload["submit_before"])
    except (KeyError, TypeError, ValueError):
        try:
            deadline = datetime.fromisoformat(event["ts"]) + timedelta(seconds=DEFAULT_SUBMIT_WINDOW_SECONDS)
        except (KeyError, TypeError, ValueError):
            return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return now < deadline


def closed_request_ids(events: list[dict]) -> set[str]:
    """Requests the journal already shows finished: filled, rejected, cancelled, or never sent.

    `gate.wait` is the executor saying a submit was blocked and did not go out, so that request is
    over the moment it is journaled; nothing has to wait for its window to run down.
    """
    return {str(e.get("payload", {}).get("request_id")) for e in events
            if e.get("type") in ("order.filled", "order.rejected", "order.cancelled", "gate.wait")
            and e.get("payload", {}).get("request_id")}


def in_flight_symbols(events: list[dict], rows: list[dict], now: datetime | None = None) -> set[str]:
    """Symbols with a reserved order the broker does not show yet and that may still be sent.

    A second order for such a symbol could double the first, so it waits. Once the submit window has
    closed with no broker order, the request never reached the broker: it is dead and blocks nothing.
    """
    now = now or datetime.now(UTC)
    closed = closed_request_ids(events)
    return {payload["symbol"] for event, payload, matches in _request_rows(events, rows)
            if not matches and payload["request_id"] not in closed and payload.get("symbol")
            and _window_open(event, payload, now)}


def dead_request_ids(events: list[dict], rows: list[dict], now: datetime | None = None) -> set[str]:
    """Reserved requests that never reached the broker: no order, no receipt, window closed."""
    now = now or datetime.now(UTC)
    receipts = {e.get("payload", {}).get("request_id") for e in events
                if e.get("type") in ("order.submitted", "order.filled")}
    blocked = {e.get("payload", {}).get("request_id") for e in events if e.get("type") == "gate.wait"}
    return {payload["request_id"] for event, payload, matches in _request_rows(events, rows)
            if not matches and payload["request_id"] not in receipts
            and (payload["request_id"] in blocked or not _window_open(event, payload, now))}


def unresolved_symbols(events: list[dict], rows: list[dict], now: datetime | None = None) -> set[str]:
    """Symbols a new order must wait for: an order working at the broker, or one still on its way.

    Before 2026-11-25 every reservation blocked its symbol until a full fill, forever: a request that
    was never submitted froze the symbol for good, a resting take-profit froze the stop behind it, and
    a receipt that differed from the reservation raised and ended the whole run. Now the broker's own
    list decides: working blocks, finished (filled, cancelled, expired) does not, and an unsent request
    blocks only while its submit window is open.
    """
    now = now or datetime.now(UTC)
    today = now.astimezone(ET).date()
    pending = set(in_flight_symbols(events, rows, now))
    for _, payload, matches in _request_rows(events, rows):
        if payload.get("symbol") and any(not order_finished(r, today) for r in matches):
            pending.add(payload["symbol"])
    return pending


def receipts_to_journal(events: list[dict], rows: list[dict], today: date, *,
                        days_back: int = 1) -> tuple[list[tuple[str, dict]], list[str]]:
    """What the broker shows for the desk's own orders that the journal still lacks.

    Returns the (event type, payload) rows to append, oldest order first, plus plain-word alerts. The
    order list is the truth about receipts, fills and cancels, so nobody has to type them in by hand:
    a submitted order gets its order.submitted, a finished one its order.filled (once, for what filled)
    or order.cancelled (nothing filled). Only orders created today are touched by default; `days_back`
    widens that window deliberately, because an order the desk placed on another machine - a paused
    cloud card, a second laptop - is the same broker fact and the ledger has to learn it. History stays
    history: the window reaches back, it never rewrites a row that is already in the journal.
    """
    from tyche.models import looks_like_option
    requests = {p["request_id"]: p for _, p, _ in _request_rows(events, [])}
    have = {kind: {} for kind in ("order.submitted", "order.filled", "order.cancelled", "order.rejected")}
    for event in events:
        rid = event.get("payload", {}).get("request_id")
        if event.get("type") in have and rid:
            have[event["type"]][rid] = have[event["type"]].get(rid, 0.0) + float(
                event["payload"].get("quantity") or 0)
    out: list[tuple[str, dict]] = []
    alerts: list[str] = []
    for row in sorted(rows, key=lambda r: int(r.get("create_time") or 0)):
        rid = str(row.get("text") or "")
        created = _broker_time(row.get("create_time"))
        if not rid.startswith((SCALP_PREFIX, TACTICAL_PREFIX, EXIT_PREFIX)) or created is None:
            continue
        if created.astimezone(ET).date() < today - timedelta(days=max(1, days_back) - 1):
            continue
        symbol = order_symbol(row)
        side = {1: "buy", 2: "sell"}.get(row.get("side"))
        if side is None:
            continue
        request = requests.get(rid, {})
        strategy = request.get("strategy_id") or (
            "PB-004" if rid.startswith(SCALP_PREFIX) else "operator-exit" if rid.startswith(EXIT_PREFIX)
            else "PB-003" if looks_like_option(symbol) else "PB-002")
        quantity, filled = float(row.get("qty") or 0), float(row.get("cum_qty") or 0)
        base = {"request_id": rid, "order_id": str(row.get("order_id")), "symbol": symbol, "side": side,
                "strategy_id": strategy, "broker_status": row.get("status"), "source": "broker order list"}
        if request.get("option"):
            base["option"] = request["option"]
            base["multiplier"] = request.get("multiplier", 100)
        if request and (request.get("symbol") != symbol or request.get("side") != side
                        or float(request.get("quantity") or 0) != quantity
                        or float(request.get("limit_price") or 0) != float(row.get("price") or 0)):
            alerts.append(f"{symbol}: broker order {row.get('order_id')} differs from what was reserved "
                          f"({side} {quantity:g} @ {row.get('price')} against {request.get('side')} "
                          f"{request.get('quantity')} @ {request.get('limit_price')})")
        if rid not in have["order.submitted"]:
            out.append(("order.submitted", {**base, "quantity": quantity, "limit_price": float(row.get("price") or 0)}))
        terminal = row.get("status") in (FILLED_STATUS, DEAD_STATUS)
        already = have["order.filled"].get(rid, 0.0)
        if terminal and filled > already:
            price = float(row.get("avg_fill_price") or 0) or float(row.get("price") or 0)
            moment = _broker_time(row.get("update_time")) or created
            out.append(("order.filled", {**base, "quantity": filled - already, "price": price,
                                         "filled_at": moment.isoformat()}))
        if (row.get("status") == DEAD_STATUS and filled == 0
                and rid not in have["order.cancelled"] and rid not in have["order.rejected"]):
            out.append(("order.cancelled", {**base, "reason": "broker shows the order cancelled or expired unfilled"}))
    return out, alerts
