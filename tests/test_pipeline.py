from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tyche.config import PLAYBOOK_LANES, load_config, rules_path_for
from tyche.models import AccountSnapshot, OrderIntent, Regime, RiskVerdict, Side
from tyche.pipeline import (
    act_wait,
    build_order_pipeline,
    build_plan_pipeline,
    conviction_tier,
    rules_hash,
)

ROOT = Path(__file__).resolve().parents[1]


def test_conviction_tiers() -> None:
    assert conviction_tier(4, 4) == "high"
    assert conviction_tier(3, 4) == "medium-high"
    assert conviction_tier(2, 4) == "medium"
    assert conviction_tier(1, 4) == "low"
    assert conviction_tier(0, 4) == "low"


def test_act_wait_gate_never_blocks_de_risking() -> None:
    assert act_wait(Side.SELL, "equity", "low", held=True) == "act"
    assert act_wait(Side.BUY, "defensive", "low", held=False) == "act"
    assert act_wait(Side.BUY, "equity", "low", held=True) == "act"
    assert act_wait(Side.BUY, "equity", "low", held=False) == "wait"
    assert act_wait(Side.BUY, "equity", "medium", held=False) == "act"


def test_rules_hash_is_stable_and_config_sensitive(tmp_path: Path) -> None:
    first = rules_hash(ROOT, "PB-001")
    assert first == rules_hash(ROOT, "PB-001")
    assert len(first) == 12
    fake = tmp_path / "config"
    (fake / "strategies").mkdir(parents=True)
    (fake / "strategies" / "pb-001.yaml").write_bytes(b"lookbacks: [63]\n")
    (fake / "universe.yaml").write_bytes(b"assets: []\n")
    assert rules_hash(tmp_path, "PB-001") != first


@pytest.mark.parametrize("strategy_newline", [b"\n", b"\r\n"])
@pytest.mark.parametrize("universe_newline", [b"\n", b"\r\n"])
def test_rules_hash_ignores_checkout_line_endings(tmp_path: Path, strategy_newline, universe_newline) -> None:
    fake = tmp_path / "config"
    (fake / "strategies").mkdir(parents=True)
    strategy = b"id: PB-001\nlookbacks: [63]\n"
    universe = b"assets:\n  - US.SPY\n"
    strategy_path = fake / "strategies" / "pb-001.yaml"
    strategy_path.write_bytes(strategy.replace(b"\n", strategy_newline))
    (fake / "universe.yaml").write_bytes(universe.replace(b"\n", universe_newline))
    expected = hashlib.sha256(strategy + universe).hexdigest()[:12]
    assert rules_hash(tmp_path, "PB-001") == expected
    strategy_path.write_bytes(strategy.replace(b"63", b"64").replace(b"\n", strategy_newline))
    assert rules_hash(tmp_path, "PB-001") != expected


def test_rules_hash_isolated_per_strategy(tmp_path: Path) -> None:
    fake = tmp_path / "config"
    (fake / "strategies").mkdir(parents=True)
    (fake / "strategies" / "pb-001.yaml").write_bytes(b"id: PB-001\n")
    (fake / "universe.yaml").write_bytes(b"assets: []\n")
    frozen = rules_hash(tmp_path, "PB-001")
    (fake / "strategies" / "pb-002.yaml").write_bytes(b"id: PB-002\n")
    assert rules_hash(tmp_path, "PB-001") == frozen
    (fake / "strategies" / "pb-002.yaml").write_bytes(b"id: PB-002\nenabled: false\n")
    assert rules_hash(tmp_path, "PB-001") == frozen
    (fake / "universe.yaml").write_bytes(b"assets: [US.SPY]\n")
    assert rules_hash(tmp_path, "PB-001") != frozen


def test_rules_hash_covers_every_mapped_lane() -> None:
    """PB-002/003/004 hashed nothing at all, so their freeze guard blocked everything (L-036)."""
    for strategy_id in PLAYBOOK_LANES:
        source = rules_path_for(ROOT, strategy_id)
        assert source.is_file(), f"{strategy_id}: {source} is the freeze source but does not exist"
        assert len(rules_hash(ROOT, strategy_id)) == 12, f"{strategy_id}: no hash"

    tactical_pair = {rules_hash(ROOT, pid) for pid in ("PB-002", "PB-003")}
    assert len(tactical_pair) == 1, "PB-002/PB-003 share config/tactical.yaml, so they freeze together"
    assert rules_hash(ROOT, "PB-004") not in tactical_pair


def test_no_freeze_source_names_a_document() -> None:
    """A doc path inside the hashed bytes re-freezes a strategy every time the prose moves (L-037)."""
    for strategy_id in PLAYBOOK_LANES:
        text = rules_path_for(ROOT, strategy_id).read_text(encoding="utf-8")
        assert "playbook/" not in text, f"{strategy_id}: thesis path leaked into frozen rules"



def test_plan_pipeline_pins_inputs(tmp_path: Path) -> None:
    prices = tmp_path / "prices.csv"
    prices.write_text("date,symbol,close\n2026-11-17,US.SPY,100\n", encoding="utf-8")
    config = load_config(ROOT)
    strategy = config.strategy_by_id("PB-001")
    checks = {"equity_trend": True, "golden_cross": True, "vol_calm": False, "credit_trend": False}
    pipe = build_plan_pipeline(ROOT, strategy, Regime.NEUTRAL, checks, prices, "reports/brief.md")
    assert pipe.thesis_ref.startswith("PB-001")
    assert pipe.rules_hash == rules_hash(ROOT, "PB-001")
    assert pipe.outlook.value == "range"
    assert pipe.conviction == "medium"
    assert (pipe.checks_score, pipe.checks_total) == (2, 4)
    assert pipe.inputs_ref.prices_sha256
    assert pipe.inputs_ref.brief == "reports/brief.md"


def test_order_pipeline_fields_are_derived_not_fabricated() -> None:
    config = load_config(ROOT)
    snapshot = AccountSnapshot(account_id="SIM-TEST", cash=100_000.0)
    intent = OrderIntent(
        symbol="US.SPY", side=Side.BUY, quantity=10, limit_price=100.0, reason="rebalance"
    )
    verdict = RiskVerdict(allowed=True, adjusted_quantity=10)
    pipe = build_order_pipeline(
        intent,
        verdict,
        snapshot,
        config,
        config.strategy_by_id("PB-001"),
        Regime.NEUTRAL,
        "medium",
    )
    assert pipe.vehicle == "etf"
    assert "equity" in pipe.vehicle_rationale
    assert pipe.expected_edge is not None
    assert pipe.expected_edge.r is None and pipe.expected_edge.pct is None
    assert "provisional" in pipe.expected_edge.label
    assert "risk_off" in pipe.invalidation
    assert pipe.protection_type == "rebalance"
    assert pipe.roll_plan is None
    assert pipe.sizing.notional == 1000.0
    assert pipe.sizing.nav_pct == 0.01
    assert pipe.sizing.single_asset_cap_pct == config.risk.max_position_weight
    assert pipe.sizing.sleeve_cap_pct == config.strategy_by_id("PB-001").sleeve_caps["neutral"].equity
    assert pipe.action == "act"