"""CLI for the Level 0 protection monitor. Alerts only; it never touches a broker.

`tyche monitor tick` is the deterministic half of ADR 0013: a runner (a schedule, a shell loop,
or a human) writes a quote file, this reads files, and the only thing it can write is journal
events. Exit codes are part of the contract (runbook §2) and a runner must not improvise around
them: `0` judged, `1` the calendar says do not run, `2` it could not judge - which is never the
same sentence as "no breaches".
"""
# ruff: noqa: B008 -- Typer's declarative command option defaults.
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from tyche.config import load_config
from tyche.journal import append_locked, journal_lock, read_events, verify_chain
from tyche.monitor import (
    DEFAULT_CADENCE_SECONDS,
    error_event,
    evaluate,
    journal_events,
    session_gate,
)
from tyche.tactical import MarketQuote
from tyche.watchlist import Watchlist

app = typer.Typer(help="Intraday breach detection. Journals and shouts; never orders.")
console = Console()


def _clock() -> datetime:
    """The wall clock, as one named function so a test can stand still.

    Recording tests need a tick that lands inside a trading session; the only other way to get
    one is to replay with `--at`, which the contract forbids from writing (§2).
    """
    return datetime.now(UTC)


def _read_quotes(path: Path) -> list[MarketQuote]:
    """Quotes come from a file the executor wrote; the kernel has no MCP arm (§2)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("quotes") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path} holds no quote list")
    return [MarketQuote.model_validate(row) for row in rows]


def _read_held(path: Path) -> set[str]:
    """Symbols the book actually holds, from a snapshot or a positions list.

    Symbols must already carry their market prefix (`US.MSFT`), the way every other reader in
    this repo expects them; an empty intersection is reported as a failure, not as an all-clear.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("positions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} holds no positions list of objects")
    held: set[str] = set()
    for row in rows:
        if not isinstance(row.get("symbol"), str):
            continue
        quantity = next((row[key] for key in ("sellable", "quantity", "qty")
                         if isinstance(row.get(key), int | float)), 0)
        if quantity > 0:
            held.add(row["symbol"])
    return held


def _emit(report: dict, as_json: bool) -> None:
    if as_json:
        console.print_json(json.dumps(report, default=str))
        return
    status = report.get("status")
    if status == "blocked":
        console.print(f"[yellow]NOT RUN[/] {report.get('reason')}")
        return
    if status == "empty":
        console.print("[yellow]NOTHING WATCHED[/] no journaled level matched an open lot; "
                      "this is not an all-clear")
        return
    if status == "no-go":
        console.print(f"[bold red]NO-GO[/] {report.get('at')} - the tick judged nothing")
        for problem in report.get("problems", []):
            console.print(f"  · {problem['reason']} ({problem['input_path']})")
        return
    heart = report.get("heartbeat") or {}
    console.print(f"[green]EVALUATED[/] {report['at']} phase={heart.get('phase')} "
                  f"watched={heart.get('watched')} breached={heart.get('breached')} "
                  f"coverage_ok={heart.get('coverage_ok')} quote_age={heart.get('quote_age_seconds')}s")
    for breach in report.get("breaches", []):
        console.print(f"  [bold red]BREACH[/] {breach['symbol']} at {breach['observed_price']} "
                      f"<= level {breach['level']} ({breach['protection_type']}, "
                      f"episode {breach['episode_id']})")
    for clear in report.get("clears", []):
        console.print(f"  [green]cleared[/] {clear['symbol']} back inside {clear['level']} "
                      f"after {clear['duration_seconds']}s")
    if report.get("gap"):
        console.print(f"  [bold yellow]GAP[/] last heartbeat {report['gap']['last_heartbeat_at']} "
                      f"({report['gap']['missed_seconds']}s > 2x cadence)")
    for note in report.get("skipped", []):
        console.print(f"  · not watched: {note}")


