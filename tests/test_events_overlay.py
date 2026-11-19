from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import yaml
from typer.testing import CliRunner

from tyche.events_cli import app as events_app
from tyche.market_calendar import (
    EventOverlay,
    SessionPhase,
    evaluate,
    events_on,
    load_overlay,
)

runner = CliRunner()

EVENT = {
    "date": "2026-11-20",
    "name": "Acme guidance cut",
    "kind": "earnings",
    "symbols": ["US.ACME"],
    "source": "https://example.com/pr",
    "added_at": "2026-11-19T09:00:00Z",
}


def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def write_overlay(root, payload):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "events.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_overlay_merges_and_triggers_caution(tmp_path):
    write_overlay(tmp_path, {"events": [EVENT]})
    overlay, error = load_overlay(tmp_path)
    assert error is None
    nov20 = events_on(date(2026, 11, 20), overlay)
    assert any(e.name == "Acme guidance cut" for e in nov20)
    gate = evaluate(utc(2026, 11, 20, 14, 35), SessionPhase.OPENING_DRIVE, root=tmp_path)
    assert gate.run and gate.strategy.event_caution
    assert gate.strategy.max_orders == 1
    assert gate.overlay_error is None
    # Static anchors survive the merge.
    assert any(e.kind == "ipo" for e in events_on(date(2026, 11, 19), overlay))


def test_missing_overlay_is_clean(tmp_path):
    overlay, error = load_overlay(tmp_path)
    assert error is None and overlay.events == []
    gate = evaluate(utc(2026, 11, 20, 14, 35), root=tmp_path)
    assert gate.run and not gate.strategy.event_caution


def test_invalid_overlay_falls_back_to_static(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "events.yaml").write_text("events: [{date: broken", encoding="utf-8")
    overlay, error = load_overlay(tmp_path)
    assert error and overlay.events == []
    gate = evaluate(utc(2026, 11, 19, 14, 35), root=tmp_path)
    assert gate.run and gate.overlay_error
    assert any(e.kind == "ipo" for e in gate.events)


def test_duplicate_overlay_events_rejected():
    with pytest.raises(ValueError):
        EventOverlay.model_validate({"events": [EVENT, EVENT]})


def test_cli_add_list_roundtrip(tmp_path):
    args = ["add", "--date", "2026-11-20", "--name", "Acme guidance cut",
            "--kind", "earnings", "--source", "https://example.com/pr",
            "--symbol", "US.ACME", "--root", str(tmp_path)]
    result = runner.invoke(events_app, args)
    assert result.exit_code == 0, result.output
    gate = evaluate(utc(2026, 11, 20, 14, 35), root=tmp_path)
    assert gate.strategy.event_caution
    # Duplicate pin refused.
    assert runner.invoke(events_app, args).exit_code == 1
    # Static anchor collision refused.
    collide = ["add", "--date", "2026-11-19", "--name", "Anthropic (ANT) Nasdaq IPO debut",
               "--kind", "ipo", "--source", "https://example.com", "--root", str(tmp_path)]
    assert runner.invoke(events_app, collide).exit_code == 1
    # Invalid kind refused.
    bad = ["add", "--date", "2026-11-20", "--name", "X", "--kind", "rumor",
           "--source", "https://example.com", "--root", str(tmp_path)]
    assert runner.invoke(events_app, bad).exit_code == 1
    listing = runner.invoke(events_app, ["list", "--root", str(tmp_path), "--json"])
    assert listing.exit_code == 0
    assert "Acme guidance cut" in listing.output and "FOMC decision" in listing.output


def test_cli_add_refuses_broken_overlay(tmp_path):
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / "events.yaml"
    path.write_text("events: [{date: broken", encoding="utf-8")
    result = runner.invoke(events_app, [
        "add", "--date", "2026-11-20", "--name", "X", "--kind", "macro",
        "--source", "https://example.com", "--root", str(tmp_path),
    ])
    assert result.exit_code == 1
    assert path.read_text(encoding="utf-8") == "events: [{date: broken"