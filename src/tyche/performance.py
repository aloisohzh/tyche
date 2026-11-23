"""Fee-net performance pack and SPY baseline, read from the record (docs/performance/README.md).

Everything here is a pure function over files the desk already produces: the hash-chained journal
(`eod.reconcile` and `plan.created` rows carry the account value per day), the published desk feed
(`nav_marks` per account, the fee-net series of finished trades) and the price CSVs the researcher
writes (`date,symbol,close`, which is where SPY comes from). Nothing is fetched and nothing is
timestamped with the wall clock, so the same inputs render the same bytes; that is what makes the
report reproducible by a judge instead of a claim on a slide.

What it refuses to do is invent: a day with no account mark is left out of the series rather than
carried forward, a day with no SPY close is listed as missing rather than interpolated, and every
small-n statistic carries its n. Sharpe over a handful of marks is a noisy estimate and the text
says so (docs/competition/scoring-map.md).
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

TRADING_DAYS_PER_YEAR = 252
BENCHMARK = "US.SPY"


@dataclass(frozen=True)
class DayRow:
    day: date
    nav: float
    daily_return: float | None
    cumulative_return: float
    drawdown: float
    benchmark_close: float | None
    benchmark_return: float | None  # cumulative, from the base close
    active_return: float | None  # desk cumulative minus benchmark cumulative
    basis: str = "start"  # close (EOD reconcile), plan (pre-trade NAV), feed (published mark, may be intraday)


@dataclass
class Pack:
    account: str
    start_day: date
    start_nav: float
    rows: list[DayRow]
    benchmark_base_day: date | None
    benchmark_base_close: float | None
    missing_benchmark_days: list[date]
    realized_vol: float | None
    sharpe: float | None
    max_drawdown: float
    orders_per_day: dict[date, int]
    rejections: list[dict[str, Any]]
    blocked_rules: dict[str, int]
    fees: dict[str, float]
    fee_net_series: list[dict[str, Any]]
    sources: list[str] = field(default_factory=list)

    @property
    def n_returns(self) -> int:
        return sum(1 for r in self.rows if r.daily_return is not None)

    @property
    def last(self) -> DayRow | None:
        return self.rows[-1] if self.rows else None


# ---------------------------------------------------------------------------
# Inputs


def _as_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def account_key(value: Any) -> str | None:
    """The desk's masked form of an account id: `***` plus the last three digits.

    The live journal holds full ids in `plan.account_id` and `...598`-style masks in order rows; the
    feed keys its marks `***598`. A value with no digits at all (a sanitized bundle's `[REDACTED]`, a
    demo alias) cannot be matched and comes back as itself.
    """
    if value in (None, ""):
        return None
    text = str(value)
    if re.fullmatch(r"\d{6,}", text) or re.fullmatch(r"[.*]+\d{3}", text):
        return "***" + text[-3:]
    return text


def _same_account(row_value: Any, account: str | None) -> bool:
    """True when the row belongs to `account`, or when neither side can say (no digits to compare).

    A journal shared by the challenge account and the personal paper account (ten times the size)
    must not mix their marks: one personal-account plan row read as the 17 Nov mark would put a
    -90% drawdown on the challenge book. A row whose id is redacted is kept, because a sanitized
    bundle has nothing else, and that is stated in the report's method notes.
    """
    key = account_key(row_value)
    want = account_key(account)
    if key is None or want is None or not key.startswith("***") or not want.startswith("***"):
        return True
    return key == want


def mark_basis_from_journal(events: list[dict[str, Any]], account: str | None = None) -> dict[date, str]:
    """What kind of mark the journal gives each day: `close` for an EOD reconcile, `plan` for a pre-trade NAV."""
    basis: dict[date, str] = {}
    for ev in events:
        payload = ev.get("payload") or {}
        if ev.get("type") == "plan.created":
            plan = payload.get("plan") or {}
            day = _as_day(plan.get("as_of"))
            if day is not None and plan.get("nav") is not None and _same_account(plan.get("account_id"), account):
                basis.setdefault(day, "plan")
    for ev in events:
        payload = ev.get("payload") or {}
        if ev.get("type") == "eod.reconcile":
            day = _as_day(payload.get("date"))
            if day is not None and payload.get("nav") is not None and _same_account(payload.get("account"), account):
                basis[day] = "close"
    return basis


def account_days_from_journal(events: list[dict[str, Any]], account: str | None = None) -> dict[date, float]:
    """One account value per day from the journal: the EOD reconcile wins, a plan's NAV is the fallback.

    `eod.reconcile.nav` is the broker's total asset after the close, which is the number the final
    results use. `plan.created.plan.nav` is a pre-trade mark, so it only stands in for a day that
    never reconciled. Rows for another account are dropped (see `_same_account`).
    """
    reconciled: dict[date, float] = {}
    planned: dict[date, float] = {}
    for ev in events:
        payload = ev.get("payload") or {}
        if ev.get("type") == "eod.reconcile":
            if not _same_account(payload.get("account"), account):
                continue
            day = _as_day(payload.get("date"))
            if day is not None and payload.get("nav") is not None:
                reconciled[day] = float(payload["nav"])
        elif ev.get("type") == "plan.created":
            plan = payload.get("plan") or {}
            if not _same_account(plan.get("account_id"), account):
                continue
            day = _as_day(plan.get("as_of"))
            if day is not None and plan.get("nav") is not None:
                planned[day] = float(plan["nav"])  # later rows overwrite earlier ones
    return {**planned, **reconciled}


def account_days_from_feed(state: dict[str, Any], account: str) -> dict[date, float]:
    """The last published mark per day for one account, from the desk feed's `nav_marks`.

    Marks are ordered by `ts` inside the feed; the latest one dated `as_of` is that day's value. A
    mark whose `as_of` is not a date (the local snapshot's "snapshot") is skipped.
    """
    out: dict[date, float] = {}
    for mark in sorted((state.get("nav_marks") or {}).get(account) or [], key=lambda m: m.get("ts") or ""):
        day = _as_day(mark.get("as_of"))
        if day is not None and mark.get("nav") is not None:
            out[day] = float(mark["nav"])
    return out


def benchmark_closes(paths: list[Path], symbol: str = BENCHMARK) -> dict[date, float]:
    """Daily closes for one symbol from long-format price CSVs (`date,symbol,close`); later files win."""
    closes: dict[date, float] = {}
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if (row.get("symbol") or "").strip() != symbol:
                    continue
                day = _as_day(row.get("date"))
                try:
                    close = float(row.get("close") or "")
                except ValueError:
                    continue
                if day is not None:
                    closes[day] = close
    return closes


def orders_per_day(events: list[dict[str, Any]]) -> dict[date, int]:
    """Executed-order count per day: one `order.submitted` row is one order against the 200/day cap."""
    counts: dict[date, int] = {}
    for ev in events:
        if ev.get("type") != "order.submitted":
            continue
        day = _as_day(ev.get("ts"))
        if day is not None:
            counts[day] = counts.get(day, 0) + 1
    return counts


def rejections(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every decision that was not taken, with why: operator and broker rejections, kernel breaches,
    gate waits and halt skips. The rejection log is the answer to "what failed and why"."""
    out: list[dict[str, Any]] = []
    for ev in events:
        kind = ev.get("type")
        payload = ev.get("payload") or {}
        day = str(ev.get("ts") or "")[:10]
        if kind == "order.rejected":
            out.append({"date": day, "kind": kind, "symbol": payload.get("symbol"),
                        "rule": payload.get("decision_by") or "broker", "detail": payload.get("reason") or ""})
        elif kind in {"gate.wait", "halt.skip", "run.skip"}:
            out.append({"date": day, "kind": kind, "symbol": payload.get("symbol"),
                        "rule": kind, "detail": payload.get("reason") or ""})
        elif kind == "plan.created":
            plan = payload.get("plan") or {}
            for order in plan.get("orders") or []:
                verdict = order.get("verdict") or {}
                if verdict.get("allowed", True):
                    continue
                intent = order.get("intent") or {}
                for breach in verdict.get("breaches") or [{"rule": "risk.kernel", "detail": ""}]:
                    out.append({"date": str(plan.get("as_of") or day)[:10], "kind": "kernel.blocked",
                                "symbol": intent.get("symbol"), "rule": breach.get("rule"),
                                "detail": breach.get("detail") or ""})
    return out


def fees_from_journal(events: list[dict[str, Any]]) -> dict[str, float]:
    """Modelled fees and the fees implied by the broker's cash, summed over every EOD reconcile."""
    modeled = implied = 0.0
    days = 0
    for ev in events:
        if ev.get("type") != "eod.reconcile":
            continue
        payload = ev.get("payload") or {}
        modeled += float(payload.get("fees_modeled") or 0.0)
        implied += float(payload.get("fees_implied") or 0.0)
        days += 1
    return {"modeled": round(modeled, 4), "implied": round(implied, 4), "unreconciled": round(implied - modeled, 4),
            "reconciled_days": days}


# ---------------------------------------------------------------------------
# Statistics


def max_drawdown(navs: list[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for nav in navs:
        peak = max(peak, nav)
        if peak > 0:
            worst = min(worst, nav / peak - 1.0)
    return worst


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def build_pack(
    *,
    account: str,
    start_day: date,
    start_nav: float,
    account_days: dict[date, float],
    benchmark: dict[date, float],
    events: list[dict[str, Any]],
    fee_net_series: list[dict[str, Any]] | None = None,
    base_day: date | None = None,
    sources: list[str] | None = None,
    mark_basis: dict[date, str] | None = None,
) -> Pack:
    """Assemble the pack. The series starts at `start_nav` on `start_day` and then holds one point per
    day the record marked; the SPY baseline is $start_nav put into SPY at the base day's close
    (the start day unless `base_day` says otherwise) and marked at each later close."""
    days = {d: v for d, v in account_days.items() if d >= start_day}
    days_marked = set(days)
    days.setdefault(start_day, start_nav)
    ordered = sorted(days)

    base_day = base_day or start_day
    base_close = benchmark.get(base_day)
    if base_close is None:
        # The nearest close on or before the base day, so a weekend start still has a base.
        earlier = [d for d in benchmark if d <= base_day]
        if earlier:
            base_day = max(earlier)
            base_close = benchmark[base_day]
        else:
            base_day = None

    rows: list[DayRow] = []
    missing: list[date] = []
    peak = -math.inf
    prev: float | None = None
    for day in ordered:
        nav = days[day]
        peak = max(peak, nav)
        close = benchmark.get(day)
        if close is None and day != start_day:
            missing.append(day)
        bench_ret = (close / base_close - 1.0) if (close is not None and base_close) else None
        cum = nav / start_nav - 1.0
        rows.append(DayRow(
            day=day,
            nav=nav,
            daily_return=(nav / prev - 1.0) if prev else None,
            cumulative_return=cum,
            drawdown=(nav / peak - 1.0) if peak > 0 else 0.0,
            benchmark_close=close,
            benchmark_return=bench_ret,
            active_return=(cum - bench_ret) if bench_ret is not None else None,
            basis="start" if (day == start_day and day not in days_marked) else (mark_basis or {}).get(day, "feed"),
        ))
        prev = nav

    daily = [r.daily_return for r in rows if r.daily_return is not None]
    sd = _stdev(daily)
    vol = sd * math.sqrt(TRADING_DAYS_PER_YEAR) if sd is not None else None
    sharpe = None
    if sd:
        sharpe = (sum(daily) / len(daily)) / sd * math.sqrt(TRADING_DAYS_PER_YEAR)

    return Pack(
        account=account,
        start_day=start_day,
        start_nav=start_nav,
        rows=rows,
        benchmark_base_day=base_day,
        benchmark_base_close=base_close,
        missing_benchmark_days=missing,
        realized_vol=vol,
        sharpe=sharpe,
        max_drawdown=max_drawdown([r.nav for r in rows]),
        orders_per_day=orders_per_day(events),
        rejections=rejections(events),
        blocked_rules=_count_rules(rejections(events)),
        fees=fees_from_journal(events),
        fee_net_series=list(fee_net_series or []),
        sources=list(sources or []),
    )


def _count_rules(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("rule") or row.get("kind"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


# ---------------------------------------------------------------------------
# Rendering


def _pct(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value * 100:+.{digits}f}%"


def _money(value: float | None) -> str:
    return "-" if value is None else f"{value:,.2f}"


def render_markdown(pack: Pack, *, order_cap: int = 200, internal_budget: int | None = None) -> str:
    last = pack.last
    lines: list[str] = []
    as_of = last.day.isoformat() if last else pack.start_day.isoformat()
    lines.append(f"# Performance pack, as of {as_of} (fee-net, generated)")
    lines.append("")
    lines.append(
        "Generated by `tyche performance report` from the journal, the published desk feed and the "
        "researcher's price CSVs. Re-run it on the same inputs and the bytes match. Nothing here is "
        "hand-edited; a number that is missing in the record is marked missing, never filled in."
    )
    lines.append("")

    # Headline
    lines.append("## Headline")
    lines.append("")
    if last:
        lines.append(f"- Account {pack.account}: {_money(last.nav)} on {last.day.isoformat()}, "
                     f"{_pct(last.cumulative_return)} since {_money(pack.start_nav)} on {pack.start_day.isoformat()}.")
        if last.benchmark_return is not None:
            lines.append(f"- SPY baseline (same cash into SPY at the {pack.benchmark_base_day} close of "
                         f"{_money(pack.benchmark_base_close)}): {_pct(last.benchmark_return)}; "
                         f"desk minus SPY {_pct(last.active_return)}.")
        else:
            lines.append(f"- SPY baseline: no SPY close in the price files for {last.day.isoformat()}, so the "
                         "comparison on the latest mark is missing (see below).")
    lines.append(f"- Max drawdown {_pct(pack.max_drawdown)}; current drawdown {_pct(last.drawdown) if last else '-'}.")
    n = pack.n_returns
    if pack.realized_vol is not None:
        lines.append(f"- Realized vol {_pct(pack.realized_vol)} annualized, Sharpe {pack.sharpe:+.2f} annualized, "
                     f"from n={n} daily marks. **Provisional:** with n this small the Sharpe is a noisy estimate "
                     "and is reported, not claimed.")
    else:
        lines.append(f"- Realized vol and Sharpe: not computable yet (n={n} daily returns; two are needed).")
    lines.append("")

    # Daily table
    lines.append("## Daily marks against SPY")
    lines.append("")
    lines.append("| Date | Account value | Mark | Day | Since start | Drawdown | SPY close | SPY since base | Desk minus SPY |")
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for r in pack.rows:
        lines.append(
            f"| {r.day.isoformat()} | {_money(r.nav)} | {r.basis} | {_pct(r.daily_return)} | {_pct(r.cumulative_return)} | "
            f"{_pct(r.drawdown)} | {_money(r.benchmark_close)} | {_pct(r.benchmark_return)} | {_pct(r.active_return)} |"
        )
    lines.append("")
    if any(r.basis == "feed" for r in pack.rows):
        feed_days = ", ".join(r.day.isoformat() for r in pack.rows if r.basis == "feed")
        lines.append(f"Mark basis: `close` is the broker's total asset at the EOD reconcile, `plan` a pre-trade NAV, "
                     f"`feed` the last published desk mark for that date, which can be an intraday capture. "
                     f"SPY is always the close, so a `feed` row ({feed_days}) compares an intraday desk mark with a "
                     "closing SPY price; read its last column as approximate until that day reconciles.")
        lines.append("")
    if pack.benchmark_base_day is None:
        lines.append("No SPY close on or before the start day was found in the price files, so there is no baseline. "
                     "Add a `date,symbol,close` CSV that holds `US.SPY` (`tyche fetch US.SPY`, or the researcher's "
                     "`data/prices.csv` from a run bundle) and re-run.")
    elif pack.missing_benchmark_days:
        missing = ", ".join(d.isoformat() for d in pack.missing_benchmark_days)
        lines.append(f"SPY close missing for: {missing}. The desk marks stand; the comparison on those days is "
                     "blank until a price file covering them is passed with `--prices`.")
    lines.append("")

    # Activity
    lines.append("## Activity and discipline")
    lines.append("")
    budget = f" (internal budget {internal_budget})" if internal_budget else ""
    lines.append(f"Executed orders per day against the competition cap of {order_cap}{budget}:")
    lines.append("")
    if pack.orders_per_day:
        lines.append("| Date | Orders submitted | Of cap |")
        lines.append("|---|---:|---:|")
        for day in sorted(pack.orders_per_day):
            count = pack.orders_per_day[day]
            lines.append(f"| {day.isoformat()} | {count} | {count / order_cap * 100:.1f}% |")
    else:
        lines.append("No `order.submitted` rows in the journal passed in.")
    lines.append("")
    lines.append("Decisions not taken, by rule (the rejection log the handbook asks for):")
    lines.append("")
    if pack.blocked_rules:
        lines.append("| Rule or gate | Count |")
        lines.append("|---|---:|")
        for rule, count in pack.blocked_rules.items():
            lines.append(f"| `{rule}` | {count} |")
        lines.append("")
        lines.append("| Date | What | Symbol | Why |")
        lines.append("|---|---|---|---|")
        for row in pack.rejections:
            detail = str(row.get("detail") or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| {row['date']} | {row['kind']} | {row.get('symbol') or '-'} | {detail} |")
    else:
        lines.append("None recorded in the journal passed in.")
    lines.append("")

    # Fees
    lines.append("## Fees and friction")
    lines.append("")
    fees = pack.fees
    lines.append(f"- Modelled fees over {fees.get('reconciled_days', 0)} reconciled day(s): {_money(fees.get('modeled'))}; "
                 f"implied by broker cash: {_money(fees.get('implied'))}; unreconciled difference "
                 f"{_money(fees.get('unreconciled'))}. The simulator exposes no fee fields, so the model is the "
                 "record and the cash delta is the check.")
    if pack.fee_net_series:
        lines.append("")
        lines.append("| Trade day | Closed trades | Gross | Fees | Net | Cumulative net |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for row in pack.fee_net_series:
            lines.append(f"| {row.get('date')} | {row.get('trades')} | {_money(row.get('gross'))} | "
                         f"{_money(row.get('fees'))} | {_money(row.get('net'))} | {_money(row.get('cumulative_net'))} |")
    lines.append("")

    # Method
    lines.append("## How to read it")
    lines.append("")
    lines.append("- Account value per day is the broker's total asset from `eod.reconcile`; a day with no reconcile "
                 "uses the last published desk mark for that date, and a day with neither is left out, never carried. "
                 "Journal rows for another account are dropped by their masked id; a row whose id is redacted "
                 "(sanitized bundles) is kept.")
    lines.append("- The SPY baseline is the same starting cash put into SPY at the base day's close with no fees, "
                 "which flatters SPY slightly; it is the bar, not a strategy.")
    lines.append("- Returns are fee-net because the account value already carries the modelled fees reconciled to cash.")
    lines.append(f"- Vol and Sharpe annualize with sqrt({TRADING_DAYS_PER_YEAR}) over n daily marks; drawdown is from the "
                 "running peak of the marks shown.")
    if pack.sources:
        lines.append("")
        lines.append("Inputs: " + "; ".join(pack.sources) + ".")
    lines.append("")
    return "\n".join(lines)


def to_json(pack: Pack) -> dict[str, Any]:
    return {
        "account": pack.account,
        "start_day": pack.start_day.isoformat(),
        "start_nav": pack.start_nav,
        "benchmark": {"symbol": BENCHMARK, "base_day": pack.benchmark_base_day.isoformat() if pack.benchmark_base_day else None,
                      "base_close": pack.benchmark_base_close,
                      "missing_days": [d.isoformat() for d in pack.missing_benchmark_days]},
        "rows": [{"day": r.day.isoformat(), "nav": r.nav, "basis": r.basis, "daily_return": r.daily_return,
                  "cumulative_return": r.cumulative_return, "drawdown": r.drawdown,
                  "benchmark_close": r.benchmark_close, "benchmark_return": r.benchmark_return,
                  "active_return": r.active_return} for r in pack.rows],
        "n_returns": pack.n_returns,
        "realized_vol": pack.realized_vol,
        "sharpe": pack.sharpe,
        "max_drawdown": pack.max_drawdown,
        "orders_per_day": {d.isoformat(): c for d, c in sorted(pack.orders_per_day.items())},
        "blocked_rules": pack.blocked_rules,
        "rejections": pack.rejections,
        "fees": pack.fees,
        "fee_net_series": pack.fee_net_series,
        "sources": pack.sources,
    }
