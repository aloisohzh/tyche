"""Paper lifecycle approvals, monitoring and explicitly enabled one-shot exits."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from pydantic import ValidationError

from tyche.broker.mcp_json import build_snapshot, extract_nav
from tyche.broker.moomoo_http import MoomooPaperHttp, PaperApiError, complete_order_rows
from tyche.config import load_config
from tyche.execution_state import combined_usage, unresolved_symbols
from tyche.journal import append_locked, journal_lock, read_events, verify_chain
from tyche.lifecycle import (
    Approval,
    BrokerOrder,
    LifecycleBook,
    LifecycleState,
    MarketSnapshot,
    Quote,
    Reservation,
    account_hash,
    review_problem,
    tick,
    validate_market,
)
from tyche.market_calendar import ET, regular_close
from tyche.models import OptionContract

app = typer.Typer(help="Paper lifecycles; only execute-exit --submit can send an approved exit.")


def emit(value: dict) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=True))


def now_utc(at: str = "") -> datetime:
    now = datetime.fromisoformat(at) if at else datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return now


def load(model, path: Path):
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def monitoring_book(path: Path, now: datetime) -> tuple[LifecycleBook, list[str]]:
    try:
        return load(LifecycleBook, path), []
    except (OSError, ValueError):
        # Research can fail without deleting previously approved protective rules.
        return LifecycleBook(news_checked_at=now, news_feed_ok=False), [
            "research book unavailable or invalid; entries disabled, retained approved exits only"
        ]


def save(path: Path, model) -> None:
    model = type(model).model_validate_json(model.model_dump_json())
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(model.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def locked_state(path: Path):
    """Atomic directory lock; never auto-break a stale or cross-host lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError("lifecycle state locked; skip, alert, do not bypass") from exc
    try:
        state = load(LifecycleState, path) if path.exists() else LifecycleState()
        yield state
    finally:
        lock.rmdir()