@app.command("tick")
def tick(
    quotes: Path = typer.Option(..., "--quotes",
                                help="Executor-written quote JSON: a list, or {\"quotes\": [...]}."),
    book: Path = typer.Option(Path("data/watchlist.json"), "--book",
                              help="Scout plans; entered rows supply levels the journal lacks."),
    positions: Path | None = typer.Option(None, "--positions",
                                          help="Book snapshot; when given, only held symbols are watched."),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    config_root: Path = typer.Option(Path("."), "--config-root"),
    cadence_seconds: int = typer.Option(DEFAULT_CADENCE_SECONDS, "--cadence-seconds", min=5, max=3600,
                                        help="Expected spacing; a heartbeat older than 2x this is a gap."),
    at: str = typer.Option("", "--at", help="Replay clock (ISO). Read-only, so it excludes --record."),
    record: bool = typer.Option(False, "--record", help="Append monitor.* events to the journal."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Evaluate every journaled protective level against a quote file, then journal the verdict."""
    if at and record:
        raise typer.BadParameter("replay clock cannot write to the journal")
    try:
        now = datetime.fromisoformat(at) if at else _clock()
    except ValueError as exc:
        raise typer.BadParameter(f"--at must be an ISO timestamp: {exc}") from exc
    if now.tzinfo is None:
        raise typer.BadParameter("the monitor requires a timezone-aware clock")

    config = load_config(config_root)
    max_age = config.tactical.max_quote_age_seconds
    run, reason = session_gate(now)
    if not run:
        _emit({"status": "blocked", "reason": reason}, as_json)
        raise typer.Exit(1)

    def judge() -> dict:
        """Read the inputs and decide. Any unreadable or invalid input is a no-go, never an all-clear."""
        problems: list[dict[str, str]] = []
        try:
            quote_rows = _read_quotes(quotes)
        except (OSError, ValueError, ValidationError) as exc:
            return {"status": "no-go", "at": now.isoformat(), "phase": "",
                    "watched": [], "skipped": [], "breaches": [], "clears": [], "gap": None,
                    "problems": [{"reason": f"quotes unreadable: {exc}", "input_path": str(quotes)}],
                    "heartbeat": None}
        held: set[str] | None = None
        if positions is not None:
            try:
                held = _read_held(positions)
            except (OSError, ValueError) as exc:
                problems.append({"reason": f"positions unreadable: {exc}", "input_path": str(positions)})
        watchlist: Watchlist | None = None
        if book.is_file():
            try:
                watchlist = Watchlist.model_validate_json(book.read_text(encoding="utf-8"))
            except ValidationError as exc:
                problems.append({"reason": f"book invalid: {exc.errors()[0]['msg']}",
                                 "input_path": str(book)})
        elif positions is None:
            problems.append({"reason": f"no book at {book} and no --positions: levels cannot be "
                                       "resolved to what is actually held", "input_path": str(book)})
        if problems:
            return {"status": "no-go", "at": now.isoformat(), "phase": "",
                    "watched": [], "skipped": [], "breaches": [], "clears": [], "gap": None,
                    "problems": problems, "heartbeat": None}
        report = evaluate(book=watchlist, quotes=quote_rows, events=read_events(journal_path),
                          now=now, cadence_seconds=cadence_seconds, max_quote_age_seconds=max_age,
                          held=held)
        if held is not None and report["status"] == "empty" and report["watched"] == []:
            journaled = len({event.get("payload", {}).get("symbol")
                             for event in read_events(journal_path)
                             if event.get("type") == "order.requested"})
            if journaled:
                report = {**report, "status": "no-go",
                          "problems": [{"reason": "the positions file matched none of the journaled "
                                                  "levels; check the market prefix on each symbol",
                                        "input_path": str(positions)}]}
        return report

    report = judge()
    if record:
        # One lock around read-and-append, so two schedulers can never both open the same
        # episode. The lock is nonblocking: a contended tick skips, and the next tick that
        # gets the lock journals the monitor.gap its stale heartbeat proves.
        try:
            with journal_lock(journal_path):
                ok, _, chain_error = verify_chain(journal_path)
                if not ok:
                    console.print(f"[bold red]JOURNAL INVALID[/] {chain_error}; nothing recorded")
                    raise typer.Exit(2)
                if report["status"] == "no-go":
                    event_type, payload = error_event(
                        "; ".join(problem["reason"] for problem in report["problems"]),
                        report["problems"][0]["input_path"] if report["problems"] else "")
                    append_locked(journal_path, event_type, payload)
                else:
                    for event_type, payload in journal_events(report):
                        append_locked(journal_path, event_type, payload)
        except RuntimeError as exc:  # "journal busy; skip overlapping run"
            console.print(f"[bold yellow]TICK SKIPPED[/] {exc} - this tick recorded nothing, "
                          "so it must not be read as 'no breaches'")
            raise typer.Exit(2) from exc

    _emit(report, as_json)
    raise typer.Exit({"evaluated": 0, "empty": 0, "no-go": 2}.get(report["status"], 2))
