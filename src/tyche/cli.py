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

from tyche.approvals import (
    TELEGRAM_APPROVAL_EVENT,
    ApprovalBatch,
    TelegramApproval,
    authorize_order,
    envelope_totals,
    envelope_usage,
    resolve_batch,
    telegram_approvals,
)
from tyche.broker import (
    MoomooCli,
    MoomooCliError,
    extract_daily_bars,
    extract_last_price,
    extract_order_id,
    snapshot_from_dir,
)
from tyche.config import load_config
from tyche.envelope import propose_exit_envelope
from tyche.events_cli import app as events_app
from tyche.execution_state import daily_usage
from tyche.freeze import lane_states, registration_events, verdict
from tyche.halt import effective_halt, repo_halt_path, set_halt
from tyche.journal import append_event, append_locked, journal_lock, read_events, verify_chain
from tyche.lanes import read_state
from tyche.lifecycle_cli import app as lifecycle_app
from tyche.market_calendar import (
    ET,
    SessionPhase,
    evaluate,
    generate_hourly_schedules,
    generate_schedules,
)
from tyche.models import AccountSnapshot, OrderIntent, PlannedOrder, Side, TradePlan, apply_fill
from tyche.monitor_cli import app as monitor_app
from tyche.nyse_calendar import diff_calendar, parse_nyse_page
from tyche.persist import persist_run
from tyche.pipeline import build_order_pipeline, build_plan_pipeline, rules_hash
from tyche.risk import RiskState, evaluate_intent
from tyche.strategies import build_intents, fit_turnover_budget, rotation_targets
from tyche.strategy_ledger import StrategyPolicy
from tyche.strategy_ledger import score as score_strategy
from tyche.tactical_cli import app as tactical_app
from tyche.trade_risk import compute_expectancy
from tyche.watchlist import Watchlist

