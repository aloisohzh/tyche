from __future__ import annotations

import json
from pathlib import Path

from tyche.broker.mcp_json import (
    account_meta,
    build_snapshot,
    extract_cash,
    extract_nav,
    extract_positions,
    extract_sim_accounts,
    snapshot_from_dir,
)
from tyche.config import RiskPolicy
from tyche.models import OrderIntent, Side
from tyche.risk import RiskState, evaluate_intent

ACCOUNTS = {
    "ret_code": 0,
    "ret_msg": "success",
    "data": {
        "accounts": [
            {"account_id": "9000002", "account_title": "US Paper", "account_type": 1, "market_id": 100},
            {"account_id": "9000001", "account_title": "Challenge", "account_type": 2, "market_id": 100},
            {"account_id": "9000003", "account_title": "HK Paper", "account_type": 1, "market_id": 1},
        ]
    },
}
CASH = {
    "ret_code": 0,
    "data": {"balance": "100000.0", "hold": "0", "mv": "6000.0", "total_asset": "106000.0"},
}
POSITIONS = {
    "ret_code": 0,
    "data": {
        "positions": [
            {
                "symbol": "SPY",
                "stock_name": "SPDR S&P 500",
                "qty": "10",
                "qty_avbl": "10",
                "cost_price": "600.0",
                "buy_avg_price": "600.0",
                "cur_price": "600.0",
                "mv": "6000.0",
                "market": 100,
                "pstn_type": 0,
            }
        ]
    },
}


def test_extract_sim_accounts_and_meta() -> None:
    accounts = extract_sim_accounts(ACCOUNTS)
    assert len(accounts) == 3
    meta = account_meta(ACCOUNTS, "9000001")
    assert meta["account_type"] == 2
    assert meta["market_id"] == 100
    assert account_meta(ACCOUNTS, "missing") is None


def test_extract_cash_and_nav() -> None:
    assert extract_cash(CASH) == 100000.0
    assert extract_nav(CASH) == 106000.0


def test_extract_positions_prefixes_bare_symbol() -> None:
    positions = extract_positions(POSITIONS)
    assert len(positions) == 1
    assert positions[0].symbol == "US.SPY"
    assert positions[0].quantity == 10
    assert positions[0].avg_cost == 600.0
    assert positions[0].last_price == 600.0


def test_extract_positions_keeps_prefixed_code() -> None:
    payload = {"data": {"positions": [{"code": "US.QQQ", "qty": "5", "cost_price": "500", "cur_price": "500"}]}}
    positions = extract_positions(payload)
    assert positions[0].symbol == "US.QQQ"


def test_build_snapshot_carries_account_meta() -> None:
    snapshot = build_snapshot("9000001", ACCOUNTS, CASH, POSITIONS)
    assert snapshot.account_id == "9000001"
    assert snapshot.cash == 100000.0
    assert snapshot.account_type == 2
    assert snapshot.market_id == 100
    assert snapshot.source == "sim_list"
    assert snapshot.env == "paper"
    assert snapshot.position("US.SPY").quantity == 10


def test_build_snapshot_without_meta_fails_closed() -> None:
    snapshot = build_snapshot("unknown", ACCOUNTS, CASH, POSITIONS)
    assert snapshot.account_type is None
    assert snapshot.market_id is None


def test_snapshot_from_dir_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "accounts.json").write_text(json.dumps(ACCOUNTS), encoding="utf-8")
    (tmp_path / "cash.json").write_text(json.dumps(CASH), encoding="utf-8")
    (tmp_path / "positions.json").write_text(json.dumps(POSITIONS), encoding="utf-8")
    snapshot = snapshot_from_dir(tmp_path, "9000001")
    assert snapshot.cash == 100000.0
    assert snapshot.account_type == 2


def test_built_snapshot_passes_kernel_for_allowlisted_account() -> None:
    snapshot = build_snapshot("9000001", ACCOUNTS, CASH, POSITIONS)
    policy = RiskPolicy(account_allowlist=["9000001"])
    intent = OrderIntent(
        symbol="US.SPY", side=Side.BUY, quantity=5, limit_price=600.0, reason="test"
    )
    verdict = evaluate_intent(
        intent=intent,
        snapshot=snapshot,
        policy=policy,
        state=RiskState(nav=snapshot.nav, prior_close_nav=snapshot.nav),
        last_price=600.0,
        universe_symbols={"US.SPY"},
        sleeve_by_symbol={"US.SPY": "equity"},
    )
    assert verdict.allowed, verdict.breaches