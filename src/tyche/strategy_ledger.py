"""Strategy mount/retire ledger: explicit scorecards and recorded decisions.

One record per strategy. A strategy is mounted only on non-provisional evidence
(>= min_closed fee-net round trips) with positive R expectancy, an acceptable
profit factor and bounded drawdown; it is retired when expectancy decays or
drawdown breaches the limit. Every decision is appended to the hash-chained
journal so the mount/retire history is auditable, never inferred after the fact.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tyche.trade_risk import ClosedTrade, ExpectancyReport, compute_expectancy

Action = Literal["mount", "hold", "retire"]


class StrategyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_closed: int = Field(default=30, ge=1)
    min_expectancy_r: float = 0.0
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = Field(default=0.04, gt=0, le=0.5)


class Scorecard(BaseModel):
    strategy_id: str
    sleeve: str
    closed_n: int
    wins: int
    losses: int
    win_rate: float | None = None
    avg_win_r: float | None = None
    avg_loss_r: float | None = None
    expectancy_r: float | None = None
    profit_factor: float | None = None
    pnl_net: float = 0.0
    fees_total: float = 0.0
    max_drawdown_pct: float | None = None
    provisional: bool = True
    open_lots: int = 0


class StrategyDecision(BaseModel):
    strategy_id: str
    action: Action
    rule: str
    at: datetime
    scorecard: Scorecard


def scorecard(strategy_id: str, report: ExpectancyReport, sleeve: str) -> Scorecard:
    trades: list[ClosedTrade] = [t for t in report.closed_trades if t.sleeve == sleeve]
    gross_win = sum(t.pnl_net for t in trades if t.pnl_net > 0)
    gross_loss = -sum(t.pnl_net for t in trades if t.pnl_net < 0)
    wins = sum(1 for t in trades if t.pnl_net > 0)
    losses = sum(1 for t in trades if t.pnl_net < 0)
    equity = peak = drawdown = 0.0
    for trade in sorted(trades, key=lambda t: t.exit_ts):
        equity += trade.pnl_net
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    nav = next((abs(t.pnl_net / t.realized_pct_nav) for t in trades
                if t.realized_pct_nav), None)
    return Scorecard(
        strategy_id=strategy_id, sleeve=sleeve, closed_n=len(trades),
        wins=wins, losses=losses,
        win_rate=wins / (wins + losses) if wins + losses else None,
        avg_win_r=report.avg_win_r, avg_loss_r=report.avg_loss_r,
        expectancy_r=report.expectancy_r,
        profit_factor=round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
        pnl_net=round(sum(t.pnl_net for t in trades), 4),
        fees_total=round(sum(t.fees for t in trades), 4),
        max_drawdown_pct=round(drawdown / nav, 6) if nav and nav > 0 else None,
        provisional=len(trades) < StrategyPolicy().min_closed,
        open_lots=sum(1 for lot in report.open_lots if lot.sleeve == sleeve),
    )


def decide(card: Scorecard, policy: StrategyPolicy, at: datetime,
           current: Literal["mounted", "retired", "candidate"] = "candidate") -> StrategyDecision:
    """Deterministic mount/retire rule. Insufficient evidence holds, never guesses."""
    if card.closed_n < policy.min_closed:
        return StrategyDecision(strategy_id=card.strategy_id, action="hold",
                                rule=f"provisional: {card.closed_n}/{policy.min_closed} closed trades",
                                at=at, scorecard=card)
    e = card.expectancy_r
    pf = card.profit_factor
    dd = card.max_drawdown_pct
    if e is None or pf is None:
        return StrategyDecision(strategy_id=card.strategy_id, action="hold",
                                rule="closed trades lack fee-net R attribution", at=at, scorecard=card)
    if current == "mounted" and (e < policy.min_expectancy_r
                                 or (dd is not None and dd > policy.max_drawdown_pct)):
        return StrategyDecision(strategy_id=card.strategy_id, action="retire",
                                rule=(f"decay: E[R] {e:.2f} below {policy.min_expectancy_r:.2f}"
                                      f" or drawdown {dd if dd is None else round(dd, 4)}"
                                      f" above {policy.max_drawdown_pct:.2%}"),
                                at=at, scorecard=card)
    if e > policy.min_expectancy_r and pf >= policy.min_profit_factor and (
            dd is None or dd <= policy.max_drawdown_pct):
        action = "hold" if current == "mounted" else "mount"
        return StrategyDecision(strategy_id=card.strategy_id, action=action,
                                rule=(f"E[R] {e:.2f} > {policy.min_expectancy_r:.2f},"
                                      f" PF {pf:.2f} >= {policy.min_profit_factor:.2f},"
                                      f" DD {dd if dd is None else round(dd, 4)}"
                                      f" <= {policy.max_drawdown_pct:.2%}"),
                                at=at, scorecard=card)
    return StrategyDecision(strategy_id=card.strategy_id, action="hold",
                            rule=f"below thresholds: E[R] {e:.2f}, PF {pf:.2f}", at=at, scorecard=card)


def strategy_events(events: list[dict], strategy_id: str) -> list[dict]:
    """Journal slice attributable to one strategy: its plans, requests and fills."""
    picked = []
    for event in events:
        payload = event.get("payload", {})
        if event.get("type") == "plan.created":
            rows = payload.get("plan", {}).get("orders", [])
            if any(row.get("intent", {}).get("strategy_id") == strategy_id for row in rows):
                picked.append(event)
            continue
        if payload.get("strategy_id") == strategy_id:
            picked.append(event)
    return picked


def status_from_journal(events: list[dict], strategy_id: str) -> Literal["mounted", "retired", "candidate"]:
    status: Literal["mounted", "retired", "candidate"] = "candidate"
    for event in events:
        payload = event.get("payload", {})
        if event.get("type") != "strategy.decision" or payload.get("strategy_id") != strategy_id:
            continue
        action = payload.get("action")
        if action == "mount":
            status = "mounted"
        elif action == "retire":
            status = "retired"
    return status


def score(
    events: list[dict], strategy_id: str, sleeve: str, sleeves: dict[str, str],
    policy: StrategyPolicy | None = None, at: datetime | None = None,
) -> StrategyDecision:
    """Score one strategy from the journal and emit the deterministic decision."""
    policy = policy or StrategyPolicy()
    report = compute_expectancy(strategy_events(events, strategy_id), sleeves)
    card = scorecard(strategy_id, report, sleeve)
    card.provisional = card.closed_n < policy.min_closed
    return decide(card, policy, at or datetime.now(UTC), status_from_journal(events, strategy_id))
