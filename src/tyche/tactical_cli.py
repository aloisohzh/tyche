"""Paper tactical preview/monitor/reservation commands. Never calls a trading API."""
# ruff: noqa: B008 -- Typer's declarative command option defaults.
from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from tyche.approvals import (
    MODE_PROTECTIVE,
    ApprovalBatch,
    authorization_record,
    authorize_order,
    envelope_totals,
    envelope_usage,
    resolve_batch,
)
from tyche.broker.mcp_json import snapshot_from_dir
from tyche.broker.tactical_data import normalize_quotes
from tyche.config import load_config
from tyche.execution_state import broker_orders, combined_usage, order_symbol, pending_intents
from tyche.halt import effective_halt
from tyche.journal import append_locked, journal_lock, read_events, verify_chain
from tyche.lifecycle import LifecycleState, account_hash
from tyche.lifecycle_cli import emit, fail, load, save
from tyche.market_calendar import ET, phase_at
from tyche.models import AccountSnapshot, OrderIntent
from tyche.scalp import bars_from_kline, plan_scalp, scalp_state
from tyche.tactical import RTH, MarketQuote, MonitorState, plan_tick, setup_hash
from tyche.watchlist import Watchlist

app = typer.Typer(help="Catalyst stocks and standard long calls/puts; paper only, no broker writes.")


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
                       events, state, config, now, halted=bool(effective_halt(journal.parent, config_root).get("halted")))
    return report, state, events, snapshot, watchlist, config


@app.command("schema")
def schema() -> None:
    emit({"watchlist": Watchlist.model_json_schema(), "quote": MarketQuote.model_json_schema(),
          "envelope": ApprovalBatch.model_json_schema(), "submitted": False})


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
        emit({"captured": True, "quote_count": capture_dir(directory, account_id, prior_close_nav,
                                                          high_water_nav), "submitted": False})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail(exc)


def capture_dir(directory: Path, account_id: str, prior_close_nav: float, high_water_nav: float) -> int:
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
    return len(quotes)


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


FEED_FILES = ("accounts.json", "cash.json", "positions.json", "quotes.json")


def scout_cycle(
    feed: Path, work: Path, book: Path, orders: Path, journal: Path, config_root: Path,
    account_id: str, prior_close_nav: float, high_water_nav: float, now: datetime,
    *, record: bool = True,
) -> dict:
    """One capture+tick cycle over a raw MCP feed directory. Never orders or submits."""
    config = load_config(config_root)
    missing = [name for name in FEED_FILES if not (feed / name).is_file()]
    if missing:
        return {"at": now.isoformat(), "skipped": f"feed missing {', '.join(missing)}",
                "interval_seconds": config.tactical.monitor_interval_seconds}
    extras = [p for p in feed.glob("book-*.json")] + [p for p in feed.glob("chain-*.json")]
    oldest = min([(feed / name).stat().st_mtime for name in FEED_FILES]
                 + [path.stat().st_mtime for path in extras])
    age = now.timestamp() - oldest
    if age > config.tactical.max_snapshot_age_seconds:
        return {"at": now.isoformat(), "skipped": f"feed stale ({int(age)}s old)",
                "interval_seconds": config.tactical.monitor_interval_seconds}
    if work != feed:
        for path in [*(feed / name for name in FEED_FILES), *extras]:
            shutil.copy2(path, work / path.name)
    capture_dir(work, account_id, prior_close_nav, high_water_nav)
    with journal_lock(journal):
        report, state, *_ = inputs(book, work / "tactical-account.json",
                                   work / "tactical-quotes.json", orders, journal, config_root, now)
        if record:
            append_locked(journal, "tactical.monitor", {"state": state.model_dump(mode="json"),
                                                      "alerts": report["alerts"]})
    report["interval_seconds"] = config.tactical.monitor_interval_seconds
    return report


