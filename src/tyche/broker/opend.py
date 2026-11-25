"""The paper account through moomoo OpenD and the official moomoo Python SDK (`pip install moomoo-api`).

The laptop runner's second road to the broker (2026-11-25), for a laptop that has OpenD, moomoo's
local gateway, but not the moomoo command line tool. It offers the same calls as `MoomooCli`, and
answers in the paper API's JSON shapes ({"ret_code": 0, "data": {...}}), so the runner's readers and
`tyche cycle` read one format whichever road the laptop uses.

Paper only, twice over: every trade-side call passes `TrdEnv.SIMULATE`, and the client first lists
OpenD's own accounts and refuses any id OpenD does not call a SIMULATE account with US rights. Live
accounts are never written to the run folder.
"""
from __future__ import annotations

import importlib
import math
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from tyche.broker.moomoo_cli import MoomooCliError
from tyche.market_calendar import ET

HOST, PORT = "127.0.0.1", 11111
INSTALL = r".venv\Scripts\python.exe -m pip install moomoo-api"

# OpenD's order states as the paper API's numbers, which `tyche cycle` reads (execution_state: 2 is
# working, 4 filled, 5 finished for good). An order that can never trade again is 5 whatever ended it
# (cancelled, expired, refused, or cancelled after a partial fill, whose fill still counts from
# cum_qty). A state the table does not know stays 1, unresolved, so it blocks rather than guesses.
STATUS = {"UNSUBMITTED": 1, "WAITING_SUBMIT": 1, "SUBMITTING": 1, "TIMEOUT": 1,
          "SUBMITTED": 2, "CANCELLING_PART": 2, "CANCELLING_ALL": 2, "FILLED_PART": 3, "FILLED_ALL": 4,
          "CANCELLED_ALL": 5, "CANCELLED_PART": 5, "FAILED": 5, "SUBMIT_FAILED": 5, "DISABLED": 5,
          "DELETED": 5, "FILL_CANCELLED": 5}


class OpenDError(MoomooCliError):
    """OpenD or the SDK refused or failed a call (a MoomooCliError, so the runner handles both alike)."""


