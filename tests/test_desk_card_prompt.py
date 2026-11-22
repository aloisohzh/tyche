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


def test_calendar_drift_check_is_premarket_alert_only_and_never_self_applying():
    """The clause the paused schedule used to carry alone is now on the fire that runs (L-019's
    live object is the card, so a check nobody schedules is a check that does not happen)."""
    prompt = _module().card_prompt((date(2026, 12, 1), date(2026, 12, 31)))
    assert "CALENDAR DRIFT" in prompt
    clause = prompt.split("CALENDAR DRIFT", 1)[1].split("\n\n", 1)[0]
    clause = " ".join(clause.split())  # the prompt wraps for reading; the contract does not
    assert "08:05 premarket only" in clause and "Skip at the 12:05 and 15:05 fires" in clause
    assert "tyche calendar-check --source" in clause and "--json" in clause
    assert "scripts/refresh_calendar.py" in clause and "calendar.check" in clause
    # Alert-only means the run cannot act on its own finding, in either direction.
    for guard in ("Never edit config", "never invent a", "not a reason to skip or to trade"):
        assert guard in clause
    assert "UNCERTAIN, not a pass" in clause
    # L-033 discipline: the clause points at the tables and the command, never at their contents.
    assert not any(year in clause for year in ("2026", "2027", "2028"))


def test_proposal_approval_is_explicit_numbered_and_never_automatic():
    """The Telegram wait step adds a gate in front of the submit path; it must never read as a way
    around the envelope, audit and reserve, and only the command's `approved` list may open it."""
    prompt = _module().card_prompt((date(2026, 12, 1), date(2026, 12, 31)))
    clause = " ".join(prompt.split("PROPOSAL APPROVAL (TELEGRAM WAIT", 1)[1].split("\n\n", 1)[0].split())
    for must in ("08:05 and 15:05 fires", "wait-for-reply", "render-proposal",
                 "templates/proposal-approval.example.json", "stop, target, exit-by",
                 "10-minute window", "`approved`", "envelope, exact-order audit, reserve",
                 "any free-text reply is a no", "A requested change is a no", "new number",
                 "never approve on the operator's behalf", "never submit after the window",
                 "The 12:05 fire never runs this step"):
        assert must in clause, must
    assert _module().prompt_markers(prompt)["has_proposal_approval"]
    # The midday clause is untouched by the addition.
    assert "MIDDAY (12:05 ET, WATCH AND SHOUT ONLY)" in prompt
