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


def test_the_card_pins_the_version_the_operator_names_and_only_one_that_exists():
    """A roster re-pin or template archive can recompile the desk into a spare "current" version nobody
    reviewed, so the operator names the verified number; a number the platform does not have is refused."""
    module = _module()
    assert module.card_pin([], {"version": 36}) == 36
    assert module.card_pin(["--pin", "35"], {"version": 36}) == 35
    for argv, agent in ((["--pin", "37"], {"version": 36}), (["--pin", "v35"], {"version": 36}),
                        (["--pin", "0"], {"version": 36}), ([], {"version": "latest"})):
        with pytest.raises(SystemExit):
            module.card_pin(argv, agent)


def test_the_card_can_be_born_on_a_recreated_desk_agent():
    module = _module()
    assert module.card_agent([]) == module.AGENT_ID
    assert module.card_agent(["--agent", "agent_00w9abcdefghijkl"]) == "agent_00w9abcdefghijkl"
    for bad in ("36", "dep_00vzb9h4ezawwl4thnva", "agent_"):
        with pytest.raises(SystemExit):
            module.card_agent(["--agent", bad])


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


def test_orders_clause_names_the_two_modes_and_forbids_writing_the_envelope():
    """Ask me or Within my bounds, decided by the same-day envelope at the fire; the run may read that
    file and never author it, so a mode can only be set by the operator from the desk."""
    prompt = _module().card_prompt(PERMANENT)
    clause = " ".join(prompt.split("ORDERS:", 1)[1].split("\n\n", 1)[0].split())
    for must in ("exactly two modes", "WITHIN MY BOUNDS for whatever a same-day envelope's lines cover", "no Telegram ask",
                 "ASK ME for everything else", "Telegram /approve N in this run", "tyche approve-telegram",
                 "Never write, edit or re-date the envelope", "entry AND exit authorization",
                 "`order` block with its exit_floor", "ONE paper"):
        assert must in clause, must
    assert "the executor may submit paper orders" in clause


def test_proposal_approval_is_explicit_numbered_and_never_automatic():
    """The Telegram wait step adds a gate in front of the submit path; it must never read as a way
    around the envelope, audit and reserve, and only the command's `approved` list may open it."""
    prompt = _module().card_prompt(PERMANENT)
    clause = " ".join(prompt.split("PROPOSAL APPROVAL (TELEGRAM WAIT", 1)[1].split("\n\n", 1)[0].split())
    for must in ("08:05 and 15:05 fires", "wait-for-reply", "render-proposal",
                 "templates/proposal-approval.example.json", "stop, target, exit-by", "`order` block",
                 "10-minute window", "`approved`", "tyche approve-telegram", "exact-order audit, reserve",
                 "for every entry no same-day envelope line covers",
                 "Skip the ask only for an entry a same-day envelope line already covers",
                 "any free-text reply is a no", "A requested change is a no", "new number",
                 "never approve on the operator's behalf", "never submit after the window",
                 "The 12:05 fire never runs this step"):
        assert must in clause, must
    assert _module().prompt_markers(prompt)["has_proposal_approval"]
    # The midday clause is untouched by the addition.
    assert "MIDDAY (12:05 ET, WATCH AND SHOUT ONLY)" in prompt


def test_feed_publish_is_the_last_step_and_never_a_trading_step():
    """The hosted page is only as fresh as the last publish; the card runs the script after the digest,
    once, and a failure is reported, not retried or patched by hand."""
    prompt = _module().card_prompt(PERMANENT)
    clause = " ".join(prompt.split("PUBLISH (2026-11-23):", 1)[1].split())
    for must in ("very last step", "after the digest is sent", "python scripts/publish_desk_data.py",
                 "Run it once", "never retry in a loop", "never edit the feed files by hand",
                 "never print a token", "places no order and changes no rule"):
        assert must in clause, must
    assert prompt.index("REPORT:") < prompt.index("PUBLISH (2026-11-23):")
    assert _module().prompt_markers(prompt)["has_feed_publish"]
    assert _module().prompt_markers(prompt)["has_performance_pack"]
    assert "regenerates the day's performance pack" in clause and "skipped, never a reason to" in clause
    # 2026-11-23: three fires left their bundles on Drive only, and the feed was built from 0 journal events.
    for must in ("restores the journal from the longest verified Drive run bundle",
                 "copies every Drive run bundle git does not hold yet into docs/performance/<run>/",
                 "withheld and named", "the new bundles and that pack",
                 "must already be on Drive under /data/drive/tyche-raw/<run>/"):
        assert must in clause, must