def fail(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        # Pydantic's default repr includes raw input, potentially full account IDs.
        reason = "invalid input: " + "; ".join(
            ".".join(map(str, error["loc"])) + " (" + error["type"] + ")"
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        )
    elif isinstance(exc, StopIteration):
        reason = "requested plan, approval or reservation not found"
    else:
        reason = str(exc)
    emit({"ok": False, "reason": reason, "submitted": False})
    raise typer.Exit(1) from exc


@app.command("schema")
def schema() -> None:
    """Machine-readable contracts for researcher/executor artifact handoffs."""
    emit({"book": LifecycleBook.model_json_schema(), "market": MarketSnapshot.model_json_schema(),
          "state": LifecycleState.model_json_schema()})


@app.command()
def preview(book: Path = typer.Option(...), plan_id: str = typer.Option(...)) -> None:
    """Present the exact whole-lifecycle contract before operator approval."""
    try:
        plans = load(LifecycleBook, book).plans
        plan = next(p for p in plans if p.plan_id == plan_id)
        risk = plan.quantity * (plan.entry_high - plan.stop.price)
        reward = plan.quantity * (plan.take_profit.price - plan.entry_high)
        emit({"plan": plan.model_dump(mode="json"), "plan_hash": plan.fingerprint(),
              "risk": {"planned_loss_at_stop_usd": round(risk, 2),
                       "planned_gain_at_target_usd": round(reward, 2),
                       "reward_risk_before_fees": round(reward / risk, 3),
                       "monitor_interval_minutes": 60,
                       "limitations": ["Synthetic triggers, not broker-native stops.",
                                       "Gaps, stale feeds, hourly latency and non-fills can exceed planned loss.",
                                       "Daily-close triggers execute no earlier than the next permitted session.",
                                       "Full-position exits only; no shorting, scaling or automatic re-entry.",
                                       "Unknown/cancelled/rejected orders require reconciliation and operator review."]},
              "approved": False, "submitted": False})
    except (OSError, ValueError, StopIteration) as exc:
        fail(exc)


@app.command()
def approve(
    book: Path = typer.Option(...), market: Path = typer.Option(...),
    state: Path = typer.Option(...), plan_id: str = typer.Option(...),
    plan_hash: str = typer.Option(..., "--hash"),
    operator_ref: str = typer.Option(...), auditor_ref: str = typer.Option(...),
    yes: bool = typer.Option(False, "--yes"),
    config_root: Path = typer.Option(Path.cwd()),
) -> None:
    """Operator-only: record approval AFTER explicit approval of this preview/hash."""
    try:
        if not yes:
            raise ValueError("explicit approval of the complete preview is required; no grant written")
        now = now_utc()
        config = load_config(config_root)
        inputs, quotes = load(LifecycleBook, book), load(MarketSnapshot, market)
        validate_market(quotes, config, now)
        plan = next(p for p in inputs.plans if p.plan_id == plan_id)
        if plan.fingerprint() != plan_hash:
            raise ValueError("preview hash changed; re-preview and obtain renewed approval")
        problem = review_problem(plan, inputs, now)
        if problem:
            raise ValueError(problem)
        from tyche.pipeline import rules_hash
        if plan.rules_hash != rules_hash(config_root, plan.strategy_id):
            raise ValueError("strategy rules changed; re-preview")
        if now >= plan.exit_deadline:
            raise ValueError("cannot approve an expired lifecycle")
        held = quotes.snapshot.position(plan.symbol)
        quantity = held.quantity if held else 0
        if plan.mode == "new_entry" and quantity:
            raise ValueError("already held: requires an explicit adopt_position lifecycle")
        if plan.mode == "adopt_position" and quantity != plan.quantity:
            raise ValueError("adoption must cover the exact current broker holding")
        key = account_hash(quotes.snapshot.account_id)
        with locked_state(state) as ledger:
            if any(r.symbol == plan.symbol and r.account_hash == key and not r.complete
                   for r in ledger.reservations):
                raise ValueError("unresolved order for this symbol; reconcile before approving")
            if any(a.plan_hash == plan_hash and a.account_hash == key for a in ledger.approvals):
                raise ValueError("this hash was already approved or revoked; use a reviewed new revision")
            if any(a.contract.symbol == plan.symbol and a.account_hash == key and not a.revoked
                   for a in ledger.approvals):
                raise ValueError("revoke the prior lifecycle before replacement")
            ledger.approvals.append(Approval(
                plan_hash=plan_hash, contract=plan.model_copy(deep=True),
                account_hash=key, approved_at=now,
                operator_ref=operator_ref, auditor_ref=auditor_ref,
                adopted_quantity=quantity if plan.mode == "adopt_position" else 0,
            ))
            save(state, ledger)
        emit({"approved": True, "plan_hash": plan_hash, "submitted": False})
    except (OSError, ValueError, StopIteration) as exc:
        fail(exc)


@app.command()
def revoke(state: Path = typer.Option(...), plan_hash: str = typer.Option(..., "--hash"),
           yes: bool = typer.Option(False, "--yes")) -> None:
    """Operator-only: revoke automation; does NOT cancel an already submitted order."""
    try:
        if not yes:
            raise ValueError("explicit operator revocation required")
        with locked_state(state) as ledger:
            matching = [a for a in ledger.approvals if a.plan_hash == plan_hash]
            if not matching:
                raise ValueError("approval not found")
            for approval in matching:
                approval.revoked = True
            save(state, ledger)
        emit({"revoked": True, "orders_cancelled": False})
    except (OSError, ValueError) as exc:
        fail(exc)


@app.command("tick")
def monitor(
    book: Path = typer.Option(...), market: Path = typer.Option(...),
    state: Path = typer.Option(...), config_root: Path = typer.Option(Path.cwd()),
    at: str = typer.Option("", help="Replay clock; cannot authorize a submission."),
    record: bool = typer.Option(False, "--record"),
) -> None:
    """Evaluate all positions. --record durably latches triggers; never submits."""
    try:
        if at and record:
            raise ValueError("replay clock cannot mutate live state")
        with locked_state(state) as ledger:
            now = now_utc(at)
            inputs, gaps = monitoring_book(book, now)
            report = tick(inputs, load(MarketSnapshot, market), ledger,
                          load_config(config_root), now)
            report["gaps"].extend(gaps)
            if record:
                save(state, ledger)
            emit(report)
    except (OSError, ValueError) as exc:
        fail(exc)


@app.command()
def reserve(
    book: Path = typer.Option(...), market: Path = typer.Option(...),
    state: Path = typer.Option(...), plan_id: str = typer.Option(...),
    plan_hash: str = typer.Option(..., "--hash"),
    config_root: Path = typer.Option(Path.cwd()),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
) -> None:
    """One-shot gate BEFORE MCP submit. Durable reservation blocks duplicate attempts.

    Only an exit-0 result authorizes its exact order. Use request_id as broker
    text/remark. Never call this again to retry an uncertain broker submission.
    """
    try:
        if not journal.is_file():
            raise ValueError("persistent journal missing; restore and reconcile before submission")
        if not state.is_file():
            raise ValueError("persistent lifecycle state missing; restore before submission")
        with journal_lock(journal), locked_state(state) as ledger:
            valid, _, reason = verify_chain(journal)
            if not valid:
                raise ValueError("journal integrity: " + str(reason))
            events = read_events(journal)
            check_execution_journal(events, ledger)
            now = now_utc()
            inputs, gaps = monitoring_book(book, now)
            quotes = load(MarketSnapshot, market)
            config = load_config(config_root)
            from tyche.halt import effective_halt
            quotes.halted = quotes.halted or effective_halt(journal.parent, config_root)["halted"]
            if abs(quotes.snapshot.nav - quotes.broker_nav) > max(1.0, quotes.broker_nav * 0.001):
                raise ValueError("broker cash, positions and NAV do not reconcile")
            report = tick(inputs, quotes, ledger, config, now)
            decision = next(d for d in report["decisions"]
                            if d["plan_id"] == plan_id and d["plan_hash"] == plan_hash)
            if not decision["authorized"] or decision["action"] not in {"buy", "sell"}:
                save(state, ledger)  # preserve reconciliation and any detected trigger
                raise ValueError(decision["reason"])
            approval = next(a for a in ledger.approvals
                            if a.plan_hash == plan_hash and not a.revoked
                            and a.account_hash == account_hash(quotes.snapshot.account_id))
            contract = approval.contract
            rows = [{"order_id": o.order_id, "symbol": o.symbol, "side": 1 if o.side == "buy" else 2,
                     "qty": o.quantity, "cum_qty": o.filled_quantity, "status": o.status,
                     "price": o.limit_price, "text": o.remark,
                     "create_time": int(o.created_at.timestamp() * 1_000_000)} for o in quotes.orders]
            if contract.symbol in unresolved_symbols(events, rows):
                raise ValueError("unresolved journal order for this symbol; no further submission")
            contracts = {o.symbol: o.option for o in quotes.orders if o.option is not None}
            count, _ = combined_usage(events, rows, now.astimezone(ET).date(), contracts)
            if count >= config.risk.competition_order_cap:
                raise ValueError("competition daily order ceiling reached across execution lanes")
            if decision["action"] == "sell":
                owned = approval.adopted_quantity + sum(
                    r.filled_quantity * (1 if r.side == "buy" else -1) for r in ledger.reservations
                    if r.account_hash == approval.account_hash and r.plan_hash == plan_hash
                )
                if decision["quantity"] != owned:
                    raise ValueError("full attributed position unavailable; reconcile before exit")
            quote = next(q for q in quotes.quotes if q.symbol == contract.symbol)
            close = datetime.combine(now.astimezone(ET).date(),
                                     regular_close(now.astimezone(ET).date()), ET)
            deadlines = [now + timedelta(seconds=60), close,
                         quotes.observed_at + timedelta(seconds=120),
                         quote.at + timedelta(seconds=contract.quote_max_age_seconds)]
            if decision["action"] == "buy":
                review = next(r for r in inputs.reviews if r.plan_hash == plan_hash)
                deadlines.extend([contract.entry_expires_at, review.valid_until,
                                  review.reviewed_at + timedelta(minutes=contract.review_max_age_minutes),
                                  inputs.news_checked_at + timedelta(hours=1)])
            submit_before = min(deadlines)
            if submit_before <= now:
                raise ValueError("authorization window expired; fetch and re-evaluate")
            request = Reservation(
                request_id="tyche-lc-" + uuid.uuid4().hex,
                plan_hash=decision["plan_hash"], account_hash=account_hash(quotes.snapshot.account_id),
                symbol=decision["symbol"], side=decision["action"],
                quantity=decision["quantity"], limit_price=decision["limit_price"],
                reason=decision["reason"], reserved_at=now,
            )
            ledger.reservations.append(request)
            save(state, ledger)  # MUST succeed before telling the executor it may submit
            append_locked(journal, "order.requested", {
                **request.model_dump(mode="json"),
                "authorization": {"mode": "lifecycle", "plan_hash": request.plan_hash},
            })  # Failure leaves the reservation blocked; no authorization is emitted.
        emit({"authorized": True, "request": request.model_dump(mode="json"),
              "submit_before": submit_before.timestamp(), "submitted": False, "warnings": gaps,
              "instructions": "One limit order, US paper RTH only; exact fields and request_id as text. "
                              "Submit strictly before submit_before; otherwise stop and request operator review."})
    except (OSError, ValueError, RuntimeError, StopIteration) as exc:
        fail(exc)


def check_execution_journal(events: list[dict], ledger: LifecycleState) -> None:
    requests = [e["payload"] for e in events if e.get("type") == "order.requested"]
    ids = [r.get("request_id") for r in requests]
    if any(not key for key in ids) or len(ids) != len(set(ids)):
        raise PaperApiError("unclassified or duplicate journal request; operator review required")
    reservations = {r.request_id: r for r in ledger.reservations}
    journal_requests = {r["request_id"]: r for r in requests}
    for row in requests:
        if (row.get("authorization", {}).get("mode") in {"lifecycle", "lifecycle_exit"}
                and row["request_id"] not in reservations):
            raise PaperApiError("journal reservation missing from lifecycle state; restore and reconcile")
    for request in ledger.reservations:
        row = journal_requests.get(request.request_id)
        if row is None or any(row.get(field) != getattr(request, field) for field in (
            "plan_hash", "account_hash", "symbol", "side", "quantity", "limit_price"
        )):
            raise PaperApiError("lifecycle reservation differs from journal; restore and reconcile")


@app.command("execute-exit")
def execute_exit(
    book: Path = typer.Option(...), market: Path = typer.Option(...),
    state: Path = typer.Option(...), plan_id: str = typer.Option(...),
    plan_hash: str = typer.Option(..., "--hash"),
    config_root: Path = typer.Option(Path.cwd()),
    journal: Path = typer.Option(Path("journal/events.jsonl")),
    submit: bool = typer.Option(False, "--submit", help="Execute an already-approved paper exit once."),
) -> None:
    """Refresh broker data and check one exact approved exit; read-only by default."""
    attempted, acknowledged = False, False
    request = None
    try:
        if not journal.is_file() or not state.is_file():
            raise PaperApiError("persistent journal/state missing; restore before execution")
        with journal_lock(journal), locked_state(state) as ledger:
            valid, _, _ = verify_chain(journal)
            if not valid:
                raise PaperApiError("journal integrity failed; no execution permitted")
            events = read_events(journal)
            check_execution_journal(events, ledger)
            config, context = load_config(config_root), load(MarketSnapshot, market)
            account = context.snapshot
            key = account_hash(account.account_id)
            if (account.env != "paper" or account.source != "sim_list" or account.market_id != 100
                    or account.account_type not in config.risk.sim_account_types
                    or account.account_id not in config.risk.account_allowlist):
                raise PaperApiError("unverified or non-allowlisted US paper account")
            approval = next((a for a in ledger.approvals if a.plan_hash == plan_hash
                             and a.contract.plan_id == plan_id and a.account_hash == key
                             and not a.revoked and a.approved_at <= now_utc()), None)
            if approval is None:
                raise PaperApiError("exact lifecycle requires prior operator approval")
            contract = approval.contract
            broker = MoomooPaperHttp.from_env()
            closes = {q.symbol: {"close": q.close, "close_at": q.close_at}
                      for q in context.quotes if q.close is not None}
            contracts = {item.symbol: item.option for item in [*account.positions, *context.orders]
                         if item.option is not None}

            def refresh():
                payloads = broker.read(account.account_id, contract.symbol,
                                       config.risk.sim_account_types, clock=now_utc)
                fresh_market = captured_market(
                    account.account_id, payloads, context.prior_close_nav, context.high_water_nav,
                    context.regime, context.conviction, closes, contracts,
                )
                from tyche.halt import is_halted
                fresh_market.halted = is_halted(journal.parent) or context.halted
                validate_market(fresh_market, config, now_utc())
                if abs(fresh_market.snapshot.nav - fresh_market.broker_nav) > max(
                    1.0, fresh_market.broker_nav * 0.001
                ):
                    raise PaperApiError("broker cash, positions and NAV do not reconcile")
                return fresh_market, payloads["orders"]

            quotes, rows = refresh()
            now = now_utc()
            inputs, gaps = monitoring_book(book, now)
            report = tick(inputs, quotes, ledger, config, now)
            if submit:
                save(state, ledger)
            decision = next((d for d in report["decisions"]
                             if d["plan_id"] == plan_id and d["plan_hash"] == plan_hash), None)
            if decision is not None and decision["action"] == "buy":
                decision["authorized"] = False
                decision["reason"] = "exit-only routine cannot authorize an entry"
            if decision is None or not decision["authorized"] or decision["action"] != "sell":
                emit({"ok": True, "submitted": False, "attempted": False,
                      "reason": decision["reason"] if decision else "no approved exit available",
                      "decision": decision, "warnings": report["gaps"] + gaps})
                return
            if contract.symbol in unresolved_symbols(events, rows):
                raise PaperApiError("unresolved journal order for this symbol; no further submission")
            count, _ = combined_usage(events, rows, now.astimezone(ET).date(), contracts)
            if count >= config.risk.competition_order_cap:
                raise PaperApiError("competition daily order ceiling reached across execution lanes")
            owned = approval.adopted_quantity + sum(
                r.filled_quantity * (1 if r.side == "buy" else -1) for r in ledger.reservations
                if r.account_hash == key and r.plan_hash == plan_hash
            )
            if decision["quantity"] != owned:
                raise PaperApiError("full attributed position unavailable; reconcile before exit")
            if not submit:
                emit({"ok": True, "submitted": False, "attempted": False,
                      "decision": decision, "warnings": report["gaps"] + gaps, "dry_run": True})
                return
            quote = next(q for q in quotes.quotes if q.symbol == contract.symbol)
            close = datetime.combine(now.astimezone(ET).date(),
                                     regular_close(now.astimezone(ET).date()), ET)
            deadline = min(now + timedelta(seconds=60), close,
                           quotes.observed_at + timedelta(seconds=120),
                           quote.at + timedelta(seconds=contract.quote_max_age_seconds))
            request = Reservation(
                request_id="tyche-lc-" + uuid.uuid4().hex, plan_hash=plan_hash, account_hash=key,
                symbol=contract.symbol, side="sell", quantity=decision["quantity"],
                limit_price=decision["limit_price"], reason=decision["reason"], reserved_at=now,
            )
            ledger.reservations.append(request)
            save(state, ledger)
            append_locked(journal, "order.requested", {
                **request.model_dump(mode="json"),
                "authorization": {"mode": "lifecycle_exit", "plan_hash": plan_hash,
                                  "as_of": now.astimezone(ET).date().isoformat()},
            })
            if now_utc() >= deadline:
                raise PaperApiError("submission window expired; reservation retained")
            attempted = True
            failure = None
            try:
                request.order_id = broker.submit_exit(account.account_id, request,
                                                       deadline=deadline, clock=now_utc)
                acknowledged = True
            except (OSError, ValueError) as exc:
                # The broker may have accepted the order even when its reply was lost.
                failure = type(exc).__name__
            save(state, ledger)
            append_locked(journal, "order.submitted" if acknowledged else "order.unknown", {
                "request_id": request.request_id, "order_id": request.order_id,
                "plan_hash": plan_hash, "account_hash": key, "failure": failure,
            })
            after, _ = refresh()
            from tyche.lifecycle import reconcile
            reconcile(ledger, after)
            before_held = quotes.snapshot.position(contract.symbol)
            after_held = after.snapshot.position(contract.symbol)
            if (after_held.quantity if after_held else 0) != before_held.quantity - request.filled_quantity:
                raise PaperApiError("fills and holdings disagree; reconcile before further execution")
            matched = any(o.order_id == request.order_id for o in after.orders)
            if request.order_id and not acknowledged:
                append_locked(journal, "order.submitted", {
                    "request_id": request.request_id, "order_id": request.order_id,
                    "plan_hash": plan_hash, "account_hash": key,
                })
            acknowledged = acknowledged or request.order_id is not None
            save(state, ledger)
            append_locked(journal, "order.reconciled", {
                **request.model_dump(mode="json"), "observed_at": after.observed_at.isoformat(),
            })
            emit({"ok": matched, "attempted": True,
                  "submitted": True if acknowledged else None, "filled": request.complete,
                  "request_id": request.request_id,
                  "outcome": "filled" if request.complete else "pending" if matched else "unknown",
                  "warnings": report["gaps"] + gaps,
                  "retry_permitted": False})
            if not matched:
                raise typer.Exit(1)
    except typer.Exit:
        raise
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, OverflowError) as exc:
        reason = str(exc) if isinstance(exc, PaperApiError) else (
            "broker, journal or lifecycle check failed; operator review required ("
            + type(exc).__name__ + ")"
        )
        emit({"ok": False, "reason": reason, "attempted": attempted,
              "submitted": True if acknowledged else None if attempted else False,
              "request_id": request.request_id if request else None, "retry_permitted": False})
        raise typer.Exit(1) from None


