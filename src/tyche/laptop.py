"""Laptop runner (2026-11-25): THE CYCLE every 15 minutes on the operator's laptop, with no AI.

The cloud cards run `tyche cycle` through two agents, and every run spends Qoder credit. The
decisions were never the agents': they live in the kernel. Here plain code does the agents' two
remaining jobs. It reads the paper account through the official moomoo CLI and sends exactly the
orders `tyche cycle --record` lists, one attempt each, so a run costs nothing and takes seconds.

The record (ledger) is the laptop's own, under runs/laptop/ (git-ignored). The broker is the referee:
every run starts from what moomoo shows, so a fresh record picks up orders and shares another record
placed (a resting buy is not doubled; its fill is managed by the day's setup). Only one record may
trade the account at a time: pause both cloud cards before the first laptop run.

The one hard rule is kept twice. The cycle refuses any account but the allowlisted paper one, and
this module only calls the CLI's `sim` commands, for that same account. It never places an order
the cycle did not list, never changes a listed field and never retries a submit.

    .venv\\Scripts\\python.exe -m tyche.cli laptop --check     read-only: CLI, sign-in, account, reads
    .venv\\Scripts\\python.exe -m tyche.cli laptop --once      one cycle now (sends what it lists)
    .venv\\Scripts\\python.exe -m tyche.cli laptop             every 15 minutes, 09:07 to 15:52 ET
"""
# ruff: noqa: B008 -- Typer's declarative command option defaults.
from __future__ import annotations

import json
import os
import subprocess
import sys
import time as clock
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import typer

from tyche.broker.moomoo_cli import MoomooCli, MoomooCliError, _walk, extract_order_id
from tyche.journal import append_event, verify_chain
from tyche.market_calendar import ET

MARKET = "US"
FIRST_SLOT, LAST_SLOT, PREMARKET_SLOT = time(9, 7), time(15, 52), time(8, 5)
SLOT_STEP = timedelta(minutes=15)
READ_TRIES = 3
# The moomoo CLI's K-line type for 1-minute bars (2 is daily, as `tyche fetch` uses).
KTYPE_1M = os.environ.get("TYCHE_MOOMOO_KTYPE_1M", "1")


def load_dotenv(repo: Path) -> None:
    """The gitignored .env fills what the shell did not set; nothing is printed."""
    path = repo / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def paper_account() -> str:
    ids = [item.strip() for item in os.environ.get("TYCHE_ALLOWED_ACCOUNT_IDS", "").split(",") if item.strip()]
    if not ids:
        raise RuntimeError("TYCHE_ALLOWED_ACCOUNT_IDS is not set in .env: the paper account is unknown")
    return ids[0]


def mask(text: str, account: str) -> str:
    return text.replace(account, "<account>") if account else text


# --- schedule ---------------------------------------------------------------------------------------

def slots(day: date, *, premarket: bool = False) -> list[datetime]:
    """The 15-minute card's clock: minutes 07, 22, 37 and 52 from 09:07 to 15:52 ET (and 08:05 ET)."""
    out = [datetime.combine(day, PREMARKET_SLOT, ET)] if premarket else []
    at, end = datetime.combine(day, FIRST_SLOT, ET), datetime.combine(day, LAST_SLOT, ET)
    while at <= end:
        out.append(at)
        at += SLOT_STEP
    return out


def next_slot(now: datetime, *, premarket: bool = False) -> datetime:
    day = now.astimezone(ET).date()
    for offset in range(8):
        for slot in slots(day + timedelta(days=offset), premarket=premarket):
            if slot > now:
                return slot
    raise RuntimeError("no slot in the next week")


# --- reads: the CLI's answers in the shapes the cycle reads -------------------------------------------

def _ok(payload: Any) -> bool:
    return not (isinstance(payload, dict) and payload.get("ret_code", 0) not in (0, "0"))