def test_fib_pullback_clause_is_switch_gated_and_approval_bound():
    """PB-007 runs only while the operator's switch says so, scans at 08:05 only, and every entry still
    goes through the same approval path as any other proposal; a dry scan is not a problem."""
    prompt = _module().card_prompt(PERMANENT)
    clause = " ".join(prompt.split("PB-007 FIB PULLBACK (2026-11-23):", 1)[1].split("BUDGET:", 1)[0].split())
    for must in ("tyche strategies --json", "never edit it in a run", "08:05 fire", "tyche fib-scan",
                 "--record", "exact-order audit", "Telegram /approve", "12:05 never scans",
                 "15:05 runs exits first", "no setup is a normal outcome", "skip this block entirely"):
        assert must in clause, must
    assert prompt.index("PROPOSAL APPROVAL (TELEGRAM WAIT") < prompt.index("PB-007 FIB PULLBACK (2026-11-23):")
    assert "PB-007 swing 20% (only while its switch is on)" in prompt
    assert _module().prompt_markers(prompt)["has_fib_pullback"]


def test_nav_references_pin_the_verified_start_and_retire_the_unverified_mark():
    prompt = _module().card_prompt(PERMANENT)
    clause = prompt.split("NAV REFERENCES (2026-11-23):", 1)[1].split("\n\n", 1)[0]
    assert "100,000.00 starting" in clause and "102,208.99" in clause and "retired" in clause
    assert "never lower it" in clause
    assert _module().prompt_markers(prompt)["has_nav_references"]


def test_operator_exit_is_direct_never_at_midday_and_paper_only():
    prompt = _module().card_prompt(PERMANENT)
    clause = prompt.split("OPERATOR EXIT (2026-11-24):", 1)[1].split("\n\n", 1)[0]
    assert "tyche exit-now" in clause and "ONE" in clause and "Never at the 12:05 fire" in clause
    assert "Paper account only" in clause and "never retry" in clause
    assert _module().prompt_markers(prompt)["has_operator_exit"]


def test_long_options_clause_is_switch_gated_buy_only_and_never_midday():
    prompt = _module().card_prompt(PERMANENT)
    clause = prompt.split("PB-003 LONG OPTIONS (2026-11-24):", 1)[1].split("\n\n", 1)[0]
    assert "tyche strategies\n--json" in clause or "tyche strategies --json" in clause
    assert "Never sell an option to open" in clause and "never a spread" in clause
    assert "AFTER 2026-11-27" in clause and "Never submit at 12:05" in clause
    assert "Options stay\ndisabled" not in prompt
    assert "PB-003 option premium cap 5%" in prompt
    assert _module().prompt_markers(prompt)["has_long_options"]


def test_a_sell_only_exit_note_never_silences_the_telegram_ask():
    prompt = _module().card_prompt(PERMANENT)
    assert "never means \"no buy authority today\"" in prompt
    assert "including on a day with a sell-only exit note" in prompt
    assert "VNQ ...597 and SMH ...500 are closed" in prompt
    assert _module().prompt_markers(prompt)["has_rulings"]


def test_an_on_demand_run_trades_like_the_close_fire_on_fresh_quotes():
    """The operator can fire the desk card outside its schedule; inside the session that run is a full
    trading run with the Telegram asks, outside it the run only reconciles."""
    prompt = _module().card_prompt(PERMANENT)
    clause = " ".join(prompt.split("ON-DEMAND RUN (2026-11-24, operator):", 1)[1].split("\n\n", 1)[0].split())
    for must in ("within 10 minutes after 08:05, 12:05 or 15:05 ET", "fresh quotes",
                 "everything the 15:05 close fire does", "PROPOSAL APPROVAL", "never scanned", "submits nothing",
                 "ON-DEMAND RUN"):
        assert must in clause, must
    assert _module().prompt_markers(prompt)["has_on_demand"]
    source = (ROOT / "scripts" / "deploy_two_fire_automation.py").read_text()
    assert '"--run-now" in sys.argv' in source and "refusing to run a deployment that is not the Tyche desk card" in source