app = typer.Typer(add_completion=False, help="Regime-aware ETF rotation agent.")
app.add_typer(lifecycle_app, name="lifecycle")
app.add_typer(tactical_app, name="tactical")
app.add_typer(events_app, name="events")
app.add_typer(monitor_app, name="monitor")
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
        lines.append("| Status | Action | Side | Symbol | Qty | Limit | Stop | Initial R | Notional | Risk notes |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        for order in plan.orders:
            status = "APPROVED" if order.verdict.allowed else "BLOCKED"
            action = order.pipeline.action if order.pipeline else "act"
            notes = "; ".join(
                [breach.rule for breach in order.verdict.breaches] + order.verdict.notes
            )
            stop = order.intent.stop_price
            if order.intent.side == Side.BUY and stop:
                risk_usd = order.effective_quantity * (order.intent.limit_price - stop)
                stop_cell = f"{stop:.2f}"
                risk_cell = f"${risk_usd:,.0f} ({risk_usd / plan.nav:.1%})"
            else:
                stop_cell = "—"
                risk_cell = "—"
            lines.append(
                f"| {status} | {action} | {order.intent.side.value} | {order.intent.symbol} | "
                f"{order.effective_quantity} | {order.intent.limit_price:.2f} | "
                f"{stop_cell} | {risk_cell} | "
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
                    (
                        f"- Initial risk: stop {order.intent.stop_price:.2f} · "
                        f"R ${sizing.effective_quantity * (order.intent.limit_price - order.intent.stop_price):,.0f} "
                        f"({sizing.effective_quantity * (order.intent.limit_price - order.intent.stop_price) / plan.nav:.2%} NAV)"
                        if order.intent.stop_price
                        else "- Initial risk: n/a (sell or legacy plan without stop)"
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
        strategy_summary = ", ".join(
            f"{s.id} top_n={s.top_n} target_vol={s.target_vol:.0%}"
            + ("" if s.enabled else " (disabled)")
            for s in config.strategies
        )
        table.add_row(
            "config",
            "ok",
            f"{len(config.universe.assets)} assets; {strategy_summary}",
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
    strategy_id: str = typer.Option(
        "", "--strategy", help="Playbook id (e.g. PB-001); required when several are enabled."
    ),
    out_dir: Path = typer.Option(Path("plans"), "--out"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Compute target weights, generate limit orders, and run the risk kernel."""
    config = load_config(config_root)
    if strategy_id:
        try:
            strategy = config.strategy_by_id(strategy_id)
        except KeyError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if not strategy.enabled:
            raise typer.BadParameter(f"strategy {strategy_id} is disabled")
        if strategy.kind != "rotation":
            raise typer.BadParameter(
                f"strategy {strategy_id} is a {strategy.kind} lane; it plans through its own command"
            )
    else:
        enabled = [s for s in config.rotation_strategies() if s.enabled]
        if len(enabled) != 1:
            ids = ", ".join(s.id for s in enabled) or "none"
            raise typer.BadParameter(
                f"--strategy is required when enabled strategies != 1 (enabled: {ids})"
            )
        strategy = enabled[0]
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
    if snapshot.broker_nav is not None and abs(snapshot.broker_nav - snapshot.nav) > max(1.0, snapshot.broker_nav * 0.001):
        raise typer.BadParameter(
            f"account snapshot does not reconcile at capture: broker {snapshot.broker_nav:,.2f} "
            f"vs computed {snapshot.nav:,.2f}; recapture cash/frozen/positions"
        )
    # Planning marks come from the price file; broker marks were reconciled above, and normal
    # overnight price movement must not read as a missing position or cash error.
    snapshot = snapshot.model_copy(update={"broker_nav": None})
    last_prices = {symbol: float(series.iloc[-1]) for symbol, series in histories.items()}
    for position in snapshot.positions:
        if position.symbol in last_prices:
            position.last_price = last_prices[position.symbol]

    result = rotation_targets(histories, config, strategy)
    intents = build_intents(result, snapshot, last_prices, config, strategy)
    intents = fit_turnover_budget(intents, snapshot.nav, config.risk.max_daily_turnover_pct)

    valid, _, error = verify_chain(journal_path)
    if not valid:
        raise typer.BadParameter(f"journal integrity: {error}")
    used_orders, used_notional = daily_usage(read_events(journal_path), as_of_date)
    state = RiskState(
        orders_today=used_orders, traded_notional_today=used_notional,
        nav=snapshot.nav,
        prior_close_nav=prior_close if prior_close is not None else snapshot.nav,
        high_water_nav=high_water if high_water is not None else snapshot.nav,
        halted=bool(effective_halt(journal_path.parent, journal_path.resolve().parent.parent).get("halted")),
    )
    sleeve_caps = strategy.sleeve_caps[result.regime.value].as_dict()
    plan_pipeline = build_plan_pipeline(
        config_root,
        strategy,
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
            intent, verdict, projected, config, strategy, result.regime, plan_pipeline.conviction
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
        risk = ""
        if order.intent.side == Side.BUY and order.intent.stop_price:
            risk_usd = order.effective_quantity * (order.intent.limit_price - order.intent.stop_price)
            risk = f"R ${risk_usd:,.0f} ({risk_usd / snapshot.nav:.1%})"
        table.add_row(
            status,
            order.intent.side.value,
            order.intent.symbol,
            str(order.effective_quantity),
            f"{order.intent.limit_price:.2f}",
            f"{order.effective_quantity * order.intent.limit_price:,.0f}",
            "; ".join(part for part in (risk, notes) if part),
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

    # Real paper accounts must use the complete-lifecycle gate. This older
    # standalone path has no durable ownership, revalidation or exit contract.
    if account_id not in {"SIM-DEMO-US", "SIM-TEST"}:
        console.print(
            "Legacy execution disabled for broker accounts: use lifecycle preview/approve, "
            "then lifecycle reserve and the paper MCP executor. --yes cannot bypass this gate."
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

    if effective_halt(journal_path.parent, journal_path.resolve().parent.parent).get("halted"):
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
def expectancy(
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Fee-net R-multiple expectancy from closed round trips in the journal (ADR 0016)."""
    config = load_config(config_root)
    report = compute_expectancy(read_events(journal_path), config.sleeve_map())
    if as_json:
        console.print_json(data=report.model_dump(mode="json"))
        return
    table = Table(title=f"Expectancy - {report.closed_n} closed, R on {report.r_n}")
    table.add_column("Sleeve")
    table.add_column("n", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("AvgWin R", justify="right")
    table.add_column("AvgLoss R", justify="right")
    table.add_column("E[R]", justify="right")
    table.add_column("Net $", justify="right")
    for sleeve in sorted(report.sleeves, key=lambda s: s.sleeve):
        table.add_row(
            sleeve.sleeve,
            str(sleeve.closed_n),
            f"{sleeve.win_rate:.0%}" if sleeve.win_rate is not None else "-",
            f"{sleeve.avg_win_r:.2f}" if sleeve.avg_win_r is not None else "-",
            f"{sleeve.avg_loss_r:.2f}" if sleeve.avg_loss_r is not None else "-",
            f"{sleeve.expectancy_r:.2f}" if sleeve.expectancy_r is not None else "-",
            f"{sleeve.pnl_net:,.2f}",
        )
    console.print(table)
    console.print(
        f"Overall E[R]: {report.expectancy_r if report.expectancy_r is not None else '-'} "
        f"| net ${report.pnl_net:,.2f} | fees ${report.fees_total:,.2f} "
        f"| unattributed fills: {report.unattributed_fills}"
    )
    for lot in report.open_lots:
        risk = f"{lot.risk_pct_nav:.2%} NAV" if lot.risk_pct_nav is not None else "no plan stop"
        console.print(f"Open {lot.symbol} {lot.qty} @ {lot.entry_price:.2f} stop {lot.stop_price} risk {risk}")
    if report.provisional:
        console.print("Provisional: fewer than 30 closed trades; do not size on this estimate.")


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
    shared = repo_halt_path(journal_path.resolve().parent.parent)
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_text(json.dumps({**state, "set_by": "operator (CLI)"}, indent=2), encoding="utf-8")
    console.print(f"Halted: {reason}")
    console.print("Shared flag written to data/halt.json - commit it (or use desk Controls) to reach cloud runs.")


@app.command()
def resume(
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Release the kill-switch after operator review."""
    state = set_halt(journal_path.parent, False, "operator resume")
    append_event(journal_path, "halt.released", state)
    shared = repo_halt_path(journal_path.resolve().parent.parent)
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_text(json.dumps({**state, "set_by": "operator (CLI)"}, indent=2), encoding="utf-8")
    console.print("Resumed: buys permitted again.")


@app.command("halt-status")
def halt_status(
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Report the effective kill-switch state across the journal and shared flags."""
    state = effective_halt(journal_path.parent, journal_path.resolve().parent.parent)
    if as_json:
        print(json.dumps(state))
        return
    if state.get("halted"):
        console.print(
            f"HALTED: {state.get('reason', '')} (source={state.get('source')}, ts={state.get('ts')})"
        )
    else:
        console.print("Not halted: buys permitted.")


@app.command("record-order")
def record_order(
    event: str = typer.Argument(
        ...,
        help="order.requested, order.submitted, order.filled, order.rejected, halt.skip or gate.wait.",
    ),
    data: str = typer.Option(..., "--data", help="JSON object with the event payload."),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
) -> None:
    """Journal an order event from the MCP submission path (executor is the single writer)."""
    allowed = {
        "order.requested",
        "order.submitted",
        "order.filled",
        "order.rejected",
        "halt.skip",
        "gate.wait",
    }
    if event not in allowed:
        raise typer.BadParameter(f"event must be one of {sorted(allowed)}")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"--data must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("--data must be a JSON object")
    if event == "order.filled":
        missing = [
            key
            for key in ("symbol", "side", "quantity", "price")
            if payload.get(key) in (None, "")
        ]
        if missing or payload.get("side") not in ("buy", "sell"):
            raise typer.BadParameter(
                "order.filled requires symbol, side (buy|sell), quantity, price "
                f"(missing/invalid: {missing or ['side']})"
            )
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
    if result.overlay_error:
        console.print(f"[bold red]Event overlay error:[/] {result.overlay_error}")
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


@app.command("calendar-check")
def calendar_check(
    source: Path = typer.Option(
        ..., "--source", help="Saved WebFetch readable output of nyse.com/trade/hours-calendars."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the drift report as JSON."),
) -> None:
    """Read-only NYSE calendar drift check: exit 0 in-sync, 1 changed/uncertain (alert operator).

    Never writes the calendar. The desk runs this once per day at pre-market; a
    non-zero exit means alert the operator with the diff and propose a reviewed
    re-pin (scripts/refresh_calendar.py) — never auto-apply.
    """
    if not source.is_file():
        console.print(f"[bold red]MISSING[/] {source} — fetch the NYSE page via WebFetch first")
        raise typer.Exit(1)
    parsed = parse_nyse_page(source.read_text(encoding="utf-8"))
    report = diff_calendar(parsed)
    clean = not report["changed"] and not report["uncertain"]
    if as_json:
        console.print_json(json.dumps(report))
        raise typer.Exit(0 if clean else 1)
    if report["uncertain"]:
        console.print("[bold yellow]UNCERTAIN[/] — parse incomplete; manual review needed")
        for warning in report["warnings"]:
            console.print(f"  · {warning}")
    if report["changed"]:
        console.print("[bold yellow]CHANGED[/] — NYSE calendar differs from the pinned tables")
        for year in report["new_years"]:
            console.print(f"  · new year published: {year}")
        if report["changes"]:
            table = Table(title="Calendar drift")
            table.add_column("Kind")
            table.add_column("Date")
            table.add_column("Action")
            table.add_column("Name", overflow="fold")
            for change in report["changes"]:
                table.add_row(change["kind"], change["date"], change["action"], change["name"])
            console.print(table)
        console.print("Propose a reviewed re-pin; do NOT auto-apply.")
    elif not report["uncertain"]:
        years = ", ".join(str(y) for y in report["years_source"])
        console.print(f"[bold green]IN SYNC[/] — pinned calendar matches NYSE ({years})")
    raise typer.Exit(0 if clean else 1)


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

    if side == "buy" and effective_halt(journal_path.parent, journal_path.resolve().parent.parent).get("halted"):
        deny("kill-switch engaged - buys blocked, de-risking sells still allowed")
    valid, _, error = verify_chain(journal_path)
    if not valid:
        deny(f"journal integrity: {error}")
    events = read_events(journal_path)
    # Within my bounds (same-day envelope) wins; otherwise today's journaled Telegram approvals.
    batch, mode, how = resolve_batch(path, events, today)
    if batch is None:
        deny(how)
    used = envelope_usage(journal_path, today)
    used_qty, used_notional = envelope_totals(events, today, symbol, side)
    # Legacy envelope checks are stock-only; options use the exact-contract tactical gate.
    from tyche.models import looks_like_option
    if looks_like_option(symbol):
        deny("option requires a verified contract and tactical reservation")
    authorized, reason = authorize_order(
        batch, symbol=symbol, side=side, qty=qty, limit=limit, today=today, used=used,
        used_qty=used_qty, used_notional=used_notional,
    )
    console.print_json(json.dumps({
        "authorized": authorized, "reason": reason, "mode": mode, "authority": how, "used": used,
        "max_orders": batch.max_orders, "as_of": batch.as_of.isoformat(),
        "today": today.isoformat(),
    }))
    raise typer.Exit(0 if authorized else 1)


@app.command("approve-telegram")
def approve_telegram(
    proposals: Path = typer.Argument(..., help="The proposal file given to scripts/telegram.py wait-for-reply."),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    at: str = typer.Option("", "--at", help="ISO timestamp for 'today' (default: now UTC)."),
) -> None:
    """Ask me: journal the operator's Telegram /approve N as today's order authorization.

    Reads `<proposals>.approved.json`, which `wait-for-reply` writes only from the numbered
    `/approve` branch, and appends one `approval.telegram` event per approved proposal that
    carries an `order` block. Idempotent per (ref, n). An approved proposal without an
    `order` block is reported and authorizes nothing: the yes must name the exact order.
    Exit 0 when at least one approval is journaled or already was, 1 otherwise.
    """
    try:
        now = datetime.fromisoformat(at) if at else datetime.now(UTC)
    except ValueError as exc:
        raise typer.BadParameter(f"--at must be an ISO timestamp: {exc}") from exc
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    today = now.astimezone(ET).date()
    sidecar = proposals.with_name(proposals.name + ".approved.json")

    def finish(payload: dict, code: int) -> None:
        console.print_json(json.dumps({**payload, "today": today.isoformat()}, default=str))
        raise typer.Exit(code)

    if not sidecar.is_file():
        finish({"journaled": [], "error": f"no approvals at {sidecar}; wait-for-reply approved nothing"}, 1)
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        ref = str(data["ref"])
        rows = data["approved"]
        assert isinstance(rows, list)
    except (json.JSONDecodeError, OSError, KeyError, TypeError, AssertionError):
        finish({"journaled": [], "error": f"{sidecar} is unreadable or not a wait-for-reply approval file"}, 1)
    valid, _, error = verify_chain(journal_path)
    if not valid:
        finish({"journaled": [], "error": f"journal integrity: {error}"}, 1)
    already = {(a.ref, a.n) for a in telegram_approvals(read_events(journal_path), today)}
    journaled: list[dict] = []
    skipped: list[dict] = []
    with journal_lock(journal_path):
        for row in rows:
            n = row.get("n") if isinstance(row, dict) else None
            order = row.get("order") if isinstance(row, dict) else None
            if not isinstance(order, dict):
                skipped.append({"n": n, "why": "approved proposal carries no order block; nothing authorized"})
                continue
            try:
                approval = TelegramApproval.model_validate({
                    **order, "as_of": today, "ref": ref, "n": n, "decided_at": str(row.get("decided_at") or "")})
            except ValidationError as exc:
                skipped.append({"n": n, "why": f"order block invalid: {exc.errors()[0]['msg']}"})
                continue
            if (approval.ref, approval.n) in already:
                journaled.append({**approval.model_dump(mode="json"), "already": True})
                continue
            append_locked(journal_path, TELEGRAM_APPROVAL_EVENT, approval.model_dump(mode="json"))
            journaled.append(approval.model_dump(mode="json"))
    finish({"ref": ref, "journaled": journaled, "skipped": skipped,
            "note": "Authorization for exactly these orders today; audit and reserve still run before one paper order."},
           0 if journaled else 1)


@app.command("propose-envelope")
def propose_envelope(
    account: Path = typer.Option(..., "--account", help="Verified paper AccountSnapshot JSON."),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    book: Path = typer.Option(Path("data/watchlist.json"), "--watchlist",
                              help="Fallback levels for positions with no journaled contract."),
    out: Path = typer.Option(Path("data/approvals.proposed.json"), "--out"),
    config_root: Path = typer.Option(Path("."), "--config-root"),
    collar: float | None = typer.Option(None, "--collar-pct",
                                        help="Override risk.exit_collar_pct (floor width below the stop)."),
    at: str = typer.Option("", "--at", help="ISO timestamp for 'today' (default: now)."),
    as_json: bool = typer.Option(False, "--json", help="Emit the draft payload instead of a table."),
) -> None:
    """Draft the operator's exit note from what is held and the stops already journaled.

    Read-only against the broker and the journal. It writes the DRAFT file and never
    `data/approvals.json`: arming is the operator's click, and a proposal that could
    auto-arm would be an approval written by the wrong party.
    """
    config = load_config(config_root)
    pct = config.risk.exit_collar_pct if collar is None else collar
    try:
        now = datetime.fromisoformat(at) if at else datetime.now(UTC)
    except ValueError as exc:
        raise typer.BadParameter(f"--at must be an ISO timestamp: {exc}") from exc
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    today = now.astimezone(ET).date()

    def report(payload: dict, code: int) -> None:
        if as_json:
            console.print_json(json.dumps(payload, default=str))
        elif message := payload.get("error"):
            console.print(f"[red]{message}[/]")
        raise typer.Exit(code)

    if not account.is_file():
        report({"draft": False, "error": f"no snapshot at {account}; run 'tyche snapshot' first"}, 1)
    if not journal_path.is_file():
        report({"draft": False, "error": f"no journal at {journal_path}; levels are read from it"}, 1)
    ok, _, error = verify_chain(journal_path)
    if not ok:
        report({"draft": False, "error": f"journal integrity: {error}"}, 1)
    try:
        snapshot = AccountSnapshot.model_validate_json(account.read_text(encoding="utf-8"))
    except ValidationError as exc:
        report({"draft": False, "error": f"snapshot invalid: {exc.errors()[0]['msg']}"}, 1)
        return
    watchlist = None
    problems: list[str] = []
    if book.is_file():
        try:
            watchlist = Watchlist.model_validate_json(book.read_text(encoding="utf-8"))
        except ValidationError as exc:
            problems.append(f"watchlist ignored ({book}): {exc.errors()[0]['msg']}")

    proposal = propose_exit_envelope(
        snapshot, read_events(journal_path), today=today, collar_pct=pct,
        max_orders_per_day=config.risk.max_orders_per_day, watchlist=watchlist,
        options_enabled=config.tactical.options_enabled, now=now,
    )
    payload = proposal.as_payload()
    payload["problems"] = problems + proposal.problems
    payload["out"] = str(out)
    if not proposal.armable:
        payload["draft"] = False
        payload["error"] = "nothing to propose: no open paper position has a usable stop"
        if out.is_file():  # a stale draft must not sit there looking armable
            out.unlink()
        report(payload, 1)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    # The same shape the desk writes: the batch plus where every number came from. The desk
    # reader also accepts a bare batch, but one file should not mean two formats.
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["draft"] = True
    if not as_json:
        table = Table(title=f"Draft exit note for {today} - collar {pct:.1%} below each stop (DRAFT, not armed)")
        table.add_column("Symbol"); table.add_column("Sell up to"); table.add_column("Floor")
        table.add_column("Stop"); table.add_column("Level from"); table.add_column("Bound")
        for row in proposal.lines:
            table.add_row(row["symbol"], str(row["max_qty"]), f"{row['limit_min']:.2f}",
                          f"{row['stop']:.2f}", row["source_label"], "yes" if row["bound"] else "no")
        console.print(table)
        for row in proposal.skipped:
            console.print(f"[yellow]not proposed[/] {row['symbol']}: {row['why']}")
        for problem in payload["problems"]:
            console.print(f"[red]problem[/] {problem}")
        console.print(f"Draft written to {out}. Arm it from the desk Risk panel; nothing arms itself.")
    report(payload, 0)


@app.command("strategies")
def strategies_cmd(
    config_root: Path = typer.Option(Path("."), "--config-root"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Report which playbooks are live: lane config, overridden by the desk switch file."""
    config = load_config(config_root)
    rows = config.playbook_switches()
    if as_json:
        print(json.dumps({"strategies": rows, "switch_file": read_state(config.root)}, default=str))
        return
    table = Table(title="Playbook switches")
    table.add_column("id")
    table.add_column("lane")
    table.add_column("live", justify="center")
    table.add_column("decided by")
    table.add_column("rules file")
    for row in rows:
        table.add_row(
            row["strategy_id"],
            row["lane"],
            "yes" if row["enabled"] else "no",
            row["source"],
            row["rules_file"],
        )
    console.print(table)
    problem = next((row["switch_file_problem"] for row in rows if row["switch_file_problem"]), None)
    if problem:
        console.print(f"[red]switch file ignored:[/red] {problem}")
    console.print(
        "Live for this run: " + (", ".join(config.enabled_playbook_ids()) or "none")
    )


@app.command("rules-freeze")
def rules_freeze(
    config_root: Path = typer.Option(Path("."), "--config-root"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    reason: str = typer.Option("", "--reason",
                               help="Required with --record: what moved in the bytes, and why."),
    record: bool = typer.Option(False, "--record",
                                help="Append the rules.frozen / rules.refrozen rows. Off by default."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Put each lane's rules hash on the journal, so a re-freeze is a record rather than git archaeology.

    Read-only unless `--record` is passed. Exit `0` means every lane's current hash is already on the
    chain; `1` means unregistered drift exists and nothing was written; `2` means this command could not
    judge - a refused lane, a broken chain, or a `--record` without a `--reason` - and is never "all
    frozen". It cannot register a lane whose playbook document disagrees with the kernel: the doc edit is
    the review, and journaling around it is exactly how a freeze hash launders a rules change (L-030).
    """
    if record and not reason.strip():
        console.print("[bold red]NO-GO[/] --record needs --reason. A freeze row with no stated cause is "
                      "the hand-written provenance this command exists to retire (L-035).")
        raise typer.Exit(2)
    states, notes = lane_states(config_root, read_events(journal_path))
    if not states:
        console.print(f"[bold red]NO-GO[/] no lane's rules could be hashed from {config_root}. "
                      "That is not the same as 'nothing to register'.")
        raise typer.Exit(2)
    chain_ok, chain_events, chain_error = verify_chain(journal_path)
    if record and not chain_ok:
        console.print(f"[bold red]NO-GO[/] journal invalid at {journal_path}: {chain_error}; nothing written.")
        raise typer.Exit(2)
    outcome = verdict(states)
    blocked = [state.blocked for state in states if state.blocked]
    # One refused lane holds the whole run: registering the healthy lanes around it would leave the
    # chain describing a review that has not happened yet.
    pending = [] if blocked else registration_events(states, reason or "<not recorded: check only>")
    report = {
        "status": outcome, "config_root": str(config_root),
        "journal": {"path": str(journal_path), "events": chain_events, "valid": chain_ok,
                    "error": chain_error},
        "lanes": [state.as_dict() for state in states], "notes": notes,
        "would_record": [{"type": event_type, "payload": payload} for event_type, payload in pending],
    }
    written: list[dict] = []
    if record and pending:
        try:
            with journal_lock(journal_path):
                for event_type, payload in pending:
                    written.append(append_locked(journal_path, event_type, payload))
        except (RuntimeError, ValueError) as exc:
            console.print(f"[bold red]NO-GO[/] {exc}; the freeze rows were not written.")
            raise typer.Exit(2) from exc
        report["recorded"] = [{"type": event["type"], "hash": event["hash"],
                               "strategy": event["payload"]["strategy"]} for event in written]
    if as_json:
        print(json.dumps(report, default=str))
    else:
        table = Table(title=f"Rules freeze ({'recording' if record else 'check only'})")
        table.add_column("lane")
        table.add_column("bytes")
        table.add_column("playbook declares")
        table.add_column("journal holds")
        table.add_column("state")
        for state in states:
            state_text = ("REFUSED" if state.blocked
                          else "registered" if not state.needs_record else state.event_type)
            table.add_row(state.strategy_id, state.computed, state.declared or "-",
                          f"{state.recorded or '-'}"
                          + (f" @{(state.recorded_ts or '')[:10]}" if state.recorded else ""),
                          state_text)
        console.print(table)
        if not chain_ok:
            console.print(f"[bold red]journal does not verify:[/] {chain_error} - the \"journal holds\" "
                          "column is not provenance, so no lane here can be called registered.")
        for text in blocked:
            console.print(f"[red]refused:[/red] {text}")
        for text in notes:
            console.print(f"[yellow]note:[/yellow] {text}")
        if written:
            for event in written:
                console.print(f"[green]journaled[/green] {event['type']} "
                              f"{event['payload']['strategy']} -> {event['payload']['new_hash']}")
        elif blocked:
            console.print("[red]nothing written:[/red] one refused lane holds the whole run")
        elif outcome == "pending":
            console.print(f"[yellow]{len(pending)} lane(s) need registering[/yellow] "
                          "- `tyche rules-freeze --record --reason \"...\"`")
        elif outcome == "registered":
            console.print("[green]every lane's current rules hash is on the chain[/green]")
    # A chain that does not verify cannot certify provenance in either direction: "registered" read off a
    # broken chain is not a fact about the bytes, so check mode refuses to call it that (exit 2, not 0/1).
    if not chain_ok:
        raise typer.Exit(2)
    if record:
        raise typer.Exit(2 if blocked else 0)
    raise typer.Exit({"registered": 0, "pending": 1, "blocked": 2}[outcome])


@app.command("fib-scan")
def fib_scan(
    bars: Path = typer.Option(..., "--bars", help="Long CSV date,symbol,open,high,low,close[,volume]."),
    book: Path = typer.Option(..., "--book", help="Where to write the LifecycleBook of proposals."),
    account: Path | None = typer.Option(None, "--account", help="Account snapshot JSON (NAV source)."),
    strategy_id: str = typer.Option("PB-007", "--strategy"),
    as_of: str | None = typer.Option(None, "--as-of", help="Use bars up to this ISO date only."),
    flat_by: str | None = typer.Option(None, "--flat-by", help="Latest holding deadline (ISO date), e.g. the window's last session."),
    held: str = typer.Option("", "--held", help="Comma-separated symbols already held or planned; skipped."),
    config_root: Path = typer.Option(Path.cwd(), "--config-root"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    record: bool = typer.Option(False, "--record", help="Journal plan.created for the proposals (R attribution needs it)."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Deterministic fib-pullback scan: daily bars -> lifecycle plan proposals (no approval, no order).

    Proposals are unapproved. They take the usual path: preview, researcher review, exact-order
    audit and the operator's `tyche lifecycle approve`. With --record the scan journals one
    plan.created carrying each intent's limit and stop, which is what fee-net R later reads.
    """
    from tyche.lifecycle import LifecycleBook
    from tyche.market_calendar import evaluate
    from tyche.strategies.fib_pullback import file_sha256, load_ohlc, scan

    config = load_config(config_root)
    try:
        strategy = config.strategy_by_id(strategy_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if strategy.kind != "fib_pullback":
        raise typer.BadParameter(f"{strategy_id} is a {strategy.kind} lane, not fib_pullback")
    try:
        cutoff = date.fromisoformat(as_of) if as_of else None
        latest = date.fromisoformat(flat_by) if flat_by else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not bars.is_file():
        raise typer.BadParameter(f"bars file not found: {bars}")
    snapshot, _, _ = _load_account(account)
    now = datetime.now(UTC)
    gate = evaluate(now, root=config_root)
    open_symbols = {s.strip() for s in held.split(",") if s.strip()}
    open_symbols |= {p.symbol for p in snapshot.positions}
    result = scan(load_ohlc(bars, cutoff), strategy, snapshot.nav, rules_hash(config_root, strategy_id), now,
                  open_symbols=open_symbols, event_names=[e.get("name", "") for e in gate.events],
                  bars_sha256=file_sha256(bars), latest_deadline=latest)
    book.parent.mkdir(parents=True, exist_ok=True)
    proposals = LifecycleBook(plans=result.plans, news_checked_at=now, news_feed_ok=False)
    book.write_text(proposals.model_dump_json(indent=2), encoding="utf-8")
    if record and result.plans:
        orders = [{"intent": OrderIntent(
            symbol=plan.symbol, side=Side.BUY, quantity=plan.quantity, limit_price=plan.entry_high,
            stop_price=plan.stop.price, strategy_id=strategy_id, setup_id=plan.plan_id,
            reason=f"{strategy_id} fib pullback proposal; unapproved",
        ).model_dump(mode="json"), "plan_hash": plan.fingerprint()} for plan in result.plans]
        append_event(journal_path, "plan.created", {
            "plan_path": str(book), "strategy_id": strategy_id, "source": "tyche fib-scan",
            "plan": {"as_of": result.as_of.isoformat() if result.as_of else None, "nav": snapshot.nav,
                     "account_id": snapshot.account_id, "strategy_id": strategy_id,
                     "rules_hash": result.rules_hash, "bars_sha256": result.bars_sha256, "orders": orders},
        })
    summary = {
        "strategy_id": strategy_id, "as_of": result.as_of.isoformat() if result.as_of else None,
        "rules_hash": result.rules_hash, "nav": snapshot.nav, "bars_sha256": result.bars_sha256,
        "book": str(book), "recorded": bool(record and result.plans),
        "plans": [{"plan_id": p.plan_id, "plan_hash": p.fingerprint(), "symbol": p.symbol,
                   "quantity": p.quantity, "entry_low": p.entry_low, "entry_high": p.entry_high,
                   "stop": p.stop.price, "target": p.take_profit.price,
                   "entry_expires_at": p.entry_expires_at.isoformat(),
                   "exit_deadline": p.exit_deadline.isoformat()} for p in result.plans],
        "signals_without_slot": [s.symbol for s in result.signals if s.symbol not in {p.symbol for p in result.plans}],
        "rejected": result.rejected,
        "authorization": "none; preview, review, audit and tyche lifecycle approve are still required",
    }
    if json_out:
        console.print_json(json.dumps(summary))
        return
    console.print(f"{strategy_id} scan as of {summary['as_of']} (rules {result.rules_hash}): "
                  f"{len(result.plans)} proposal(s) -> {book}")
    for row in summary["plans"]:
        console.print(f"  {row['symbol']}: qty {row['quantity']} zone {row['entry_low']}-{row['entry_high']} "
                      f"stop {row['stop']} target {row['target']} hash {row['plan_hash'][:12]}")
    for symbol, why in sorted(result.rejected.items()):
        console.print(f"  skip {symbol}: {why}")


@app.command("strategy-score")
def strategy_score(
    strategy_id: str = typer.Option("PB-004", "--strategy"),
    sleeve: str = typer.Option("equity", "--sleeve"),
    journal_path: Path = typer.Option(Path("journal/events.jsonl"), "--journal"),
    config_root: Path = typer.Option(Path("."), "--config-root"),
    min_closed: int = typer.Option(30, "--min-closed", min=1),
    min_expectancy_r: float = typer.Option(0.0, "--min-expectancy-r"),
    min_profit_factor: float = typer.Option(1.2, "--min-profit-factor"),
    max_drawdown_pct: float = typer.Option(0.04, "--max-drawdown-pct"),
    record: bool = typer.Option(False, "--record"),
) -> None:
    """Score one strategy from the journal and decide mount/hold/retire."""
    ok, _, error = verify_chain(journal_path)
    if not ok:
        raise typer.BadParameter(f"journal integrity: {error} or journal missing")
    config = load_config(config_root)
    sleeves = dict(config.sleeve_map())
    sleeves.update({symbol: sleeve for symbol in config.scalp.symbols})
    policy = StrategyPolicy(min_closed=min_closed, min_expectancy_r=min_expectancy_r,
                            min_profit_factor=min_profit_factor, max_drawdown_pct=max_drawdown_pct)
    decision = score_strategy(read_events(journal_path), strategy_id, sleeve, sleeves, policy)
    if record:
        append_event(journal_path, "strategy.decision", decision.model_dump(mode="json"))
    console.print_json(decision.model_dump_json())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