@app.command("scout")
def scout(
    feed: Path = typer.Option(..., "--feed"), work: Path = typer.Option(..., "--dir"),
    book: Path = typer.Option(...), orders: Path = typer.Option(...),
    account_id: str = typer.Option(...),
    prior_close_nav: float = typer.Option(...), high_water_nav: float = typer.Option(...),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
    config_root: Path = typer.Option(Path.cwd()),
    until: str = typer.Option(""), max_cycles: int = typer.Option(0),
) -> None:
    """Continuous intraday scout: capture feed -> tick at the configured cadence.

    Stops when an actionable order appears (freezing the exact quotes for the
    auditor/reservation window), at --until, after --max-cycles, or when the
    regular session ends. Refresh the feed faster than monitor_interval_seconds.
    """
    try:
        stop = datetime.fromisoformat(until) if until else None
        if stop is not None and stop.tzinfo is None:
            raise ValueError("--until must include a timezone")
        if not orders.is_file():
            raise ValueError(f"orders file required: {orders}")
        cycles = failures = 0
        while True:
            now = now_utc()
            if stop is not None and now >= stop:
                emit({"scout": "stopped", "reason": "until reached", "cycles": cycles})
                return
            if max_cycles and cycles >= max_cycles:
                emit({"scout": "stopped", "reason": "cycle budget", "cycles": cycles})
                return
            cycles += 1
            try:
                line = scout_cycle(feed, work, book, orders, journal, config_root, account_id,
                                   prior_close_nav, high_water_nav, now)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                failures += 1
                line = {"at": now.isoformat(), "error": str(exc)}
                if failures >= 5:
                    emit({"scout": "aborted after repeated errors", "cycles": cycles, "last": line})
                    raise
            else:
                failures = 0
            emit(line)
            if line.get("orders"):
                emit({"scout": "stopped", "reason": "actionable order frozen for audit", "cycles": cycles})
                return
            if phase_at(now) not in RTH:
                emit({"scout": "stopped", "reason": "outside regular session", "cycles": cycles})
                return
            time.sleep(max(0.0, line.get("interval_seconds", 120)
                           - (now_utc() - now).total_seconds()))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        fail(exc)


