"""The live card instruction is a trading contract: pin its fires, gates and midday limits."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "desk_card_prompt_test", ROOT / "scripts/deploy_two_fire_automation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PERMANENT = "2026-11-24.."
LEGACY = "2026-11-19..2026-11-30"


def test_the_card_is_permanent_and_fires_three_times_every_weekday():
    """One card, no end date. Holidays are not in the cron: the monthly day lists had to be regenerated
    every month, and a month nobody regenerated is a desk that silently stops. `tyche calendar --json`
    ends a holiday fire read-only at its first step instead."""
    cron = _module().desk_cron().split()
    assert cron == ["5", "8,12,15", "*", "*", "1-5"]  # 08:05 / 12:05 / 15:05 ET, Monday to Friday, forever
    assert _module().card_window(date(2026, 11, 24)) == PERMANENT


def test_the_start_day_is_the_next_weekday_unless_given():
    module = _module()
    assert module.card_start([], today=date(2026, 11, 22)) == date(2026, 11, 23)   # Sunday -> Monday
    assert module.card_start([], today=date(2026, 11, 27)) == date(2026, 11, 30)   # Friday -> Monday
    assert module.card_start(["--start", "2026-11-24"], today=date(2026, 11, 22)) == date(2026, 11, 24)


def test_the_clock_clause_tells_the_card_the_truth_about_its_own_cron():
    module = _module()
    permanent = module.card_prompt(PERMANENT)
    clock = permanent.split("CLOCK:", 1)[1].split("\n\n", 1)[0]
    assert "every Monday to Friday from 2026-11-24 with no end date" in clock
    assert "the only holiday filter" in clock and "tyche calendar --json" in clock
    assert "{{CADENCE}}" not in permanent and "{{WINDOW}}" not in permanent
    # A prompt write onto a still-live monthly card must not claim a cadence that card does not have.
    legacy = module.card_prompt(LEGACY).split("CLOCK:", 1)[1].split("\n\n", 1)[0]
    assert "only on NYSE trading days in the card window 2026-11-19..2026-11-30" in legacy
    assert "every Monday to Friday" not in legacy
    for prompt in (permanent, module.card_prompt(LEGACY)):
        assert module.prompt_markers(prompt)["has_holiday_note"]


def test_a_prompt_update_resends_the_live_cards_cron_and_metadata_unchanged():
    """The post-write drift guard insists only `initial_events` moved, so the payload must carry the
    card's own schedule and metadata, not this script's idea of them: a cadence change is a new card."""
    module = _module()
    live = {"id": "dep_nov", "schedule": {"type": "cron", "expression": "5 8,12,15 19-20,23-25,27,30 11 *",
                                          "timezone": "America/New_York", "upcoming_runs_at": ["x"]},
            "metadata": {"source": "operator", "profile": "three-fire", "window": LEGACY}}
    payload = module.update_payload(live, module.card_prompt(module.live_window(live)))
    assert payload["schedule"] == {"type": "cron", "expression": "5 8,12,15 19-20,23-25,27,30 11 *",
                                   "timezone": "America/New_York"}
    assert payload["metadata"] == live["metadata"]
    assert "card window 2026-11-19..2026-11-30" in payload["initial_events"][0]["content"][0]["text"]
    with pytest.raises(SystemExit):
        module.live_window({"id": "dep_x", "metadata": {}})


def test_creating_the_card_sees_every_other_desk_card_that_would_still_fire():
    """Two cards that both fire are two writers (STATE). The guard lists what is still active on or after
    the start day; a paused card and a monthly card already ended are not writers."""
    rows = [
        {"id": "nov", "name": "Tyche desk - premarket and close", "status": "active",
         "metadata": {"window": "2026-11-19..2026-11-30"}},
        {"id": "dec", "name": "Tyche desk - premarket and close (Dec)", "status": "paused",
         "metadata": {"window": "2026-12-01..2026-12-31"}},
        {"id": "oct", "name": "Tyche desk - premarket and close (Oct)", "status": "active",
         "metadata": {"window": "2026-10-01..2026-10-31"}},
        {"id": "scout", "name": "tyche scout", "status": "active", "metadata": {}},
    ]
    assert [c["id"] for c in _module().other_writers(rows, date(2026, 11, 24))] == ["nov"]
    assert _module().other_writers(rows, date(2026, 12, 1)) == []


def test_midday_fire_watches_and_shouts_but_never_trades():
    prompt = _module().card_prompt(PERMANENT)
    assert "MIDDAY (12:05 ET, WATCH AND SHOUT ONLY)" in prompt
    midday = prompt.split("MIDDAY (12:05 ET, WATCH AND SHOUT ONLY):", 1)[1].split("\n\n", 1)[0].lower()
    for forbidden in ("reserve", "approve", "revoke", "modify", "config", "propose"):
        assert forbidden in midday
    assert "urgent risk alert" in midday and "never at this fire" in midday


def test_premarket_and_close_authority_and_contracts_survive_the_edit():
    markers = _module().prompt_markers(_module().card_prompt(PERMANENT))
    assert all(markers.values()), markers
    assert "the executor may submit paper orders" in _module().PROMPT


def test_calendar_drift_check_is_premarket_alert_only_and_never_self_applying():
    """The clause the paused schedule used to carry alone is now on the fire that runs (L-019's
    live object is the card, so a check nobody schedules is a check that does not happen)."""
    prompt = _module().card_prompt(PERMANENT)
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
    prompt = _module().card_prompt(PERMANENT)
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
