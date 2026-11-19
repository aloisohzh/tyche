"""Normalize the observed MCP quote/chain/book payloads; no network calls or writes."""
from __future__ import annotations

from datetime import UTC, date, datetime

from tyche.models import OptionContract, looks_like_option
from tyche.tactical import MarketQuote


def successful(payload: dict):
    if payload.get("ret_code") != 0 or "data" not in payload:
        raise ValueError("successful MCP payload required")
    return payload["data"]


def normalize_quotes(quote_payload: dict, book_payloads: list[dict], chain_payloads: list[dict]) -> list[MarketQuote]:
    books = {}
    for payload in book_payloads:
        for row in successful(payload):
            code = row["code"]
            if code in books:
                raise ValueError("duplicate order book")
            candidates = row["books"]
            if len(candidates) != 1:
                raise ValueError("ambiguous exchange books; choose a verified consolidated book")
            book = candidates[0]
            bids = [r for r in book["bid_list"] if r["volume"] > 0 and r["price"] > 0]
            asks = [r for r in book["ask_list"] if r["volume"] > 0 and r["price"] > 0]
            if not bids or not asks:
                continue  # no executable two-sided market
            books[code] = (max(r["price"] for r in bids), min(r["price"] for r in asks),
                           datetime.fromtimestamp(int(book["exchange_data_time_ms"]) / 1000, UTC))
    contracts = {}
    for payload in chain_payloads:
        for row in successful(payload)["option_chain"]:
            if row["option_standard_type"] != "STANDARD" or int(row["lot_size"]) != 100:
                continue
            right = {"CALL": "call", "PUT": "put"}.get(row["option_type"])
            if right is None:
                raise ValueError("unrecognized option right")
            contract = OptionContract(underlying=row["stock_owner"], expiry=date.fromisoformat(row["strike_time"]),
                                      right=right, strike=row["strike_price"])
            if not contract.matches(row["code"]):
                raise ValueError("chain contract identity mismatch")
            if row["code"] in contracts and contracts[row["code"]] != contract:
                raise ValueError("conflicting chain metadata")
            contracts[row["code"]] = contract
    out = []
    for row in successful(quote_payload)["quote_list"]:
        symbol = row["code"]
        if symbol not in books:
            continue
        bid, ask, book_at = books[symbol]
        option = None
        extra = {}
        if looks_like_option(symbol):
            option = contracts.get(symbol)
            data = row.get("option_ex_data") or {}
            if (option is None or float(data.get("contract_multiplier", 0)) != 100
                    or float(data.get("strike_price", 0)) != option.strike
                    or data.get("option_type") != option.right.upper()):
                raise ValueError("quote needs matching standard-chain metadata and multiplier")
            extra = {"open_interest": data["open_interest"], "delta": data["delta"],
                     "implied_volatility": data["implied_volatility"]}
        out.append(MarketQuote(
            symbol=symbol, at=datetime.fromtimestamp(int(row["data_time"]) / 1000, UTC),
            book_at=book_at, last=row["last_price"], bid=bid, ask=ask,
            tradable=row.get("sec_status") == "NORMAL" and row.get("suspension") is False,
            option=option, volume=row["volume"], **extra,
        ))
    return out
