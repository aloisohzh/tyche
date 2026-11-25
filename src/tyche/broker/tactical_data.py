"""Normalize the observed MCP quote/chain/book payloads; no network calls or writes."""
from __future__ import annotations

from datetime import UTC, date, datetime

from tyche.models import OptionContract, looks_like_option
from tyche.tactical import MarketQuote


def successful(payload: dict):
    if payload.get("ret_code") != 0 or "data" not in payload:
        raise ValueError("successful MCP payload required")
    return payload["data"]


# A venue whose book stopped updating this long before the newest venue is a dead feed, not the market.
VENUE_LAG_MS = 300_000


def consolidate_book(books: list[dict]) -> tuple[float, float, datetime] | None:
    """NBBO across the venue books in one MCP row.

    The best bid can come from one venue and the best ask from another; that is
    a single consolidated top of book, not an ambiguous choice. The timestamp is
    the oldest contributing venue so consolidation never masks a stale side. A
    venue with no timestamp, or one that fell minutes behind the others, does not
    contribute at all: one silent venue used to date the whole book in 1970.
    """
    def prices(levels) -> list[float]:
        # A level saved without its size still names a price someone quoted; only a stated zero is empty.
        return [float(r["price"]) for r in levels or []
                if float(r.get("price") or 0) > 0 and float(r.get("volume", 1) or 0) > 0]

    venues = []
    for book in books:
        v_bids, v_asks = prices(book.get("bid_list")), prices(book.get("ask_list"))
        try:
            stamp = int(book.get("exchange_data_time_ms") or 0)
        except (TypeError, ValueError):
            stamp = 0
        if v_bids and v_asks and stamp > 0:
            venues.append((max(v_bids), min(v_asks), stamp))
    if not venues:
        return None  # no executable two-sided market on any venue
    newest = max(stamp for _, _, stamp in venues)
    venues = [v for v in venues if newest - v[2] <= VENUE_LAG_MS]
    return (max(b for b, _, _ in venues), min(a for _, a, _ in venues),
            datetime.fromtimestamp(min(s for _, _, s in venues) / 1000, UTC))


def synthetic_book(last: float, at: datetime, spread_pct: float) -> tuple[float, float, datetime]:
    """A two-sided market around the last trade for a stock saved without its order book.

    The last-trade time is the book's age, so before the open (when the last trade is yesterday's close)
    this is never fresh and the real book is still required. Liquid large caps trade inside a few
    basis points; an order priced here either trades at once or rests a tick away from the market.
    """
    half = spread_pct / 2
    return round(last * (1 - half), 2), round(last * (1 + half), 2), at


def normalize_quotes(quote_payload: dict, book_payloads: list[dict], chain_payloads: list[dict],
                     *, synthetic_spread_pct: float | None = None,
                     contracts: dict[str, OptionContract] | None = None,
                     problems: list[str] | None = None) -> list[MarketQuote]:
    """Quotes joined to their order books.

    With `synthetic_spread_pct`, a stock that has a quote but no saved book still gets a market (see
    `synthetic_book`); an option never does. `contracts` is option metadata the caller already holds
    (a watchlist entry's own contract block), used when no chain payload names the symbol. With
    `problems`, one bad row is named there and skipped instead of failing every other symbol.
    """
    def skip(text: str) -> None:
        if problems is None:
            raise ValueError(text)
        problems.append(text)

    books = {}
    for payload in book_payloads:
        try:
            rows = successful(payload)
        except (ValueError, AttributeError):
            skip("an order-book payload reports an error; its symbol has no book")
            continue
        for row in [rows] if isinstance(rows, dict) else rows:   # one symbol saved without the list around it
            try:
                code = row["code"]
                consolidated = consolidate_book(row["books"])
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                if problems is None:
                    raise
                problems.append(f"an order-book row is unusable ({type(exc).__name__}: {str(exc)[:60]}); "
                                "its symbol has no book")
                continue
            if code in books:
                skip(f"{code}: duplicate order book")
                continue
            if consolidated is None:
                continue
            books[code] = consolidated
    held = dict(contracts or {})
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
    for symbol, contract in held.items():
        contracts.setdefault(symbol, contract)
    out = []
    seen: set[str] = set()
    for row in successful(quote_payload)["quote_list"]:
        try:
            symbol = row["code"]
            at = datetime.fromtimestamp(int(row["data_time"]) / 1000, UTC)
            if float(row.get("last_price") or 0) <= 0:
                raise ValueError("no last price")
        except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
            if problems is None:
                raise
            label = row.get("code", "?") if isinstance(row, dict) else "?"
            problems.append(f"{label}: quote row unusable ({type(exc).__name__}: {str(exc)[:60]}); not priced this run")
            continue
        if symbol in seen and problems is not None:
            continue  # the same symbol quoted twice: the first row stands
        seen.add(symbol)
        if symbol in books:
            bid, ask, book_at = books[symbol]
        elif synthetic_spread_pct and not looks_like_option(symbol) and float(row.get("last_price") or 0) > 0:
            bid, ask, book_at = synthetic_book(float(row["last_price"]), at, synthetic_spread_pct)
        else:
            continue
        option = None
        extra = {}
        if looks_like_option(symbol):
            option = contracts.get(symbol)
            data = row.get("option_ex_data") or {}
            if (option is None or float(data.get("contract_multiplier", 0)) != 100
                    or float(data.get("strike_price", 0)) != option.strike
                    or data.get("option_type") != option.right.upper()):
                skip(f"{symbol}: quote needs matching standard-chain metadata and multiplier")
                continue
            extra = {"open_interest": data.get("open_interest") or 0, "delta": data.get("delta"),
                     "implied_volatility": data.get("implied_volatility")}
        out.append(MarketQuote(
            symbol=symbol, at=at,
            book_at=book_at, last=row["last_price"], bid=bid, ask=ask,
            tradable=row.get("sec_status") == "NORMAL" and row.get("suspension") is False,
            option=option, volume=row.get("volume") or 0, **extra,
        ))
    return out