def _plain(value: Any) -> Any:
    """numpy/pandas scalars as plain JSON values (NaN as null), so `is False` and json.dumps behave."""
    if hasattr(value, "item") and not isinstance(value, (list, dict, str)):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class OpenDClient:
    """`MoomooCli`'s paper calls, answered by OpenD through the moomoo SDK."""

    def __init__(self, host: str = HOST, port: int = PORT, module: Any = None) -> None:
        self.host, self.port = host, port
        self._ft = module
        self._quote = None
        self._trade = None
        self._paper: set[str] | None = None

    # --- the road itself -------------------------------------------------------------------------

    def available(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                return True
        except OSError:
            return False

    def resolved_binary(self) -> str | None:
        return f"OpenD at {self.host}:{self.port}" if self.available() else None

    @property
    def ft(self) -> Any:
        if self._ft is None:
            try:
                self._ft = importlib.import_module("moomoo")
            except ImportError as exc:
                raise OpenDError(f"the moomoo Python package is not installed; paste: {INSTALL}") from exc
        return self._ft

    def _quote_ctx(self) -> Any:
        if self._quote is None:
            self._quote = self.ft.OpenQuoteContext(host=self.host, port=self.port)
        return self._quote

    def _trade_ctx(self) -> Any:
        if self._trade is None:
            self._trade = self.ft.OpenSecTradeContext(filter_trdmarket=self.ft.TrdMarket.US, host=self.host,
                                                      port=self.port)
        return self._trade

    def close(self) -> None:
        for ctx in (self._quote, self._trade):
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:  # noqa: BLE001, S110 - closing must never fail a run
                    pass
        self._quote = self._trade = None

    def _call(self, label: str, fn, *args, **kwargs) -> Any:
        try:
            answer = fn(*args, **kwargs)
        except OpenDError:
            raise
        except Exception as exc:
            raise OpenDError(f"OpenD {label} failed: {type(exc).__name__}: {exc}") from exc
        ret, data = answer[0], answer[1]
        if ret != self.ft.RET_OK:
            raise OpenDError(f"OpenD {label} failed: {data}")
        return data

    @staticmethod
    def _records(frame: Any) -> list[dict]:
        rows = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
        return [{key: _plain(value) for key, value in row.items()} for row in rows]

    # --- reads -----------------------------------------------------------------------------------

    def sim_accounts(self) -> dict:
        """OpenD's paper accounts with US rights, labelled as the paper API labels a US paper account.

        `tyche cycle` accepts only account_type 1/2 with market_id 100 (config.risk); only a row OpenD
        itself calls SIMULATE with US rights gets those labels. Live rows are left out entirely."""
        rows = self._records(self._call("account list", self._trade_ctx().get_acc_list))
        out: list[dict] = []
        paper: set[str] = set()
        for row in rows:
            markets = [str(m).upper() for m in (row.get("trdmarket_auth") or [])]
            if str(row.get("trd_env")).upper() != "SIMULATE" or "US" not in markets:
                continue
            account = str(row.get("acc_id"))
            paper.add(account)
            out.append({"account_id": account, "account_type": 2 if str(row.get("acc_type")).upper() == "MARGIN" else 1,
                        "market_id": 100, "trd_env": "SIMULATE", "acc_type": row.get("acc_type"),
                        "sim_acc_type": row.get("sim_acc_type"),
                        "competition_acc_name": row.get("competition_acc_name"), "source": "OpenD"})
        self._paper = paper
        return {"ret_code": 0, "data": {"accounts": out}}

    def _account(self, account: str) -> int | str:
        if self._paper is None:
            self.sim_accounts()
        if str(account) not in (self._paper or set()):
            raise OpenDError("OpenD does not list that account as a US paper (SIMULATE) account; "
                             "nothing was read or sent for it")
        return int(account) if str(account).isdigit() else str(account)  # the SDK's ids are numbers

    def sim_funds(self, account: str) -> dict:
        acc = self._account(account)
        frame = self._call("funds", self._trade_ctx().accinfo_query, trd_env=self.ft.TrdEnv.SIMULATE, acc_id=acc,
                           currency=self.ft.Currency.USD)
        rows = self._records(frame)
        if not rows:
            raise OpenDError("OpenD funds answer is empty")
        row = rows[0]
        return {"ret_code": 0, "data": {"balance": row.get("cash"), "hold": row.get("frozen_cash") or 0,
                                        "total_asset": row.get("total_assets"), "market_val": row.get("market_val"),
                                        "currency": "USD"}}

    def sim_positions(self, account: str, market: str = "US") -> dict:
        acc = self._account(account)
        frame = self._call("positions", self._trade_ctx().position_list_query, trd_env=self.ft.TrdEnv.SIMULATE,
                           acc_id=acc)
        out = []
        for row in self._records(frame):
            side = str(row.get("position_side") or "LONG").upper()
            cost = row.get("average_cost") or row.get("cost_price")
            out.append({"symbol": row.get("code"), "stock_name": row.get("stock_name"), "qty": row.get("qty"),
                        "qty_avbl": row.get("can_sell_qty"), "cost_price": cost, "cur_price": row.get("nominal_price"),
                        "market_val": row.get("market_val"), "pstn_type": 0 if side == "LONG" else 1})
        return {"ret_code": 0, "data": {"positions": out}}

    def _orders(self, frame: Any) -> list[dict]:
        out = []
        for row in self._records(frame):
            state = str(row.get("order_status") or "").upper()
            side = str(row.get("trd_side") or "").upper()
            out.append({"order_id": str(row.get("order_id")), "symbol": row.get("code"),
                        "side": {"BUY": "buy", "SELL": "sell"}.get(side, side), "qty": row.get("qty"),
                        "cum_qty": row.get("dealt_qty") or 0, "price": row.get("price"),
                        "avg_fill_price": row.get("dealt_avg_price"), "status": STATUS.get(state, 1),
                        "broker_status": state, "create_time": row.get("create_time"),
                        "update_time": row.get("updated_time") or row.get("create_time"),
                        "text": row.get("remark") or "", "order_type": row.get("order_type"),
                        "time_in_force": row.get("time_in_force"), "last_err_msg": row.get("last_err_msg")})
        return out

    def sim_order_list(self, account: str, market: str = "US") -> dict:
        """Today's orders, every state (OpenD's order list is the current day's)."""
        acc = self._account(account)
        frame = self._call("order list", self._trade_ctx().order_list_query, trd_env=self.ft.TrdEnv.SIMULATE,
                           acc_id=acc)
        return {"ret_code": 0, "data": {"orders": self._orders(frame)}, "pagination": {"has_more": False}}

    def sim_order_history(self, account: str, market: str = "US") -> dict:
        """The last five days' orders; today's list above is the one the cycle depends on."""
        acc = self._account(account)
        now = datetime.now(UTC).astimezone(ET)
        start = (now - timedelta(days=5)).strftime("%Y-%m-%d 00:00:00")
        frame = self._call("order history", self._trade_ctx().history_order_list_query,
                           trd_env=self.ft.TrdEnv.SIMULATE, acc_id=acc, start=start,
                           end=now.strftime("%Y-%m-%d %H:%M:%S"))
        return {"ret_code": 0, "data": {"orders": self._orders(frame)}, "pagination": {"has_more": False}}

    def quote(self, symbols: list[str]) -> dict:
        frame = self._call("quote", self._quote_ctx().get_market_snapshot, list(symbols))
        out = []
        for row in self._records(frame):
            suspended = bool(row.get("suspension"))
            state = str(row.get("sec_status") or "").upper()
            if state in ("", "N/A", "NONE"):
                # Older OpenD builds leave the status out of a snapshot; a stock that is not suspended trades.
                state = "SUSPENDED" if suspended else "NORMAL"
            out.append({"code": row.get("code"), "last_price": row.get("last_price"),
                        "data_time": row.get("update_time"), "volume": row.get("volume") or 0, "sec_status": state,
                        "suspension": suspended, "bid_price": row.get("bid_price"), "ask_price": row.get("ask_price"),
                        "prev_close_price": row.get("prev_close_price")})
        return {"ret_code": 0, "data": {"quote_list": out}}

    def kline_1m(self, symbol: str, num: int = 12) -> dict:
        """Today's 1-minute bars (the latest `num`), from OpenD's history K-line call."""
        today = datetime.now(UTC).astimezone(ET).date().isoformat()
        frame = self._call("1-minute bars", self._quote_ctx().request_history_kline, symbol, start=today, end=today,
                           ktype=self.ft.KLType.K_1M, max_count=1000)
        rows = self._records(frame)[-num:]
        return {"ret_code": 0, "data": {"kline_list": [
            {"time_key": r.get("time_key"), "open_price": r.get("open"), "high_price": r.get("high"),
             "low_price": r.get("low"), "close_price": r.get("close"), "volume": r.get("volume")} for r in rows]}}

    # --- the two order calls (paper only) ----------------------------------------------------------

    def _place(self, side: Any, symbol: str, quantity: int, account: str, limit_price: float, remark: str) -> dict:
        acc = self._account(account)
        frame = self._call("order", self._trade_ctx().place_order, price=round(float(limit_price), 2),
                           qty=int(quantity), code=symbol, trd_side=side, order_type=self.ft.OrderType.NORMAL,
                           trd_env=self.ft.TrdEnv.SIMULATE, acc_id=acc, remark=(remark[:64] or None),
                           time_in_force=self.ft.TimeInForce.DAY)
        rows = self._records(frame)
        order_id = str(rows[0].get("order_id")) if rows else None
        return {"ret_code": 0, "data": {"order_id": order_id}}

    def sim_order_buy(self, symbol: str, quantity: int, account: str, limit_price: float, market: str = "US",
                      remark: str = "") -> dict:
        return self._place(self.ft.TrdSide.BUY, symbol, quantity, account, limit_price, remark)

    def sim_order_sell(self, symbol: str, quantity: int, account: str, limit_price: float, market: str = "US",
                       remark: str = "") -> dict:
        return self._place(self.ft.TrdSide.SELL, symbol, quantity, account, limit_price, remark)

    def sim_order_cancel(self, order_id: str, account: str, market: str = "US") -> dict:
        acc = self._account(account)
        self._call("cancel", self._trade_ctx().modify_order, self.ft.ModifyOrderOp.CANCEL, str(order_id), 0, 0,
                   trd_env=self.ft.TrdEnv.SIMULATE, acc_id=acc)
        return {"ret_code": 0, "data": {"order_id": str(order_id)}}