def _rows(payload: Any, *keys: str) -> list[dict] | None:
    """The list under data.<key> (or the payload itself, or the longest list of objects in it)."""
    if isinstance(payload, list) and all(isinstance(r, dict) for r in payload):
        return payload
    data = payload.get("data") if isinstance(payload, dict) else None
    for key in keys:
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return data[key]
        if isinstance(payload, dict) and isinstance(payload.get(key), list):
            return payload[key]
    if isinstance(data, list) and all(isinstance(r, dict) for r in data):
        return data
    found = [node for node in _walk(payload) if isinstance(node, list) and node
             and all(isinstance(r, dict) for r in node)]
    return max(found, key=len) if found else None


def _rename(row: dict, aliases: dict[str, tuple[str, ...]]) -> dict:
    row = dict(row)
    for field, names in aliases.items():
        if row.get(field) is None:
            for name in names:
                if row.get(name) is not None:
                    row[field] = row[name]
                    break
    return row


ACCOUNT_ALIASES = {"account_id": ("acc_id", "accID", "id"), "account_type": ("acc_type", "accType"),
                   "market_id": ("market", "trd_market", "marketId")}
POSITION_ALIASES = {"symbol": ("code", "stock_code"), "qty": ("quantity", "position_qty"),
                    "qty_avbl": ("can_sell_qty", "sellable_qty", "available_qty"),
                    "cost_price": ("average_cost", "avg_cost", "cost_price_valid"),
                    "cur_price": ("nominal_price", "last_price", "price")}
ORDER_ALIASES = {"order_id": ("id", "orderId", "order_id_ex"), "symbol": ("code", "stock_code"),
                 "side": ("trd_side", "trdSide"), "qty": ("quantity",), "cum_qty": ("dealt_qty", "filled_qty"),
                 "avg_fill_price": ("dealt_avg_price", "fill_price"), "status": ("order_status",),
                 "create_time": ("created_at", "create_timestamp"), "update_time": ("updated_time", "updated_at"),
                 "text": ("remark",)}


def as_accounts(payload: Any) -> dict:
    rows = _rows(payload, "accounts", "account_list", "acc_list") or []
    return {"ret_code": 0, "data": {"accounts": [_rename(r, ACCOUNT_ALIASES) for r in rows]}}


def as_cash(payload: Any) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return {"ret_code": 0, "data": payload["data"]}
    rows = _rows(payload, "funds", "funds_list")
    return {"ret_code": 0, "data": rows[0] if rows else payload}


def as_positions(payload: Any) -> dict:
    rows = _rows(payload, "positions", "position_list", "positions_list")
    if rows is None:
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            rows = []  # an answer with nothing held
        else:
            raise ValueError("the CLI's position answer has no position list")
    out = []
    for row in rows:
        row = _rename(row, POSITION_ALIASES)
        row.setdefault("pstn_type", 0)
        out.append(row)
    return {"ret_code": 0, "data": {"positions": out}}


def _micros(value: Any) -> Any:
    """Order times in microseconds since the epoch, as the paper API gives them."""
    text = str(value or "").strip()
    if text.isdigit():
        return {10: int(text) * 1_000_000, 13: int(text) * 1000}.get(len(text), int(text))
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ET)  # moomoo states US order times in New York time
    return int(moment.timestamp() * 1_000_000)


def as_orders(*payloads: Any) -> dict:
    """Open orders and order history joined by order id (the later answer wins)."""
    rows: dict[str, dict] = {}
    for payload in payloads:
        for row in _rows(payload, "orders", "order_list") or []:
            row = _rename(row, ORDER_ALIASES)
            for key in ("create_time", "update_time"):
                if row.get(key) is not None:
                    row[key] = _micros(row[key])
            row.setdefault("text", "")
            row.setdefault("update_time", row.get("create_time"))
            rows[str(row.get("order_id"))] = row
    return {"ret_code": 0, "data": {"orders": list(rows.values())}, "pagination": {"has_more": False}}


def _millis(value: Any) -> int | None:
    text = str(value or "").strip()
    if text.replace(".", "", 1).isdigit():
        number = float(text)
        return int(number * 1000) if number < 1e11 else int(number)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ET)  # moomoo states US quote and bar times in New York time
    return int(moment.timestamp() * 1000)


