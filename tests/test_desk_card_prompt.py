"""The live card instruction is a trading contract: pin its fires, its one order path and its one hard rule."""
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
    """Two desk cards that both fire would each do the research and send the digests. The guard lists what
    is still active on or after the start day; a paused card and a monthly card already ended do not count."""
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


def _clause(prompt: str, start: str, end: str = "\n\n") -> str:
    """One clause of the brief with its line wraps removed: the brief wraps for reading, the contract does not."""
    return " ".join(prompt.split(start, 1)[1].split(end, 1)[0].split())


def test_the_brief_is_complete_and_stays_short():
    """Every marker `--apply-update` insists on is present, and the brief does not grow back: the
    27,000-character brief of 24 Nov asked for about 45 hand steps and placed no order."""
    module = _module()
    prompt = module.card_prompt(PERMANENT)
    markers = module.prompt_markers(prompt)
    assert all(markers.values()), markers
    assert len(prompt) < 17_000, len(prompt)
    assert "{{CYCLE}}" not in prompt and "{{RUN_KIND}}" not in prompt and "{{RUN_EXAMPLE}}" not in prompt
    # The markers are read from the platform's JSON, where a line break is two characters: every
    # marker phrase therefore has to sit on one line of the brief.
    import json
    events = json.dumps([{"type": "user.message", "content": [{"type": "text", "text": prompt}]}])
    assert all(module.prompt_markers(events).values()), module.prompt_markers(events)


def test_every_fire_runs_the_cycle_and_the_midday_fire_may_trade():
    """12:05 used to watch and shout only, so a setup that came into range at noon waited three hours."""
    prompt = _module().card_prompt(PERMANENT)
    fires = _clause(prompt, "FIRES:")
    for must in ("08:05 ET premarket: BOOTSTRAP, RESEARCH, THE CYCLE once", "DIGEST, PUBLISH",
                 "12:05 ET: BOOTSTRAP, RESEARCH only if today's watchlist is missing, THE CYCLE once, PUBLISH",
                 "15:05 ET: BOOTSTRAP, THE CYCLE once, DIGEST, PUBLISH",
                 "It is expected, never a second desk and never a reason to block",
                 "never reserves a second order for a symbol while one is on its way or working"):
        assert must in fires, must
    assert "Every run inside the session may place orders, the 12:05 fire included" in " ".join(prompt.split())
    for gone in ("WATCH AND SHOUT", "submits nothing", "never at this fire", "Never at the 12:05 fire"):
        assert gone not in prompt, gone


def test_the_order_path_is_one_command_and_nothing_is_run_by_hand():
    prompt = _module().card_prompt(PERMANENT)
    cycle = _clause(prompt, "THE CYCLE (2026-11-25):", "\n\nPROBLEMS:")
    order = [cycle.index(step) for step in ("1. LIST:", "2. READ:", "3. DECIDE:", "4. SEND:", "5. TELL:")]
    assert order == sorted(order)
    for must in ("`tyche cycle --dir <run> --reads`", "`tyche cycle --dir <run> --record`",
                 "Only the executor reads or writes at the broker",
                 "copy that file whole with `cp`: nothing is retyped",
                 "sim_trade_history_order_list, every page until has_more is false",
                 "ONE sim_trade_input_order paper LIMIT order with exactly the item's symbol, side, quantity and limit_price",
                 "the item's `remark` as the order remark", "before the item's `submit_before`",
                 "One attempt per item: never a retry, never a changed field and never an order that is not on the list",
                 "prints the same answer again and reserves nothing twice",
                 'python scripts/telegram.py send "$(cat <run>/telegram.txt)"',
                 "Never run tactical tick, reserve, scalp, capture, lifecycle or record-order beside it",
                 "never copy the journal"):
        assert must in cycle, must
    # None of the 24 Nov hand steps is asked for anywhere in the brief.
    for gone in ("tyche tactical", "tyche record-order", "tyche approve-telegram", "wait-for-reply",
                 "tyche lifecycle", "tyche journal-verify", "nav-refs", "scalp-lock.json", "--prior-close-nav",
                 "exact-order audit"):
        assert gone not in prompt, gone
    problems = _clause(prompt, "PROBLEMS:")
    for must in ('a "blocked" answer names its own fix in `reason`', "Do that fix once",
                 "Never place an order by hand", "never edit the journal, a config file or an approval file"):
        assert must in problems, must


