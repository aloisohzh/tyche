"""The 15-minute card brief: one job (THE CYCLE, once), the same order path as the desk card."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("scalp_card", ROOT / "scripts" / "deploy_scalp_card.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_card_has_one_job_and_a_time_box():
    mod = _module()
    prompt = mod.card_prompt()
    flat = _flat(prompt)
    for must in ("ONE job: run THE CYCLE below once, for every lane, and stop",
                 "this brief wins (see RULINGS)",
                 "GATE: if the New York date is after 2026-11-30, end the run",
                 "TIME LIMIT: this run owns 13 minutes from its scheduled start",
                 "An order is never sent after its `submit_before`",
                 "NOTHING ELSE: no research, no watchlist edit, no digest, no publish step and no lock file",
                 "a quiet run sends no Telegram"):
        assert must in flat, must
    assert prompt.index("GATE:") < prompt.index("TIME LIMIT:") < prompt.index("BOOTSTRAP:") < prompt.index("THE CYCLE (2026-11-25)")
    assert "{{" not in prompt
    assert len(prompt) < 9_500, len(prompt)
    # Markers are read from the platform's JSON, so each phrase must sit on one line of the brief.
    events = json.dumps([{"type": "user.message", "content": [{"type": "text", "text": prompt}]}])
    assert all(mod.prompt_markers(events).values()), mod.prompt_markers(events)


def test_both_cards_carry_the_same_order_path_word_for_word():
    """Two briefs that each described the order path drifted apart within a day (24 Nov). The 15-minute
    card imports the desk card's text, so the only difference is the name of the run folder."""
    mod = _module()
    desk_prompt = mod.desk.card_prompt("2026-11-24..")
    card_prompt = mod.card_prompt()

    def shared(prompt: str) -> str:
        text = prompt.split("THE CYCLE (2026-11-25):", 1)[1]
        text = text.split("\n\nOTHER LANES", 1)[0].split("\n\nNOTHING ELSE", 1)[0]
        for kind, example in (("<premarket|midday|close|ondemand>", "2026-11-25-premarket-1305"),
                              ("cycle", "2026-11-25-cycle-1437")):
            text = text.replace(f"<New York date>-{kind}-<HHMM UTC>", "<RUN>").replace(example, "<EXAMPLE>")
        return text
    assert shared(desk_prompt) == shared(card_prompt)
    assert "RULINGS (2026-11-25, operator)" in shared(card_prompt) and "PROBLEMS:" in shared(card_prompt)
    assert "<New York date>-cycle-<HHMM UTC>" in card_prompt and "2026-11-25-cycle-1437" in card_prompt


def test_the_card_no_longer_runs_any_step_by_hand():
    prompt = _module().card_prompt()
    for gone in ("tyche tactical", "tyche record-order", "tyche journal-verify", "scalp-lock.json",
                 "PROTECTION WATCH", "FILLS FIRST", "--prior-close-nav", "watch-book.json", "at most 10 minutes"):
        assert gone not in prompt, gone


def test_the_card_explains_what_the_runs_around_the_open_and_the_close_do():
    flat = _flat(_module().card_prompt())
    for must in ("minutes 07, 22, 37 and 52 from 09:07 to 15:52 New York time",
                 "The desk card (08:05, 12:05 and 15:05 ET) does the research, writes the day's watchlist",
                 "never a second writer to stop for",
                 "before 09:30 it rests the day's stock buys",
                 "the 15:37 run (12:37 on an early close) sells every stock and scalp lot",
                 "the 15:52 run (12:52) is the second chance"):
        assert must in flat, must


def test_the_schedule_matches_what_the_brief_says_and_what_the_kernel_needs():
    """The brief's times are only true while the cron and the two exit rules stay where they are."""
    from tyche.config import load_config
    mod = _module()
    assert mod.SCALP_CRON == "7,22,37,52 9-15 * * 1-5"
    config = load_config(ROOT)
    # 15:37 is after the scalp's flatten line, and it is the stock lane's last check before its exit time.
    assert 60 - config.scalp.flatten_minutes_before_close <= 37
    assert 37 + config.tactical.monitor_interval_seconds // 60 >= 60 - config.tactical.session_exit_minutes_before_close
    assert config.tactical.monitor_interval_seconds == 900          # one check every 15 minutes


def test_writes_to_the_cloud_refuse_anything_but_this_card():
    source = (ROOT / "scripts" / "deploy_scalp_card.py").read_text()
    for flag, refusal in (('"--apply-update" in sys.argv', "refusing to update a deployment that is not the Tyche scalp card"),
                          ('"--run-now" in sys.argv', "refusing to run a deployment that is not the Tyche scalp card"),
                          ('"--pause" in sys.argv', "refusing to pause a deployment that is not the Tyche scalp card")):
        assert flag in source and refusal in source, flag
    assert "the live brief has no THE CYCLE clause yet; run --apply-update first" in source
    # The name is how the three guards recognise the card, and what the desk brief calls it.
    mod = _module()
    assert mod.CARD_NAME.startswith("Tyche scalp")
    assert mod.CARD_NAME in mod.desk.card_prompt("2026-11-24..")
