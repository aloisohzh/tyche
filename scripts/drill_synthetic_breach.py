"""Synthetic-breach drill: ADR 0013 runbook §8.4, the gate options enablement waits behind.

One command walks a synthetic lot through the whole protection chain and writes nothing but
its own scratch files under `data/drill/`:

    detect (monitor tick) -> de-duplicate -> render the urgent digest (never send)
    -> reserve the bounded exit (never submit) -> refuse the retry -> clear

The lot is synthetic on purpose: `US.MSFT` (a tactical-universe name, so the desk's real
config is what gets exercised) with a 470 stop, 10 shares nobody holds, and a journal the
desk never reads. The real journal, the operator envelope, the draft file, the switches and
every config yaml are hashed before and after, and the drill fails if one byte moved. There
is no broker import anywhere in this file - the kernel cannot reach a trading API, which is
the property under test rather than a convenience - and the run still checks that nothing
submission-shaped landed on the scratch chain.

Clocks: without `--at` the drill runs on the wall clock, so leg 0 proves the calendar gate
through the real process entry point and the recording legs only run inside a regular
session. With `--at` the same command objects run against a pinned clock, which is what makes
the drill repeatable off-session; the report states `pinned_clock: true` so a rehearsal can
never be mistaken for a live-session measurement. What neither mode measures is listed in
`not_measured` rather than quietly omitted.

Run: .venv/Scripts/python.exe scripts/drill_synthetic_breach.py --at 2026-11-25T14:35:00+00:00
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typer.testing import CliRunner

from tyche.approvals import ApprovalBatch
from tyche.cli import app
from tyche.config import load_config
from tyche.journal import append_event, read_events, verify_chain
from tyche.market_calendar import ET
from tyche.tactical import setup_hash
from tyche.watchlist import WatchlistEntry

DRILL = ROOT / "data" / "drill"
SYMBOL = "US.MSFT"
HELD = 10
STOP, TARGET, PRICE_OK, PRICE_BREACH = 470.0, 540.0, 490.0, 455.0
NAV = 30_000.0  # the synthetic account's broker NAV; cash is whatever reconciles to it
ACCOUNT_ID = "SIM-DEMO-US"  # the committed demo id: a real account id never enters a drill file
STEP, CADENCE = 60, 300  # seconds between legs, and the tick spacing the runbook's 5-minute tier uses

# The clock every leg runs on, in one mutable holder so a rehearsal can step it.
CLOCK: list[datetime] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def fingerprints() -> dict[str, str]:
    """Everything the drill must not touch. Absent must stay absent, so absence hashes too."""
    watched = [ROOT / "journal" / "events.jsonl", ROOT / "data" / "approvals.json",
               ROOT / "data" / "approvals.proposed.json", ROOT / "data" / "strategies.json",
               ROOT / "data" / "halt.json"]
    watched += sorted((ROOT / "config").rglob("*.yaml"))
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in watched}


def plan(start: datetime) -> WatchlistEntry:
    """The synthetic setup, shaped exactly like what the tactical lane journals at entry."""
    return WatchlistEntry.model_validate({
        "symbol": SYMBOL, "sleeve": "equity", "strategy": "PB-002 tactical break",
        "entry_low": 480.0, "entry_high": 485.0, "stop": STOP, "target": TARGET,
        "expiry": start.astimezone(ET).date() + timedelta(days=30), "status": "entered",
        "setup_id": f"DRILL-{start.astimezone(ET).date():%Y%m%d}-MSFT-SYNTH", "direction": "bullish",
        "thesis": "Synthetic drill lot. Not a trade idea, not research, not a position."})


def market_inputs(at: datetime, last: float) -> tuple[list[dict], dict]:
    """Quote and account rows as a runner writes them at `at`: five seconds old, two-sided, sim-list.

    Cash is derived from the fixed synthetic NAV and the lot's market value, because the risk
    kernel reconciles computed NAV against `broker_nav` and a drill fixture that fails that check
    would be testing its own arithmetic instead of the protection chain.
    """
    quote = {"symbol": SYMBOL, "at": (at - timedelta(seconds=5)).isoformat(),
             "book_at": (at - timedelta(seconds=5)).isoformat(), "last": last,
             "bid": round(last - 0.10, 2), "ask": round(last + 0.10, 2), "tradable": True}
    account = {"account_id": ACCOUNT_ID, "cash": round(NAV - HELD * last, 2), "broker_nav": NAV,
               "prior_close_nav": 30_200.0, "high_water_nav": 31_000.0,
               "captured_at": (at - timedelta(seconds=5)).isoformat(), "env": "paper",
               "account_type": 1, "market_id": 100, "source": "sim_list",
               "positions": [{"symbol": SYMBOL, "quantity": HELD, "available_quantity": HELD,
                              "avg_cost": 482.0, "last_price": last}]}
    return [quote], account


def write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def build_fixtures(start: datetime, entry: WatchlistEntry, batch: ApprovalBatch, config) -> dict[str, Path]:
    """Scratch inputs only. Nothing here reaches data/watchlist.json, the envelope or the journal."""
    DRILL.mkdir(parents=True, exist_ok=True)
    paths = {key: DRILL / name for key, name in {
        "book": "book.json", "account": "account.json", "quotes": "quotes.json",
        "orders": "orders.json", "envelope": "envelope.json", "lifecycle": "lifecycle-state.json",
        "journal": "events.jsonl", "digest": "digest.json", "report": "drill-report.json"}.items()}
    write(paths["book"], {"as_of": start.astimezone(ET).date().isoformat(),
                          "entries": [entry.model_dump(mode="json")]})
    write(paths["orders"], {"ret_code": 0, "data": {"orders": []}, "pagination": {"has_more": False}})
    write(paths["lifecycle"], {})
    write(paths["envelope"], json.loads(batch.model_dump_json()))
    paths["journal"].unlink(missing_ok=True)  # a drill always starts from an empty scratch chain
    append_event(paths["journal"], "order.requested", {
        "symbol": SYMBOL, "side": "buy", "quantity": HELD, "setup_id": entry.setup_id,
        "strategy_id": "PB-002", "setup_hash": setup_hash(entry, config, ACCOUNT_ID),
        "protected_setup": entry.model_dump(mode="json")})
    refresh(paths, start, PRICE_OK)
    return paths


def refresh(paths: dict[str, Path], at: datetime, last: float) -> None:
    quotes, account = market_inputs(at, last)
    write(paths["quotes"], quotes)
    write(paths["account"], account)


def run_cli(*args: str) -> tuple[int, str, float]:
    """Invoke the desk's own command objects and time them; the scheduler calls this same app."""
    started = time.perf_counter()
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.output, round((time.perf_counter() - started) * 1000, 1)


