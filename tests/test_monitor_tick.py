"""The Level 0 monitor tick: ADR 0013 runbook §8.1-8.3.

Every test here exists to prove one of two things: a breach is reported exactly once, or a
tick that could not judge is never allowed to read as "no breaches". The second property is
the one that would actually cost money, so most of this file is about failure paths.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tyche.cli import app
from tyche.journal import append_event, journal_lock, read_events, verify_chain
from tyche.monitor import DEFAULT_CADENCE_SECONDS, evaluate, session_gate, watch_targets
from tyche.tactical import MarketQuote
from tyche.watchlist import Watchlist, WatchlistEntry

ROOT = Path(__file__).resolve().parents[1]
# Friday 2026-11-20 at 10:00 ET: a trading day, inside the regular session.
NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
HASH = "a9a899f896ac0353cd85043aba118e3fda5d315477fcdabebe07a0c079199d25"


def plan(**overrides) -> dict:
    base = {
        "symbol": "US.MSFT", "sleeve": "equity", "strategy": "PB-002 tactical break",
        "entry_low": 490.0, "entry_high": 495.0, "stop": 470.0, "target": 540.0,
        "expiry": date(2026, 12, 31), "setup_id": "TAC-20261119-MSFT-L4", "direction": "bullish",
    }
    base.update(overrides)
    return WatchlistEntry.model_validate(base).model_dump(mode="json")


def journaled(**payload) -> dict:
    return {"type": "order.requested", "payload": payload}


def quote(symbol: str = "US.MSFT", last: float = 500.0, *, at: datetime = NOW,
          **overrides) -> MarketQuote:
    base = {"symbol": symbol, "at": at, "book_at": at, "last": last, "bid": last - 0.05,
            "ask": last + 0.05, "tradable": True}
    base.update(overrides)
    return MarketQuote.model_validate(base)


def run(*args) -> tuple[int, str]:
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.output


def tick_eval(*, quotes=None, events=None, now=NOW, **overrides):
    kwargs = {"cadence_seconds": DEFAULT_CADENCE_SECONDS, "max_quote_age_seconds": 120}
    kwargs.update(overrides)
    return evaluate(book=None, quotes=list(quotes if quotes is not None else []),
                    events=list(events if events is not None else []), now=now, **kwargs)


# ---------------------------------------------------------------- pure evaluation


def test_a_breached_level_emits_exactly_one_breach_event():
    events = [journaled(symbol="US.MSFT", side="buy", setup_hash=HASH, strategy_id="PB-002",
                        protected_setup=plan())]
    report = tick_eval(quotes=[quote(last=465.0)], events=events)
    assert report["status"] == "evaluated"
    assert len(report["breaches"]) == 1
    breach = report["breaches"][0]
    assert breach["symbol"] == "US.MSFT" and breach["level"] == 470.0
    assert breach["observed_price"] == 465.0 and breach["protection_type"] == "synthetic_stop"
    assert breach["exit_ref"] == "TAC-20261119-MSFT-L4"
    assert report["heartbeat"]["breached"] == 1


def test_the_same_breach_on_the_next_tick_emits_nothing_new():
    """De-duplication is by transition: a choppy afternoon must not repeat an episode."""
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan())]
    first = tick_eval(quotes=[quote(last=465.0)], events=events)
    carried = events + [{"type": "monitor.breach", "ts": NOW.isoformat(), "payload": first["breaches"][0]}]
    second = tick_eval(quotes=[quote(last=461.0)], events=carried)
    assert second["breaches"] == [] and second["clears"] == []
    assert second["heartbeat"]["breached"] == 1  # still open, still one episode


def test_price_back_inside_the_level_closes_the_episode():
    breach = {"symbol": "US.MSFT", "level": 470.0, "episode_id": "abc123",
              "strategy_id": "PB-002", "protection_type": "synthetic_stop",
              "observed_price": 465.0, "observed_at": (NOW - timedelta(minutes=6)).isoformat(),
              "exit_ref": "TAC-20261119-MSFT-L4"}
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan()),
              {"type": "monitor.breach", "ts": (NOW - timedelta(minutes=6)).isoformat(),
               "payload": breach}]
    report = tick_eval(quotes=[quote(last=481.0)], events=events)
    assert report["breaches"] == [] and len(report["clears"]) == 1
    assert report["clears"][0]["episode_id"] == "abc123"
    assert report["clears"][0]["duration_seconds"] == pytest.approx(360.0, abs=1.0)


def test_exposure_is_measured_from_the_print_not_from_the_append():
    """A writer that got to the journal late must not invent four minutes of extra risk.

    The clear leg's duration is the number an operator reads as "how long was I naked", so it
    is anchored to `observed_at`; the record timestamp is bookkeeping.
    """
    breach = {"symbol": "US.MSFT", "level": 470.0, "episode_id": "abc123",
              "observed_price": 465.0, "observed_at": (NOW - timedelta(minutes=2)).isoformat()}
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan()),
              {"type": "monitor.breach", "ts": NOW.isoformat(), "payload": breach}]
    assert tick_eval(quotes=[quote(last=481.0)], events=events)["clears"][0]["duration_seconds"] == \
        pytest.approx(120.0, abs=1.0)
    heartbeat = {"type": "monitor.heartbeat", "ts": NOW.isoformat(),
                 "payload": {"watched": 1, "tick_at": (NOW - timedelta(minutes=12)).isoformat()}}
    report = tick_eval(quotes=[quote()], events=[events[0], heartbeat], cadence_seconds=300)
    assert report["gap"]["missed_seconds"] == pytest.approx(720.0, abs=1)


def test_a_stale_quote_is_a_no_go_and_never_a_clean_report():
    old = NOW - timedelta(minutes=30)
    report = tick_eval(quotes=[quote(last=465.0, at=old, book_at=old)],
                       events=[journaled(symbol="US.MSFT", side="buy", protected_setup=plan())])
    assert report["status"] == "no-go"
    assert report["heartbeat"] is None and report["breaches"] == []
    assert "stale" in report["problems"][0]["reason"]


def test_a_missing_quote_is_named_rather_than_reported_as_no_breaches():
    report = tick_eval(quotes=[], events=[journaled(symbol="US.MSFT", side="buy",
                                                    protected_setup=plan())])
    assert report["status"] == "no-go" and "US.MSFT" in report["problems"][0]["reason"]


def test_an_untradable_quote_is_a_no_go():
    report = tick_eval(quotes=[quote(last=465.0, tradable=False)],
                       events=[journaled(symbol="US.MSFT", side="buy", protected_setup=plan())])
    assert report["status"] == "no-go"


def test_no_watch_targets_means_no_heartbeat_and_no_all_clear():
    report = tick_eval(quotes=[quote()], events=[])
    assert report["status"] == "empty"
    assert report["heartbeat"] is None


def test_a_naive_clock_is_refused_rather_than_assumed():
    with pytest.raises(ValueError):
        tick_eval(quotes=[quote()], now=datetime(2026, 11, 20, 14, 0))


def test_a_bearish_put_is_watched_at_its_underlying_and_upwards():
    put = {"symbol": "US.MSFT261218P460000", "underlying": "US.MSFT", "right": "put",
           "strike": 460.0, "expiry": date(2026, 12, 18), "multiplier": 100}
    events = [journaled(symbol="US.MSFT261218P460000", side="buy", strategy_id="PB-003",
                        protected_setup=plan(symbol="US.MSFT261218P460000", direction="bearish",
                                             target=430.0, stop=505.0, premium_limit=12.0,
                                             option=put, setup_id="TAC-PUT-1"))]
    targets, skipped, _ = watch_targets(None, events)
    assert skipped == [] and len(targets) == 1
    assert targets[0].quote_symbol == "US.MSFT" and targets[0].protection_type == "defined_risk"
    rising = tick_eval(quotes=[quote("US.MSFT", 512.0)], events=events)
    falling = tick_eval(quotes=[quote("US.MSFT", 480.0)], events=events)
    assert len(rising["breaches"]) == 1 and falling["breaches"] == []


def test_a_journaled_level_for_a_symbol_the_book_dropped_is_not_watched():
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan())]
    targets, skipped, _ = watch_targets(None, events, held={"US.SPY"})
    assert targets == [] and any("holds nothing" in note for note in skipped)


def test_an_entered_watchlist_row_supplies_a_level_the_journal_lacks():
    book = Watchlist.model_validate({"as_of": date(2026, 11, 20),
                                     "entries": [plan(status="entered"),
                                                 plan(symbol="US.AAPL", setup_id="TAC-2",
                                                      stop=180.0, entry_low=195.0,
                                                      entry_high=200.0, target=230.0,
                                                      status="watch")]})
    targets, _, _ = watch_targets(book, [])
    assert [t.symbol for t in targets] == ["US.MSFT"]


def test_the_gap_is_a_journal_event_not_a_silent_miss():
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan()),
              {"type": "monitor.heartbeat", "ts": (NOW - timedelta(minutes=30)).isoformat(),
               "payload": {"watched": 1}}]
    report = tick_eval(quotes=[quote()], events=events, cadence_seconds=300)
    assert report["gap"]["missed_seconds"] == pytest.approx(1800.0, abs=1)
    assert report["heartbeat"]["coverage_ok"] is False


def test_an_ordinary_tick_after_a_short_pause_reports_no_gap():
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan()),
              {"type": "monitor.heartbeat", "ts": (NOW - timedelta(minutes=5)).isoformat(),
               "payload": {"watched": 1}}]
    report = tick_eval(quotes=[quote()], events=events, cadence_seconds=300)
    assert report["gap"] is None and report["heartbeat"]["coverage_ok"] is True


def test_replay_reproduces_the_same_verdict_from_the_same_inputs():
    """§8.3: the guard is a pure function, which is what makes an LLM-free breach call reviewable."""
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan())]
    quotes = [quote(last=465.0)]
    first = tick_eval(quotes=quotes, events=events)
    second = tick_eval(quotes=quotes, events=events)
    assert first == second
    assert first["breaches"][0]["episode_id"] == second["breaches"][0]["episode_id"]


def test_the_calendar_gate_blocks_a_weekend_and_a_closed_session():
    saturday = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)
    assert session_gate(saturday) == (False, "2026-11-21 is not a trading day")
    after_close = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
    assert session_gate(after_close)[0] is False


# ---------------------------------------------------------------- the CLI surface


def write_inputs(tmp_path: Path, *, quotes: list[dict], events: list[dict]) -> tuple[Path, Path]:
    quote_file = tmp_path / "quotes.json"
    quote_file.write_text(json.dumps(quotes), encoding="utf-8")
    journal = tmp_path / "events.jsonl"
    for event in events:
        append_event(journal, event["type"], event["payload"])
    return quote_file, journal


def test_cli_records_one_breach_then_a_clear_and_the_chain_stays_valid(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.monitor_cli._clock", lambda: NOW)
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan())]
    quote_file, journal = write_inputs(tmp_path, quotes=[{"symbol": "US.MSFT", "at": NOW.isoformat(),
                                                          "book_at": NOW.isoformat(), "last": 465.0,
                                                          "bid": 464.95, "ask": 465.05,
                                                          "tradable": True}], events=events)
    args = ["monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
            "--book", str(tmp_path / "absent.json"), "--positions", str(tmp_path / "positions.json"),
            "--config-root", str(ROOT), "--record"]
    (tmp_path / "positions.json").write_text(json.dumps({"positions": [{"symbol": "US.MSFT",
                                                                       "quantity": 39}]}),
                                             encoding="utf-8")
    code, out = run(*args)
    assert code == 0 and "BREACH" in out
    types = [event["type"] for event in read_events(journal)][-2:]
    assert types == ["monitor.breach", "monitor.heartbeat"]

    quote_file.write_text(json.dumps([{**json.loads(quote_file.read_text(encoding="utf-8"))[0],
                                       "last": 490.0}]), encoding="utf-8")
    code, out = run(*args)
    assert code == 0 and "cleared" in out
    assert [event["type"] for event in read_events(journal)][-2:] == ["monitor.clear",
                                                                      "monitor.heartbeat"]
    assert verify_chain(journal)[0]


def test_cli_exits_two_and_journals_an_error_when_the_book_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.monitor_cli._clock", lambda: NOW)
    quote_file, journal = write_inputs(tmp_path, quotes=[{"symbol": "US.MSFT",
                                                          "at": NOW.isoformat(),
                                                          "book_at": NOW.isoformat(),
                                                          "last": 465.0, "bid": 464.95,
                                                          "ask": 465.05, "tradable": True}],
                                       events=[])
    bad = tmp_path / "watchlist.json"
    bad.write_text(json.dumps({"as_of": "2026-11-20", "entries": [{"symbol": "US.MSFT"}]}),
                   encoding="utf-8")
    code, out = run("monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
                    "--book", str(bad), "--config-root", str(ROOT), "--record")
    assert code == 2 and "NO-GO" in out
    last = read_events(journal)[-1]
    assert last["type"] == "monitor.error" and "book invalid" in last["payload"]["reason"]


def test_cli_refuses_a_prefix_mismatch_instead_of_calling_it_an_empty_watch(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.monitor_cli._clock", lambda: NOW)
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan())]
    quote_file, journal = write_inputs(tmp_path, quotes=[{"symbol": "US.MSFT", "at": NOW.isoformat(),
                                                          "book_at": NOW.isoformat(), "last": 500.0,
                                                          "bid": 499.95, "ask": 500.05,
                                                          "tradable": True}], events=events)
    positions = tmp_path / "positions.json"
    positions.write_text(json.dumps({"positions": [{"symbol": "MSFT", "quantity": 39}]}),
                         encoding="utf-8")
    code, out = run("monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
                    "--book", str(tmp_path / "absent.json"), "--positions", str(positions),
                    "--config-root", str(ROOT))
    assert code == 2 and "matched none of the journaled levels" in out, out


def test_cli_exits_one_outside_the_session_and_writes_nothing(tmp_path):
    quote_file, journal = write_inputs(tmp_path, quotes=[], events=[])
    before = read_events(journal)
    evening = datetime(2026, 11, 20, 23, 0, tzinfo=UTC)
    code, out = run("monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
                    "--book", str(tmp_path / "absent.json"), "--config-root", str(ROOT),
                    "--at", evening.isoformat())
    assert code == 1 and "NOT RUN" in out and read_events(journal) == before


def test_replay_clock_cannot_record(tmp_path):
    """§2: a replay must not be able to rewrite what the journal says was protected."""
    quote_file, journal = write_inputs(tmp_path, quotes=[], events=[])
    (tmp_path / "p.json").write_text(json.dumps([]), encoding="utf-8")
    code, out = run("monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
                    "--config-root", str(ROOT), "--at", NOW.isoformat(), "--record", "--book",
                    str(tmp_path / "absent.json"), "--positions", str(tmp_path / "p.json"))
    assert code != 0 and "replay" in out.lower()


def test_a_naive_replay_clock_is_rejected(tmp_path):
    quote_file, journal = write_inputs(tmp_path, quotes=[], events=[])
    code, out = run("monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
                    "--config-root", str(ROOT), "--at", "2026-11-20T14:00:00")
    assert code != 0 and "timezone-aware" in out


def test_a_contended_journal_skips_the_tick_without_touching_the_chain(tmp_path, monkeypatch):
    monkeypatch.setattr("tyche.monitor_cli._clock", lambda: NOW)
    events = [journaled(symbol="US.MSFT", side="buy", protected_setup=plan())]
    quote_file, journal = write_inputs(tmp_path, quotes=[{"symbol": "US.MSFT", "at": NOW.isoformat(),
                                                          "book_at": NOW.isoformat(), "last": 465.0,
                                                          "bid": 464.95, "ask": 465.05,
                                                          "tradable": True}], events=events)
    (tmp_path / "positions.json").write_text(json.dumps([{"symbol": "US.MSFT", "quantity": 39}]),
                                             encoding="utf-8")
    before = read_events(journal)
    with journal_lock(journal):
        code, out = run("monitor", "tick", "--quotes", str(quote_file), "--journal", str(journal),
                        "--book", str(tmp_path / "absent.json"), "--positions",
                        str(tmp_path / "positions.json"), "--config-root", str(ROOT),
                        "--record")
    assert code == 2 and "SKIPPED" in out, out
    assert read_events(journal) == before and verify_chain(journal)[0]
