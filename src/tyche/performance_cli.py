"""`tyche performance report`: the fee-net performance pack and SPY baseline, from files only.

Reads the journal, the published desk feed and one or more `date,symbol,close` CSVs; writes one
Markdown report (and optionally JSON). Deterministic: no network, no wall clock, so the same
inputs give the same bytes and a judge can re-run it from the public repo.
"""
# ruff: noqa: B008 -- Typer's declarative command option defaults.
from __future__ import annotations

import glob
import json
from datetime import date
from pathlib import Path

import typer
from rich.console import Console

from tyche.journal import read_events, verify_chain
from tyche.performance import (
    account_days_from_feed,
    account_days_from_journal,
    benchmark_closes,
    build_pack,
    render_markdown,
    to_json,
)

app = typer.Typer(help="Fee-net performance pack and SPY baseline, read from the record.")
console = Console()

DEFAULT_START = date(2026, 11, 17)
DEFAULT_START_NAV = 100_000.0


def _challenge_account(state: dict) -> str | None:
    """The feed's primary account mask, else the one account whose marks are not demo or drill."""
    feed = state.get("feed") or {}
    if feed.get("primary_account"):
        return str(feed["primary_account"])
    marks = state.get("nav_marks") or {}
    real = [acct for acct in marks if acct.startswith("***")]
    return real[0] if len(real) == 1 else None


@app.command("report")
def report(
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal",
                                      help="Hash-chained journal; verified before it is read."),
    feed: Path | None = typer.Option(Path("desk-site/web/data/state.json"), "--feed",
                                     help="Published desk feed (nav_marks, fee-net series); optional."),
    prices: list[str] = typer.Option([], "--prices",
                                     help="Price CSV path or glob (date,symbol,close) holding US.SPY; repeatable."),
    account: str | None = typer.Option(None, "--account", help="Feed account mask, e.g. ***598; default: the feed's primary."),
    start: str = typer.Option(DEFAULT_START.isoformat(), "--start", help="First day of the window."),
    start_nav: float = typer.Option(DEFAULT_START_NAV, "--start-nav", help="Starting virtual funds."),
    base: str | None = typer.Option(None, "--base", help="Day whose SPY close is the baseline buy; default: --start."),
    out: Path | None = typer.Option(None, "--out", help="Markdown path to write; default: print."),
    json_out: Path | None = typer.Option(None, "--json-out", help="Also write the pack as JSON."),
    order_cap: int = typer.Option(200, "--order-cap"),
    internal_budget: int | None = typer.Option(120, "--internal-budget"),
    skip_verify: bool = typer.Option(False, "--skip-verify", help="Read a journal whose chain is not verified (demo only)."),
) -> None:
    """Build the fee-net pack: daily marks vs SPY, vol, Sharpe, drawdown, orders vs cap, rejections, fees."""
    sources: list[str] = []
    events: list[dict] = []
    if journal_path.is_file():
        if not skip_verify:
            ok, count, error = verify_chain(journal_path)
            if not ok:
                console.print(f"journal chain FAILED at {count}: {error}. A sanitized bundle copy "
                              "(account ids redacted) cannot verify; pass --skip-verify and say so in the report.")
                raise typer.Exit(2)
        events = read_events(journal_path)
        sources.append(f"journal `{journal_path.as_posix()}` ({len(events)} events)")
    else:
        console.print(f"no journal at {journal_path}; account values come from the feed only")

    state: dict = {}
    if feed is not None and feed.is_file():
        state = json.loads(feed.read_text(encoding="utf-8"))
        sources.append(f"feed `{feed.as_posix()}`")
    acct = account or _challenge_account(state) or "challenge"

    days = account_days_from_feed(state, acct) if state else {}
    days.update(account_days_from_journal(events))  # reconcile rows win over published marks

    paths: list[Path] = []
    for pattern in prices:
        matches = sorted(Path(p) for p in glob.glob(pattern))
        paths.extend(matches or ([Path(pattern)] if Path(pattern).is_file() else []))
    closes = benchmark_closes(paths) if paths else {}
    if paths:
        sources.append("prices " + ", ".join(f"`{p.as_posix()}`" for p in paths))

    pack = build_pack(
        account=acct,
        start_day=date.fromisoformat(start),
        start_nav=start_nav,
        account_days=days,
        benchmark=closes,
        events=events,
        fee_net_series=((state.get("expectancy") or {}).get("fee_net_series") or []) if state else [],
        base_day=date.fromisoformat(base) if base else None,
        sources=sources,
    )
    text = render_markdown(pack, order_cap=order_cap, internal_budget=internal_budget)
    if out is None:
        print(text)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"wrote {out}")
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(to_json(pack), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        console.print(f"wrote {json_out}")
    if pack.missing_benchmark_days:
        console.print("SPY close missing for " + ", ".join(d.isoformat() for d in pack.missing_benchmark_days)
                      + "; pass a price CSV that covers them with --prices.")
