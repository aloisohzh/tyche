from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from tyche.cli import app

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = [
    "US.SPY",
    "US.QQQ",
    "US.IWM",
    "US.EFA",
    "US.EEM",
    "US.TLT",
    "US.IEF",
    "US.GLD",
    "US.DBC",
    "US.VNQ",
    "US.HYG",
]


def _write_prices(tmp_path: Path) -> Path:
    days = pd.bdate_range("2024-01-01", periods=320)
    rng = np.random.default_rng(7)
    rows: list[tuple[str, str, float]] = []
    for symbol in SYMBOLS:
        returns = rng.normal(0.0004, 0.0080, len(days))
        prices = 100.0 * np.cumprod(1.0 + returns)
        rows.extend(
            (day.strftime("%Y-%m-%d"), symbol, round(float(price), 2))
            for day, price in zip(days, prices, strict=True)
        )
    prices_path = tmp_path / "prices.csv"
    pd.DataFrame(rows, columns=["date", "symbol", "close"]).to_csv(prices_path, index=False)
    return prices_path


def test_plan_cli_end_to_end(tmp_path: Path) -> None:
    prices_path = _write_prices(tmp_path)

    journal_path = tmp_path / "events.jsonl"
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "--prices",
            str(prices_path),
            "--config-root",
            str(ROOT),
            "--out",
            str(tmp_path / "plans"),
            "--journal",
            str(journal_path),
        ],
    )

    assert result.exit_code == 0, result.output
    plans = list((tmp_path / "plans").glob("*-plan.json"))
    assert len(plans) == 1
    payload = json.loads(plans[0].read_text(encoding="utf-8"))
    assert payload["regime"] in {"risk_on", "neutral", "risk_off"}
    assert payload["targets"]
    pipe = payload["pipeline"]
    assert pipe["thesis_ref"].startswith("PB-001")
    assert pipe["outlook"] in {"bullish", "bearish", "range"}
    assert pipe["conviction"] in {"high", "medium-high", "medium", "low"}
    assert pipe["inputs_ref"]["prices_sha256"]
    for order in payload["orders"]:
        op = order["pipeline"]
        assert op["vehicle"] == "etf"
        assert op["invalidation"]
        assert op["protection_type"] == "rebalance"
        assert op["action"] in {"act", "wait"}
        assert op["sizing"]["notional"] >= 0
    md = plans[0].with_suffix(".md").read_text(encoding="utf-8")
    assert "## Pipeline" in md
    assert "Act/wait gate" in md
    events = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").strip().splitlines()
    ]
    assert events[0]["type"] == "plan.created"
    assert events[0]["payload"]["plan"]["pipeline"]["thesis_ref"] == pipe["thesis_ref"]


def _account_marked_above_close(prices_path: Path, drift: float) -> dict:
    closes = pd.read_csv(prices_path).groupby("symbol")["close"].last().to_dict()
    quantity = 10
    broker_mark = round(closes["US.SPY"] + drift, 2)
    return {
        "account_id": "SIM-PLAN-TEST",
        "cash": 100_000.0 - quantity * broker_mark,
        "broker_nav": 100_000.0,
        "prior_close_nav": 100_000.0,
        "high_water_nav": 100_000.0,
        "account_type": 2,
        "market_id": 100,
        "source": "sim_list",
        "positions": [
            {
                "symbol": "US.SPY",
                "quantity": quantity,
                "avg_cost": closes["US.SPY"],
                "last_price": broker_mark,
            }
        ],
    }


def _run_plan(tmp_path: Path, prices_path: Path, account_path: Path):
    return CliRunner().invoke(
        app,
        [
            "plan",
            "--prices",
            str(prices_path),
            "--account",
            str(account_path),
            "--config-root",
            str(ROOT),
            "--out",
            str(tmp_path / "plans"),
            "--journal",
            str(tmp_path / "events.jsonl"),
        ],
    )


def test_plan_tolerates_overnight_mark_drift(tmp_path: Path) -> None:
    prices_path = _write_prices(tmp_path)
    account_path = tmp_path / "account.json"
    account_path.write_text(json.dumps(_account_marked_above_close(prices_path, 5.0)), encoding="utf-8")

    result = _run_plan(tmp_path, prices_path, account_path)

    assert result.exit_code == 0, result.output
    plan = json.loads(next((tmp_path / "plans").glob("*-plan.json")).read_text(encoding="utf-8"))
    rules = {breach["rule"] for order in plan["orders"] for breach in order["verdict"]["breaches"]}
    assert "account.reconcile" not in rules


def test_plan_rejects_snapshot_that_does_not_reconcile_at_capture(tmp_path: Path) -> None:
    prices_path = _write_prices(tmp_path)
    payload = _account_marked_above_close(prices_path, 5.0)
    payload["cash"] -= 500.0
    account_path = tmp_path / "account.json"
    account_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_plan(tmp_path, prices_path, account_path)

    assert result.exit_code != 0
    assert "does not reconcile at capture" in result.output


