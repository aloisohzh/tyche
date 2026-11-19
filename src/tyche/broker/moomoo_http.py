from __future__ import annotations

import http.client
import json
import os
import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote, urlencode

from tyche.lifecycle import Reservation, account_hash
from tyche.models import looks_like_option


class PaperApiError(ValueError):
    pass


def successful_payload(payload: dict) -> dict:
    if (not isinstance(payload, dict) or type(payload.get("ret_code")) is not int
            or payload["ret_code"] != 0 or not isinstance(payload.get("data"), dict)
            or payload.get("error") or payload.get("skipped")):
        raise PaperApiError("failed or incomplete paper API response")
    return payload


def complete_order_rows(pages: list[dict]) -> list[dict]:
    if not pages:
        raise PaperApiError("order pages missing")
    rows = []
    for index, page in enumerate(pages):
        successful_payload(page)
        more = (page.get("pagination") or {}).get("has_more")
        if type(more) is not bool or more != (index < len(pages) - 1):
            raise PaperApiError("explicit consecutive order pagination completeness required")
        batch = page["data"].get("orders")
        if not isinstance(batch, list):
            raise PaperApiError("order array missing")
        rows.extend(batch)
    ids = [str(row["order_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise PaperApiError("duplicate broker order IDs")
    return rows


class MoomooPaperHttp:
    def __init__(self, token: str):
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise PaperApiError("dedicated Moomoo OAuth access token required")
        self._token = token

    @classmethod
    def from_env(cls) -> MoomooPaperHttp:
        return cls(os.environ.get("TYCHE_MOOMOO_ACCESS_TOKEN", ""))

    def _request(self, method, path, body=None, *, deadline=None, clock=None):
        clock = clock or (lambda: datetime.now(UTC))
        conn = http.client.HTTPSConnection("webapi.moomoo.com", timeout=15)
        try:
            encoded = json.dumps(body, allow_nan=False).encode() if body is not None else None
            conn.connect()
            if deadline is not None and clock() >= deadline:
                raise PaperApiError("submission window expired; reservation retained")
            # http.client sends once and does not follow redirects or retry POSTs.
            conn.request(method, path, body=encoded, headers={
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json", "User-Agent": "tyche/0.1",
                "X-Client-Name": "tyche", "X-Cli-Cmd": "lifecycle execute-exit",
            })
            response = conn.getresponse()
            if not 200 <= response.status < 300:
                raise PaperApiError("paper API request failed; no automatic retry")
            data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise PaperApiError("paper API response exceeds size limit")
            return successful_payload(json.loads(data))
        except (OSError, http.client.HTTPException, ValueError):
            raise PaperApiError("paper API transport or response failed; no automatic retry") from None
        finally:
            conn.close()

    def _orders(self, path: str) -> list[dict]:
        pages, seen = [], set()
        query = {"market": 100}
        for _ in range(100):
            page = self._request("GET", path + "?" + urlencode(query))
            pages.append(page)
            pagination = page.get("pagination") or {}
            if pagination.get("has_more") is False:
                return complete_order_rows(pages)
            cursor = pagination.get("next_key")
            if (pagination.get("has_more") is not True or not isinstance(cursor, str)
                    or not cursor or cursor in seen):
                raise PaperApiError("incomplete or repeated broker pagination cursor")
            seen.add(cursor)
            query["next_key"] = cursor
        raise PaperApiError("broker order pagination limit reached; incomplete history")

    def read(self, account_id: str, symbol: str, account_types, *, clock) -> dict:
        observed_at = clock()
        accounts = self._request("GET", "/api/v1.0/sim-trade/accounts")
        matches = [a for a in accounts["data"]["accounts"]
                   if str(a["account_id"]) == account_id]
        if (len(matches) != 1 or matches[0].get("market_id") != 100
                or matches[0].get("account_type") not in account_types):
            raise PaperApiError("unverified US paper account")
        base = "/api/v1.0/sim-trade/" + quote(account_id, safe="")
        history = self._orders(base + "/history-orders")
        current = self._orders(base + "/orders")
        merged = {str(row["order_id"]): row for row in history}
        fields = ("symbol", "side", "qty", "cum_qty", "status", "price", "create_time", "text")
        for row in current:
            prior = merged.get(str(row["order_id"]))
            if prior and any(prior.get(field) != row.get(field) for field in fields):
                raise PaperApiError("broker orders changed during capture; reconcile on next check")
            merged[str(row["order_id"])] = row
        cash = self._request("GET", base + "/cash-info")
        positions = self._request("GET", base + "/positions?market=100")
        quotes = self._request("POST", "/api/v1.0/quote/stock-quote", {"code_list": [symbol]})
        if not {"balance", "hold", "total_asset"} <= cash["data"].keys():
            raise PaperApiError("explicit cash, frozen funds and NAV required")
        if any((p.get("pagination") or {}).get("has_more") for p in (accounts, cash, positions, quotes)):
            raise PaperApiError("incomplete account, position or quote response")
        return {"accounts": accounts, "cash": cash, "positions": positions,
                "quotes": quotes, "orders": list(merged.values()), "observed_at": observed_at}

    def submit_exit(self, account_id: str, request: Reservation, *, deadline, clock) -> str:
        if (request.side != "sell" or request.account_hash != account_hash(account_id)
                or not re.fullmatch(r"US\.[A-Z][A-Z0-9.]*", request.symbol)
                or looks_like_option(request.symbol)
                or Decimal(str(request.limit_price)) != Decimal(f"{request.limit_price:.2f}")):
            raise PaperApiError("only exact account-bound stock/ETF limit exits are supported")
        result = self._request(
            "POST", "/api/v1.0/sim-trade/" + quote(account_id, safe="") + "/orders",
            {"market": 100, "symbol": request.symbol.removeprefix("US."),
             "order_side": 2, "order_type": 1, "qty": str(request.quantity),
             "price": f"{request.limit_price:.2f}", "order_trade_time_type": 1,
             "text": request.request_id}, deadline=deadline, clock=clock,
        )
        order_id = result["data"].get("order_id")
        if not isinstance(order_id, (str, int)) or isinstance(order_id, bool) or not str(order_id).strip():
            raise PaperApiError("broker receipt missing; outcome unknown, do not retry")
        return str(order_id)
