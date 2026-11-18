from __future__ import annotations

import json
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


def test_plan_cli_end_to_end(tmp_path: Path) -> None:
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
    assert journal_path.read_text(encoding="utf-8").strip()


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