def test_the_rulings_retire_the_old_gates_and_keep_the_one_hard_rule():
    """The agents' own instructions still carry the 24 Nov gates; the dated operator rulings are what
    tells them those gates are retired for cycle runs, so they travel with every executor delegation."""
    prompt = _module().card_prompt(PERMANENT)
    rulings = _clause(prompt, "RULINGS (2026-11-25, operator).", "\n\nOTHER LANES")
    for must in ("quote this block in every executor delegation",
                 "`tyche cycle --record` IS the reservation", "journals order.requested before it prints",
                 "An item under `submit` is authorized. Nothing else is.",
                 "data/standing-approval.json", "data/scalp-approvals.json",
                 "needs no Telegram approval, no auditor review and no per-order envelope",
                 "selling a lot the desk holds needs no approval line at all",
                 "reads up to 15 minutes old are fresh", "a reserved order has 10 minutes to be sent",
                 "The 30, 60, 90 and 120 second figures in older text are retired",
                 "Broker status 5 is a finished order", "No other cancel and no modify",
                 "the allowlisted US paper account only, and the command refuses anything else",
                 "Never a live account, a market order, a short sale or an order the command did not list"):
        assert must in rulings, must
    assert "this brief wins (see RULINGS)" in " ".join(prompt.split())


def test_the_rulings_state_the_clocks_the_config_really_has():
    """A ruling that quotes a number the kernel does not use is how the old brief and the old kernel
    came to disagree; the two figures in the brief are read back from config here."""
    from tyche.config import load_config
    config = load_config(ROOT)
    assert config.tactical.max_snapshot_age_seconds == config.tactical.max_quote_age_seconds == 900
    assert config.scalp.max_snapshot_age_seconds == config.scalp.max_quote_age_seconds == 900
    assert config.tactical.submit_window_seconds == config.scalp.entry_submit_window_seconds == 600
    assert config.tactical.resting_reach_pct == 0.03 and config.tactical.min_reward_risk == 1.5   # RESEARCH
    assert config.tactical.max_confirmation_ticks == 1


def test_research_writes_the_one_file_the_command_reads_and_aims_at_prices_that_can_fill():
    prompt = _module().card_prompt(PERMANENT)
    research = _clause(prompt, "RESEARCH:", "\n\nPB-003 OPTION")
    for must in ("/data/drive/tyche-raw/watchlist.json", '{"as_of": "<New York date>", "entries": [...]}',
                 "At most one entry per symbol", "stop < entry_low <= entry_high < target",
                 "at least 1.5 times the risk", "sources (at least one URL)", 'axis "fundamental"',
                 "a setup without both does not trade",
                 "Leave out setup_id, expiry, reviewed_at and exit_at for a stock",
                 "a price up to 3% above the zone rests a DAY limit at entry_high",
                 "entry_high no more than about 1% below the last price",
                 "a desk that only waits places no trade",
                 "`tyche cycle --dir <run> --reads`", 'an alert "left out: ..." names a setup and the field to fix',
                 "read `stocks.decisions`"):
        assert must in research, must