def as_quotes(payload: Any) -> dict:
    rows = _rows(payload, "quote_list", "quotes", "list") or []
    out = []
    for row in rows:
        row = _rename(row, {"code": ("symbol",), "last_price": ("price", "cur_price"),
                            "data_time": ("update_time", "time", "timestamp")})
        if row.get("data_time") is not None:
            row["data_time"] = _millis(row["data_time"])
        if row.get("code") and "." not in str(row["code"]):
            row["code"] = f"{MARKET}.{row['code']}"
        out.append(row)
    return {"ret_code": 0, "data": {"quote_list": out}}


def as_bars(payload: Any) -> dict:
    rows = _rows(payload, "kline_list", "klines", "list") or []
    out = []
    for row in rows:
        row = _rename(row, {"time_key": ("time", "timestamp", "k_time"), "open_price": ("open",),
                            "high_price": ("high",), "low_price": ("low",), "close_price": ("close",)})
        stamp = _millis(row.get("time_key"))
        if stamp is None:
            continue
        out.append({"time_key": stamp, "open_price": row.get("open_price"), "high_price": row.get("high_price"),
                    "low_price": row.get("low_price"), "close_price": row.get("close_price")})
    return {"ret_code": 0, "data": {"kline_list": out}}


class Broker:
    """The paper account through the moomoo CLI: reads, and the two order commands. `sim` only."""

    def __init__(self, cli: MoomooCli, account: str) -> None:
        self.cli = cli
        self.account = account

    def _read(self, call) -> Any:
        last: Exception | None = None
        for attempt in range(READ_TRIES):
            try:
                answer = call()
                if _ok(answer):
                    return answer
                last = MoomooCliError(f"error code {answer.get('ret_code')}")
            except MoomooCliError as exc:
                last = exc
            clock.sleep(1.5 * (attempt + 1))
        raise MoomooCliError(mask(str(last), self.account))

    def save_reads(self, run: Path, reads: dict) -> list[str]:
        """Write the run's broker reads; returns what could not be read (the cycle then says what to fix)."""
        run.mkdir(parents=True, exist_ok=True)
        notes: list[str] = []

        def save(name: str, payload: dict) -> None:
            (run / name).write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")

        save("accounts.json", as_accounts(self._read(self.cli.sim_accounts)))
        save("cash.json", as_cash(self._read(lambda: self.cli.sim_funds(self.account))))
        save("positions.json", as_positions(self._read(lambda: self.cli.sim_positions(self.account, MARKET))))
        open_orders = self._read(lambda: self.cli.sim_order_list(self.account, MARKET))
        history = self._read(lambda: self.cli.sim_order_history(self.account, MARKET))
        save("orders.json", as_orders(history, open_orders))
        codes = list(reads.get("quotes") or [])
        if codes:
            save("quotes.json", as_quotes(self._read(lambda: self.cli.quote(codes))))
        for code in reads.get("bars") or []:
            try:
                answer = self._read(lambda code=code: self.cli._json(
                    ["kline", code, "--ktype", KTYPE_1M, "--num", "12", "--format", "json"]))
                save(f"bars-{code}.json", as_bars(answer))
            except MoomooCliError as exc:
                notes.append(f"{code}: 1-minute bars not read ({str(exc)[:80]})")
        if reads.get("books"):
            notes.append("order books are not read on the laptop; stocks are priced from their quotes")
        return notes

    def cancel(self, order_id: str) -> tuple[bool, str]:
        try:
            answer = self.cli.sim_order_cancel(str(order_id), self.account, MARKET)
        except MoomooCliError as exc:
            return False, mask(str(exc), self.account)[:200]
        return _ok(answer), "" if _ok(answer) else f"error code {answer.get('ret_code')}"

    def place(self, item: dict) -> tuple[bool, str, str | None]:
        """ONE paper limit order exactly as listed. Never a retry, never a changed field."""
        if item.get("order_type") != "LIMIT" or item.get("side") not in ("buy", "sell"):
            return False, "not a listed limit buy or sell", None
        send = self.cli.sim_order_buy if item["side"] == "buy" else self.cli.sim_order_sell
        try:
            answer = send(str(item["symbol"]), int(item["quantity"]), self.account, float(item["limit_price"]),
                          MARKET, remark=str(item["remark"]))
        except MoomooCliError as exc:
            return False, mask(str(exc), self.account)[:200], None
        if not _ok(answer):
            return False, f"broker error code {answer.get('ret_code')}", None
        return True, "", extract_order_id(answer)


