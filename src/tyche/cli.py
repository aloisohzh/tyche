from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from tyche.approvals import ApprovalBatch, authorize_order, envelope_usage
from tyche.broker import (
    MoomooCli,
    MoomooCliError,
    extract_daily_bars,
    extract_last_price,
    extract_order_id,
    snapshot_from_dir,
)
from tyche.config import load_config
from tyche.halt import is_halted, set_halt
from tyche.journal import append_event, verify_chain
from tyche.market_calendar import (
    ET,
    SessionPhase,
    evaluate,
    generate_hourly_schedules,
    generate_schedules,
)
from tyche.models import AccountSnapshot, PlannedOrder, Side, TradePlan, apply_fill
from tyche.persist import persist_run
from tyche.pipeline import build_order_pipeline, build_plan_pipeline
from tyche.risk import RiskState, evaluate_intent
from tyche.strategy import build_intents, fit_turnover_budget, rotation_targets
from tyche.watchlist import Watchlist

app = typer.Typer(add_completion=False, help="Regime-aware ETF rotation agent.")
console = Console()


def _load_prices(path: Path) -> dict[str, pd.Series]:
    if not path.is_file():
        raise typer.BadParameter(f"price file not found: {path}")
    frame = pd.read_csv(path, parse_dates=["date"])
    missing = {"date", "symbol", "close"} - set(frame.columns)
    if missing:
        raise typer.BadParameter(f"price file missing columns: {sorted(missing)}")
    wide = frame.pivot_table(
        index="date", columns="symbol", values="close", aggfunc="last"
    ).sort_index()
    return {str(symbol): wide[symbol].dropna() for symbol in wide.columns}


