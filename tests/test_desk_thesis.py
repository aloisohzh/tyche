"""Desk rendering of the per-trade thesis: stages, contract fields, sleeve attribution."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

THESIS = {
    "thesis": "NVDA breaks the prior 5-bar high with the tape up",
    "synthesis": "Long NVDA on a deterministic breakout with a hard timeout",
    "edge": "target 101.0 is 2R from 100.5 against stop 100.25",
    "bear_case": "a close back below 100.25 invalidates the breakout",
    "invalidation": "stop 100.25, 20-minute timeout, or session flatten",
    "horizon": "intraday; flat before the close",
    "direction": "bullish",
    "factors": [
        {"name": "5-bar high breakout", "axis": "technical", "state": "pass",
         "why": "latest close is above the prior highs", "detail": ""},
        {"name": "spread", "axis": "liquidity", "state": "pass",
         "why": "spread inside the cap", "detail": ""},
        {"name": "macro / sentiment / seasonality", "axis": "macro", "state": "unknown",
         "why": "this lane carries no macro input", "detail": ""},
    ],
    "outlook": {"regime": "", "conviction": "low", "alignment": {"technical": "bull"}},
    "thesis_ref": None,
    "source": "deterministic",
}


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("desk_server_thesis_test",
                                                  ROOT / "dashboard" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def card() -> dict:
    return {
        "symbol": "US.NVDA", "side": "buy", "quantity": 10, "effective_quantity": 10,
        "limit_price": 100.5, "stop_price": 100.25, "notional": 1005.0, "reason": "breakout",
        "order": {},
    }


def test_stages_read_the_journaled_thesis(srv):
    stages = srv.stage_track({"strategy_id": "PB-004"}, "US.NVDA", None, "breakout",
                             {"stop": 100.25, "target": 101.0, "limit": 100.5}, THESIS)
    assert stages["thesis"]["text"].startswith("NVDA breaks")
    assert stages["thesis"]["invalidation"].startswith("stop 100.25")
    assert stages["multifactor"]["state"] == "partial"
    assert stages["multifactor"]["covered"] == ["liquidity", "technical"]
    assert stages["multifactor"]["missing"] == ["macro / sentiment / seasonality"]
    assert stages["outlook"]["mapped"] == "bullish"
    assert stages["outlook"]["conviction"] == "low"
    assert stages["edge"]["expected"] == THESIS["edge"]


def test_contract_prefers_journaled_thesis_over_generic_defaults(srv):
    contract = srv.derive_contract(card(), {"strategy_id": "PB-004"}, None, THESIS)
    fields = contract["fields"]
    assert fields["expected_edge"]["value"] == THESIS["edge"]
    assert fields["expected_edge"]["provenance"] == "journaled"
    assert fields["invalidation"]["value"] == THESIS["invalidation"]
    assert THESIS["bear_case"] in fields["invalidation"]["note"]
    assert fields["thesis_ref"]["provenance"] == "derived"
    assert "no macro regime" in fields["outlook"]["value"]
    assert "technical bull" in fields["outlook"]["value"]


def test_scalp_symbols_attribute_to_an_intraday_sleeve(srv):
    assert srv.SLEEVE_MAP["US.NVDA"] == "intraday"
    assert srv.SLEEVE_MAP["US.SPY"] != "intraday"
