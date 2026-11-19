"""Paper tactical preview/monitor/reservation commands. Never calls a trading API."""
# ruff: noqa: B008 -- Typer's declarative command option defaults.
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import typer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from tyche.approvals import ApprovalBatch, authorize_order, envelope_totals, envelope_usage
from tyche.broker.mcp_json import snapshot_from_dir
from tyche.broker.tactical_data import normalize_quotes
from tyche.config import load_config
from tyche.execution_state import broker_orders, pending_intents
from tyche.halt import is_halted
from tyche.journal import append_locked, journal_lock, read_events, verify_chain
from tyche.lifecycle import LifecycleState, account_hash
from tyche.lifecycle_cli import emit, fail, load, save
from tyche.market_calendar import ET
from tyche.models import AccountSnapshot, OrderIntent
from tyche.tactical import MarketQuote, MonitorState, plan_tick, setup_hash
from tyche.watchlist import Watchlist

app = typer.Typer(help="Catalyst stocks and standard long calls/puts; paper only, no broker writes.")


class Audit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_hash: str
    reviewed_at: AwareDatetime
    valid_until: AwareDatetime
    verdict: Literal["approved", "rejected"]
    reference: str = Field(min_length=5)


def now_utc() -> datetime:
    return datetime.now(UTC)


def monitor_state(events: list[dict]) -> MonitorState:
    state = MonitorState()
    for event in events:
        payload = event.get("payload", {})
        if event.get("type") == "tactical.monitor":
            state = MonitorState.model_validate(payload["state"])
        elif event.get("type") == "order.requested" and payload.get("protected_setup"):
            from tyche.watchlist import WatchlistEntry
            entry = WatchlistEntry.model_validate(payload["protected_setup"])
            state.protected[entry.symbol] = entry
    return state


def inputs(book: Path, account: Path, quotes: Path, orders: Path, journal: Path, config_root: Path, now: datetime):
    if not journal.is_file():
        raise ValueError("persistent journal required; restore rather than invent empty history")
    ok, _, error = verify_chain(journal)
    if not ok:
        raise ValueError(f"journal integrity: {error}")
    events = read_events(journal)
    state = monitor_state(events)
    snapshot = load(AccountSnapshot, account)
    if snapshot.source != "sim_list" or snapshot.account_type not in (1, 2) or snapshot.market_id != 100:
        raise ValueError("verified US paper account snapshot required")
    quote_rows = [MarketQuote.model_validate(row) for row in json.loads(quotes.read_text(encoding="utf-8"))]
    contracts = {q.symbol: q.option for q in quote_rows if q.option}
    contracts.update({p.symbol: p.option for p in snapshot.positions if p.option})
    rows = broker_orders(json.loads(orders.read_text(encoding="utf-8")))
    config, watchlist = load_config(config_root), load(Watchlist, book)
    report = plan_tick(watchlist, snapshot, quote_rows, pending_intents(rows, contracts), rows,
                       events, state, config, now, halted=is_halted(journal.parent))
    return report, state, events, snapshot, watchlist, config


@app.command("schema")
def schema() -> None:
    emit({"watchlist": Watchlist.model_json_schema(), "quote": MarketQuote.model_json_schema(),
          "audit": Audit.model_json_schema(), "envelope": ApprovalBatch.model_json_schema(),
          "submitted": False})


@app.command("capture")
def capture(
    directory: Path = typer.Option(..., "--dir"), account_id: str = typer.Option(...),
    prior_close_nav: float = typer.Option(...), high_water_nav: float = typer.Option(...),
) -> None:
    """Normalize accounts/cash/positions/quotes + book-*.json + chain-*.json in-place.

    Persist ALL order pages separately as one orders array with has_more=false;
    never delete old orders to fit a schema. Inputs remain the original MCP JSON.
    """
    try:
        def raw(path):
            return json.loads(path.read_text(encoding="utf-8"))
        quotes = normalize_quotes(raw(directory / "quotes.json"),
                                  [raw(p) for p in directory.glob("book-*.json")],
                                  [raw(p) for p in directory.glob("chain-*.json")])
        if not quotes:
            raise ValueError("no verified two-sided quotes")
        snapshot = snapshot_from_dir(directory, account_id,
                                     contracts={q.symbol: q.option for q in quotes if q.option})
        snapshot = AccountSnapshot.model_validate({**snapshot.model_dump(),
                                                   "prior_close_nav": prior_close_nav,
                                                   "high_water_nav": high_water_nav})
        save(directory / "tactical-account.json", snapshot)
        (directory / "tactical-quotes.json").write_text(
            json.dumps([q.model_dump(mode="json") for q in quotes], indent=2), encoding="utf-8")
        emit({"captured": True, "quote_count": len(quotes), "submitted": False})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail(exc)


@app.command("tick")
def monitor(
    book: Path = typer.Option(...), account: Path = typer.Option(...),
    quotes: Path = typer.Option(...), orders: Path = typer.Option(...),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
    config_root: Path = typer.Option(Path.cwd()),
    at: str = typer.Option("", help="Read-only replay clock."),
    record: bool = typer.Option(False, "--record"),
) -> None:
    """Preview entries and exits. --record persists confirmations and latched triggers."""
    try:
        if at and record:
            raise ValueError("replay clock cannot record monitor state")
        now = datetime.fromisoformat(at) if at else now_utc()
        with journal_lock(journal):
            report, state, *_ = inputs(book, account, quotes, orders, journal, config_root, now)
            if record:
                append_locked(journal, "tactical.monitor", {"state": state.model_dump(mode="json"),
                                                          "alerts": report["alerts"]})
        emit(report)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        fail(exc)


