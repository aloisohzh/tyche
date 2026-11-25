"""`tyche cycle`: one command from saved broker reads to the list of orders to send.

Until 2026-11-25 an order needed about 45 hand-run steps spread over two agents: restore the journal,
find the NAV references, capture, tick, reserve one symbol at a time, journal each receipt by hand.
A run took longer than the data it had just read stayed "fresh", so the kernel refused its own
orders and no trade was placed. This command does every deterministic step in one process:

1. finds the ledger (the longest verified journal under the Drive root) and heals forks into it;
2. finds today's watchlist and the NAV references;
3. normalizes the saved broker reads and checks the account is the allowlisted paper account;
4. journals what the broker shows about the desk's own orders (receipts, fills, cancels);
5. runs the PB-004 scalp kernel and the PB-002/PB-003 tactical kernel;
6. authorizes every order against the operator's standing paper approval and reserves it;
7. prints ONE flat list: what to cancel, what to submit, in order.

It never calls a broker. The executor agent reads the market, saves the payloads, runs this, and
sends exactly what `submit` lists. The paper-account check is unchanged and comes first.
"""
# ruff: noqa: B008 -- Typer's declarative command option defaults.
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from tyche.approvals import resolve_batch
from tyche.config import load_config
from tyche.execution_state import (
    SCALP_PREFIX,
    TACTICAL_PREFIX,
    broker_orders,
    combined_usage,
    dead_request_ids,
    order_finished,
    order_symbol,
    pending_intents,
    receipts_to_journal,
)
from tyche.halt import effective_halt
from tyche.journal import append_locked, journal_lock, read_events, verify_chain
from tyche.leases import SCALP, STOCK, shared_symbols, ticker_leases
from tyche.market_calendar import ET, SessionPhase, phase_at, regular_close
from tyche.models import OPTION_SYMBOL, AccountSnapshot, OptionContract
from tyche.scalp import ScalpLot, ScalpState, bars_from_kline, plan_scalp, scalp_state
from tyche.tactical import RTH, MarketQuote, plan_tick
from tyche.tactical_cli import (
    arm_scalp_locked,
    authorize_tactical,
    capture_dir,
    monitor_state,
    verified_paper,
)
from tyche.watchlist import Watchlist, WatchlistEntry

DRIVE_ROOT = Path("/data/drive/tyche-raw")
REQUIRED_READS = ("accounts.json", "cash.json", "positions.json", "orders.json", "quotes.json")
ORDER_ROW_FIELDS = ("order_id", "symbol", "side", "qty", "cum_qty", "price", "status", "create_time")
# The challenge's verified starting NAV: the high-water mark until a verified close exceeds it.
START_NAV = 100_000.0
NAV_REFS_FILE = "nav-refs.json"
# How far back a sibling journal may hold an order event the ledger lacks and still be merged in.
MERGE_HOURS = 36
MERGE_TYPES = ("order.requested", "order.submitted", "order.filled", "order.cancelled", "order.rejected",
               "gate.wait", "approval.telegram")
# A longer chain is a bigger file in practice, so only the few largest journals are verified per run.
LEDGER_CANDIDATES = 5
FREEZE_REASON = ("config bytes changed on main through an operator-merged pull request; "
                 "registered automatically by tyche cycle")


# The broker's servers and the Drive mount stamp the reads, this container reads the clock. A reading
# that looks a little ahead of "now" is a clock difference between machines (or a 1-minute bar stamped
# with the minute it ends in), never a reason to refuse the run.
CLOCK_SKEW_SECONDS = 300


def now_utc() -> datetime:
    return datetime.now(UTC)


def _not_ahead(stamp: datetime | None, now: datetime) -> datetime | None:
    """`stamp`, or `now` when it is at most the allowed clock difference ahead of `now`."""
    if stamp is None or stamp.tzinfo is None:
        return stamp
    return now if 0 < (stamp - now).total_seconds() <= CLOCK_SKEW_SECONDS else stamp


def find_ledger(drive_root: Path) -> Path | None:
    """The longest verified journal under the Drive root (the same rule the publish step uses).

    Every run bundle may hold a copy of the journal; the ledger is whichever verified chain has the
    most events, and every writer appends to that one file in place. A chain that does not verify is
    never the ledger, however long it is.
    """
    paths = []
    for path in drive_root.glob("*/journal/events.jsonl"):
        try:
            paths.append((path.stat().st_size, path))
        except OSError:
            continue
    best: tuple[int, str, Path] | None = None
    for _, path in sorted(paths, key=lambda row: (row[0], str(row[1])), reverse=True)[:LEDGER_CANDIDATES]:
        ok, count, _ = verify_chain(path)
        if ok and count and (best is None or (count, path.parent.parent.name) > best[:2]):
            best = (count, path.parent.parent.name, path)
    return best[2] if best else None


def _merge_key(event: dict) -> tuple | None:
    payload = event.get("payload") or {}
    if event.get("type") == "approval.telegram":
        return ("approval.telegram", payload.get("ref"), payload.get("n"))
    request_id = payload.get("request_id")
    return (event.get("type"), request_id) if request_id else None


def missing_order_events(ledger_events: list[dict], drive_root: Path, ledger: Path,
                         now: datetime) -> list[tuple[str, dict]]:
    """Order events a recent sibling journal holds and the ledger lacks (a fork to heal).

    A run that copied the journal into its own folder and wrote there left its reservations out of
    the ledger. Left alone, the next run would not know about those orders. Each missing event is
    appended once, in its original order, with the time it was first written kept beside it.
    """
    since = now - timedelta(hours=MERGE_HOURS)
    have = {_merge_key(e) for e in ledger_events if e.get("type") in MERGE_TYPES} - {None}
    siblings = []
    for path in drive_root.glob("*/journal/events.jsonl"):
        try:
            if path.resolve() == ledger.resolve():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:
            continue
        if modified >= since:
            siblings.append((modified, path))
    found: list[tuple[str, str, dict]] = []
    for _, path in sorted(siblings, key=lambda row: row[0], reverse=True)[:12]:
        try:
            rows = read_events(path)
        except (OSError, ValueError):
            continue  # a sibling that cannot be read heals nothing; the ledger itself is verified
        for event in rows:
            key = _merge_key(event) if event.get("type") in MERGE_TYPES else None
            if key is None or key in have:
                continue
            try:
                stamp = datetime.fromisoformat(str(event.get("ts")))
            except ValueError:
                continue
            if stamp.tzinfo is None or stamp < since:
                continue
            have.add(key)
            found.append((event["ts"], event["type"],
                          {**(event.get("payload") or {}), "merged_from": path.parent.parent.name,
                           "first_written": event["ts"]}))
    return [(kind, payload) for _, kind, payload in sorted(found, key=lambda row: row[0])]