def _load_account(
    path: Path | None,
) -> tuple[AccountSnapshot, float | None, float | None]:
    if path is None:
        snapshot = AccountSnapshot(account_id="SIM-DEMO-US", cash=100_000.0)
        return snapshot, None, snapshot.nav
    if not path.is_file():
        raise typer.BadParameter(f"account file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot = AccountSnapshot.model_validate(payload)
    prior_close = payload.get("prior_close_nav")
    high_water = payload.get("high_water_nav", prior_close)
    return (
        snapshot,
        float(prior_close) if prior_close is not None else None,
        float(high_water) if high_water is not None else snapshot.nav,
    )


def _plan_markdown(plan: TradePlan) -> str:
    lines = [
        f"# Trade plan — {plan.as_of.isoformat()}",
        "",
        f"- Account: `{plan.account_id}`",
        f"- NAV: {plan.nav:,.2f} USD",
        f"- Cash: {plan.cash:,.2f} USD",
        f"- Regime: **{plan.regime.value}**",
        f"- Portfolio vol estimate: {plan.portfolio_vol:.2%}",
        f"- Volatility scale: {plan.vol_scale:.2f}",
        "",
        "## Regime checks",
        "",
    ]
    for name, passed in plan.regime_checks.items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")

    if plan.pipeline is not None:
        pipe = plan.pipeline
        lines.extend(
            [
                "",
                "## Pipeline",
                "",
                f"- Thesis: {pipe.thesis_ref}",
                f"- Inputs: `{pipe.inputs_ref.prices_path}` "
                f"(sha256 {pipe.inputs_ref.prices_sha256[:12]}…)"
                + (f" · brief `{pipe.inputs_ref.brief}`" if pipe.inputs_ref.brief else ""),
                (f"- Outlook: **{pipe.outlook.value}** · conviction {pipe.conviction} "
                 f"({pipe.checks_score}/{pipe.checks_total} checks)"),
                f"- Act/wait gate: {pipe.act_wait_rule}",
            ]
        )

    lines.extend(
        ["", "## Targets", "", "| Symbol | Target | Momentum | Volatility | Score | Selected |"]
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for symbol, weight in sorted(plan.targets.items(), key=lambda item: -item[1]):
        signal = plan.signals.get(symbol)
        if signal is None:
            lines.append(f"| {symbol} | {weight:.2%} |  |  |  |  |")
        else:
            lines.append(
                f"| {symbol} | {weight:.2%} | {signal.momentum:.2%} | "
                f"{signal.volatility:.2%} | {signal.score:.2f} | "
                f"{'yes' if signal.selected else 'no'} |"
            )

    lines.extend(["", "## Orders", ""])
    if not plan.orders:
        lines.append("_No trades required; portfolio is within rebalancing bands._")
    else:
        lines.append("| Status | Action | Side | Symbol | Qty | Limit | Notional | Risk notes |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | --- |")
        for order in plan.orders:
            status = "APPROVED" if order.verdict.allowed else "BLOCKED"
            action = order.pipeline.action if order.pipeline else "act"
            notes = "; ".join(
                [breach.rule for breach in order.verdict.breaches] + order.verdict.notes
            )
            lines.append(
                f"| {status} | {action} | {order.intent.side.value} | {order.intent.symbol} | "
                f"{order.effective_quantity} | {order.intent.limit_price:.2f} | "
                f"{order.effective_quantity * order.intent.limit_price:,.2f} | {notes} |"
            )
        for order in plan.orders:
            pipe = order.pipeline
            if pipe is None:
                continue
            sizing = pipe.sizing
            lines.extend(
                [
                    "",
                    f"### {order.intent.side.value.upper()} {order.intent.symbol}",
                    "",
                    f"- Vehicle: {pipe.vehicle} — {pipe.vehicle_rationale}",
                    f"- Expected edge: {pipe.expected_edge.label if pipe.expected_edge else 'n/a'}",
                    f"- Invalidation: {pipe.invalidation}",
                    f"- Protection: {pipe.protection_type}"
                    + (f" · roll plan: {pipe.roll_plan}" if pipe.roll_plan else ""),
                    f"- Sizing: {sizing.quantity} → {sizing.effective_quantity} eff · "
                    f"${sizing.notional:,.2f} ({sizing.nav_pct:.2%} NAV) · "
                    f"single-asset cap {sizing.single_asset_cap_pct:.0%}"
                    + (
                        f" · sleeve cap {sizing.sleeve_cap_pct:.0%}"
                        if sizing.sleeve_cap_pct is not None
                        else ""
                    ),
                ]
            )

    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in plan.notes)
    lines.append("")
    lines.append("_Generated by tyche. Paper trading only; not investment advice._")
    return "\n".join(lines)


@app.command()
def doctor(
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    moomoo_binary: str = typer.Option("moomoo", "--moomoo-binary"),
) -> None:
    """Check configuration, data directories, and Moomoo integration."""
    table = Table(title="tyche doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")

    try:
        config = load_config(config_root)
        table.add_row(
            "config",
            "ok",
            f"{len(config.universe.assets)} assets, top_n={config.strategy.top_n}, "
            f"target_vol={config.strategy.target_vol:.0%}",
        )
    except (ValidationError, FileNotFoundError, TypeError, ValueError) as exc:
        table.add_row("config", "FAIL", str(exc))
        console.print(table)
        raise typer.Exit(1) from exc

    cli = MoomooCli(moomoo_binary)
    if cli.available():
        try:
            table.add_row("moomoo CLI", "ok", cli.version())
        except MoomooCliError as exc:
            table.add_row("moomoo CLI", "error", str(exc))
    else:
        table.add_row(
            "moomoo CLI",
            "missing",
            "Install per docs/runbooks/operations.md, then run 'moomoo auth login'.",
        )

    skills_dir = Path.home() / ".qoder" / "skills"
    if skills_dir.is_dir():
        installed = sorted(path.name for path in skills_dir.glob("moomoo*"))
        table.add_row("moomoo skills", "ok" if installed else "missing", ", ".join(installed))
    else:
        table.add_row("moomoo skills", "missing", f"{skills_dir} not found")

    table.add_row("journal", "ok", str(Path.cwd() / "journal" / "events.jsonl"))
    console.print(table)


@app.command()
def plan(
    prices: Path = typer.Option(..., "--prices", help="Long CSV with date,symbol,close."),
    as_of: str | None = typer.Option(
        None, "--as-of", help="ISO date; defaults to last price date."
    ),
    account: Path | None = typer.Option(None, "--account", help="Account snapshot JSON."),
    brief: Path | None = typer.Option(
        None, "--brief", help="Research brief path to pin in the plan's inputs_ref."
    ),
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    out_dir: Path = typer.Option(Path("plans"), "--out"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Compute target weights, generate limit orders, and run the risk kernel."""
    config = load_config(config_root)
    histories = _load_prices(prices)

    if as_of:
        try:
            as_of_date = date.fromisoformat(as_of)
        except ValueError as exc:
            raise typer.BadParameter(f"invalid --as-of date: {as_of}") from exc
    else:
        as_of_date = max(series.index[-1].date() for series in histories.values())

    stamp = pd.Timestamp(as_of_date)
    histories = {
        symbol: series[series.index <= stamp]
        for symbol, series in histories.items()
        if not series[series.index <= stamp].empty
    }
    if not histories:
        raise typer.BadParameter(f"no price data on or before {as_of_date}")

    snapshot, prior_close, high_water = _load_account(account)
    last_prices = {symbol: float(series.iloc[-1]) for symbol, series in histories.items()}
    for position in snapshot.positions:
        if position.symbol in last_prices:
            position.last_price = last_prices[position.symbol]

    result = rotation_targets(histories, config)
    intents = build_intents(result, snapshot, last_prices, config)
    intents = fit_turnover_budget(intents, snapshot.nav, config.risk.max_daily_turnover_pct)

    state = RiskState(
        nav=snapshot.nav,
        prior_close_nav=prior_close if prior_close is not None else snapshot.nav,
        high_water_nav=high_water if high_water is not None else snapshot.nav,
        halted=is_halted(journal_path.parent),
    )
    sleeve_caps = config.strategy.sleeve_caps[result.regime.value].as_dict()
    plan_pipeline = build_plan_pipeline(
        config_root,
        config,
        result.regime,
        result.regime_checks,
        prices,
        str(brief) if brief else None,
    )
    projected = snapshot.model_copy(deep=True)
    planned: list[PlannedOrder] = []
    for intent in intents:
        verdict = evaluate_intent(
            intent=intent,
            snapshot=projected,
            policy=config.risk,
            state=state,
            last_price=last_prices.get(intent.symbol, 0.0),
            universe_symbols=set(config.universe.by_symbol()),
            sleeve_by_symbol=config.universe.sleeve_by_symbol(),
            sleeve_caps=sleeve_caps,
        )
        order_pipeline = build_order_pipeline(
            intent, verdict, projected, config, result.regime, plan_pipeline.conviction
        )
        if verdict.allowed:
            quantity = min(intent.quantity, verdict.adjusted_quantity)
            state.orders_today += 1
            if intent.side == Side.BUY:
                state.traded_notional_today += quantity * intent.limit_price
            projected = apply_fill(projected, intent, quantity)
        planned.append(
            PlannedOrder(intent=intent, verdict=verdict, pipeline=order_pipeline)
        )

    trade_plan = TradePlan(
        as_of=as_of_date,
        account_id=snapshot.account_id,
        nav=snapshot.nav,
        cash=snapshot.cash,
        regime=result.regime,
        targets=result.targets,
        signals=result.signals,
        regime_checks=result.regime_checks,
        portfolio_vol=result.portfolio_vol,
        vol_scale=result.vol_scale,
        orders=planned,
        pipeline=plan_pipeline,
        notes=result.notes,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{as_of_date.isoformat()}-plan.json"
    md_path = out_dir / f"{as_of_date.isoformat()}-plan.md"
    json_path.write_text(json.dumps(trade_plan.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(_plan_markdown(trade_plan), encoding="utf-8")
    append_event(
        journal_path,
        "plan.created",
        {"plan_path": str(json_path), "plan": trade_plan.model_dump(mode="json")},
    )

    table = Table(title=f"Plan {as_of_date} - {result.regime.value}")
    table.add_column("Status")
    table.add_column("Side")
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Notional", justify="right")
    table.add_column("Risk", overflow="fold")
    for order in planned:
        status = "APPROVED" if order.verdict.allowed else "BLOCKED"
        notes = "; ".join([breach.rule for breach in order.verdict.breaches] + order.verdict.notes)
        table.add_row(
            status,
            order.intent.side.value,
            order.intent.symbol,
            str(order.effective_quantity),
            f"{order.intent.limit_price:.2f}",
            f"{order.effective_quantity * order.intent.limit_price:,.0f}",
            notes,
        )
    console.print(table)
    console.print(f"Wrote {json_path} and {md_path}")
    if not planned:
        console.print("No trades required.")


@app.command()
def fetch(
    symbols: list[str] = typer.Argument(None, help="Symbols; defaults to the configured universe."),
    num: int = typer.Option(370, "--num", help="Daily bars to request per symbol (max 370)."),
    out: Path = typer.Option(Path("data/prices.csv"), "--out"),
    merge: bool = typer.Option(True, "--merge/--no-merge"),
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    moomoo_binary: str = typer.Option("moomoo", "--moomoo-binary"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Fetch daily closes through the moomoo CLI and write the price CSV."""
    if not 60 <= num <= 370:
        raise typer.BadParameter("--num must be between 60 and 370")
    config = load_config(config_root)
    targets = symbols or [asset.symbol for asset in config.universe.assets]
    cli = MoomooCli(moomoo_binary)
    if not cli.available():
        console.print("moomoo CLI not found. See docs/runbooks/operations.md for setup.")
        raise typer.Exit(2)

    table = Table(title="Daily closes")
    table.add_column("Symbol")
    table.add_column("Bars", justify="right")
    table.add_column("Last date")
    table.add_column("Last close", justify="right")
    table.add_column("Status")

    rows: list[dict] = []
    failed: list[str] = []
    for symbol in targets:
        try:
            bars = extract_daily_bars(cli.kline(symbol, num))
        except MoomooCliError as exc:
            table.add_row(symbol, "0", "", "", f"FAIL: {exc}")
            failed.append(symbol)
            continue
        if not bars:
            table.add_row(symbol, "0", "", "", "FAIL: no bars returned")
            failed.append(symbol)
            continue
        rows.extend(
            {"date": bar_date.isoformat(), "symbol": symbol, "close": close}
            for bar_date, close in bars
        )
        table.add_row(
            symbol,
            str(len(bars)),
            bars[-1][0].isoformat(),
            f"{bars[-1][1]:,.2f}",
            "ok",
        )

    if not rows:
        console.print(table)
        console.print("No price rows fetched; nothing written.")
        raise typer.Exit(1)

    frame = pd.DataFrame(rows, columns=["date", "symbol", "close"])
    if merge and out.is_file():
        existing = pd.read_csv(out, parse_dates=["date"])
        existing["date"] = existing["date"].dt.strftime("%Y-%m-%d")
        frame = (
            pd.concat([existing, frame], ignore_index=True)
            .drop_duplicates(["date", "symbol"], keep="last")
            .sort_values(["date", "symbol"])
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)

    append_event(
        journal_path,
        "prices.fetched",
        {
            "path": str(out),
            "rows": len(frame),
            "symbols": sorted(frame["symbol"].unique().tolist()),
            "last_date": str(frame["date"].max()),
            "failed": failed,
        },
    )
    console.print(table)
    console.print(f"Wrote {len(frame):,} rows to {out}")
    if failed:
        console.print(f"Failed symbols: {', '.join(failed)}")
        raise typer.Exit(1)


@app.command()
def execute(
    plan_path: Path = typer.Option(..., "--plan", help="Plan JSON produced by the plan command."),
    account_id: str = typer.Option(..., "--account-id", help="Simulated Moomoo account ID."),
    yes: bool = typer.Option(False, "--yes", help="Confirm submission of approved orders."),
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    moomoo_binary: str = typer.Option("moomoo", "--moomoo-binary"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Re-validate and submit approved paper orders, one attempt each."""
    config = load_config(config_root)
    if not plan_path.is_file():
        raise typer.BadParameter(f"plan file not found: {plan_path}")
    try:
        plan = TradePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise typer.BadParameter(f"invalid plan: {exc}") from exc

    if account_id != plan.account_id:
        raise typer.BadParameter(
            f"account {account_id} does not match the plan account {plan.account_id}"
        )
    if account_id not in config.risk.account_allowlist:
        console.print(
            f"Refusing {account_id}: not in the paper account allowlist."
        )
        raise typer.Exit(2)

    approved = [
        order for order in plan.orders if order.verdict.allowed and order.effective_quantity > 0
    ]
    waited = [
        order for order in approved if order.pipeline is not None and order.pipeline.action == "wait"
    ]
    if waited:
        approved = [order for order in approved if order not in waited]
        for order in waited:
            append_event(
                journal_path,
                "gate.wait",
                {
                    "symbol": order.intent.symbol,
                    "side": order.intent.side.value,
                    "reason": "act/wait gate: low conviction on new non-defensive entry",
                },
            )
        console.print(
            f"Act/wait gate: withheld {len(waited)} low-conviction new entry(ies); journaled gate.wait."
        )
    if not approved:
        console.print("No approved orders in this plan.")
        return

    if is_halted(journal_path.parent):
        withheld = [order for order in approved if order.intent.side == Side.BUY]
        approved = [order for order in approved if order.intent.side == Side.SELL]
        for order in withheld:
            append_event(
                journal_path,
                "halt.skip",
                {"symbol": order.intent.symbol, "side": "buy", "reason": "halt active"},
            )
        console.print(f"Halt active: withheld {len(withheld)} buy(s); de-risking sells only.")
        if not approved:
            return

    cli = MoomooCli(moomoo_binary)
    if not cli.available():
        console.print("moomoo CLI not found. See docs/runbooks/operations.md for setup.")
        raise typer.Exit(2)

    symbols = sorted({order.intent.symbol for order in approved})
    try:
        quote_payload = cli.quote(symbols)
        accounts_payload = cli.sim_accounts()
    except MoomooCliError as exc:
        console.print(f"Pre-flight failed: {exc}")
        raise typer.Exit(1) from exc

    fresh_prices = {symbol: extract_last_price(quote_payload, symbol) for symbol in symbols}
    problems: list[str] = []
    for order in approved:
        symbol = order.intent.symbol
        price = fresh_prices.get(symbol)
        if price is None or price <= 0:
            problems.append(f"{symbol}: no fresh price")
            continue
        if price < config.risk.min_price:
            problems.append(f"{symbol}: price {price:.2f} below minimum")
        deviation = abs(order.intent.limit_price / price - 1.0)
        if deviation > config.risk.max_limit_deviation_pct:
            problems.append(
                f"{symbol}: limit {order.intent.limit_price:.2f} is {deviation:.1%} from last {price:.2f}"
            )
    if account_id not in json.dumps(accounts_payload):
        problems.append(f"account {account_id} not found in the simulated account list")
    if problems:
        console.print("Pre-flight rejected the batch; nothing submitted:")
        for problem in problems:
            console.print(f"- {problem}")
        raise typer.Exit(1)

    if not yes:
        table = Table(title="Execution preview (not submitted)")
        table.add_column("Side")
        table.add_column("Symbol")
        table.add_column("Qty", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Last", justify="right")
        for order in approved:
            table.add_row(
                order.intent.side.value,
                order.intent.symbol,
                str(order.effective_quantity),
                f"{order.intent.limit_price:.2f}",
                f"{fresh_prices[order.intent.symbol] or 0.0:.2f}",
            )
        console.print(table)
        console.print("Confirmation required: re-run the same command with --yes.")
        raise typer.Exit(2)

    submitted: list[dict] = []
    failures: list[dict] = []
    for index, order in enumerate(approved, start=1):
        intent = order.intent
        quantity = order.effective_quantity
        remark = f"jz-{plan.as_of.isoformat()}-{index}"
        request = {
            "plan": str(plan_path),
            "symbol": intent.symbol,
            "side": intent.side.value,
            "quantity": quantity,
            "limit_price": intent.limit_price,
            "remark": remark,
        }
        append_event(journal_path, "order.requested", request)
        try:
            if intent.side == Side.BUY:
                response = cli.sim_order_buy(
                    intent.symbol, quantity, account_id, intent.limit_price, remark=remark
                )
            else:
                response = cli.sim_order_sell(
                    intent.symbol, quantity, account_id, intent.limit_price, remark=remark
                )
        except MoomooCliError as exc:
            failure = {**request, "error": str(exc)[:500]}
            failures.append(failure)
            append_event(journal_path, "order.rejected", failure)
            break

        record = {**request, "order_id": extract_order_id(response) or ""}
        submitted.append(record)
        append_event(journal_path, "order.submitted", record)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = plan_path.with_name(f"execution-{stamp}.json")
    receipt_path.write_text(
        json.dumps(
            {
                "plan": str(plan_path),
                "account_id": account_id,
                "generated_at": stamp,
                "submitted": submitted,
                "failures": failures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    table = Table(title="Execution receipt")
    table.add_column("Status")
    table.add_column("Side")
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Order ID")
    for record in submitted:
        table.add_row(
            "SUBMITTED",
            record["side"],
            record["symbol"],
            str(record["quantity"]),
            f"{record['limit_price']:.2f}",
            record["order_id"] or "unknown",
        )
    for failure in failures:
        table.add_row(
            "FAILED",
            failure["side"],
            failure["symbol"],
            str(failure["quantity"]),
            f"{failure['limit_price']:.2f}",
            failure["error"][:60],
        )
    console.print(table)
    console.print(f"Wrote {receipt_path}")

    if failures:
        append_event(
            journal_path,
            "run.failed",
            {"stage": "execute", "plan": str(plan_path), "failures": failures},
        )
        console.print("Execution stopped after a failure; no retries were attempted.")
        raise typer.Exit(1)


@app.command()
def accounts(moomoo_binary: str = typer.Option("moomoo", "--moomoo-binary")) -> None:
    """List simulated accounts through the moomoo CLI."""
    cli = MoomooCli(moomoo_binary)
    if not cli.available():
        console.print("moomoo CLI not found. See docs/runbooks/operations.md for setup.")
        raise typer.Exit(2)
    try:
        console.print_json(data=cli.sim_accounts())
    except MoomooCliError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc


@app.command()
def quote(
    symbols: list[str] = typer.Argument(..., help="Symbols such as US.SPY US.QQQ"),
    moomoo_binary: str = typer.Option("moomoo", "--moomoo-binary"),
) -> None:
    """Fetch quotes through the moomoo CLI."""
    cli = MoomooCli(moomoo_binary)
    if not cli.available():
        console.print("moomoo CLI not found. See docs/runbooks/operations.md for setup.")
        raise typer.Exit(2)
    try:
        console.print_json(data=cli.quote(symbols))
    except MoomooCliError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc


@app.command()
def snapshot(
    directory: Path = typer.Option(..., "--dir", help="Run dir with accounts/cash/positions JSON."),
    account_id: str = typer.Option(..., "--account-id", help="Paper account the snapshots were fetched for."),
) -> None:
    """Write snapshot.json: env, account type/market and account linkage, file-visible for audit."""
    snap = snapshot_from_dir(directory, account_id)
    if snap.account_type is None or snap.market_id is None:
        raise typer.BadParameter(
            f"account ***{account_id[-3:]} not found in {directory}/accounts.json"
        )
    out_path = directory / "snapshot.json"
    out_path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    console.print(
        f"Wrote {out_path}: env={snap.env}, account_type={snap.account_type}, "
        f"market_id={snap.market_id}, account=***{account_id[-3:]}"
    )


@app.command("journal-verify")
def journal_verify(
    path: Path = typer.Option(Path("journal/events.jsonl"), "--path"),
) -> None:
    """Verify the hash chain of the audit journal."""
    ok, count, error = verify_chain(path)
    if ok:
        console.print(f"Journal OK: {count} events, chain intact.")
    else:
        console.print(f"Journal INVALID after {count} events: {error}")
        raise typer.Exit(1)


@app.command()
def halt(
    reason: str = typer.Option(..., "--reason", help="Why the agent is being halted."),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Engage the kill-switch: block buys, allow de-risking sells."""
    state = set_halt(journal_path.parent, True, reason)
    append_event(journal_path, "halt.engaged", state)
    console.print(f"Halted: {reason}")


@app.command()
def resume(
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Release the kill-switch after operator review."""
    state = set_halt(journal_path.parent, False, "operator resume")
    append_event(journal_path, "halt.released", state)
    console.print("Resumed: buys permitted again.")


@app.command("record-order")
def record_order(
    event: str = typer.Argument(..., help="order.requested, order.submitted, order.rejected, halt.skip or gate.wait."),
    data: str = typer.Option(..., "--data", help="JSON object with the event payload."),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Journal an order event from the MCP submission path (executor is the single writer)."""
    allowed = {"order.requested", "order.submitted", "order.rejected", "halt.skip", "gate.wait"}
    if event not in allowed:
        raise typer.BadParameter(f"event must be one of {sorted(allowed)}")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"--data must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("--data must be a JSON object")
    append_event(journal_path, event, payload)
    console.print(f"Journaled {event}.")


@app.command()
def persist(
    raw_dir: Path = typer.Option(..., "--raw", help="Directory of raw run artifacts."),
    git_dir: Path = typer.Option(..., "--git", help="Destination for sanitized, git-tracked copies."),
    bucket_dir: Path | None = typer.Option(None, "--bucket", help="OSS bucket mount for raw copies."),
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
) -> None:
    """Copy raw artifacts to the bucket and sanitized copies to git."""
    config = load_config(config_root)
    extra = os.environ.get("TYCHE_ALLOWED_ACCOUNT_IDS", "")
    account_ids = [*config.risk.account_allowlist, *(x.strip() for x in extra.split(",") if x.strip())]
    manifest = persist_run(raw_dir, git_dir, account_ids, bucket_dir)
    console.print(
        f"Persisted {len(manifest['raw'])} raw and {len(manifest['sanitized'])} sanitized file(s)."
    )


@app.command()
def calendar(
    at: str = typer.Option("", "--at", help="ISO timestamp to evaluate (default: now UTC)."),
    phase: str = typer.Option("", "--phase", help="Intended schedule phase for mismatch gating, e.g. opening_drive."),
    as_json: bool = typer.Option(False, "--json", help="Emit the gate result as JSON; exit 0=run, 1=skip."),
) -> None:
    """Calendar gate: should a scheduled run act now, and with which strategy?"""
    try:
        now = datetime.fromisoformat(at) if at else datetime.now(UTC)
    except ValueError as exc:
        raise typer.BadParameter(f"--at must be an ISO timestamp: {exc}") from exc
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    intended: SessionPhase | None = None
    if phase:
        try:
            intended = SessionPhase(phase)
        except ValueError as exc:
            choices = ", ".join(p.value for p in SessionPhase)
            raise typer.BadParameter(f"--phase must be one of: {choices}") from exc

    result = evaluate(now, intended)
    if as_json:
        console.print_json(result.model_dump_json())
        raise typer.Exit(0 if result.run else 1)

    verdict = "[bold green]RUN[/]" if result.run else "[bold red]SKIP[/]"
    console.print(f"{verdict}  {result.reason}")
    table = Table(title=f"Market gate · {result.now_et:%Y-%m-%d %H:%M %Z}")
    table.add_column("Field")
    table.add_column("Value", overflow="fold")
    table.add_row("Now (UTC)", f"{result.now_utc:%Y-%m-%d %H:%M}")
    table.add_row("Now (ET)", f"{result.now_et:%Y-%m-%d %H:%M %Z}")
    table.add_row("Trading day", "yes" if result.trading_day else "no")
    table.add_row("Half day", "yes" if result.half_day else "no")
    table.add_row("Holiday", result.holiday or "—")
    table.add_row("Session phase", result.phase.value)
    strategy = result.strategy
    table.add_row("Activity", strategy.activity)
    table.add_row("Sleeves", ", ".join(strategy.sleeves) or "—")
    table.add_row("New entries", "yes" if strategy.new_entries else "no")
    table.add_row("Max orders", str(strategy.max_orders))
    table.add_row("Event caution", "yes" if strategy.event_caution else "no")
    table.add_row("Risk note", strategy.risk_note)
    console.print(table)

    if result.events:
        events = Table(title="Events today")
        events.add_column("Name")
        events.add_column("Kind")
        events.add_column("ET time")
        for event in result.events:
            events.add_row(event.name, event.kind, event.time_et or "—")
        console.print(events)

    if result.next_run:
        nr = result.next_run
        minutes = nr.in_seconds // 60
        console.print(
            f"Next run: [bold]{nr.name}[/] ({nr.phase.value}) "
            f"{nr.utc:%Y-%m-%d %H:%M} UTC · {nr.et:%H:%M} ET · in {minutes} min"
        )


@app.command()
def schedules(
    start: date | None = typer.Option(None, "--start", help="Range start YYYY-MM-DD (default: today)."),
    end: date | None = typer.Option(None, "--end", help="Range end YYYY-MM-DD (default: start + 13 days)."),
    as_json: bool = typer.Option(False, "--json", help="Emit schedule defs as JSON for Qoder Forward."),
    hourly: bool = typer.Option(False, "--hourly", help="Emit the single gate-routed hourly cron (live desk cadence)."),
) -> None:
    """Emit calendar-gated Qoder Forward cron schedules (UTC) for a date range."""
    start = start or datetime.now(UTC).date()
    end = end or start + timedelta(days=13)
    try:
        defs = generate_hourly_schedules(start, end) if hourly else generate_schedules(start, end)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if as_json:
        console.print_json(json.dumps([d.model_dump(mode="json") for d in defs]))
        return
    table = Table(title=f"Forward schedules · {start} → {end} (UTC cron)")
    table.add_column("Name")
    table.add_column("Cron")
    table.add_column("Phase")
    table.add_column("Activity")
    table.add_column("ET")
    table.add_column("SGT")
    table.add_column("Days", justify="right")
    for definition in defs:
        table.add_row(
            definition.name, definition.cron,
            definition.phase.value if definition.phase else "gate-routed",
            definition.activity, definition.et_time, definition.sgt_time, str(definition.days),
        )
    console.print(table)
    console.print(
        f"{len(defs)} schedule(s); holidays and weekends excluded by computed day lists."
    )


@app.command()
def watchlist(
    path: Path = typer.Option(
        Path("data/watchlist.json"), "--path", help="Watchlist JSON (Drive working copy in cloud)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit watchlist + freshness as JSON."),
) -> None:
    """Validate the scout watchlist; exit 0 valid, 1 missing/invalid (scout must refresh)."""
    if not path.is_file():
        console.print(f"[bold red]MISSING[/] {path} — scout must build the watchlist")
        raise typer.Exit(1)
    try:
        book = Watchlist.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        console.print(f"[bold red]INVALID[/] {path}")
        console.print(str(exc))
        raise typer.Exit(1) from exc
    today = datetime.now(ET).date()
    stale = book.stale(today)
    active = book.active(today)
    if as_json:
        payload = book.model_dump(mode="json")
        payload.update(stale=stale, active_count=len(active), today=today.isoformat())
        console.print_json(json.dumps(payload))
        return
    verdict = "[bold yellow]STALE[/]" if stale else "[bold green]FRESH[/]"
    console.print(f"{verdict}  as of {book.as_of} · {len(active)} active / {len(book.entries)} entries")
    table = Table(title=f"Watchlist · {path}")
    table.add_column("Symbol")
    table.add_column("Sleeve")
    table.add_column("Strategy", overflow="fold")
    table.add_column("Entry zone", justify="right")
    table.add_column("Stop", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Expiry")
    table.add_column("Status")
    for entry in book.entries:
        table.add_row(
            entry.symbol, entry.sleeve, entry.strategy,
            f"{entry.entry_low:.2f}-{entry.entry_high:.2f}",
            f"{entry.stop:.2f}", f"{entry.target:.2f}",
            entry.expiry.isoformat(), entry.status,
        )
    console.print(table)


@app.command()
def approvals(
    path: Path = typer.Option(
        Path("data/approvals.json"), "--path", help="Operator envelope JSON (git-tracked, cloud-synced)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit envelope + validity as JSON."),
) -> None:
    """Validate the operator's pre-approved order envelope; exit 0 valid, 1 missing/invalid."""
    if not path.is_file():
        console.print(f"[bold red]MISSING[/] {path} — no pre-approved envelope; orders stay always_ask")
        raise typer.Exit(1)
    try:
        batch = ApprovalBatch.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        console.print(f"[bold red]INVALID[/] {path}")
        console.print(str(exc))
        raise typer.Exit(1) from exc
    today = datetime.now(ET).date()
    valid = batch.valid_on(today)
    if as_json:
        payload = batch.model_dump(mode="json")
        payload.update(valid_today=valid, today=today.isoformat())
        console.print_json(json.dumps(payload))
        return
    verdict = "[bold green]VALID TODAY[/]" if valid else "[bold yellow]NOT VALID TODAY[/]"
    console.print(f"{verdict}  as of {batch.as_of} · {len(batch.orders)} line(s) · budget {batch.max_orders}")
    table = Table(title=f"Approval envelope · {path}")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Max qty", justify="right")
    table.add_column("Limit bound", justify="right")
    for line in batch.orders:
        bound = f"<= {line.limit_max:.2f}" if line.side == "buy" else f">= {line.limit_min:.2f}"
        table.add_row(line.symbol, line.side, str(line.max_qty), bound)
    console.print(table)


@app.command()
def authorize(
    symbol: str = typer.Option(..., "--symbol"),
    side: str = typer.Option(..., "--side", help="buy or sell."),
    qty: int = typer.Option(..., "--qty"),
    limit: float | None = typer.Option(None, "--limit", help="Limit price; market orders are never envelope-authorized."),
    path: Path = typer.Option(Path("data/approvals.json"), "--path"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    at: str = typer.Option("", "--at", help="ISO timestamp for 'today' (default: now UTC)."),
) -> None:
    """Envelope gate for one order: exit 0 authorized, 1 denied (stay always_ask)."""
    if side not in {"buy", "sell"}:
        raise typer.BadParameter("--side must be buy or sell")
    try:
        now = datetime.fromisoformat(at) if at else datetime.now(UTC)
    except ValueError as exc:
        raise typer.BadParameter(f"--at must be an ISO timestamp: {exc}") from exc
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    today = now.astimezone(ET).date()

    def deny(reason: str) -> None:
        console.print_json(json.dumps({"authorized": False, "reason": reason, "today": today.isoformat()}))
        raise typer.Exit(1)

    if not path.is_file():
        deny(f"no envelope at {path}; operator has not pre-approved any batch")
    try:
        batch = ApprovalBatch.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        deny(f"envelope invalid: {exc.errors()[0]['msg']}")
    used = envelope_usage(journal_path, today)
    authorized, reason = authorize_order(
        batch, symbol=symbol, side=side, qty=qty, limit=limit, today=today, used=used
    )
    console.print_json(json.dumps({
        "authorized": authorized, "reason": reason, "used": used,
        "max_orders": batch.max_orders, "as_of": batch.as_of.isoformat(),
        "today": today.isoformat(),
    }))
    raise typer.Exit(0 if authorized else 1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