@app.command("reserve")
def reserve(
    book: Path = typer.Option(...), account: Path = typer.Option(...),
    quotes: Path = typer.Option(...), orders: Path = typer.Option(...),
    symbol: str = typer.Option(...), envelope: Path = typer.Option(...),
    audit: Path = typer.Option(...), lifecycle_state: Path = typer.Option(...),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
    config_root: Path = typer.Option(Path.cwd()),
) -> None:
    """Atomically check and reserve ONE exact limit order, never submit/retry.

    Gate defaults OFF pending a single-writer cloud/broker drill. Executor must
    persist this journal before submission, use request_id as broker text, send
    once within 30s, then record the receipt. Timeout/unknown outcome blocks retry.
    """
    try:
        now = now_utc()
        today = now.astimezone(ET).date()
        with journal_lock(journal):
            report, state, events, snapshot, watchlist, config = inputs(
                book, account, quotes, orders, journal, config_root, now)
            if not config.tactical.execution_enabled:
                raise ValueError("tactical rollout gate disabled: cloud monitor and broker drill not verified")
            other = load(LifecycleState, lifecycle_state)
            if any(a.account_hash == account_hash(snapshot.account_id) and not a.revoked
                   and a.contract.symbol == symbol for a in other.approvals):
                raise ValueError("symbol owned by existing lifecycle; do not create a second executor")
            candidates = [r for r in report["orders"] if r["intent"]["symbol"] == symbol]
            if len(candidates) != 1:
                raise ValueError(f"no unique actionable order: {report['decisions']}")
            proposal = candidates[0]
            intent = OrderIntent.model_validate(proposal["intent"])
            review = load(Audit, audit)
            if (review.verdict != "approved" or review.order_hash != proposal["order_hash"]
                    or not review.reviewed_at <= now < review.valid_until
                    or (now - review.reviewed_at).total_seconds() > 120
                    or (review.valid_until - review.reviewed_at).total_seconds() > 120):
                raise ValueError("fresh auditor approval required for this exact order hash")
            batch = load(ApprovalBatch, envelope)
            if batch.approved_at.tzinfo is None or batch.approved_at > now:
                raise ValueError("invalid envelope approval time")
            line = batch.line_for(symbol, intent.side.value)
            if line is None or line.setup_hash != proposal["setup_hash"]:
                raise ValueError("operator envelope must bind the complete setup/account/config hash")
            entry = state.protected.get(symbol) if snapshot.position(symbol) else None
            entry = entry or next(e for e in watchlist.entries if e.symbol == symbol)
            if setup_hash(entry, config, snapshot.account_id) != line.setup_hash:
                raise ValueError("protected setup changed; obtain renewed approval")
            if intent.side.value == "buy":
                exit_line = batch.line_for(symbol, "sell")
                if (exit_line is None or exit_line.setup_hash != line.setup_hash
                        or exit_line.multiplier != intent.multiplier or exit_line.max_qty < intent.quantity):
                    raise ValueError("entry requires a matching bounded exit authorization")
            used_qty, used_notional = envelope_totals(events, today, symbol, intent.side.value)
            authorized, reason = authorize_order(
                batch, symbol=symbol, side=intent.side.value, qty=intent.quantity,
                limit=intent.limit_price, today=today, used=envelope_usage(journal, today),
                used_qty=used_qty, used_notional=used_notional, multiplier=intent.multiplier)
            if not authorized:
                raise ValueError(reason)
            request_id = "tyche-tac-" + uuid.uuid4().hex
            payload = {**intent.model_dump(mode="json"), "request_id": request_id,
                       "multiplier": intent.multiplier, "setup_hash": proposal["setup_hash"],
                       "order_hash": proposal["order_hash"], "auditor_ref": review.reference,
                       "protected_setup": entry.model_dump(mode="json"),
                       "authorization": {"kind": "envelope", "as_of": today.isoformat()},
                       "submit_before": (now + timedelta(seconds=30)).isoformat()}
            append_locked(journal, "tactical.monitor", {"state": state.model_dump(mode="json")})
            append_locked(journal, "order.requested", payload)
        emit({"authorized": True, "request": payload, "risk": proposal["risk"], "submitted": False,
              "instructions": "Persist the journal, then one US-paper limit order, exact fields and request_id as text. No retry."})
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, StopIteration) as exc:
        fail(exc)


@app.command("rollout-check")
def rollout_check(config_root: Path = typer.Option(Path.cwd())) -> None:
    config = load_config(config_root)
    emit({"local_planner_enabled": config.tactical.enabled,
          "local_options_enabled": config.tactical.options_enabled,
          "execution_gate_enabled": config.tactical.execution_enabled,
          "cloud_monitor_verified": False, "broker_option_round_trip_verified": False,
          "target_monitor_interval_seconds": config.tactical.monitor_interval_seconds,
          "blockers": ["Publish tested source to the existing cloud repository mount.",
                       "Use one durable writer for journal and BOTH strategy lanes; file locks are not distributed locks.",
                       "Validate lightweight 120-second Qoder-native monitoring, expiry exit and missed-heartbeat alerts.",
                       "Verify option submission/partial fills/cancel/expiry behavior in an authorized paper drill.",
                       "Restore protected setups, journal and complete broker history before every run.",
                       "Obtain exact setup-bound operator envelopes and auditor approval; then enable the rollout gate."],
          "submitted": False})