def _first_error(exc: ValueError) -> str:
    """The first thing wrong with a setup, in the validator's own words (field name first when it has one)."""
    for error in getattr(exc, "errors", list)():
        where = ".".join(str(part) for part in error.get("loc") or ())
        what = str(error.get("msg") or "").removeprefix("Value error, ")
        return f"{where}: {what}" if where else what
    return str(exc).splitlines()[0]


def read_watchlist(path: Path) -> tuple[Watchlist, list[str]]:
    """One watchlist file, setup by setup: a setup that fails its checks is named and left out.

    The file used to be all or nothing, so one malformed option block silenced every stock setup
    beside it. Raises ValueError only when the file itself cannot be read as a dated list.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise ValueError('expected {"as_of": "YYYY-MM-DD", "entries": [...]}')  # noqa: TRY004 - a bad file, like any other
    as_of = datetime.strptime(str(raw.get("as_of")), "%Y-%m-%d").date()
    written_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    entries: list[WatchlistEntry] = []
    notes: list[str] = []
    seen: set[str] = set()
    for item in raw["entries"]:
        label = str((item or {}).get("symbol") or (item or {}).get("setup_id") or "?") if isinstance(item, dict) else "?"
        if isinstance(item, dict):
            # Bookkeeping fields the research need not type: a slip in one of them must not cost the
            # day. The evidence itself (thesis, catalyst, sources, factors, levels) is never defaulted.
            item = dict(item)
            ticker = item.get("symbol")
            if isinstance(ticker, str) and ticker.isalpha() and ticker.isupper() and len(ticker) <= 5:
                item["symbol"] = f"US.{ticker}"  # a bare ticker; every other lane spells it US.KO
            if isinstance(item.get("sources"), list):
                # A source given as {"url": ..., "title": ...} is the same citation as its URL alone.
                item["sources"] = [s["url"] if isinstance(s, dict) and isinstance(s.get("url"), str) else s
                                   for s in item["sources"]]
            for key, default in (("expiry", as_of.isoformat()), ("reviewed_at", written_at),
                                 ("setup_id", f"{label.removeprefix('US.').lower()}-{as_of.isoformat()}")):
                if item.get(key) in (None, ""):
                    item[key] = default
        try:
            entry = WatchlistEntry.model_validate(item)
        except ValueError as exc:
            notes.append(f"watchlist setup {label} left out: {_first_error(exc)[:160]}")
            continue
        keys = {entry.symbol, f"id:{entry.setup_id}"} if entry.setup_id else {entry.symbol}
        if keys & seen:
            notes.append(f"watchlist setup {label} left out: a second setup for the same symbol or setup id")
            continue
        seen |= keys
        entries.append(entry)
    return Watchlist(as_of=as_of, entries=entries), notes


def find_watchlist(book: Path | None, directory: Path, drive_root: Path, today) -> tuple[Watchlist, str | None, list[str]]:
    """Today's watchlist: (book, where it came from, notes).

    `--book` wins. Otherwise the canonical file on Drive, then the newest research file a run saved.
    Only a file dated today counts: yesterday's levels are never traded. With none, the run still
    protects what the desk holds and still runs the scalp; it just opens no new stock position.
    """
    candidates: list[Path] = []
    if book is not None:
        candidates = [book]
    else:
        fixed = [directory / "watchlist.json", drive_root / "watchlist.json"]
        research = [p for pattern in ("*/research/watchlist.json", "*/research/proposals-watchlist.json",
                                      "*/research/watchlist-published.json")
                    for p in drive_root.glob(pattern)]

        def modified(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0
        candidates = [p for p in fixed if p.is_file()] + sorted(research, key=modified, reverse=True)[:8]
    problems: list[str] = []
    for path in candidates:
        try:
            found, notes = read_watchlist(path)
        except (OSError, ValueError, TypeError) as exc:
            problems.append(f"{path} cannot be read ({str(exc).splitlines()[0][:120]})")
            continue
        if found.as_of == today:
            return found, str(path), notes
        problems.append(f"{path} is dated {found.as_of}")
    note = ("no watchlist dated today" + (f" ({problems[0]})" if problems else "")
            + "; no new stock or option entries until the research run writes one")
    return Watchlist(as_of=today, entries=[]), None, [note]


def _nav_source(drive_root: Path, events: list[dict]) -> dict:
    try:
        source = json.loads((drive_root / NAV_REFS_FILE).read_text(encoding="utf-8"))
        if isinstance(source, dict):
            return source
    except (OSError, ValueError):
        pass
    for event in reversed(events):
        if event.get("type") == "nav.refs_updated":
            return event.get("payload") or {}
    return {}


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def find_nav_refs(prior: float | None, high: float | None, drive_root: Path,
                  events: list[dict]) -> tuple[float, float, str | None]:
    """prior-close and high-water NAV as last written: the flags, else Drive nav-refs.json, else the
    journal's last `nav.refs_updated`, else the challenge's verified 100,000 start (with a note)."""
    source = _nav_source(drive_root, events)
    prior_nav = _positive(prior) or _positive(source.get("prior_close_nav"))
    high_nav = _positive(high) or _positive(source.get("high_water_nav"))
    note = None
    if prior_nav is None or high_nav is None:
        note = ("NAV references not found on Drive or in the journal: using the verified 100,000 start "
                f"until a run writes {DRIVE_ROOT / NAV_REFS_FILE}")
    return prior_nav or high_nav or START_NAV, high_nav or START_NAV, note


def session_nav_refs(drive_root: Path, events: list[dict], today, nav: float, flat: bool, now: datetime, *,
                     prior: float | None = None, high: float | None = None) -> tuple[dict, bool, str | None]:
    """Today's NAV references, kept by the cycle itself: (document, rolled today, note).

    Nobody has to look these up or type them in any more. The first run of a session sets
    prior_close_nav from the last NAV the previous session's final run saw; with nothing saved and no
    position held, the account is worth exactly what it closed at, so the NAV in hand is used. The
    high-water mark starts at the verified 100,000 and only ever rises, and only from such a close.
    Every recorded run then saves the NAV it saw, which is what tomorrow's first run reads.
    """
    source = _nav_source(drive_root, events)
    as_of = str(source.get("as_of") or "")
    stored_prior, stored_high = _positive(source.get("prior_close_nav")), _positive(source.get("high_water_nav"))
    last_nav = _positive(source.get("last_nav"))
    note = None
    rolled = as_of != today.isoformat() or stored_prior is None
    if not rolled:
        prior_nav, high_nav = stored_prior, stored_high or START_NAV
    else:
        if last_nav is not None and as_of and as_of < today.isoformat():
            prior_nav = last_nav
        elif flat:
            prior_nav = nav
        else:
            prior_nav = stored_prior or START_NAV
            note = ("no closing NAV saved for the last session and a position is held: prior-close NAV "
                    f"taken as {prior_nav:,.2f} for today")
        high_nav = max(stored_high or START_NAV, prior_nav)
    prior_nav, high_nav = _positive(prior) or prior_nav, _positive(high) or high_nav
    return ({"as_of": today.isoformat(), "prior_close_nav": round(prior_nav, 2),
             "high_water_nav": round(high_nav, 2), "last_nav": round(nav, 2), "last_nav_at": now.isoformat()},
            rolled, note)


def contract_from_symbol(symbol: str) -> OptionContract | None:
    """A standard US option's contract read from its own code (US.KO261218C97000)."""
    match = OPTION_SYMBOL.fullmatch(symbol)
    if not match:
        return None
    root, expiry, right, strike = match.groups()
    try:
        return OptionContract(underlying=f"US.{root}", expiry=datetime.strptime(expiry, "%y%m%d").date(),
                              right="call" if right == "C" else "put", strike=int(strike) / 1000)
    except ValueError:
        return None


