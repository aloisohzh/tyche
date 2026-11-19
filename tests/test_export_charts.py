"""Charts exporter: account redaction, masked-id matching, marker omission."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_charts


@pytest.fixture()
def inputs(tmp_path: Path) -> tuple[Path, Path]:
    prices = tmp_path / "prices.csv"
    prices.write_text(
        "date,symbol,close\n"
        "2026-11-16,US.SPY,700.0\n"
        "2026-11-17,US.SPY,710.0\n"
        "2026-11-18,US.SPY,720.0\n"
        "2026-11-16,US.TLT,90.0\n"
        "2026-11-17,US.TLT,91.0\n"
        "2026-11-18,US.TLT,92.0\n",
        encoding="utf-8",
    )
    events = [
        {
            "ts": "2026-11-17T15:00:00Z",
            "type": "plan.created",
            "payload": {"plan": {"as_of": "2026-11-17", "regime": "neutral", "nav": 1000.0, "account_id": "1234567"}},
        },
        {
            "ts": "2026-11-18T15:00:00Z",
            "type": "order.submitted",
            "payload": {"account": "***567", "symbol": "US.SPY", "side": "buy", "quantity": 10, "limit_price": 720.7},
        },
        {
            "ts": "2026-11-18T15:01:00Z",
            "type": "order.submitted",
            "payload": {"account": "***999", "symbol": "US.SPY", "side": "buy", "quantity": 5, "limit_price": 720.7},
        },
        {
            "ts": "2026-11-10T15:00:00Z",
            "type": "order.submitted",
            "payload": {"account": "***567", "symbol": "US.SPY", "side": "sell", "quantity": 1, "limit_price": 690.0},
        },
        {
            "ts": "2026-11-18T15:02:00Z",
            "type": "order.submitted",
            "payload": {"account": "***567", "symbol": "US.QQQ", "side": "buy", "quantity": 2, "limit_price": 600.0},
        },
        {
            "ts": "2026-11-18T16:00:00Z",
            "type": "plan.created",
            "payload": {"plan": {"as_of": "2026-11-18", "regime": "risk_on", "nav": 1010.0, "account_id": "1234567"}},
        },
    ]
    journal = tmp_path / "events.jsonl"
    journal.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return prices, journal


def test_masked_and_raw_account_matching(inputs: tuple[Path, Path]) -> None:
    prices, journal = inputs
    payload = export_charts.build_payload(prices, journal, "1234567")
    markers = payload["markers"]["US.SPY"]
    assert len(markers) == 1
    assert markers[0]["position"] == "belowBar"
    assert markers[0]["shape"] == "arrowUp"
    assert markers[0]["text"] == "buy 10 @ 720.7"
    assert payload["omitted_markers"] == 2
    assert payload["regimes"] == [
        {"from": "2026-11-17", "regime": "neutral"},
        {"from": "2026-11-18", "regime": "risk_on"},
    ]
    assert [point["value"] for point in payload["nav"]] == [1000.0, 1010.0]


def test_account_id_never_reaches_output(inputs: tuple[Path, Path], tmp_path: Path) -> None:
    prices, journal = inputs
    payload = export_charts.build_payload(prices, journal, "1234567")
    assert "1234567" not in json.dumps(payload)
    assert payload["account_label"] == "live sim account (id redacted)"
    out = tmp_path / "charts.html"
    export_charts.render(payload, ROOT / "templates" / "charts.html", out)
    html = out.read_text(encoding="utf-8")
    assert "1234567" not in html
    assert "__PAYLOAD__" not in html


def test_sim_account_label_passthrough(inputs: tuple[Path, Path]) -> None:
    prices, journal = inputs
    payload = export_charts.build_payload(prices, journal, "SIM-DEMO-US")
    assert payload["account_label"] == "SIM-DEMO-US"
    assert payload["markers"] == {}
    assert payload["regimes"] == []


def test_regime_strip_forward_fills(inputs: tuple[Path, Path]) -> None:
    prices, journal = inputs
    strip = export_charts.build_payload(prices, journal, "1234567")["regime_strip"]
    assert [point["time"] for point in strip] == ["2026-11-16", "2026-11-17", "2026-11-18"]
    assert strip[0]["value"] == 0
    assert strip[1]["color"] == export_charts.REGIME_COLORS["neutral"]
    assert strip[2]["color"] == export_charts.REGIME_COLORS["risk_on"]


def test_empty_prices_rejected(tmp_path: Path, inputs: tuple[Path, Path]) -> None:
    _, journal = inputs
    prices = tmp_path / "empty.csv"
    prices.write_text("date,symbol,close\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no price rows"):
        export_charts.build_payload(prices, journal, "1234567")