def tick(paths: dict[str, Path]) -> tuple[int, str, float]:
    return run_cli("monitor", "tick", "--quotes", str(paths["quotes"]), "--book", str(paths["book"]),
                   "--positions", str(paths["account"]), "--journal", str(paths["journal"]),
                   "--config-root", str(ROOT), "--cadence-seconds", str(CADENCE), "--record")


def gate_probe(paths: dict[str, Path]) -> tuple[int, str, float]:
    """Leg 0: the installed console entry point, in its own process, on the real wall clock."""
    started = time.perf_counter()
    done = subprocess.run(
        [sys.executable, "-m", "tyche.cli", "monitor", "tick", "--quotes", str(paths["quotes"]),
         "--book", str(paths["book"]), "--positions", str(paths["account"]),
         "--journal", str(DRILL / "gate.jsonl"), "--config-root", str(ROOT)],
        capture_output=True, text=True, check=False, cwd=ROOT)
    return done.returncode, (done.stdout + done.stderr).strip(), round(
        (time.perf_counter() - started) * 1000, 1)


def monitor_events(journal: Path) -> list[dict]:
    return [event for event in read_events(journal) if event["type"].startswith("monitor.")]


def payload_of(output: str) -> dict:
    """The command's own JSON reply, so the drill reports what it said rather than a log tail."""
    try:
        parsed = json.loads(output.strip())
    except ValueError:
        return {"raw": output.strip()[:300]}
    return parsed if isinstance(parsed, dict) else {"raw": str(parsed)[:300]}


def orders_journaled(journal: Path) -> int:
    return sum(1 for event in read_events(journal) if event["type"] == "order.requested")