def _prefixed(symbol: object) -> str:
    text = str(symbol or "")
    return text if "." in text else f"US.{text}"


def known_contracts(watchlist: Watchlist, events: list[dict], positions_payload, order_rows: list[dict]) -> dict:
    """Option metadata for everything the run can meet: held lots and open orders (read from the
    symbol), then the ledger's protected setups and today's watchlist (the researcher's verified block)."""
    contracts: dict[str, OptionContract] = {}
    rows = (positions_payload.get("data") or {}).get("positions") if isinstance(positions_payload, dict) else None
    for item in [*(rows or []), *order_rows]:
        symbol = _prefixed(item.get("symbol") or item.get("code")) if isinstance(item, dict) else ""
        contract = contract_from_symbol(symbol)
        if contract is not None:
            contracts[symbol] = contract
    for symbol, entry in monitor_state(events).protected.items():
        if entry.option:
            contracts[symbol] = entry.option
    contracts.update({e.symbol: e.option for e in watchlist.entries if e.option})
    return contracts


def reads_needed(config, watchlist: Watchlist, events: list[dict], phase: SessionPhase, now: datetime) -> dict:
    """Which symbols the executor has to read before the cycle can decide (`--reads`)."""
    since = now - timedelta(days=5)
    stocks: list[str] = []
    options: list[str] = []

    def add(symbol: str, underlying: str | None = None) -> None:
        for item in (underlying, symbol):
            if not item:
                continue
            bucket = options if contract_from_symbol(item) else stocks
            if item not in bucket:
                bucket.append(item)
    if config.tactical.enabled:
        for entry in watchlist.entries:
            if entry.underlying in config.tactical.symbols:
                add(entry.symbol, entry.underlying)
        for event in events:
            payload = event.get("payload") or {}
            setup = payload.get("protected_setup")
            if event.get("type") != "order.requested" or not isinstance(setup, dict):
                continue
            try:
                recent = datetime.fromisoformat(str(event.get("ts"))) >= since
            except (TypeError, ValueError):
                recent = False
            if recent and setup.get("symbol"):
                add(str(setup["symbol"]), (setup.get("option") or {}).get("underlying"))
    scalp_on = config.scalp.enabled and config.strategy_enabled("PB-004") and phase in RTH
    scalp = list(config.scalp.symbols) if scalp_on else []
    for symbol in scalp:
        add(symbol)
    # Before the open the last-trade price is yesterday's close, so a stock needs its live book too.
    books = [*options, *(stocks if phase == SessionPhase.PRE_MARKET else [])]
    return {"quotes": [*stocks, *options], "books": books, "bars": scalp,
            "bars_note": "1-minute bars, the latest 12 per symbol" if scalp else "none"}


