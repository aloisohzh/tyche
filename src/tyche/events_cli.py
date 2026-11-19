"""Discovered-event overlay: the scout proposes, the Desk Head validates and pins.

Pinned events (config/events.yaml) merge into the calendar gate, so a validated
catalyst drives the same event-day caution as the static macro/FOMC anchors.
This CLI never fetches news and never authorizes orders.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from tyche.market_calendar import EVENTS_2026, DiscoveredEvent, EventOverlay, load_overlay

app = typer.Typer(help="Pin discovered catalysts into the calendar gate.")

HEADER = (
    "# Discovered events pinned by the Desk Head after scout proposal + source\n"
    "# validation (tyche events add). Merged into the calendar gate: any event on\n"
    "# a date makes it an event day (drive phases halve orders and risk).\n"
    "# Static macro/FOMC/earnings anchors live in src/tyche/market_calendar.py.\n"
)


def emit(value: dict | list) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=True))


def save_overlay(root: Path, overlay: EventOverlay) -> None:
    path = root / "config" / "events.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = HEADER + yaml.safe_dump(overlay.model_dump(mode="json"), sort_keys=False)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@app.command("list")
def list_events(
    root: Path = typer.Option(Path.cwd(), "--root", help="Repo root holding config/events.yaml."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Static anchors + pinned discoveries, chronologically."""
    overlay, error = load_overlay(root)
    if error:
        typer.echo(error, err=True)
        raise typer.Exit(1)
    rows = [{"origin": "static", **e.model_dump(mode="json")} for e in EVENTS_2026]
    rows += [{"origin": "discovered", **e.model_dump(mode="json")} for e in overlay.events]
    rows.sort(key=lambda r: (r["date"], r["name"]))
    if as_json:
        emit(rows)
        return
    for row in rows:
        symbols = ",".join(row.get("symbols") or []) or "market-wide"
        typer.echo(f"{row['date']}  {row['kind']:<8} {row['name']}  [{symbols}] ({row['origin']})")


@app.command()
def add(
    event_date: date = typer.Option(..., "--date", help="Event date YYYY-MM-DD."),
    name: str = typer.Option(..., "--name", help="Short event name."),
    kind: str = typer.Option(..., "--kind", help="macro | fomc | earnings | ipo | index."),
    source: str = typer.Option(..., "--source", help="URL or MCP payload reference validating the event."),
    symbol: list[str] = typer.Option([], "--symbol", help="Affected symbol (repeatable); empty = market-wide."),
    time_et: str = typer.Option("", "--time-et", help="ET wall-clock time HH:MM, if known."),
    root: Path = typer.Option(Path.cwd(), "--root", help="Repo root holding config/events.yaml."),
) -> None:
    """Validate and pin one discovered event; the gate merges it immediately."""
    try:
        event = DiscoveredEvent(date=event_date, name=name, kind=kind,
                                time_et=time_et or None, symbols=symbol,
                                source=source, added_at=datetime.now(UTC))
        overlay, error = load_overlay(root)
        if error:
            raise ValueError(error + "; fix the overlay before pinning")
        if any(e.date == event.date and e.name == event.name
               for e in overlay.events + EVENTS_2026):
            raise ValueError("event already pinned for that date and name")
        overlay.events.append(event)
        overlay.events.sort(key=lambda e: (e.date, e.name))
        save_overlay(root, overlay)
        emit({"pinned": True, "event": event.model_dump(mode="json"), "submitted": False})
    except (OSError, ValueError, ValidationError) as exc:
        reason = str(exc)
        if isinstance(exc, ValidationError):
            reason = "invalid event: " + "; ".join(
                ".".join(map(str, e["loc"])) + " (" + e["type"] + ")"
                for e in exc.errors(include_input=False)
            )
        emit({"pinned": False, "reason": reason})
        raise typer.Exit(1) from exc