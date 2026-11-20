"""The live card instruction is a trading contract: pin its fires, gates and midday limits."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "desk_card_prompt_test", ROOT / "scripts/deploy_two_fire_automation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_card_fires_three_times_on_trading_days_only():
    cron = _module().desk_cron(date(2026, 11, 19), date(2026, 11, 30)).split()
    assert cron[1] == "8,12,15"                      # 08:05 / 12:05 / 15:05 ET
    assert cron[2] == "19-20,23-25,27,30"            # weekends and Thanksgiving excluded
    assert cron[3:] == ["11", "*"]                   # one month per card


def test_midday_fire_watches_and_shouts_but_never_trades():
    prompt = _module().card_prompt((date(2026, 11, 19), date(2026, 11, 30)))
    assert "{{WINDOW}}" not in prompt
    assert "MIDDAY (12:05 ET, WATCH AND SHOUT ONLY)" in prompt
    midday = prompt.split("MIDDAY (12:05 ET, WATCH AND SHOUT ONLY):", 1)[1].split("\n\n", 1)[0].lower()
    for forbidden in ("reserve", "approve", "revoke", "modify", "config", "propose"):
        assert forbidden in midday
    assert "urgent risk alert" in midday and "never at this fire" in midday


def test_premarket_and_close_authority_and_contracts_survive_the_edit():
    markers = _module().prompt_markers(_module().card_prompt((date(2026, 12, 1), date(2026, 12, 31))))
    assert all(markers.values()), markers
    assert "the executor may submit paper orders" in _module().PROMPT