def digest_for(breach: dict, entry: WatchlistEntry, phase: str, at: datetime,
               floor: float, collar: float) -> dict:
    """The §7 alert object: symbol, quantity, level versus quote, and the exact operator action.

    `render-digest`, not `send-digest`: rung 1 bark routing is not approved, so the drill proves
    the text the operator would read and the ref a retry would duplicate - never a delivery.
    """
    return {
        "phase": phase, "timestamp": at.isoformat(),
        "mode": "PAPER - Level 0 protection monitor (synthetic drill)",
        "stance": "One journaled level breached. Nothing here is a live position.",
        "orders_summary": f"{HELD} {SYMBOL} shares reserved for exit; zero orders submitted.",
        "orders": [{
            "action": "RESERVE", "symbol": SYMBOL, "qty": str(HELD),
            "value": f"limit {breach['observed_price']:.2f}, floor {floor:.2f}",
            "status": "reserved, never submitted by this drill",
            "reason": f"{breach['protection_type']}: quote at or below the journaled stop "
                      f"{breach['level']:.2f} (source {breach['level_source']}, exit {breach['exit_ref']})"}],
        "account": {"nav": f"{NAV:,.2f} (synthetic)",
                    "cash": f"{NAV - HELD * breach['observed_price']:,.2f} (synthetic)",
                    "positions": f"1 synthetic lot, {HELD} shares", "kill_switch": "not engaged"},
        "protection": [
            (f"{SYMBOL} {HELD} shares: last {breach['observed_price']:.2f} vs stop "
             f"{breach['level']:.2f}; armed floor {floor:.2f} (stop widened by {collar:.1%})."),
            f"Episode {breach['episode_id']} opened {breach['observed_at']}.",
            "Do: confirm or cancel the reserved exit on the desk. The kernel will not submit it.",
            f"Setup {entry.setup_id}, expiry {entry.expiry.isoformat()}, sleeve {entry.sleeve}."],
        "problems": ["Synthetic drill fixture: lot, quote and account id are not real."],
        "urgent": True,
        "next_check": f"Ticks every {CADENCE}s; the next restates this only when the episode closes.",
    }


def render(digest: dict, path: Path) -> tuple[str, str, float]:
    """Render through the shipping renderer - the same code path a send would take."""
    write(path, digest)
    started = time.perf_counter()
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "telegram.py"), "render-digest", str(path)],
        capture_output=True, text=True, check=False, cwd=ROOT)
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    if done.returncode != 0:
        raise SystemExit(f"drill invalid: the renderer refused the digest - "
                         f"{(done.stdout + done.stderr).strip()[:300]}")
    text = done.stdout.strip()
    return text, hashlib.sha256(text.encode()).hexdigest()[:8], elapsed


