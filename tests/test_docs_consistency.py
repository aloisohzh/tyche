from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _risk() -> dict:
    return yaml.safe_load((ROOT / "config" / "risk.yaml").read_text(encoding="utf-8"))


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_published_order_and_turnover_match_config() -> None:
    risk = _risk()
    orders = risk["max_orders_per_day"]
    turnover = risk["max_daily_turnover_pct"]
    readme = _doc("README.md")
    assert f"Internal order budget is {orders}/day" in readme
    assert f"competition ceiling {risk['competition_order_cap']}" in readme
    assert f"daily turnover {turnover:.0%} of NAV" in readme
    card = _doc("docs/risk-card.md")
    assert f"| Executed orders/day | ≤ {risk['competition_order_cap']} | ≤ {orders} |" in card
    assert "`max_daily_turnover_pct`" in card


def test_published_price_floor_matches_config() -> None:
    price = _risk()["min_price"]
    assert f"${price:.2f} minimum price" in _doc("README.md")
    assert f"| Min price | ${price:.2f} | ${price:.2f} |" in _doc("docs/risk-card.md")
