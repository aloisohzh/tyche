from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tyche.pipeline import rules_hash

RULES_HASH_LINE = re.compile(r"\*\*Rules hash:\*\*\s*`([0-9a-f]{12})`")
PLAYBOOK_ID = re.compile(r"^(PB-\d{3})-")


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


def _playbook_hashes() -> list[tuple[str, str]]:
    found = []
    for path in sorted((ROOT / "docs" / "playbooks").glob("PB-*.md")):
        matched = PLAYBOOK_ID.match(path.name)
        declared = RULES_HASH_LINE.search(path.read_text(encoding="utf-8"))
        if matched and declared:
            found.append((matched.group(1), declared.group(1)))
    return found


def test_declared_playbook_rules_hash_matches_the_kernel() -> None:
    """A freeze hash that never matched its bytes silently launders a rules change (L-030)."""
    pairs = _playbook_hashes()
    assert pairs, "no playbook declares a rules hash; the guard would pass vacuously"
    for strategy_id, declared in pairs:
        frozen = ROOT / "config" / "strategies" / f"{strategy_id.lower()}.yaml"
        if not frozen.is_file():
            continue  # planned playbook with no kernel config yet
        assert declared == rules_hash(ROOT, strategy_id), (
            f"{strategy_id}: playbook says {declared} but the kernel computes "
            f"{rules_hash(ROOT, strategy_id)}; re-register the rules, do not just edit the doc"
        )


def test_playbook_ids_are_claimed_once() -> None:
    """PB-004 named two setups at once and attribution became unreliable (L-029)."""
    table = _doc("docs/playbooks/README.md")
    ids = re.findall(r"^\| (PB-\d{3}) \|", table, flags=re.MULTILINE)
    assert ids, "playbook index table is missing"
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"playbook id claimed by more than one setup: {sorted(duplicates)}"