def test_feed_publish_is_the_last_step_and_never_a_trading_step():
    """The hosted page is only as fresh as the last publish; the card runs the script after the digest,
    once, and a failure is reported, not retried or patched by hand."""
    prompt = _module().card_prompt(PERMANENT)
    clause = " ".join(prompt.split("PUBLISH (2026-11-23):", 1)[1].split())
    for must in ("very last step", "after the digest is sent", "python scripts/publish_desk_data.py",
                 "Run it once", "never retry in a loop", "never edit the feed files by hand",
                 "never print a token", "places no order and changes no rule"):
        assert must in clause, must
    assert prompt.index("DIGEST (08:05") < prompt.index("PUBLISH (2026-11-23):")
    assert prompt.rstrip().endswith("It places no order and changes no rule.")
    assert _module().prompt_markers(prompt)["has_feed_publish"]
    assert _module().prompt_markers(prompt)["has_performance_pack"]
    assert "regenerates the day's performance pack" in clause and "skipped, never a reason to" in clause
    # 2026-11-23: three fires left their bundles on Drive only, and the feed was built from 0 journal events.
    for must in ("restores the journal from the longest verified Drive run bundle",
                 "copies every Drive run bundle git does not hold yet into docs/performance/<run>/",
                 "withheld and named", "the new bundles and that pack",
                 "must already be on Drive under /data/drive/tyche-raw/<run>/"):
        assert must in clause, must


def test_the_digest_reports_only_what_the_cycle_report_shows():
    prompt = _module().card_prompt(PERMANENT)
    digest = _clause(prompt, "DIGEST (08:05, 15:05 and on-demand runs):")
    for must in ("SENTINEL FORMAT V1", "python scripts/telegram.py send-digest <file>", "<run>/cycle.json",
                 "Say plainly when no order was placed",
                 "Never claim a fill or an approval the report does not show",
                 "never include an account id or a token", "UNCONFIRMED: do not send it again",
                 "The 12:05 fire sends no digest"):
        assert must in digest, must


def test_operator_exit_is_direct_and_paper_only():
    prompt = _module().card_prompt(PERMANENT)
    clause = _clause(prompt, "OPERATOR EXIT (2026-11-24):")
    for must in ("only when the operator asked today", "tyche exit-now", "--journal <ledger>",
                 "ONE limit sell", "never to retry", "Paper account only, always"):
        assert must in clause, must
    assert _module().prompt_markers(prompt)["has_operator_exit"]


def test_long_options_clause_is_switch_gated_optional_and_buy_only():
    prompt = _module().card_prompt(PERMANENT)
    clause = _clause(prompt, "PB-003 OPTION (2026-11-24 test;")
    for must in ("only while `tyche strategies --json` lists PB-003 enabled", "at most ONE long call",
                 "expiry after 2026-11-27", "open interest of at least 100", "premium_limit",
                 "Never sell an option to open, never a spread",
                 "leave the option out: the stock setups do not depend on it"):
        assert must in clause, must
    assert _module().prompt_markers(prompt)["has_long_options"]


def test_an_on_demand_run_is_a_whole_run_on_fresh_reads():
    """The operator can fire the desk card outside its schedule; it researches if the day has no
    watchlist yet and then runs the same cycle as any fire. Outside the session the cycle skips."""
    prompt = _module().card_prompt(PERMANENT)
    clause = _clause(prompt, "ON-DEMAND RUN (2026-11-24, operator):")
    for must in ("within 10 minutes after 08:05, 12:05 or 15:05 ET", "RESEARCH only if today's watchlist is missing",
                 "THE CYCLE once on fresh reads", 'a DIGEST titled "ON-DEMAND RUN"',
                 'Outside the session the cycle answers "skip"'):
        assert must in clause, must
    assert _module().prompt_markers(prompt)["has_on_demand"]
    source = (ROOT / "scripts" / "deploy_two_fire_automation.py").read_text()
    assert '"--run-now" in sys.argv' in source and "refusing to run a deployment that is not the Tyche desk card" in source


def test_lanes_the_operator_parked_place_no_order_from_the_brief():
    prompt = _module().card_prompt(PERMANENT)
    assert "PB-001 ballast and PB-007 place no order from this brief" in _clause(prompt, "OTHER LANES:")
    for gone in ("tyche fib-scan", "tyche rebalance", "lifecycle reserve"):
        assert gone not in prompt, gone
