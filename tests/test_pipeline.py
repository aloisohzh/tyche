from __future__ import annotations

from pathlib import Path

from tyche.config import load_config
from tyche.models import AccountSnapshot, OrderIntent, Regime, RiskVerdict, Side
from tyche.pipeline import (
    PLAYBOOK,
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
    first = rules_hash(ROOT)
    assert first == rules_hash(ROOT)
    assert len(first) == 12
    fake = tmp_path / "config"
    fake.mkdir()
    (fake / "strategy.yaml").write_bytes(b"lookbacks: [63]\n")
    (fake / "universe.yaml").write_bytes(b"assets: []\n")
    assert rules_hash(tmp_path) != first


def test_plan_pipeline_pins_inputs(tmp_path: Path) -> None:
    prices = tmp_path / "prices.csv"
    prices.write_text("date,symbol,close\n2026-11-17,US.SPY,100\n", encoding="utf-8")
    config = load_config(ROOT)
    checks = {"equity_trend": True, "golden_cross": True, "vol_calm": False, "credit_trend": False}
    pipe = build_plan_pipeline(ROOT, config, Regime.NEUTRAL, checks, prices, "reports/brief.md")
    assert pipe.thesis_ref.startswith(PLAYBOOK)
    assert pipe.rules_hash == rules_hash(ROOT)
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
    pipe = build_order_pipeline(intent, verdict, snapshot, config, Regime.NEUTRAL, "medium")
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
    assert pipe.sizing.sleeve_cap_pct == config.strategy.sleeve_caps["neutral"].equity
    assert pipe.action == "act"