@app.command()
def receipt(state: Path = typer.Option(...), request_id: str = typer.Option(...),
            order_id: str = typer.Option(...)) -> None:
    """Record the id returned by a successful submit; this does not mark a fill."""
    try:
        with locked_state(state) as ledger:
            request = next(r for r in ledger.reservations if r.request_id == request_id)
            if request.order_id and request.order_id != order_id:
                raise ValueError("cannot replace an existing broker order id")
            request.order_id = order_id
            save(state, ledger)
        emit({"recorded": True, "filled": False})
    except (OSError, ValueError, StopIteration) as exc:
        fail(exc)


def whole(value) -> int:
    numeric = float(value)
    if not numeric.is_integer() or numeric < 0:
        raise ValueError("only nonnegative whole-share quantities are supported")
    return int(numeric)


def raw(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("ret_code") != 0 or not isinstance(payload.get("data"), dict):
        raise ValueError(f"failed or malformed MCP response: {path.name}")
    return payload


def captured_market(account_id, payloads, prior_close_nav, high_water_nav,
                    regime, conviction, closes, contracts=None) -> MarketSnapshot:
    contracts = contracts or {}
    orders = []
    for row in payloads["orders"]:
        if row["side"] not in (1, 2):
            raise ValueError("unsupported broker order side")
        orders.append(BrokerOrder(
            order_id=str(row["order_id"]), symbol="US." + row["symbol"],
            option=contracts.get("US." + row["symbol"]),
            side="buy" if row["side"] == 1 else "sell", quantity=whole(row["qty"]),
            filled_quantity=whole(row["cum_qty"]), status=row["status"],
            limit_price=float(row["price"]), remark=row.get("text") or "",
            created_at=datetime.fromtimestamp(int(row["create_time"]) / 1_000_000, UTC),
        ))
    available = {}
    for row in payloads["positions"]["data"]["positions"]:
        if row["pstn_type"] != 0:
            raise ValueError("short/unsupported position: cannot automate this account")
        whole(row["qty"])
        available["US." + row["symbol"]] = whole(row["qty_avbl"])
    quotes = []
    for row in payloads["quotes"]["data"]["quote_list"]:
        close = closes.get(row["code"], {})
        quotes.append(Quote(
            symbol=row["code"], last=row["last_price"],
            at=datetime.fromtimestamp(int(row["data_time"]) / 1000, UTC),
            tradable=row.get("sec_status") == "NORMAL" and row.get("suspension") is False,
            close=close.get("close"), close_at=close.get("close_at"),
        ))
    return MarketSnapshot(
        observed_at=payloads["observed_at"], snapshot=build_snapshot(
            account_id, payloads["accounts"], payloads["cash"], payloads["positions"],
            captured_at=payloads["observed_at"], contracts=contracts,
        ), regime=regime, conviction=conviction, broker_nav=extract_nav(payloads["cash"]),
        prior_close_nav=prior_close_nav, high_water_nav=high_water_nav, available=available,
        quotes=quotes, orders=orders, orders_complete=True,
    )


@app.command()
def capture(
    directory: Path = typer.Option(..., "--dir"), account_id: str = typer.Option(...),
    observed_at: str = typer.Option(..., help="UTC timestamp of the OLDEST broker read in this batch."),
    prior_close_nav: float = typer.Option(...), high_water_nav: float = typer.Option(...),
    regime: str = typer.Option(..., help="Regime from the current deterministic kernel plan."),
    conviction: str = typer.Option(..., help="Conviction tier from the current kernel plan pipeline."),
    out: Path = typer.Option(...),
) -> None:
    """Normalize observed MCP payloads. Raw JSON is never a guessed model schema.

    Required files: accounts.json, cash.json, positions.json, quotes.json,
    orders.json (or orders-*.json for every paginated page). Optional closes.json
    maps symbols to {close, close_at} derived from completed daily bars.
    """
    try:
        accounts, cash, positions, quotes = [raw(directory / name) for name in (
            "accounts.json", "cash.json", "positions.json", "quotes.json"
        )]
        order_paths = list(directory.glob("orders-*.json"))
        if order_paths:
            if (directory / "orders.json").exists():
                raise ValueError("mixed single-page and multi-page order history")
            order_paths.sort(key=lambda p: int(p.stem.removeprefix("orders-")))
            if [int(p.stem.removeprefix("orders-")) for p in order_paths] != list(range(1, len(order_paths) + 1)):
                raise ValueError("order pages must be numbered consecutively from orders-1.json")
        else:
            order_paths = [directory / "orders.json"]
        pages = [raw(path) for path in order_paths]
        closes_path = directory / "closes.json"
        closes = json.loads(closes_path.read_text()) if closes_path.exists() else {}
        contract_path = directory / "contracts.json"
        contracts = {symbol: OptionContract.model_validate(value) for symbol, value in
                     json.loads(contract_path.read_text()).items()} if contract_path.is_file() else {}
        result = captured_market(
            account_id, {"accounts": accounts, "cash": cash, "positions": positions,
                         "quotes": quotes, "orders": complete_order_rows(pages),
                         "observed_at": now_utc(observed_at)},
            prior_close_nav, high_water_nav, regime, conviction, closes, contracts,
        )
        save(out, result)
        emit({"captured": True, "path": str(out), "submitted": False})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail(exc)