def send_listed(broker: Broker, report: dict, now_fn=lambda: datetime.now(UTC)) -> list[dict]:
    """THE CYCLE step 4: cancel `cancel`, then each `submit` item in order after its `cancel_first`."""
    results: list[dict] = []
    for item in report.get("cancel") or []:
        ok, why = broker.cancel(str(item["order_id"]))
        results.append({"action": "cancel", "order_id": str(item["order_id"]), "symbol": item.get("symbol"),
                        "done": ok, "why": why})
    for item in report.get("submit") or []:
        row = {"action": "submit", "symbol": item["symbol"], "side": item["side"], "quantity": item["quantity"],
               "limit_price": item["limit_price"], "remark": item["remark"], "done": False, "why": ""}
        results.append(row)
        try:
            deadline = datetime.fromisoformat(str(item["submit_before"]))
        except ValueError:
            row["why"] = "submit_before unreadable"
            continue
        if now_fn() >= deadline:
            row["why"] = "its submit_before passed"
            continue
        refused = next((oid for oid in item.get("cancel_first") or [] if not broker.cancel(str(oid))[0]), None)
        if refused is not None:
            row["why"] = f"cancel of order {refused} failed first"
            continue
        row["done"], row["why"], row["order_id"] = broker.place(item)
    return results


# --- one run ------------------------------------------------------------------------------------------

