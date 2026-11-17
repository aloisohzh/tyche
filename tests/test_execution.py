from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import ClassVar

from typer.testing import CliRunner

from tyche.broker.moomoo_cli import (
    extract_daily_bars,
    extract_last_price,
    extract_order_id,
)
from tyche.cli import app
from tyche.models import (
    OrderIntent,
    PlannedOrder,
    Regime,
    RiskVerdict,
    Side,
    TradePlan,
)

ROOT = Path(__file__).resolve().parents[1]


def make_plan(account_id: str = "SIM-TEST") -> TradePlan:
    approved = PlannedOrder(
        intent=OrderIntent(
            symbol="US.SPY",
            side=Side.BUY,
            quantity=10,
            limit_price=100.0,
            reason="test",
        ),
        verdict=RiskVerdict(allowed=True, adjusted_quantity=10),
    )
    blocked = PlannedOrder(
        intent=OrderIntent(
            symbol="US.QQQ",
            side=Side.BUY,
            quantity=5,
            limit_price=200.0,
            reason="test",
        ),
        verdict=RiskVerdict(
            allowed=False,
            breaches=[],
            adjusted_quantity=5,
        ),
    )
    return TradePlan(
        as_of=date(2026, 11, 17),
        account_id=account_id,
        nav=100_000.0,
        cash=100_000.0,
        regime=Regime.RISK_ON,
        targets={"US.SPY": 0.01, "CASH": 0.99},
        signals={},
        regime_checks={"equity_trend": True},
        portfolio_vol=0.10,
        vol_scale=1.0,
        orders=[approved, blocked],
    )


class FakeCli:
    submitted: ClassVar[list[dict]] = []
    prices: ClassVar[dict[str, float]] = {"US.SPY": 100.0, "US.QQQ": 200.0}

    def __init__(self, binary: str = "moomoo", timeout: float = 45.0) -> None:
        pass

    def available(self) -> bool:
        return True

    def kline(self, symbol: str, num: int = 370) -> dict:
        return {
            "data": {
                "kline_list": [
                    {"time_key": "2026-11-13", "close_price": 99.0},
                    {"time_key": "2026-11-16", "close_price": 100.0},
                ]
            }
        }

    def quote(self, symbols: list[str]) -> dict:
        return {
            "data": [
                {"code": symbol, "last_price": self.prices.get(symbol, 0.0)} for symbol in symbols
            ]
        }

    def sim_accounts(self) -> dict:
        return {"data": [{"code": "SIM-TEST"}]}

    def sim_order_buy(self, symbol, quantity, account, limit_price, market="US", remark=""):
        FakeCli.submitted.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "limit_price": limit_price,
                "remark": remark,
            }
        )
        return {"data": {"order_id": f"OID-{len(FakeCli.submitted)}"}}

    def sim_order_sell(self, symbol, quantity, account, limit_price, market="US", remark=""):
        return self.sim_order_buy(symbol, quantity, account, limit_price, market, remark)


def test_extract_daily_bars_from_nested_payload() -> None:
    payload = {
        "data": {
            "kline_list": [
                {"time_key": "2026-11-12 00:00:00", "close_price": "99.5"},
                {"time_key": "20261113", "close_price": 100.0},
                {"time_key": "1794787200000", "close_price": 101.0},
            ]
        }
    }
    bars = extract_daily_bars(payload)
    assert len(bars) == 3
    assert bars[0] == (date(2026, 11, 12), 99.5)
    assert bars[1] == (date(2026, 11, 13), 100.0)
    assert bars[2] == (date(2026, 11, 16), 101.0)


def test_extract_last_price_and_order_id() -> None:
    quote = {"data": [{"code": "US.SPY", "last_price": "402.45"}]}
    assert extract_last_price(quote, "US.SPY") == 402.45
    assert extract_last_price(quote, "US.QQQ") is None
    assert extract_order_id({"data": {"order_id": 12345}}) == "12345"


def test_execute_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    FakeCli.submitted = []
    monkeypatch.setattr("tyche.cli.MoomooCli", FakeCli)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(make_plan().model_dump_json(indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "execute",
            "--plan",
            str(plan_path),
            "--account-id",
            "SIM-TEST",
            "--config-root",
            str(ROOT),
            "--journal",
            str(tmp_path / "events.jsonl"),
        ],
    )
    assert result.exit_code == 2
    assert FakeCli.submitted == []
    assert not (tmp_path / "events.jsonl").exists()


def test_execute_submits_only_approved_orders(tmp_path: Path, monkeypatch) -> None:
    FakeCli.submitted = []
    monkeypatch.setattr("tyche.cli.MoomooCli", FakeCli)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(make_plan().model_dump_json(indent=2), encoding="utf-8")
    journal_path = tmp_path / "events.jsonl"

    result = CliRunner().invoke(
        app,
        [
            "execute",
            "--plan",
            str(plan_path),
            "--account-id",
            "SIM-TEST",
            "--yes",
            "--config-root",
            str(ROOT),
            "--journal",
            str(journal_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(FakeCli.submitted) == 1
    assert FakeCli.submitted[0]["symbol"] == "US.SPY"
    assert list(tmp_path.glob("execution-*.json"))

    events = journal_path.read_text(encoding="utf-8").splitlines()
    types = [json.loads(line)["type"] for line in events]
    assert types == ["order.requested", "order.submitted"]


def test_execute_rejects_non_paper_account(tmp_path: Path, monkeypatch) -> None:
    FakeCli.submitted = []
    monkeypatch.setattr("tyche.cli.MoomooCli", FakeCli)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        make_plan(account_id="LIVE-123").model_dump_json(indent=2), encoding="utf-8"
    )

    result = CliRunner().invoke(
        app,
        [
            "execute",
            "--plan",
            str(plan_path),
            "--account-id",
            "LIVE-123",
            "--yes",
            "--config-root",
            str(ROOT),
            "--journal",
            str(tmp_path / "events.jsonl"),
        ],
    )
    assert result.exit_code == 2
    assert FakeCli.submitted == []


def test_execute_preflight_rejects_stale_limit(tmp_path: Path, monkeypatch) -> None:
    FakeCli.submitted = []
    FakeCli.prices = {"US.SPY": 110.0}
    monkeypatch.setattr("tyche.cli.MoomooCli", FakeCli)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(make_plan().model_dump_json(indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "execute",
            "--plan",
            str(plan_path),
            "--account-id",
            "SIM-TEST",
            "--yes",
            "--config-root",
            str(ROOT),
            "--journal",
            str(tmp_path / "events.jsonl"),
        ],
    )
    assert result.exit_code == 1
    assert FakeCli.submitted == []
    assert not list(tmp_path.glob("execution-*.json"))
    FakeCli.prices = {"US.SPY": 100.0, "US.QQQ": 200.0}


def test_fetch_writes_price_csv(tmp_path: Path, monkeypatch) -> None:
    FakeCli.submitted = []
    monkeypatch.setattr("tyche.cli.MoomooCli", FakeCli)
    out = tmp_path / "prices.csv"
    journal_path = tmp_path / "events.jsonl"

    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "US.SPY",
            "--num",
            "60",
            "--out",
            str(out),
            "--config-root",
            str(ROOT),
            "--journal",
            str(journal_path),
        ],
    )
    assert result.exit_code == 0, result.output
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "date,symbol,close"
    assert len(lines) == 3
    event = json.loads(journal_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["type"] == "prices.fetched"
    assert event["payload"]["symbols"] == ["US.SPY"]