def _load_reads(directory: Path, quotes_expected: bool = True) -> tuple[dict, str | None]:
    quotes = directory / "quotes.json"
    if not quotes_expected and not quotes.is_file():
        # Nothing to price this run (no setup, no lot, scalp not in session): an empty quote list.
        directory.mkdir(parents=True, exist_ok=True)
        quotes.write_text(json.dumps({"ret_code": 0, "data": {"quote_list": []}}), encoding="utf-8")
    missing = [name for name in REQUIRED_READS if not (directory / name).is_file()]
    if missing:
        return {}, f"save these broker reads into {directory} first: {', '.join(missing)}"
    payloads: dict = {}
    for name in REQUIRED_READS:
        try:
            payloads[name] = json.loads((directory / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {}, f"{name} is not valid JSON ({str(exc)[:80]}); save it again"
        if isinstance(payloads[name], dict) and payloads[name].get("ret_code", 0) != 0:
            return {}, (f"the broker answered error {payloads[name].get('ret_code')} for {name}: read it "
                        "again (up to 3 tries, the paper API sometimes fails once) and re-run")
    return payloads, None


_SIDES = {"1": 1, "2": 2, "buy": 1, "sell": 2}


def merged_orders(payload) -> tuple[dict, str | None]:
    """One order-list payload from whatever the read step saved: (payload, note).

    The file may be one page or a JSON list of pages, a row may appear twice after pages are joined,
    and a hand-typed row may carry its side or status as text. None of that is a reason to stop a
    run, so the rows are merged by order id (the later row wins) and the two codes become numbers.
    An unfinished page list (`has_more` true on the last page) is still refused by `broker_orders`.
    """
    pages = payload if isinstance(payload, list) else [payload]
    rows: dict[str, dict] = {}
    listed = 0
    for page in pages:
        if not isinstance(page, dict) or page.get("ret_code", 0) != 0:
            raise ValueError("an order-list page is not a successful broker answer; read it again")
        found = (page.get("data") or {}).get("orders")
        if not isinstance(found, list):
            raise TypeError('broker orders array missing: expected {"data":{"orders":[...]}}')
        for row in found:
            if not isinstance(row, dict):
                raise TypeError("an order row is not an object")
            row = dict(row)
            side = _SIDES.get(str(row.get("side")).strip().lower())
            if side is not None:
                row["side"] = side
            if str(row.get("status")).strip().lstrip("-").isdigit():
                row["status"] = int(str(row["status"]).strip())
            listed += 1
            rows[str(row.get("order_id"))] = row
    more = bool(((pages[-1] if pages else {}).get("pagination") or {}).get("has_more"))
    note = (f"orders.json listed {listed - len(rows)} order(s) twice; each is counted once"
            if listed != len(rows) else None)
    return {"ret_code": 0, "data": {"orders": list(rows.values())}, "pagination": {"has_more": more}}, note


def reconcile_scalp_lots(state: ScalpState, snapshot: AccountSnapshot, rows: list[dict], config,
                         now: datetime, today, skip: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Make the journal's scalp lots agree with what the broker actually holds.

    The broker's positions are the truth. A lot the broker does not hold is closed; a lot of a
    different size is resized; shares of a scalp symbol that no lot explains are sold at once, because
    this lane is flat by the close. A shared ticker the stock lane holds this run (`skip`, see
    tyche.leases) is left alone entirely: its shares are that lane's to manage.
    """
    cfg, alerts = config.scalp, []
    for symbol in [s for s in state.lots if s in skip]:
        state.lots.pop(symbol)
    for symbol in list(state.lots):
        position = snapshot.position(symbol)
        if position is None or position.quantity <= 0:
            state.lots.pop(symbol)
            alerts.append(f"{symbol}: the journal shows an open scalp lot the broker does not hold; treated as closed")
            continue
        working_sell = any(order_symbol(r) == symbol and r.get("side") == 2 and not order_finished(r, today)
                           for r in rows)
        quantity = position.quantity if working_sell else position.sellable
        if quantity <= 0:
            state.lots.pop(symbol)
            alerts.append(f"{symbol}: the broker shows no sellable shares for the scalp lot this run")
        elif quantity != state.lots[symbol].quantity:
            state.lots[symbol] = state.lots[symbol].model_copy(update={"quantity": quantity})
    for position in snapshot.positions:
        if (position.symbol in cfg.symbols and position.symbol not in state.lots and position.symbol not in skip
                and position.quantity > 0):
            cost = position.avg_cost or position.last_price
            if cost <= 0:
                continue
            state.lots[position.symbol] = ScalpLot(
                symbol=position.symbol, quantity=position.sellable or position.quantity, entry=cost,
                stop=cost * (1 - cfg.stop_pct), target=cost * (1 + cfg.target_r * cfg.stop_pct),
                opened_at=now - timedelta(minutes=cfg.timeout_minutes), deadline=now)
            alerts.append(f"{position.symbol}: the broker holds {position.quantity} shares no scalp lot "
                          "explains; selling them now")
    return alerts


def _order_row(payload: dict, note: str = "") -> dict:
    """One order exactly as the executor must send it."""
    reason = str(payload.get("reason") or "")
    return {"symbol": payload["symbol"], "side": payload["side"], "quantity": payload["quantity"],
            "limit_price": payload["limit_price"], "order_type": "LIMIT", "time_in_force": "DAY",
            "remark": payload["request_id"], "submit_before": payload["submit_before"],
            "cancel_first": list(payload.get("cancel_first") or []),
            "lane": payload.get("strategy_id"), "why": (note or reason)[:200]}


def _telegram_line(row: dict) -> str:
    ticker = str(row["symbol"]).removeprefix("US.")
    return f"{row['side'].upper()} {row['quantity']} {ticker} @ {row['limit_price']:g} ({row['lane']}: {row['why'][:70]})"


def run_cycle(*, directory: Path, record: bool, now: datetime, config_root: Path, drive_root: Path = DRIVE_ROOT,
              journal: Path | None = None, book: Path | None = None, account_id: str | None = None,
              prior_close_nav: float | None = None, high_water_nav: float | None = None,
              stock_envelope: Path | None = None, scalp_envelope: Path | None = None,
              reads_only: bool = False) -> dict:
    """Run one cycle and return its report. Journals only with `record`; never contacts a broker."""
    out: dict = {"status": "ok", "as_of": now.isoformat(), "phase": None, "recorded": False,
                 "ledger": None, "watchlist": None, "cancel": [], "submit": [], "alerts": []}

    def stop(status: str, reason: str) -> dict:
        out.update(status=status, reason=reason)
        return out

    config = load_config(config_root)
    phase = phase_at(now)
    today = now.astimezone(ET).date()
    out["phase"] = phase.value
    premarket = phase == SessionPhase.PRE_MARKET
    if phase not in RTH and not premarket:
        return stop("skip", f"market phase is {phase.value}: nothing to trade until the next session")
    stock_envelope = stock_envelope or config_root / "data" / "standing-approval.json"
    scalp_envelope = scalp_envelope or config_root / "data" / "scalp-approvals.json"

    ledger = journal or find_ledger(drive_root)
    if ledger is None or not ledger.is_file():
        return stop("blocked", f"no verified ledger journal under {drive_root}; the Drive mount is missing or empty")
    ok, _, error = verify_chain(ledger)
    if not ok:
        return stop("blocked", f"ledger {ledger} does not verify: {error}")
    out["ledger"] = str(ledger)
    events = read_events(ledger)
    watchlist, book_path, book_notes = find_watchlist(book, directory, drive_root, today)
    out["watchlist"] = book_path
    out["setups"] = [entry.symbol for entry in watchlist.entries]
    out["alerts"].extend(book_notes)
    close = datetime.combine(today, regular_close(today), ET)
    session_exit = close - timedelta(minutes=config.tactical.session_exit_minutes_before_close)
    for entry in watchlist.entries:
        # A stock lot leaves at the session's exit time unless the research names an earlier one, and
        # a review stamped ahead of the clock is a time-zone slip, not research from the future.
        if entry.option is None and entry.exit_at is None:
            entry.exit_at = session_exit
        if entry.reviewed_at is not None and timedelta(0) < entry.reviewed_at - now <= timedelta(hours=24):
            entry.reviewed_at = now
            out["alerts"].append(f"{entry.symbol}: reviewed_at was ahead of the clock (time-zone slip); taken as now")

    if reads_only:
        out["reads"] = reads_needed(config, watchlist, events, phase, now)
        out["next"] = ("Read the account, cash, positions and today's orders, one quote call for every "
                       "symbol under reads.quotes, an order book for each symbol under reads.books and "
                       "1-minute bars for each symbol under reads.bars; save them into the run folder; "
                       "then run `tyche cycle --dir <run> --record`.")
        return out

    payloads, problem = _load_reads(directory, bool(reads_needed(config, watchlist, events, phase, now)["quotes"]))
    if problem:
        return stop("blocked", problem)
    account_id = account_id or next(
        (item.strip() for item in os.environ.get("TYCHE_ALLOWED_ACCOUNT_IDS", "").split(",") if item.strip()), None)
    if not account_id:
        return stop("blocked", "TYCHE_ALLOWED_ACCOUNT_IDS is not set for this run: the paper account is unknown")
    try:
        orders_payload, orders_note = merged_orders(payloads["orders.json"])
        rows = broker_orders(orders_payload)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return stop("blocked", f"orders.json unusable: {exc}")
    if orders_note:
        out["alerts"].append(orders_note)
    for row in rows:
        lacking = [key for key in ORDER_ROW_FIELDS if row.get(key) is None]
        if lacking:
            return stop("blocked", f"orders.json row {row.get('order_id')} lacks {', '.join(lacking)}; "
                                   "save each order with " + ", ".join(ORDER_ROW_FIELDS) + ", text and update_time")
    prior, high, _ = find_nav_refs(prior_close_nav, high_water_nav, drive_root, events)
    contracts = known_contracts(watchlist, events, payloads["positions.json"], rows)
    problems: list[str] = []
    try:
        capture_dir(directory, account_id, prior, high,
                    synthetic_spread_pct=config.tactical.synthetic_spread_pct,
                    contracts=contracts, problems=problems)
        snapshot = verified_paper(AccountSnapshot.model_validate_json(
            (directory / "tactical-account.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        text = str(exc).replace(account_id, "<account>")
        if isinstance(exc, KeyError):
            text = f"a saved read lacks the field {text}; save that read again in the shape the brief lists"
        hint = (" (accounts.json must keep the paper account's own row with account_id, account_type and "
                "market_id)" if "paper account" in text else "")
        return stop("blocked", f"broker reads unusable: {text[:300]}{hint}")
    # The one hard rule, checked before anything can be reserved: the allowlisted paper account only.
    if snapshot.env != "paper" or snapshot.account_id not in config.risk.account_allowlist:
        return stop("blocked", "paper account verification failed: this is not the allowlisted paper account")
    out["alerts"].extend(problems)
    nav_refs, nav_rolled, nav_note = session_nav_refs(
        drive_root, events, today, snapshot.nav, not snapshot.positions, now,
        prior=prior_close_nav, high=high_water_nav)
    if nav_note:
        out["alerts"].append(nav_note)
    prior, high = nav_refs["prior_close_nav"], nav_refs["high_water_nav"]
    snapshot = snapshot.model_copy(update={"prior_close_nav": prior, "high_water_nav": high,
                                           "captured_at": _not_ahead(snapshot.captured_at, now)})
    # snapshot.json is what the publish step and the desk page read a run's NAV from.
    for name in ("tactical-account.json", "snapshot.json"):
        (directory / name).write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    quotes = [MarketQuote.model_validate(row) for row in json.loads(
        (directory / "tactical-quotes.json").read_text(encoding="utf-8"))]
    quotes = [q.model_copy(update={"at": _not_ahead(q.at, now), "book_at": _not_ahead(q.book_at, now)})
              for q in quotes]
    quote_map = {q.symbol: q for q in quotes}
    contracts.update({q.symbol: q.option for q in quotes if q.option})
    halted = bool(effective_halt(ledger.parent, config_root).get("halted"))
    if halted:
        out["alerts"].append("kill-switch is on: no buys this run; exits still go out")
    out["account"] = {"nav": round(snapshot.nav, 2), "cash": round(snapshot.cash, 2),
                      "positions": [{"symbol": p.symbol, "quantity": p.quantity} for p in snapshot.positions],
                      "prior_close_nav": prior, "high_water_nav": high}

    def journal_step() -> None:
        nonlocal events

        def append(kind: str, payload: dict) -> None:
            if record:
                events.append(append_locked(ledger, kind, payload))
            else:
                events.append({"ts": now.isoformat(), "type": kind, "payload": payload})

        if record and nav_rolled:
            append("nav.refs_updated", {**nav_refs, "source": "tyche cycle: first run of the session"})
        # 1. Heal forks, then let the broker's own order list write the receipts nobody typed in.
        merged = missing_order_events(events, drive_root, ledger, now)
        for kind, payload in merged:
            append(kind, payload)
        if merged:
            out["alerts"].append(f"{len(merged)} order event(s) from another run's journal copy merged into the ledger")
        receipts, receipt_alerts = receipts_to_journal(events, rows, today)
        for kind, payload in receipts:
            append(kind, payload)
        out["alerts"].extend(receipt_alerts)
        out["journaled_receipts"] = [
            f"{kind} {payload['symbol']} {payload['side']}"
            + (f" {payload['quantity']:g}" if payload.get("quantity") is not None else "")
            for kind, payload in receipts]
        fills = [p for kind, p in receipts if kind == "order.filled"]
        # A reservation whose window closed with no broker order was never sent. Say so once, loudly:
        # this is how the operator learns that the orders the command lists are not being placed.
        told = {(e.get("payload") or {}).get("request_id") for e in events if e.get("type") == "order.unsent"}
        dead = dead_request_ids(events, rows, now) - told
        unsent = []
        for event in list(events):
            payload = event.get("payload") or {}
            if event.get("type") != "order.requested" or payload.get("request_id") not in dead:
                continue
            try:
                listed = datetime.fromisoformat(str(event.get("ts")))
            except ValueError:
                continue
            if listed.tzinfo is not None and listed.astimezone(ET).date() == today:
                unsent.append((listed, payload))
        for listed, payload in unsent:
            append("order.unsent", {key: payload.get(key) for key in (
                "request_id", "symbol", "side", "quantity", "limit_price", "strategy_id")}
                | {"listed_at": listed.isoformat()})
        if unsent:
            names = ", ".join(f"{p.get('side')} {p.get('quantity')} {str(p.get('symbol')).removeprefix('US.')} "
                              f"(listed {listed.astimezone(ET):%H:%M} ET)" for listed, p in unsent[:6])
            out["alerts"].append(f"URGENT: {len(unsent)} order(s) the command listed never reached the broker: "
                                 f"{names}. Each is free to be listed again; check that the executor places "
                                 "what it is given.")
        cancel_ids: set[str] = set()
        sells: list[dict] = []
        buys: list[dict] = []

        # Shared tickers (2026-11-25): a ticker both lanes may trade is held by one lane per run.
        scalp_cfg = config.scalp
        scalp_book = scalp_state(events, today, scalp_cfg.timeout_minutes, stop_pct=scalp_cfg.stop_pct,
                                 target_r=scalp_cfg.target_r, never_sent=dead_request_ids(events, rows, now))
        leases, lease_alerts = ticker_leases(
            shared_symbols(config), events=events, rows=rows, snapshot=snapshot, scalp_lots=set(scalp_book.lots),
            stock_setups={e.symbol for e in watchlist.entries if e.option is None}, today=today, now=now)
        out["alerts"].extend(lease_alerts)
        if leases:
            out["shared_tickers"] = dict(leases)
        scalp_skip = {symbol for symbol, lane in leases.items() if lane == STOCK}
        stock_skip = {symbol: "shared ticker held or worked by the PB-004 scalp this run"
                      for symbol, lane in leases.items() if lane == SCALP}

        # 2. PB-004 scalp: exits first, then breakout entries (regular session only).
        scalp_report: dict = {"decisions": [], "orders": [], "alerts": []}
        if config.scalp.enabled and config.strategy_enabled("PB-004") and not premarket:
            cfg = config.scalp
            state = scalp_book
            out["alerts"].extend(reconcile_scalp_lots(state, snapshot, rows, config, now, today, skip=scalp_skip))
            bars = {}
            for symbol in cfg.symbols:
                path = directory / f"bars-{symbol}.json"
                if not path.is_file():
                    continue
                try:
                    series = bars_from_kline(json.loads(path.read_text(encoding="utf-8")))
                    series[-1] = series[-1].model_copy(update={"at": _not_ahead(series[-1].at, now)})
                    bars[symbol] = series
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    out["alerts"].append(f"{symbol}: 1-minute bars unusable ({str(exc)[:60]})")
            count, turnover = combined_usage(events, rows, today, contracts)
            scalp_report = plan_scalp(quote_map, bars, state, snapshot, config, now, orders_today=count,
                                      traded_notional_today=turnover, halted=halted, skip=scalp_skip)
            entering = {o["intent"]["symbol"] for o in scalp_report["orders"]
                        if o["intent"].get("side") == "buy" and o["intent"].get("symbol") in leases}
            if record and scalp_report["orders"]:
                batch, mode, how = resolve_batch(scalp_envelope, events, today)
                armed = arm_scalp_locked(scalp_report["orders"], batch=batch, mode=mode, how=how, journal=ledger,
                                         today=today, now=now, rows=rows, config=config,
                                         held={p.symbol: p.quantity for p in snapshot.positions})
                events = read_events(ledger)
                for item in armed:
                    if "request" in item:
                        row = _order_row(item["request"])
                        (sells if row["side"] == "sell" else buys).append(row)
                        cancel_ids.update(row["cancel_first"])
                    else:
                        if item.get("side") == "buy":
                            entering.discard(item.get("symbol"))  # refused: the ticker stays free this run
                        out["alerts"].append(f"{item['symbol']} scalp {item['side']} not sent: "
                                             f"{item.get('skipped') or item.get('denied')}")
            for symbol in entering:
                # The scalp plans first, so a free shared ticker it enters is its own for this run.
                stock_skip[symbol] = "shared ticker the PB-004 scalp enters this run"
            # An entry still unfilled after its time-to-live is pulled so the symbol is free again.
            for row in rows:
                created = _created(row)
                if (str(row.get("text") or "").startswith(SCALP_PREFIX) and row.get("side") == 1
                        and not order_finished(row, today) and created is not None
                        and (now - created).total_seconds() >= cfg.entry_ttl_seconds):
                    out["cancel"].append({"order_id": str(row["order_id"]), "symbol": order_symbol(row),
                                          "why": "scalp entry still unfilled after "
                                                 f"{int((now - created).total_seconds() // 60)} minutes"})
            flatten = close - timedelta(minutes=cfg.flatten_minutes_before_close)
            open_lots = sorted(state.lots)
            if now >= flatten and open_lots:
                out["alerts"].append("URGENT: scalp lot(s) still open at the flatten time: " + ", ".join(open_lots))
        out["scalp"] = {"decisions": scalp_report["decisions"], "alerts": scalp_report["alerts"]}

        # 3. PB-002 stocks and PB-003 options: protection first, then entries from today's watchlist.
        tactical_report: dict = {"decisions": [], "orders": [], "alerts": []}
        if config.tactical.enabled:
            state = monitor_state(events)
            if state.last_tick and state.last_tick > now:
                state.last_tick = None  # another container's clock ran ahead; start the heartbeat again
            batch, mode, how = resolve_batch(stock_envelope, events, today)
            if batch is not None:
                # A lot is sized to fit the operator's line instead of being refused for exceeding it:
                # the kernel alone would size a 20%-of-NAV lot the 10% line then turns away whole.
                for entry in watchlist.entries:
                    line = batch.line_for(entry.symbol, "buy", multiplier=100 if entry.option else 1,
                                          underlying=entry.underlying)
                    if line is not None and line.max_qty and (entry.max_quantity or line.max_qty + 1) > line.max_qty:
                        entry.max_quantity = line.max_qty
            tactical_report = plan_tick(watchlist, snapshot, quotes, pending_intents(rows, contracts), rows,
                                        events, state, config, now, halted=halted, skip=stock_skip)
            if record:
                append("tactical.monitor", {"state": state.model_dump(mode="json"),
                                            "alerts": tactical_report["alerts"]})
            for proposal in tactical_report["orders"]:
                intent = proposal["intent"]
                label = f"{intent['symbol']} {intent['side']} {intent['quantity']} @ {intent['limit_price']}"
                if not config.tactical.execution_enabled:
                    out["alerts"].append(f"{label} not sent: execution_enabled is false in config/tactical.yaml")
                    continue
                try:
                    payload, _ = authorize_tactical(
                        proposal, batch=batch, mode=mode, how=how, events=events, journal=ledger, today=today,
                        now=now, snapshot=snapshot, state=state, watchlist=watchlist, config=config, halted=halted)
                except (ValueError, StopIteration) as exc:
                    out["alerts"].append(f"{label} not sent: {str(exc) or 'no plan on file for this symbol'}")
                    continue
                if record:
                    append("order.requested", payload)
                resting = payload.get("resting") or {}
                note = ""
                if resting.get("kind") == "entry":
                    note = f"resting buy at the plan's price; {resting.get('limit_basis', '')}"
                elif resting.get("kind") == "take_profit":
                    note = f"take-profit resting at the target; {resting.get('limit_basis', '')}"
                row = _order_row(payload, note)
                (sells if row["side"] == "sell" else buys).append(row)
                cancel_ids.update(row["cancel_first"])
            # A stock lot leaves before the close, so a buy still resting when the last check before
            # that exit time runs is pulled: it must not fill after its own exit has gone.
            if not premarket and now + timedelta(seconds=config.tactical.monitor_interval_seconds) >= session_exit:
                for row in rows:
                    if (str(row.get("text") or "").startswith(TACTICAL_PREFIX) and row.get("side") == 1
                            and not order_finished(row, today)):
                        out["cancel"].append({"order_id": str(row["order_id"]), "symbol": order_symbol(row),
                                              "why": "resting buy pulled before the session's exit time"})
            for alert in tactical_report["alerts"]:
                if "heartbeat gap" in alert and config.tactical.max_confirmation_ticks == 1:
                    continue  # nothing to rebuild when one quote confirms a setup
                urgent = "protection quote unavailable" in alert or "unprotected" in alert
                out["alerts"].append(("URGENT: " if urgent else "") + alert)
        out["stocks"] = {"decisions": tactical_report["decisions"]}

        out["cancel"] = [c for c in {c["order_id"]: c for c in out["cancel"]}.values()
                         if c["order_id"] not in cancel_ids]
        if record:
            # Sells first: an exit never waits behind an entry.
            out["submit"] = [{"n": index, **row} for index, row in enumerate([*sells, *buys], start=1)]
        else:
            out["preview"] = ([{"lane": "PB-004", **o["intent"]} for o in scalp_report["orders"]]
                              + [{"lane": o["intent"].get("strategy_id"), **o["intent"]} for o in tactical_report["orders"]])
        out["fills_seen"] = [f"{p['side']} {p['quantity']:g} {p['symbol']} @ {p['price']}" for p in fills]

    try:
        if record:
            with journal_lock(ledger):
                events = read_events(ledger)
                journal_step()
                _register_freeze(config_root, ledger, events, out)
        else:
            journal_step()
    except RuntimeError as exc:
        return stop("blocked", f"{exc}: another run is writing the ledger; nothing was reserved")
    except (ValueError, KeyError, TypeError) as exc:
        text = str(exc).replace(account_id, "<account>")
        return stop("blocked", f"cycle could not finish: {text[:300]}")
    out["recorded"] = record
    if record:
        try:
            (drive_root / NAV_REFS_FILE).write_text(json.dumps(nav_refs, indent=2), encoding="utf-8")
        except OSError as exc:
            out["alerts"].append(f"NAV references not saved ({str(exc)[:80]}); the journal still holds today's")
    lines = [_telegram_line(row) for row in out["submit"]]
    if lines or out["fills_seen"]:
        clock = now.astimezone(ET).strftime("%H:%M ET")
        head = f"TYCHE {clock} (paper): {len(lines)} order(s) sent" if lines else f"TYCHE {clock} (paper)"
        out["telegram"] = "\n".join([head, *lines, *(f"FILLED {text}" for text in out["fills_seen"])])
    urgent = [a for a in out["alerts"] if a.startswith("URGENT")]
    if urgent:
        out["telegram_urgent"] = "TYCHE URGENT (paper): " + "; ".join(a.removeprefix("URGENT: ") for a in urgent)
    out["instructions"] = _instructions(out, record)
    return out


def _created(row: dict) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(row.get("create_time")) / 1_000_000, UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _instructions(out: dict, record: bool) -> str:
    if not record:
        return "Dry run: nothing was reserved and nothing may be submitted. Run again with --record to trade."
    if not out["cancel"] and not out["submit"]:
        return "Nothing to cancel or submit this run. Do not place any order."
    return ("1) Cancel every order under `cancel`. 2) Then for each item under `submit`, in order: cancel its "
            "`cancel_first` order ids if it lists any (if a cancel fails, skip that item), then place ONE paper "
            "LIMIT order with exactly its symbol, side, quantity and limit_price, time in force DAY and the "
            "`remark` as the order's remark, before its `submit_before`. Never retry a submit, never change a "
            "field, never place anything not listed. The next run reads the receipts and fills from the "
            "broker's order list by itself: no record-order step is needed.")


def _register_freeze(config_root: Path, ledger: Path, events: list[dict], out: dict) -> None:
    """Put a changed lane's rules hash on the ledger so a merged config change needs no extra step.

    Best effort and never a brake: a lane whose playbook document disagrees with the bytes is left
    for the operator (`tyche rules-freeze` refuses it too) and only named in the alerts.
    """
    try:
        from tyche.freeze import lane_states, registration_events
        states, _ = lane_states(config_root, events)
        refused = [s.strategy_id for s in states if s.blocked]
        if refused:
            out["alerts"].append("rules freeze: playbook document disagrees with the config for "
                                 + ", ".join(refused) + " (not registered; trading is not affected)")
            return
        rows = registration_events(states, FREEZE_REASON)
        for kind, payload in rows:
            append_locked(ledger, kind, {**payload, "ledger": "ledger", "recorded_by": "tyche cycle"})
        if rows:
            out["rules_registered"] = [payload["strategy"] for _, payload in rows]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out["alerts"].append(f"rules freeze not registered ({str(exc)[:80]}); trading is not affected")


def cycle_command(
    directory: Path = typer.Option(..., "--dir", help="Run folder holding the saved broker reads."),
    record: bool = typer.Option(False, "--record", help="Reserve and journal the orders. Without it: a dry run."),
    reads: bool = typer.Option(False, "--reads", help="Only print which symbols to read, then stop."),
    drive_root: Path = typer.Option(DRIVE_ROOT, "--drive-root"),
    journal: Path | None = typer.Option(None, "--journal", help="Ledger journal; default: the longest verified chain on Drive."),
    book: Path | None = typer.Option(None, "--book", help="Watchlist; default: today's on Drive."),
    account_id: str | None = typer.Option(None, "--account-id", help="Default: TYCHE_ALLOWED_ACCOUNT_IDS."),
    prior_close_nav: float | None = typer.Option(None, "--prior-close-nav"),
    high_water_nav: float | None = typer.Option(None, "--high-water-nav"),
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    at: str = typer.Option("", "--at", help="Replay clock (ISO, with timezone). Never with --record."),
) -> None:
    """One command for a whole trading run: saved broker reads in, the orders to send out.

    Step 1: `tyche cycle --dir <run> --reads` prints the symbols to read. Step 2: save the reads as
    accounts.json, cash.json, positions.json, orders.json, quotes.json, book-<US.SYMBOL>.json and
    bars-<US.SYMBOL>.json in <run>. Step 3: `tyche cycle --dir <run> --record` prints `cancel` and
    `submit`. Exit 0: done (status ok or skip). Exit 1: status blocked, with the reason to fix.
    """
    earlier = _already_recorded(directory) if record else None
    if earlier is not None:
        # An agent that runs the same step twice must get the same list, never an empty one: the first
        # run's orders are reserved in the ledger and a second pass would see them as already on the way.
        earlier["already_recorded"] = True
        earlier["instructions"] = ("This run folder was already recorded: this is the SAME answer again and "
                                   "nothing new was reserved. Send only the items you have not sent yet. "
                                   + str(earlier.get("instructions") or ""))
        sys.stdout.write(json.dumps(earlier, indent=2, ensure_ascii=True, default=str) + "\n")
        raise typer.Exit(0)
    try:
        if at and record:
            raise ValueError("a replay clock cannot record")
        now = datetime.fromisoformat(at) if at else now_utc()
        if now.tzinfo is None:
            raise ValueError("--at needs a timezone")
        report = run_cycle(directory=directory, record=record, now=now, config_root=config_root,
                           drive_root=drive_root, journal=journal, book=book, account_id=account_id,
                           prior_close_nav=prior_close_nav, high_water_nav=high_water_nav, reads_only=reads)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        report = {"status": "blocked", "reason": str(exc)[:400], "cancel": [], "submit": []}
    if report.get("status") == "blocked" and not at:
        alert = blocked_alert(drive_root, str(report.get("reason") or ""), now_utc())
        if alert:
            report["telegram_urgent"] = alert
        report["instructions"] = ("Blocked: place no order. `reason` names the fix. Do it once and run the same "
                                  "command again; if it is still blocked, send telegram-urgent.txt if this run "
                                  "folder has one, and end the run.")
    text = json.dumps(report, indent=2, ensure_ascii=True, default=str)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if not reads:
            (directory / "cycle.json").write_text(text, encoding="utf-8")
        # The two messages as files, so the run sends them with `"$(cat <file>)"` and retypes nothing.
        # A message the latest answer no longer carries is removed, so a fixed problem is not announced.
        for key, name in (("telegram", "telegram.txt"), ("telegram_urgent", "telegram-urgent.txt")):
            if report.get(key):
                (directory / name).write_text(str(report[key]), encoding="utf-8")
            elif not reads:
                (directory / name).unlink(missing_ok=True)
    except OSError:
        pass
    sys.stdout.write(text + "\n")
    raise typer.Exit(1 if report.get("status") == "blocked" else 0)


def _already_recorded(directory: Path) -> dict | None:
    """The stored answer of a run folder whose orders were already reserved, else None."""
    try:
        report = json.loads((directory / "cycle.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    done = isinstance(report, dict) and report.get("recorded") is True and report.get("status") == "ok"
    return report if done else None


def blocked_alert(drive_root: Path, reason: str, now: datetime) -> str | None:
    """The line to send when a run is blocked: once an hour per reason, not every 15 minutes all night."""
    path = drive_root / "cycle-blocked.json"
    key = reason[:80]
    try:
        last = json.loads(path.read_text(encoding="utf-8"))
        recent = last.get("reason") == key and 0 <= (now - datetime.fromisoformat(last["at"])).total_seconds() < 3600
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        recent = False
    if recent:
        return None
    try:
        path.write_text(json.dumps({"reason": key, "at": now.isoformat()}), encoding="utf-8")
    except OSError:
        pass
    return f"TYCHE BLOCKED (paper), no orders this run: {reason[:300]}"