@app.command("reserve")
def reserve(
    book: Path = typer.Option(...), account: Path = typer.Option(...),
    quotes: Path = typer.Option(...), orders: Path = typer.Option(...),
    symbol: str = typer.Option(...),
    envelope: Path | None = typer.Option(None, help="Within my bounds: the same-day envelope. "
                                                     "Omit or point at a missing file for Ask me (journaled Telegram approvals)."),
    lifecycle_state: Path = typer.Option(...),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
    config_root: Path = typer.Option(Path.cwd()),
) -> None:
    """Atomically check and reserve ONE exact limit order, never submit/retry.

    The authority is today's envelope (Within my bounds) or, without one, today's
    journaled Telegram approvals (Ask me); no second signature file races the quote clock.
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
            batch, mode, how = resolve_batch(envelope, events, today)
            line = batch.line_for(symbol, intent.side.value) if batch is not None else None
            protective = bool(proposal.get("protective")) and intent.side.value == "sell" and snapshot.position(symbol)
            if protective and (line is None or batch is None):
                # A stop/target/time exit of a lot the desk holds removes risk: it is authorized by the
                # entry the operator approved, not by a second yes today (direction 2026-11-24).
                mode, how = MODE_PROTECTIVE, f"protective exit: {intent.reason}; no operator line needed"
            else:
                if batch is None:
                    raise ValueError(how)
                if batch.approved_at.tzinfo is None or batch.approved_at > now:
                    raise ValueError("invalid envelope approval time")
                if line is None:
                    raise ValueError("operator envelope has no line for this order")
            # A line with no setup_hash is the operator's symbol-level pre-approval (2026-11-24 ruling:
            # "pre-approve now, I sleep"): any setup the kernel produces is authorized inside the line's
            # quantity and price bounds. A line that names a hash still binds that exact setup.
            if line is not None and line.setup_hash is not None and line.setup_hash != proposal["setup_hash"]:
                raise ValueError("operator envelope must bind the complete setup/account/config hash")
            entry = state.protected.get(symbol) if snapshot.position(symbol) else None
            entry = entry or next(e for e in watchlist.entries if e.symbol == symbol)
            if line is not None and line.setup_hash is not None and setup_hash(entry, config, snapshot.account_id) != line.setup_hash:
                raise ValueError("protected setup changed; obtain renewed approval")
            if intent.side.value == "buy":
                exit_line = batch.line_for(symbol, "sell")
                if (exit_line is None or exit_line.setup_hash != line.setup_hash
                        or exit_line.multiplier != intent.multiplier or exit_line.max_qty < intent.quantity):
                    raise ValueError("entry requires a matching bounded exit authorization")
            used_qty, used_notional = envelope_totals(events, today, symbol, intent.side.value)
            if intent.side.value == "buy" and effective_halt(journal.parent, config_root).get("halted"):
                raise ValueError("kill-switch engaged - buys blocked, de-risking sells still allowed")
            if mode != MODE_PROTECTIVE:
                authorized, reason = authorize_order(
                    batch, symbol=symbol, side=intent.side.value, qty=intent.quantity,
                    limit=intent.limit_price, today=today, used=envelope_usage(journal, today),
                    used_qty=used_qty, used_notional=used_notional, multiplier=intent.multiplier)
                if not authorized:
                    raise ValueError(reason)
            request_id = "tyche-tac-" + uuid.uuid4().hex
            resting = proposal.get("resting")
            payload = {**intent.model_dump(mode="json"), "request_id": request_id,
                       "multiplier": intent.multiplier, "setup_hash": proposal["setup_hash"],
                       "order_hash": proposal["order_hash"],
                       "protected_setup": entry.model_dump(mode="json"),
                       "reasons": proposal.get("reasons"),
                       "resting": resting,
                       "cancel_first": proposal.get("cancel_first") or [],
                       "authorization": authorization_record(mode, today),
                       "submit_before": (now + timedelta(seconds=30)).isoformat()}
            append_locked(journal, "tactical.monitor", {"state": state.model_dump(mode="json")})
            append_locked(journal, "order.requested", payload)
        steps = []
        if payload["cancel_first"]:
            steps.append("Cancel the desk's own working order(s) " + ", ".join(payload["cancel_first"])
                         + " for this symbol first and journal order.cancelled for their request ids.")
        steps.append("Persist the journal, then one US-paper limit order, exact fields and request_id as text"
                     + (", time in force DAY (it rests until filled or the close)" if resting else "") + ". No retry.")
        emit({"authorized": True, "request": payload, "risk": proposal["risk"], "submitted": False,
              "authority": how, "instructions": " ".join(steps)})
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, StopIteration) as exc:
        fail(exc)


@app.command("scalp")
def scalp(
    feed: Path = typer.Option(..., "--feed"), work: Path = typer.Option(..., "--dir"),
    orders: Path = typer.Option(...),
    envelope: Path | None = typer.Option(None, help="Within my bounds: the same-day envelope. "
                                                     "Omit or point at a missing file for Ask me (journaled Telegram approvals)."),
    account_id: str = typer.Option(...),
    prior_close_nav: float = typer.Option(...), high_water_nav: float = typer.Option(...),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
    config_root: Path = typer.Option(Path.cwd()),
    record: bool = typer.Option(False, "--record"),
) -> None:
    """PB-004 scalp cycle: exits, breakout entries, envelope authorization.

    Feed layout: accounts/cash/positions/quotes.json, book-*.json and
    bars-<US.SYMBOL>.json raw MCP kline payloads. With --record, passing orders
    are envelope-authorized and journaled as requests for the executor to submit.
    """
    try:
        config = load_config(config_root)
        if not config.scalp.enabled:
            raise ValueError("scalp lane disabled in config/scalp.yaml")
        if record and not config.strategy_enabled("PB-004"):
            # The operator's switch (data/strategies.json) gates the arm path; a dry run still evaluates.
            raise ValueError("PB-004 is switched off (tyche strategies); dry run only")
        now = now_utc()
        missing = [name for name in FEED_FILES if not (feed / name).is_file()]
        if missing:
            raise ValueError(f"feed missing {', '.join(missing)}")
        if work != feed:
            for path in [*(feed / name for name in FEED_FILES), *feed.glob("book-*.json")]:
                shutil.copy2(path, work / path.name)
        capture_dir(work, account_id, prior_close_nav, high_water_nav)
        snapshot = load(AccountSnapshot, work / "tactical-account.json")
        quotes = {q.symbol: q for q in (MarketQuote.model_validate(row) for row in json.loads(
            (work / "tactical-quotes.json").read_text(encoding="utf-8")))}
        bars = {symbol: bars_from_kline(json.loads((feed / f"bars-{symbol}.json").read_text(encoding="utf-8")))
                for symbol in config.scalp.symbols if (feed / f"bars-{symbol}.json").is_file()}
        if not journal.is_file():
            raise ValueError("persistent journal required")
        ok, _, error = verify_chain(journal)
        if not ok:
            raise ValueError(f"journal integrity: {error}")
        events = read_events(journal)
        today = now.astimezone(ET).date()
        rows = broker_orders(json.loads(orders.read_text(encoding="utf-8")))
        count, turnover = combined_usage(events, rows, today, {})
        state = scalp_state(events, today, config.scalp.timeout_minutes,
                            stop_pct=config.scalp.stop_pct, target_r=config.scalp.target_r)
        report = plan_scalp(quotes, bars, state, snapshot, config, now, orders_today=count,
                            traded_notional_today=turnover,
                            halted=bool(effective_halt(journal.parent, config_root).get("halted")))
        if record and report["orders"]:
            report["requests"] = _arm_scalp(report["orders"], envelope, journal, today, count,
                                            rows=rows)
        emit(report)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        fail(exc)


def _arm_scalp(proposals: list[dict], envelope: Path | None, journal: Path, today, used: int,
               rows: list[dict] | None = None) -> list[dict]:
    batch, mode, how = resolve_batch(envelope, read_events(journal), today)
    if batch is None:
        raise ValueError(how)
    armed = []
    now = now_utc()
    with journal_lock(journal):
        events = read_events(journal)
        for proposal in proposals:
            intent = OrderIntent.model_validate(proposal["intent"])
            live = _live_broker_order(rows or [], events, intent.symbol)
            if live is not None:
                armed.append({"symbol": intent.symbol, "side": intent.side.value,
                              "skipped": "broker already has a live order; reconcile before re-arm",
                              "order_id": live.get("order_id")})
                continue
            prior = _latest_scalp_request(events, intent.symbol, intent.side.value)
            gap_payload = None
            if prior is not None:
                resolution = _request_resolution(events, prior["payload"].get("request_id"))
                if resolution == "order.submitted":
                    armed.append({"symbol": intent.symbol, "side": intent.side.value,
                                  "skipped": "request already submitted; reconcile before re-arm",
                                  "request": prior["payload"]})
                    continue
                submit_before = prior["payload"].get("submit_before")
                if resolution is None and submit_before and datetime.fromisoformat(submit_before) > now:
                    armed.append({"symbol": intent.symbol, "side": intent.side.value,
                                  "skipped": "active request pending; retry the existing request",
                                  "request": prior["payload"]})
                    continue
                if (intent.side.value == "sell" and resolution in (None, "gate.wait")
                        and not _gap_recorded(events, prior["payload"].get("request_id"))):
                    gap = append_locked(journal, "protection.gap", {
                        "symbol": intent.symbol, "side": "sell", "strategy_id": "PB-004",
                        "request_id": prior["payload"].get("request_id"),
                        "resolution": resolution or "expired",
                        "submit_before": submit_before,
                        "reason": "exit request never reached the broker; re-arming with fresh quotes"})
                    events = read_events(journal)
                    gap_payload = gap["payload"]
            used_qty, used_notional = envelope_totals(events, today, intent.symbol, intent.side.value)
            ok, reason = authorize_order(
                batch, symbol=intent.symbol, side=intent.side.value, qty=intent.quantity,
                limit=intent.limit_price, today=today, used=envelope_usage(journal, today),
                used_qty=used_qty, used_notional=used_notional, multiplier=intent.multiplier)
            if not ok:
                denied = {"symbol": intent.symbol, "side": intent.side.value, "denied": reason}
                if gap_payload:
                    denied["protection_gap"] = gap_payload
                armed.append(denied)
                continue
            request_id = "tyche-scl-" + uuid.uuid4().hex
            plan_intent = {**intent.model_dump(mode="json"), **proposal.get("plan", {})}
            append_locked(journal, "plan.created", {"plan": {"nav": None, "orders": [
                {"intent": plan_intent}], "strategy_id": "PB-004",
                "thesis": proposal.get("thesis")}})
            payload = {**intent.model_dump(mode="json"), "request_id": request_id,
                       "multiplier": intent.multiplier, "setup_hash": None,
                       "order_hash": proposal["order_hash"],
                       "authorization": authorization_record(mode, today),
                       "submit_before": proposal.get("submit_before") or (
                           now + timedelta(seconds=ENTRY_SUBMIT_WINDOW_SECONDS)).isoformat()}
            append_locked(journal, "order.requested", payload)
            events = read_events(journal)
            entry = {"request": payload, "authorized": reason}
            if gap_payload:
                entry["protection_gap"] = gap_payload
            armed.append(entry)
    return armed


RESOLVED_REQUEST_EVENTS = {"order.submitted", "order.filled", "order.rejected",
                           "order.cancelled", "gate.wait"}
ENTRY_SUBMIT_WINDOW_SECONDS = 90


def _latest_scalp_request(events: list[dict], symbol: str, side: str) -> dict | None:
    latest = None
    for event in events:
        payload = event.get("payload", {})
        if (event.get("type") == "order.requested" and payload.get("strategy_id") == "PB-004"
                and payload.get("symbol") == symbol and payload.get("side") == side):
            latest = event
    return latest


def _request_resolution(events: list[dict], request_id: str | None) -> str | None:
    if not request_id:
        return None
    for event in events:
        if (event.get("type") in RESOLVED_REQUEST_EVENTS
                and event.get("payload", {}).get("request_id") == request_id):
            return event["type"]
    return None


def _gap_recorded(events: list[dict], request_id: str | None) -> bool:
    return any(event.get("type") == "protection.gap"
               and event.get("payload", {}).get("request_id") == request_id
               for event in events)


def _live_broker_order(rows: list[dict], events: list[dict], symbol: str) -> dict | None:
    """An order the broker still shows open, matched by request-id text.

    The journal can miss an order.submitted receipt, so the broker list is the
    tie-breaker that prevents a second exit on the same position.
    """
    request_ids = {event.get("payload", {}).get("request_id") for event in events
                   if event.get("type") == "order.requested"
                   and event.get("payload", {}).get("strategy_id") == "PB-004"
                   and event.get("payload", {}).get("symbol") == symbol}
    for row in rows:
        if order_symbol(row) != symbol:
            continue
        if (row.get("status") == 4
                and float(row.get("cum_qty", 0)) == float(row.get("qty", 0))):
            continue
        if str(row.get("text") or "") in request_ids:
            return row
    return None



@app.command("rollout-check")
def rollout_check(config_root: Path = typer.Option(Path.cwd())) -> None:
    config = load_config(config_root)
    emit({"local_planner_enabled": config.tactical.enabled,
          "local_options_enabled": config.options_live,
          "execution_gate_enabled": config.tactical.execution_enabled,
          "cloud_monitor_verified": False, "broker_option_round_trip_verified": False,
          "target_monitor_interval_seconds": config.tactical.monitor_interval_seconds,
          "blockers": ["Publish tested source to the existing cloud repository mount.",
                       "Use one durable writer for journal and BOTH strategy lanes; file locks are not distributed locks.",
                       "Validate configured-cadence monitoring, exits before the next scheduled check and missed-heartbeat alerts.",
                       "Verify option submission/partial fills/cancel/expiry behavior in an authorized paper drill.",
                       "Restore protected setups, journal and complete broker history before every run.",
                       "Obtain exact setup-bound operator envelopes and auditor approval; then enable the rollout gate."],
          "submitted": False})