def _write_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "accounts.json").write_text(
        json.dumps(
            {"data": {"accounts": [{"account_id": "9999598", "account_type": 2, "market_id": 100}]}}
        ),
        encoding="utf-8",
    )
    (run_dir / "cash.json").write_text(
        json.dumps({"data": {"balance": 100000.0, "total_asset": 100000.0}}), encoding="utf-8"
    )
    (run_dir / "positions.json").write_text(json.dumps({"data": {"positions": []}}), encoding="utf-8")
    return run_dir


def test_snapshot_cli_writes_audit_metadata(tmp_path: Path) -> None:
    run_dir = _write_run_dir(tmp_path)
    result = CliRunner().invoke(
        app, ["snapshot", "--dir", str(run_dir), "--account-id", "9999598"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads((run_dir / "snapshot.json").read_text(encoding="utf-8"))
    assert payload["account_id"] == "9999598"
    assert payload["env"] == "paper"
    assert payload["account_type"] == 2
    assert payload["market_id"] == 100
    assert payload["cash"] == 100000.0
    assert "9999598" not in result.output


def test_snapshot_cli_rejects_unknown_account(tmp_path: Path) -> None:
    run_dir = _write_run_dir(tmp_path)
    result = CliRunner().invoke(
        app, ["snapshot", "--dir", str(run_dir), "--account-id", "1111111"]
    )
    assert result.exit_code != 0
    assert not (run_dir / "snapshot.json").exists()


def test_record_order_journals_mcp_events(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    runner = CliRunner()
    for event in ("order.requested", "order.submitted"):
        result = runner.invoke(
            app,
            [
                "record-order",
                event,
                "--data",
                json.dumps({"symbol": "US.SPY", "side": "sell", "quantity": 1}),
                "--journal",
                str(journal_path),
            ],
        )
        assert result.exit_code == 0, result.output
    lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "order.requested"
    assert json.loads(lines[1])["type"] == "order.submitted"
    bad = runner.invoke(
        app,
        ["record-order", "order.unknown", "--data", "{}", "--journal", str(journal_path)],
    )
    assert bad.exit_code != 0
    bad_json = runner.invoke(
        app,
        ["record-order", "order.submitted", "--data", "not-json", "--journal", str(journal_path)],
    )
    assert bad_json.exit_code != 0


def test_record_order_normalizes_plain_text_authorization(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    result = CliRunner().invoke(app, [
        "record-order", "order.requested", "--journal", str(journal_path), "--data",
        json.dumps({"symbol": "US.PG", "side": "buy", "quantity": 57, "limit_price": 199.0,
                    "authorization": "operator approved PG line"}),
    ])
    assert result.exit_code == 0, result.output
    row = json.loads(journal_path.read_text(encoding="utf-8").strip())["payload"]
    assert row["authorization"] == {"kind": "manual", "note": "operator approved PG line"}


def test_record_order_rejects_an_unreadable_authorization_shape(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    result = CliRunner().invoke(app, [
        "record-order", "order.requested", "--journal", str(journal_path), "--data",
        json.dumps({"symbol": "US.PG", "side": "buy", "quantity": 57,
                    "authorization": ["not", "an", "approval"]}),
    ])
    assert result.exit_code != 0
    assert not journal_path.exists()


def test_record_order_filled_requires_canonical_payload(tmp_path: Path) -> None:
    runner = CliRunner()
    journal_path = tmp_path / "events.jsonl"
    good = runner.invoke(
        app,
        [
            "record-order",
            "order.filled",
            "--data",
            json.dumps({"symbol": "US.SPY", "side": "buy", "quantity": 10, "price": 100.0}),
            "--journal",
            str(journal_path),
        ],
    )
    assert good.exit_code == 0, good.output
    bad = runner.invoke(
        app,
        [
            "record-order",
            "order.filled",
            "--data",
            json.dumps({"symbol": "US.SPY", "quantity": 10, "price": 100.0}),
            "--journal",
            str(journal_path),
        ],
    )
    assert bad.exit_code != 0


def test_record_order_protection_gap_needs_request_and_resolution(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    runner = CliRunner()
    base = ["record-order", "protection.gap", "--journal", str(journal_path), "--data"]
    ok = runner.invoke(app, base + [json.dumps({"request_id": "req-1", "resolution": "expired"})])
    assert ok.exit_code == 0, ok.output
    assert json.loads(journal_path.read_text(encoding="utf-8").strip())["type"] == "protection.gap"
    no_request = runner.invoke(app, base + [json.dumps({"resolution": "expired"})])
    assert no_request.exit_code != 0
    invented = runner.invoke(app, base + [json.dumps({"request_id": "req-1", "resolution": "filled"})])
    assert invented.exit_code != 0

def test_record_order_journals_a_cancel_the_broker_actually_reports(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    runner = CliRunner()
    ok = runner.invoke(app, ["record-order", "order.cancelled", "--journal", str(journal_path),
                             "--data", json.dumps({"request_id": "tyche-exit-1", "order_id": "3125782",
                                                   "symbol": "US.NVDA", "side": "sell"})])
    assert ok.exit_code == 0, ok.output
    anonymous = runner.invoke(app, ["record-order", "order.cancelled", "--journal", str(journal_path),
                                    "--data", json.dumps({"symbol": "US.NVDA"})])
    assert anonymous.exit_code != 0


def _plan(symbol: str = "US.PG") -> dict:
    return {"symbol": symbol, "sleeve": "equity", "strategy": "PB-002 defensive momentum",
            "entry_low": 170.0, "entry_high": 172.5, "stop": 169.3, "target": 178.0,
            "expiry": "2026-12-04", "setup_id": "TAC-20261125-PG", "hold": "swing"}


def test_record_order_stamps_the_fingerprint_an_exit_note_needs(tmp_path: Path) -> None:
    from tyche.config import load_config
    from tyche.tactical import setup_hash
    from tyche.watchlist import WatchlistEntry

    root = Path(__file__).resolve().parents[1]
    journal_path = tmp_path / "events.jsonl"
    runner = CliRunner()
    payload = {"symbol": "US.PG", "side": "buy", "quantity": 31, "account_id": "***598",
               "protected_setup": _plan()}
    result = runner.invoke(app, ["record-order", "order.requested", "--journal", str(journal_path),
                                 "--config-root", str(root), "--data", json.dumps(payload)])
    assert result.exit_code == 0, result.output
    row = json.loads(journal_path.read_text(encoding="utf-8").strip())["payload"]
    assert row["setup_hash"] == setup_hash(WatchlistEntry.model_validate(_plan()),
                                           load_config(root), "***598")
    assert row["setup_id"] == "TAC-20261125-PG"
    # A hash the kernel already wrote is copied, never recomputed, and a plan with no account
    # cannot be hashed at all: the row would draft an envelope line the lane refuses to arm.
    hashed = runner.invoke(app, ["record-order", "order.requested", "--journal", str(journal_path),
                                 "--config-root", str(root),
                                 "--data", json.dumps({**payload, "setup_hash": "already-bound"})])
    assert hashed.exit_code == 0, hashed.output
    assert json.loads(journal_path.read_text(encoding="utf-8").splitlines()[-1])["payload"]["setup_hash"] \
        == "already-bound"
    orphan = runner.invoke(app, ["record-order", "order.requested", "--journal", str(journal_path),
                                 "--config-root", str(root),
                                 "--data", json.dumps({"symbol": "US.PG", "protected_setup": _plan()})])
    assert orphan.exit_code != 0 and "account_id" in orphan.output


def _broker_row(**overrides) -> dict:
    now_us = int(datetime.now(UTC).timestamp() * 1_000_000)
    row = {"order_id": "3125999", "symbol": "US.KO", "side": 1, "qty": 100, "cum_qty": 100,
           "price": 97.5, "status": 4, "create_time": now_us, "update_time": now_us,
           "avg_fill_price": 97.6, "text": "tyche-tac-abcdef"}
    row.update(overrides)
    return row


def test_sync_receipts_heals_the_journal_from_the_broker_list(tmp_path: Path) -> None:
    journal_path, orders = tmp_path / "events.jsonl", tmp_path / "orders.json"
    orders.write_text(json.dumps({"ret_code": 0, "data": {"orders": [_broker_row()]}}), encoding="utf-8")
    runner = CliRunner()
    base = ["sync-receipts", "--orders", str(orders), "--journal", str(journal_path)]
    dry = runner.invoke(app, base)
    assert dry.exit_code == 0 and "DRY" in dry.output and not journal_path.exists()
    written = runner.invoke(app, base + ["--record"])
    assert written.exit_code == 0 and "Chain OK" in written.output, written.output
    events = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    assert [e["type"] for e in events] == ["order.submitted", "order.filled"]
    assert events[1]["payload"]["price"] == 97.6 and events[1]["payload"]["source"] == "broker order list"
    again = runner.invoke(app, base + ["--record"])
    assert "Nothing to heal" in again.output
def test_sync_receipts_heals_a_cancel_and_refuses_a_bad_page(tmp_path: Path) -> None:
    journal_path, orders = tmp_path / "events.jsonl", tmp_path / "orders.json"
    orders.write_text(json.dumps({"ret_code": 0, "data": {"orders": [
        _broker_row(status=5, cum_qty=0, text="tyche-exit-deadbeef")]}}), encoding="utf-8")
    result = CliRunner().invoke(app, ["sync-receipts", "--orders", str(orders), "--journal",
                                      str(journal_path), "--record"])
    assert result.exit_code == 0, result.output
    assert json.loads(journal_path.read_text(encoding="utf-8").splitlines()[-1])["type"] == "order.cancelled"
    orders.write_text(json.dumps({"ret_code": 1, "data": {}}), encoding="utf-8")
    bad = CliRunner().invoke(app, ["sync-receipts", "--orders", str(orders), "--journal", str(journal_path)])
    assert bad.exit_code != 0
