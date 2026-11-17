"""Read-side adapter for Moomoo MCP sim payloads.

The executor agent fetches MCP JSON (sim_trade_account_list, sim_trade_cash_info,
sim_trade_position_list) and writes it to disk; the deterministic core consumes it
here. Shapes are grounded in the live MCP responses: accounts under
``data.accounts[]``, cash as ``data.balance`` (NAV ``data.total_asset``), positions
under ``data.positions[]`` with bare ``symbol`` tickers that need a market prefix.
Submission stays with the executor; this module only reads and reconciles.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tyche.broker.moomoo_cli import _walk
from tyche.models import AccountSnapshot, Position

MARKET_PREFIX = {100: "US", 1: "HK", 14: "SG", 16: "JP", 102: "KR"}


def extract_sim_accounts(payload: Any) -> list[dict]:
    candidates: list[list[dict]] = []
    for node in _walk(payload):
        if (
            isinstance(node, list)
            and node
            and all(isinstance(item, dict) for item in node)
            and all("account_id" in item and "market_id" in item for item in node)
        ):
            candidates.append(node)
    return max(candidates, key=len) if candidates else []


def account_meta(payload: Any, account_id: str) -> dict | None:
    for account in extract_sim_accounts(payload):
        if str(account.get("account_id")) == str(account_id):
            return account
    return None


def _first_float(node: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            return float(node[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def extract_cash(payload: Any) -> float | None:
    for node in _walk(payload):
        if isinstance(node, dict) and any(k in node for k in ("balance", "cash", "avl_cash")):
            value = _first_float(node, ("balance", "cash", "avl_cash", "available_cash"))
            if value is not None and value >= 0:
                return value
    return None


def extract_nav(payload: Any) -> float | None:
    for node in _walk(payload):
        if isinstance(node, dict) and any(
            k in node for k in ("total_asset", "total_assets", "nav", "net_asset")
        ):
            value = _first_float(node, ("total_asset", "total_assets", "nav", "net_asset"))
            if value is not None and value >= 0:
                return value
    return None


def _find_position_list(payload: Any) -> list[dict]:
    candidates: list[list[dict]] = []
    for node in _walk(payload):
        if (
            isinstance(node, list)
            and node
            and all(isinstance(item, dict) for item in node)
            and any(
                ("symbol" in item or "code" in item) and ("qty" in item or "quantity" in item)
                for item in node
            )
        ):
            candidates.append(node)
    return max(candidates, key=len) if candidates else []


def extract_positions(payload: Any, market_prefix: str = "US") -> list[Position]:
    positions: list[Position] = []
    for item in _find_position_list(payload):
        if item.get("pstn_type") not in (0, None):
            continue
        raw_symbol = item.get("symbol") or item.get("code")
        if not raw_symbol:
            continue
        symbol = str(raw_symbol)
        if "." not in symbol:
            symbol = f"{market_prefix}.{symbol}"
        try:
            quantity = int(float(item.get("qty", item.get("quantity", 0))))
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        cost = _first_float(item, ("cost_price", "buy_avg_price", "avg_cost")) or 0.0
        last = _first_float(item, ("cur_price", "last_price", "price")) or cost
        positions.append(
            Position(symbol=symbol, quantity=quantity, avg_cost=cost, last_price=last)
        )
    return positions


def build_snapshot(
    account_id: str,
    accounts_payload: Any,
    cash_payload: Any,
    positions_payload: Any,
    *,
    env: str = "paper",
    source: str = "sim_list",
    market_prefix: str = "US",
) -> AccountSnapshot:
    meta = account_meta(accounts_payload, account_id)
    cash = extract_cash(cash_payload)
    if cash is None:
        raise ValueError("no cash balance found in the funds payload")
    return AccountSnapshot(
        account_id=str(account_id),
        cash=cash,
        positions=extract_positions(positions_payload, market_prefix),
        env=env,
        account_type=meta.get("account_type") if meta else None,
        market_id=meta.get("market_id") if meta else None,
        source=source,
    )


def snapshot_from_dir(
    directory: Path,
    account_id: str,
    *,
    env: str = "paper",
    source: str = "sim_list",
    market_prefix: str = "US",
) -> AccountSnapshot:
    directory = Path(directory)
    accounts = json.loads((directory / "accounts.json").read_text(encoding="utf-8"))
    cash = json.loads((directory / "cash.json").read_text(encoding="utf-8"))
    positions = json.loads((directory / "positions.json").read_text(encoding="utf-8"))
    return build_snapshot(
        account_id,
        accounts,
        cash,
        positions,
        env=env,
        source=source,
        market_prefix=market_prefix,
    )