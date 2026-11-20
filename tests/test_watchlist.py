from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tyche.cli import app
from tyche.watchlist import Watchlist, WatchlistEntry


def entry(**overrides):
    base = {
        "symbol": "EFA", "sleeve": "equity", "strategy": "regime rotation momentum",
        "entry_low": 80.0, "entry_high": 81.5, "stop": 78.0, "target": 86.0,
        "expiry": date(2026, 11, 20),
    }
    base.update(overrides)
    return base


def test_valid_entry_and_book():
    book = Watchlist(as_of=date(2026, 11, 18), entries=[WatchlistEntry(**entry())])
    assert book.entries[0].status == "watch"
    assert not book.stale(date(2026, 11, 18))
    assert book.active(date(2026, 11, 18)) == book.entries


def test_level_ordering_enforced():
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(stop=80.5))  # stop inside the entry zone
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(target=81.0))  # target below entry_high
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(entry_low=82.0))  # inverted zone
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(entry_low=-1.0))


def test_duplicate_symbols_rejected():
    with pytest.raises(ValidationError):
        Watchlist(as_of=date(2026, 11, 18), entries=[
            WatchlistEntry(**entry()), WatchlistEntry(**entry()),
        ])


def test_stale_and_active_filtering():
    book = Watchlist(as_of=date(2026, 11, 18), entries=[
        WatchlistEntry(**entry()),
        WatchlistEntry(**entry(symbol="VNQ", expiry=date(2026, 11, 19))),
        WatchlistEntry(**entry(symbol="DBC", status="entered")),
        WatchlistEntry(**entry(symbol="GLD", status="dropped")),
    ])
    assert book.stale(date(2026, 11, 19))
    active = {e.symbol for e in book.active(date(2026, 11, 19))}
    assert active == {"EFA", "VNQ"}  # expired-after-today kept; entered/dropped excluded
    assert {e.symbol for e in book.active(date(2026, 11, 20))} == {"EFA"}


def test_cli_watchlist_valid(tmp_path):
    path = tmp_path / "watchlist.json"
    book = Watchlist(as_of=date(2026, 11, 18), entries=[WatchlistEntry(**entry())])
    path.write_text(book.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(app, ["watchlist", "--path", str(path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["entries"][0]["symbol"] == "EFA"
    assert "stale" in payload and "active_count" in payload


def test_cli_watchlist_missing(tmp_path):
    result = CliRunner().invoke(app, ["watchlist", "--path", str(tmp_path / "nope.json")])
    assert result.exit_code == 1


def test_cli_watchlist_invalid(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"as_of": "2026-11-18", "entries": [entry(stop=99.0)]}, default=str))
    result = CliRunner().invoke(app, ["watchlist", "--path", str(path)])
    assert result.exit_code == 1


def test_thesis_carries_factors_and_outlook():
    book = Watchlist(as_of=date(2026, 11, 18), entries=[WatchlistEntry(**entry(
        synthesis="Reclaimed 81 on volume", edge="2R to the prior high",
        bear_case="fails back under 80", invalidation="daily close below 80",
        horizon="2-4 weeks", thesis_ref="scout-2026-11-18-efa",
        factors=[{"name": "reclaim", "axis": "technical", "state": "pass",
                  "why": "closed above 81 on above-average volume"},
                 {"name": "CPI print", "axis": "macro", "state": "unknown",
                  "why": "not published yet"}],
        outlook={"regime": "neutral", "conviction": "medium",
                 "alignment": {"technical": "bull", "macro": "neutral"}},
    ))])
    thesis = book.entries[0]
    assert thesis.factors[0].state == "pass" and thesis.factors[1].state == "unknown"
    assert thesis.outlook is not None and thesis.outlook.conviction == "medium"
    assert thesis.thesis_ref == "scout-2026-11-18-efa"


def test_thesis_rejects_unknown_axes_and_states():
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(factors=[{"name": "vibes", "axis": "astrology",
                                         "state": "pass", "why": "?"}]))
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(factors=[{"name": "breakout", "axis": "technical",
                                         "state": "maybe", "why": "?"}]))
    with pytest.raises(ValidationError):
        WatchlistEntry(**entry(outlook={"regime": "risk_on", "conviction": "certain"}))