def reserve(paths: dict[str, Path]) -> tuple[int, str, float]:
    return run_cli("tactical", "reserve", "--symbol", SYMBOL, "--book", str(paths["book"]),
                   "--account", str(paths["account"]), "--quotes", str(paths["quotes"]),
                   "--orders", str(paths["orders"]), "--envelope", str(paths["envelope"]),
                   "--lifecycle-state", str(paths["lifecycle"]), "--journal", str(paths["journal"]),
                   "--config-root", str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic-breach drill (ADR 0013 runbook §8.4).")
    parser.add_argument("--at", help="Pin the clock (tz-aware ISO) to rehearse outside a session.")
    args = parser.parse_args()
    start = datetime.now(UTC) if args.at is None else datetime.fromisoformat(args.at)
    if start.tzinfo is None:
        raise SystemExit("--at must carry a timezone offset")
    CLOCK.append(start)

    config = load_config(ROOT)
    collar = config.risk.exit_collar_pct
    entry = plan(start)
    floor = round(STOP * (1 - collar), 4)
    batch = ApprovalBatch(
        as_of=start.astimezone(ET).date(), approved_at=start - timedelta(minutes=5),
        approved_by="drill fixture (kernel-generated, not an operator approval)", max_orders=3,
        max_notional=None, note="Synthetic envelope under data/drill/; never armed, never synced.",
        orders=[{"symbol": SYMBOL, "side": "sell", "max_qty": HELD, "max_total_qty": HELD,
                 "limit_min": floor, "multiplier": 1,
                 "setup_hash": setup_hash(entry, config, ACCOUNT_ID)}])
    paths = build_fixtures(start, entry, batch, config)
    report: dict = {
        "drill": "synthetic-breach", "runbook": "docs/runbooks/intraday-protection-monitor.md §8.4",
        "started_at": start.isoformat(), "pinned_clock": args.at is not None,
        "config": {"collar_pct": collar, "universe": config.tactical.symbols,
                   "options_enabled": config.tactical.options_enabled, "cadence_seconds": CADENCE,
                   "max_quote_age_seconds": config.tactical.max_quote_age_seconds},
        "synthetic_lot": {"symbol": SYMBOL, "quantity": HELD, "stop": STOP, "floor": floor,
                          "breach_quote": PRICE_BREACH, "account_id": ACCOUNT_ID,
                          "setup_hash": batch.orders[0].setup_hash[:12]},
        "before": fingerprints(),
        "real_journal_chain_valid_before": verify_chain(ROOT / "journal" / "events.jsonl")[0],
        "legs": [], "not_measured": ["schedule wake-up latency and cron reliability",
                                     "Telegram delivery (rung 1 bark routing is not approved)",
                                     "operator reaction time (nobody was paged by a drill)"]}
    if args.at is not None:
        report["not_measured"].append(
            "wall-clock elapsed since the events were appended: the chain stamps the real time while "
            "the commands judge on the pinned one, so every duration here is a market-time duration")

    def leg(name: str, **fields) -> None:
        report["legs"].append({"leg": name, **fields})

    code, output, ms = gate_probe(paths)
    leg("0 calendar gate (real process, real clock)", exit=code, ms=ms, output=output.splitlines()[:1])
    if code == 1 and args.at is None:
        report["why"] = ("The gate refused the tick, which is the contract. The recording legs need a "
                         "regular session, or an explicit --at rehearsal clock.")
        return finish(report, paths)

    # Legs 1+ run the recorded tick chain on the drill clock, stepped like a real morning.
    from tyche import monitor_cli, tactical_cli  # both clocks are restored in the finally block

    real_clocks = (monitor_cli._clock, tactical_cli.now_utc)
    monitor_cli._clock = tactical_cli.now_utc = lambda: CLOCK[0]
    try:
        seen, ticks, detection_ms = len(monitor_events(paths["journal"])), {}, None
        for name, price in (("clean", PRICE_OK), ("breach", PRICE_BREACH), ("repeat", PRICE_BREACH)):
            CLOCK[0] = CLOCK[0] + timedelta(seconds=STEP)
            refresh(paths, CLOCK[0], price)
            code, output, ms = tick(paths)
            events = monitor_events(paths["journal"])
            new, seen = events[seen:], len(events)
            ticks[name] = new
            leg(f"tick: {name} at {price}", exit=code, ms=ms, emitted=[e["type"] for e in new],
                output=output.strip().splitlines()[:1])
            if code != 0:
                raise SystemExit(f"drill invalid: the {name} tick exited {code}: {output.strip()[:200]}")
            if name == "breach":
                detection_ms = ms

        breaches = [event for event in ticks["breach"] if event["type"] == "monitor.breach"]
        heart = next((event for event in ticks["breach"] if event["type"] == "monitor.heartbeat"), None)
        report["detection"] = {
            "breach_events": len(breaches), "detection_ms": detection_ms,
            "duplicate_on_repeat": sum(1 for e in ticks["repeat"] if e["type"] == "monitor.breach"),
            "gap_events": sum(1 for tick_events in ticks.values() for e in tick_events
                              if e["type"] == "monitor.gap"),
            "heartbeat": heart["payload"] if heart else None}
        if len(breaches) != 1 or report["detection"]["duplicate_on_repeat"]:
            raise SystemExit("drill invalid: the breach was not reported exactly once")

        CLOCK[0] = CLOCK[0] + timedelta(seconds=5)
        refresh(paths, CLOCK[0], PRICE_BREACH)
        text, ref, ms = render(digest_for(breaches[0]["payload"], entry,
                                         (report["detection"]["heartbeat"] or {}).get("phase", "regular"),
                                         CLOCK[0], floor, collar), paths["digest"])
        report["digest"] = {"render_ms": ms, "chars": len(text), "ref": ref, "sent": False,
                            "text": text}
        leg("urgent digest rendered, not sent", exit=0, ms=ms, chars=len(text), ref=ref)

        code, output, ms = reserve(paths)
        reply = payload_of(output)
        request = reply.get("request") or {}
        leg("reserve the bounded exit (never submit)", exit=code, ms=ms,
            order_requests=orders_journaled(paths["journal"]))
        if code != 0 or orders_journaled(paths["journal"]) != 2:
            raise SystemExit(f"drill invalid: reservation refused ({code}): {output.strip()[:300]}")
        report["reserve"] = {"exit": code, "ms": ms, "authorized": reply.get("authorized"),
                             "submitted": reply.get("submitted"), "request_id": request.get("request_id"),
                             "order": {key: request.get(key) for key in
                                       ("symbol", "side", "quantity", "limit_price", "reason")},
                             "submit_before": request.get("submit_before"),
                             "instructions": reply.get("instructions"),
                             "order_requests_total": orders_journaled(paths["journal"])}

        CLOCK[0] = CLOCK[0] + timedelta(seconds=5)
        refresh(paths, CLOCK[0], PRICE_BREACH)
        code, output, ms = reserve(paths)
        reply = payload_of(output)
        report["retry"] = {"exit": code, "ms": ms, "refused": reply.get("reason"),
                           "order_requests_total": orders_journaled(paths["journal"])}
        leg("retry the same exit", exit=code, ms=ms, order_requests=report["retry"]["order_requests_total"],
            refused=report["retry"]["refused"])
        if code == 0 or report["retry"]["order_requests_total"] != 2:
            raise SystemExit("drill invalid: a reserved exit was reserved twice")

        CLOCK[0] = CLOCK[0] + timedelta(seconds=STEP)
        refresh(paths, CLOCK[0], PRICE_OK)
        code, output, ms = tick(paths)
        events = monitor_events(paths["journal"])
        new, _ = events[seen:], len(events)
        report["clear"] = {"exit": code, "ms": ms, "emitted": [e["type"] for e in new],
                           "duration_seconds": next((e["payload"].get("duration_seconds") for e in new
                                                     if e["type"] == "monitor.clear"), None)}
        leg("tick: recovered", exit=code, ms=ms, emitted=[e["type"] for e in new])
        if code != 0 or report["clear"]["duration_seconds"] is None:
            raise SystemExit("drill invalid: the episode did not close with a duration")
    finally:
        monitor_cli._clock, tactical_cli.now_utc = real_clocks

    return finish(report, paths)


def finish(report: dict, paths: dict[str, Path]) -> int:
    """Re-hash everything the drill must not touch: an unchanged byte is the pass criterion."""
    after = fingerprints()
    report["after"] = after
    report["protected_files_changed"] = sorted(key for key, value in report["before"].items()
                                               if after[key] != value)
    valid, count, error = verify_chain(paths["journal"])
    report["scratch_journal"] = {"chain_valid": valid, "events": count, "error": error}
    report["real_journal_chain_valid_after"] = verify_chain(ROOT / "journal" / "events.jsonl")[0]
    kinds = {event["type"] for event in read_events(paths["journal"])}
    report["submission_events_journaled"] = sorted(kinds & {"order.submitted", "order.receipt",
                                                            "order.filled"})
    report["checks"] = {
        "protected_files_untouched": not report["protected_files_changed"],
        "real_journal_chain_valid": report["real_journal_chain_valid_before"]
        and report["real_journal_chain_valid_after"],
        "scratch_chain_valid": valid,
        "breach_reported_once": report.get("detection", {}).get("breach_events") == 1,
        "no_duplicate_alert": report.get("detection", {}).get("duplicate_on_repeat") == 0,
        "no_coverage_gap": report.get("detection", {}).get("gap_events") == 0,
        "episode_closed_with_duration": report.get("clear", {}).get("duration_seconds") is not None,
        "exit_reserved_once": report.get("reserve", {}).get("order_requests_total") == 2,
        "reserve_said_not_submitted": report.get("reserve", {}).get("submitted") is False,
        "retry_refused": report.get("retry", {}).get("exit") == 1
        and bool(report.get("retry", {}).get("refused")),
        "nothing_submission_shaped": not report["submission_events_journaled"]}
    # A refusal before the recording legs ran is an honest stop, not a pass.
    report["verdict"] = "PASS" if all(report["checks"].values()) else "INCOMPLETE"
    print(json.dumps({key: value for key, value in report.items() if key not in ("before", "after")},
                     indent=2, default=str))
    write(paths["report"], report)
    # A stamped copy too: the rehearsal and the live-session run must not overwrite each other.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    write(paths["report"].with_name(f"drill-report-{stamp}.json"), report)
    print(f"\nreport: {paths['report'].relative_to(ROOT).as_posix()}  verdict: {report['verdict']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