class Runner:
    def __init__(self, repo: Path, cli: MoomooCli, *, drive: Path | None = None, python: str | None = None,
                 pull: bool = True, telegram: bool = True) -> None:
        self.repo = repo
        self.drive = drive or repo / "runs" / "laptop"
        self.journal = self.drive / "ledger" / "journal" / "events.jsonl"
        self.python = python or sys.executable
        self.cli = cli
        self.pull = pull
        self.telegram = telegram

    def log(self, text: str) -> None:
        stamp = datetime.now(UTC).astimezone(ET).strftime("%a %H:%M:%S ET")
        line = f"{stamp}  {text}"
        print(line, flush=True)
        try:
            self.drive.mkdir(parents=True, exist_ok=True)
            with (self.drive / "runner.log").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    def ensure_ledger(self) -> None:
        if not self.journal.is_file():
            append_event(self.journal, "run.started", {"run": "laptop ledger opened",
                                                       "note": "the broker is the referee; see tyche.laptop"})
        ok, _, error = verify_chain(self.journal)
        if not ok:
            raise RuntimeError(f"the laptop ledger does not verify: {error}")

    def watchlist(self, today: date) -> Path | None:
        """Today's research, as the cloud desk published it to GitHub (newest first)."""
        found = []
        for pattern in ("*/research/watchlist.json", "*/research/watchlist-published.json",
                        "*/research/proposals-watchlist.json"):
            found += [p for p in (self.repo / "docs" / "performance").glob(f"{today.isoformat()}-{pattern}")]
        local = self.drive / "watchlist.json"
        if local.is_file():
            found.append(local)
        return max(found, key=lambda p: p.stat().st_mtime) if found else None

    def nav_refs(self, today: date) -> dict[str, float]:
        """Prior-close and high-water NAV from today's published desk run, for the laptop's first run."""
        if (self.drive / "nav-refs.json").is_file():
            return {}
        for path in sorted((self.repo / "docs" / "performance").glob(f"{today.isoformat()}-*/snapshot.json"),
                           reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {"--prior-close-nav": float(data["prior_close_nav"]),
                        "--high-water-nav": float(data["high_water_nav"])}
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return {}

    def tyche(self, *args: str) -> tuple[int, dict]:
        done = subprocess.run([self.python, "-m", "tyche.cli", *args], cwd=self.repo, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
        try:
            return done.returncode, json.loads(done.stdout)
        except ValueError:
            return done.returncode, {"status": "blocked", "reason": (done.stderr or done.stdout)[-400:]}

    def git_pull(self) -> None:
        if not self.pull:
            return
        done = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=self.repo, capture_output=True,
                              text=True, timeout=120, check=False)
        if done.returncode != 0:
            self.log("git pull did not run cleanly; using the code and research already here: "
                     + (done.stderr or done.stdout).strip()[:160])

    def tell(self, text: str) -> None:
        if not (self.telegram and text.strip()):
            return
        done = subprocess.run([self.python, "scripts/telegram.py", "send", text], cwd=self.repo,
                              capture_output=True, text=True, timeout=90, check=False)
        if done.returncode != 0:
            self.log("Telegram send failed: " + (done.stderr or done.stdout).strip()[-160:])

    def run_once(self, now: datetime | None = None, *, record: bool = True) -> dict:
        now = now or datetime.now(UTC)
        account = paper_account()
        broker = Broker(self.cli, account)
        self.git_pull()
        self.ensure_ledger()
        today = now.astimezone(ET).date()
        run = self.drive / f"{today.isoformat()}-laptop-{now.astimezone(UTC):%H%M%S}"
        common = ["--dir", str(run), "--drive-root", str(self.drive), "--journal", str(self.journal),
                  "--config-root", str(self.repo)]
        book = self.watchlist(today)
        if book is not None:
            common += ["--book", str(book)]
        _, plan = self.tyche("cycle", *common, "--reads")
        if plan.get("status") != "ok":
            self.log(f"{plan.get('status')}: {plan.get('reason', '')[:200]}")
            if plan.get("telegram_urgent"):
                self.tell(str(plan["telegram_urgent"]))
            return plan
        try:
            notes = broker.save_reads(run, plan.get("reads") or {})
        except MoomooCliError as exc:
            reason = f"moomoo CLI read failed: {mask(str(exc), account)[:200]}"
            self.log("blocked: " + reason)
            self.tell(f"TYCHE BLOCKED (paper, laptop), no orders this run: {reason}")
            return {"status": "blocked", "reason": reason}
        for note in notes:
            self.log(note)
        refs = [str(part) for pair in self.nav_refs(today).items() for part in pair]
        _, report = self.tyche("cycle", *common, *refs, *(["--record"] if record else []))
        status = report.get("status")
        if status != "ok":
            self.log(f"{status}: {str(report.get('reason', ''))[:240]}")
            urgent = run / "telegram-urgent.txt"
            if urgent.is_file():
                self.tell(urgent.read_text(encoding="utf-8"))
            return report
        if report.get("already_recorded"):
            # The same folder twice gives the same list again: those orders were sent the first time.
            self.log("this run folder was already recorded and sent; nothing is sent twice")
            return report
        results = send_listed(broker, report) if record and report.get("recorded") else []
        (run / "sent.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
        placed = [r for r in results if r["action"] == "submit" and r["done"]]
        refused = [r for r in results if not r["done"]]
        for row in results:
            label = (f"{row['side']} {row['quantity']} {row['symbol']} @ {row['limit_price']}"
                     if row["action"] == "submit" else f"cancel {row['order_id']} {row.get('symbol') or ''}")
            self.log(("sent   " if row["done"] else "NOT SENT ") + label + (f" ({row['why']})" if row["why"] else ""))
        message = (run / "telegram.txt").read_text(encoding="utf-8") if (run / "telegram.txt").is_file() else ""
        lines = [f"NOT SENT: {r.get('side', 'cancel')} {r.get('quantity', '')} {r.get('symbol') or ''}: {r['why']}"
                 for r in refused]
        if report.get("submit") and not placed:
            lines.append("No listed order was placed this run.")
        self.tell("\n".join(part for part in [message, *lines] if part))
        if (run / "telegram-urgent.txt").is_file():
            self.tell((run / "telegram-urgent.txt").read_text(encoding="utf-8"))
        self.log(f"ok: {len(placed)} placed, {len(refused)} not sent, "
                 f"{len(report.get('alerts') or [])} alert(s), setups {report.get('setups') or []}")
        return report

    def loop(self, *, premarket: bool = False) -> None:
        self.log("laptop runner started: every 15 minutes from 09:07 to 15:52 ET on trading days. "
                 "Keep this window open and the laptop awake. Ctrl+C stops it.")
        while True:
            now = datetime.now(UTC)
            slot = next_slot(now, premarket=premarket)
            self.log(f"next run {slot:%a %H:%M} ET")
            while datetime.now(UTC) < slot:
                clock.sleep(min(30.0, max(0.5, (slot - datetime.now(UTC)).total_seconds())))
            late = (datetime.now(UTC) - slot).total_seconds()
            if late > 600:
                self.log(f"skipped the {slot:%H:%M} ET run: the laptop was asleep for {late / 60:.0f} minutes")
                continue
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 - one bad run must not end the night's runner
                text = str(exc)
                try:
                    text = mask(text, paper_account())
                except RuntimeError:
                    pass
                self.log(f"run failed: {type(exc).__name__}: {text[:240]}")
                self.tell(f"TYCHE (paper, laptop): a run failed and placed nothing: {text[:200]}")


def check(runner: Runner) -> bool:
    """Read-only: CLI found and signed in, the paper account listed, and every read the cycle needs."""
    account = paper_account()
    binary = runner.cli.resolved_binary()
    print("moomoo CLI:", binary or "NOT FOUND")
    if binary is None:
        return False
    broker = Broker(runner.cli, account)
    run = runner.drive / f"check-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    try:
        notes = broker.save_reads(run, {"quotes": ["US.NVDA"], "bars": ["US.NVDA"]})
    except MoomooCliError as exc:
        print("read failed:", mask(str(exc), account)[:300])
        return False
    accounts = json.loads((run / "accounts.json").read_text(encoding="utf-8"))["data"]["accounts"]
    mine = next((a for a in accounts if str(a.get("account_id")) == account), None)
    print("paper account listed:", "yes" if mine else "NO",
          f"(type {mine.get('account_type')}, market {mine.get('market_id')})" if mine else "")
    positions = json.loads((run / "positions.json").read_text(encoding="utf-8"))["data"]["positions"]
    orders = json.loads((run / "orders.json").read_text(encoding="utf-8"))["data"]["orders"]
    quotes = json.loads((run / "quotes.json").read_text(encoding="utf-8"))["data"]["quote_list"]
    bars = json.loads((run / "bars-US.NVDA.json").read_text(encoding="utf-8"))["data"]["kline_list"] \
        if (run / "bars-US.NVDA.json").is_file() else []
    print(f"positions {len(positions)}, orders {len(orders)}, NVDA quote rows {len(quotes)}, NVDA 1-minute bars {len(bars)}")
    for note in notes:
        print("note:", note)
    print("saved in", run)
    return bool(mine and quotes)


def laptop_command(
    once: bool = typer.Option(False, "--once", help="One cycle now, then stop."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Read and decide; reserve and send nothing."),
    check_only: bool = typer.Option(False, "--check", help="Read-only check of the CLI and the account."),
    premarket: bool = typer.Option(False, "--premarket", help="Also run at 08:05 ET (resting entries)."),
    no_pull: bool = typer.Option(False, "--no-pull", help="Do not git pull before each run."),
    moomoo_binary: str = typer.Option(os.environ.get("TYCHE_MOOMOO_CLI", "moomoo"), "--moomoo"),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    """THE CYCLE on this laptop, with the moomoo CLI and no AI (see tyche.laptop)."""
    load_dotenv(repo)
    runner = Runner(repo, MoomooCli(moomoo_binary, timeout=60.0), pull=not no_pull)
    if check_only:
        raise typer.Exit(0 if check(runner) else 1)
    if once or dry_run:
        report = runner.run_once(record=not dry_run)
        raise typer.Exit(0 if report.get("status") in ("ok", "skip") else 1)
    runner.loop(premarket=premarket)
