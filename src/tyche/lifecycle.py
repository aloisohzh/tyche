"""Paper-only, long-only trade lifecycle decisions. No broker writes occur here.

Plans are immutable approval contracts; reviews are replaceable evidence. An
expired review blocks entries, never an approved stop/target/time exit. Runtime
state must be kept on the shared Drive, not an ephemeral repository mount.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from tyche.config import AppConfig
from tyche.market_calendar import ET, SessionPhase, evaluate, is_trading_day, regular_close
from tyche.models import AccountSnapshot, Instrument, OrderIntent, Regime, Side
from tyche.risk import RiskState, evaluate_intent

RTH = {SessionPhase.OPENING_DRIVE, SessionPhase.MIDDAY, SessionPhase.CLOSING_DRIVE}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Trigger(StrictModel):
    price: float = Field(gt=0)
    basis: Literal["last", "daily_close"] = "last"


class LifecyclePlan(StrictModel):
    plan_id: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)
    symbol: str = Field(pattern=r"^US\.[A-Z][A-Z0-9.]*$")
    strategy_id: str = Field(pattern=r"^PB-\d{3}$")
    rules_hash: str = Field(min_length=1)
    thesis: str = Field(min_length=10)
    invalidation_rules: list[str] = Field(min_length=1)
    created_at: AwareDatetime
    mode: Literal["new_entry", "adopt_position"] = "new_entry"
    quantity: int = Field(gt=0)
    entry_low: float = Field(gt=0)
    entry_high: float = Field(gt=0)
    stop: Trigger
    take_profit: Trigger
    entry_expires_at: AwareDatetime
    exit_deadline: AwareDatetime
    exit_on_invalidation: Literal[True] = True
    review_max_age_minutes: int = Field(default=60, ge=1, le=60)
    quote_max_age_seconds: int = Field(default=120, ge=1, le=300)
    max_slippage_bps: int = Field(default=30, ge=0, le=100)

    @model_validator(mode="after")
    def consistent(self) -> LifecyclePlan:
        if not self.stop.price < self.entry_low <= self.entry_high < self.take_profit.price:
            raise ValueError("require stop < entry_low <= entry_high < take_profit")
        if not self.created_at < self.entry_expires_at <= self.exit_deadline:
            raise ValueError("require created_at < entry_expires_at <= exit_deadline")
        local = self.exit_deadline.astimezone(ET)
        if not is_trading_day(local.date()):
            raise ValueError("exit_deadline must be on a trading day")
        if not datetime.strptime("09:30", "%H:%M").time() <= local.time() < regular_close(local.date()):
            raise ValueError("exit_deadline must be before the regular-session close")
        if any(not rule.strip() for rule in self.invalidation_rules):
            raise ValueError("invalidation rules must not be blank")
        return self

    def fingerprint(self) -> str:
        body = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()


class Review(StrictModel):
    plan_hash: str
    reviewed_at: AwareDatetime
    valid_until: AwareDatetime
    verdict: Literal["valid", "uncertain", "invalidated"]
    reason: str = Field(min_length=10)
    evidence: list[str] = Field(min_length=1)
    acknowledged_events: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounded(self) -> Review:
        if not self.reviewed_at < self.valid_until <= self.reviewed_at + timedelta(hours=1):
            raise ValueError("review validity must be positive and no more than one hour")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("review evidence must not be blank")
        return self


class MarketEvent(StrictModel):
    event_id: str
    at: AwareDatetime
    symbols: list[str] = Field(default_factory=list)  # empty means market-wide
    material: bool = True
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class LifecycleBook(StrictModel):
    schema_version: Literal[1] = 1
    plans: list[LifecyclePlan] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    news_checked_at: AwareDatetime
    news_feed_ok: bool
    events: list[MarketEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self) -> LifecycleBook:
        for values in ([p.plan_id for p in self.plans], [p.symbol for p in self.plans],
                       [r.plan_hash for r in self.reviews], [e.event_id for e in self.events]):
            if len(values) != len(set(values)):
                raise ValueError("duplicate plan id, symbol, review hash or event id")
        return self


class Quote(StrictModel):
    symbol: str
    last: float = Field(gt=0)
    at: AwareDatetime
    tradable: bool
    # A completed daily bar, NOT the current intraday last or previous-close field.
    close: float | None = Field(default=None, gt=0)
    close_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def close_pair(self) -> Quote:
        if (self.close is None) != (self.close_at is None):
            raise ValueError("close and close_at must be provided together")
        return self


class BrokerOrder(Instrument, StrictModel):
    order_id: str
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    filled_quantity: int = Field(ge=0)
    status: int
    created_at: AwareDatetime
    limit_price: float = Field(gt=0)
    remark: str = ""

    @model_validator(mode="after")
    def fill_bounds(self) -> BrokerOrder:
        if self.filled_quantity > self.quantity:
            raise ValueError("broker fill exceeds order quantity")
        if (self.status == 4) != (self.filled_quantity == self.quantity):
            raise ValueError("inconsistent or unverified full-fill broker status")
        return self

    @property
    def complete(self) -> bool:
        # status=4 fully-filled verified against the actual sim API. All other
        # statuses remain blocking until reconciled, not guessed as cancelled.
        return self.status == 4 and self.filled_quantity == self.quantity


class MarketSnapshot(StrictModel):
    observed_at: AwareDatetime
    snapshot: AccountSnapshot
    regime: Regime
    conviction: Literal["high", "medium-high", "medium", "low"]
    broker_nav: float = Field(gt=0)
    prior_close_nav: float = Field(gt=0)
    high_water_nav: float = Field(gt=0)
    available: dict[str, int]
    quotes: list[Quote]
    orders: list[BrokerOrder]
    orders_complete: Literal[True]
    halted: bool = False

    @model_validator(mode="after")
    def unique(self) -> MarketSnapshot:
        if len({q.symbol for q in self.quotes}) != len(self.quotes):
            raise ValueError("duplicate quotes")
        if len({o.order_id for o in self.orders}) != len(self.orders):
            raise ValueError("duplicate broker order ids")
        positions = {p.symbol: p for p in self.snapshot.positions}
        if len(positions) != len(self.snapshot.positions):
            raise ValueError("duplicate broker positions")
        if any(q < 0 or q > (positions[s].quantity if s in positions else 0)
               for s, q in self.available.items()):
            raise ValueError("available quantity outside broker holding")
        if self.snapshot.captured_at is not None and self.snapshot.captured_at.tzinfo is None:
            raise ValueError("broker capture timestamp must include a timezone")
        if self.snapshot.broker_nav is not None and abs(self.broker_nav - self.snapshot.broker_nav) > 0.01:
            raise ValueError("conflicting broker NAV values")
        return self


class Approval(StrictModel):
    plan_hash: str
    contract: LifecyclePlan
    account_hash: str
    approved_at: AwareDatetime
    operator_ref: str = Field(min_length=1)
    auditor_ref: str = Field(min_length=1)
    adopted_quantity: int = Field(default=0, ge=0)
    revoked: bool = False

    @model_validator(mode="after")
    def contract_hash(self) -> Approval:
        if self.contract.fingerprint() != self.plan_hash:
            raise ValueError("approval contract hash mismatch")
        expected = self.contract.quantity if self.contract.mode == "adopt_position" else 0
        if self.adopted_quantity != expected or self.approved_at < self.contract.created_at:
            raise ValueError("approval ownership or timestamp inconsistent with contract")
        return self


class Reservation(StrictModel):
    request_id: str
    plan_hash: str
    account_hash: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    limit_price: float = Field(gt=0)
    reason: str
    reserved_at: AwareDatetime
    order_id: str | None = None
    filled_quantity: int = Field(default=0, ge=0)
    complete: bool = False

    @model_validator(mode="after")
    def fill_bounds(self) -> Reservation:
        if self.filled_quantity > self.quantity or (self.complete and (
            self.filled_quantity != self.quantity or not self.order_id
        )):
            raise ValueError("invalid reservation fill evidence")
        return self


class LifecycleState(StrictModel):
    schema_version: Literal[1] = 1
    approvals: list[Approval] = Field(default_factory=list)
    reservations: list[Reservation] = Field(default_factory=list)
    latched_exits: dict[str, str] = Field(default_factory=dict)
    last_tick_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def unique(self) -> LifecycleState:
        groups = [
            [(a.account_hash, a.plan_hash) for a in self.approvals],
            [(a.account_hash, a.contract.symbol) for a in self.approvals if not a.revoked],
            [r.request_id for r in self.reservations],
            [(r.account_hash, r.order_id) for r in self.reservations if r.order_id],
        ]
        if any(len(values) != len(set(values)) for values in groups):
            raise ValueError("duplicate lifecycle approval, ownership or reservation")
        grants = {(a.account_hash, a.plan_hash): a for a in self.approvals}
        for request in self.reservations:
            grant = grants.get((request.account_hash, request.plan_hash))
            if (grant is None or request.symbol != grant.contract.symbol
                    or request.quantity > grant.contract.quantity
                    or request.reserved_at < grant.approved_at):
                raise ValueError("reservation does not match its approved contract")
        for key, grant in grants.items():
            requests = [r for r in self.reservations if (r.account_hash, r.plan_hash) == key]
            buys = [r for r in requests if r.side == "buy"]
            owned = grant.adopted_quantity + sum(r.filled_quantity for r in buys)
            if (len(buys) > 1 or (buys and grant.contract.mode != "new_entry")
                    or sum(r.filled_quantity for r in requests if r.side == "sell") > owned):
                raise ValueError("reservation totals violate lifecycle ownership")
        return self


class Decision(StrictModel):
    plan_id: str
    plan_hash: str
    symbol: str
    action: Literal["buy", "sell", "hold", "blocked", "review", "closed"]
    reason: str
    quantity: int = 0
    limit_price: float | None = None
    authorized: bool = False
    warnings: list[str] = Field(default_factory=list)


def account_hash(account_id: str) -> str:
    return hashlib.sha256(account_id.encode()).hexdigest()


def fresh(at: datetime, now: datetime, seconds: int) -> bool:
    return 0 <= (now - at).total_seconds() <= seconds


def validate_market(market: MarketSnapshot, config: AppConfig, now: datetime) -> None:
    account = market.snapshot
    if (account.env != "paper" or account.source != "sim_list"
            or account.account_id not in config.risk.account_allowlist
            or account.account_type not in config.risk.sim_account_types
            or account.market_id != 100):
        raise ValueError("unverified or non-allowlisted US paper account")
    if not fresh(market.observed_at, now, 120) or (
        account.captured_at is not None and not fresh(account.captured_at, now, 120)
    ):
        raise ValueError("broker snapshot stale or future-dated; fetch again")
    if any(order.created_at > now for order in market.orders):
        raise ValueError("broker order timestamp is in the future")


def reconcile(state: LifecycleState, market: MarketSnapshot) -> None:
    """Match reservations to broker evidence; uncertainty never releases a lock."""
    key = account_hash(market.snapshot.account_id)
    for request in state.reservations:
        if request.account_hash != key:
            continue
        matches = [o for o in market.orders if (
            o.order_id == request.order_id if request.order_id
            else o.remark == request.request_id
        )]
        if len(matches) > 1:
            raise ValueError("ambiguous broker reservation match")
        if not matches:
            continue
        order = matches[0]
        if (order.symbol, order.side, order.quantity) != (
            request.symbol, request.side, request.quantity
        ) or order.filled_quantity < request.filled_quantity or (
            abs(order.limit_price - request.limit_price) > 0.001
            or (request.complete and not order.complete)
        ):
            raise ValueError("broker order identity or cumulative fill mismatch")
        request.order_id = order.order_id
        request.filled_quantity = order.filled_quantity
        request.complete = order.complete


def review_problem(plan: LifecyclePlan, book: LifecycleBook, now: datetime) -> str | None:
    reviews = [r for r in book.reviews if r.plan_hash == plan.fingerprint()]
    if not reviews:
        return "missing review for this exact plan revision"
    review = reviews[0]
    if (not fresh(review.reviewed_at, now, plan.review_max_age_minutes * 60)
            or now >= review.valid_until or review.reviewed_at < plan.created_at):
        return "research review expired or future-dated"
    if review.verdict != "valid":
        return "thesis " + review.verdict
    if not book.news_feed_ok or not fresh(book.news_checked_at, now, 3600):
        return "news coverage missing, stale or unavailable"
    for event in book.events:
        if not event.material or (event.symbols and plan.symbol not in event.symbols):
            continue
        if now < event.at <= now + timedelta(minutes=30):
            return "material event imminent: " + event.event_id
        if event.at <= now and event.at >= plan.created_at and (
            event.event_id not in review.acknowledged_events or review.reviewed_at < event.at
        ):
            return "material event requires revalidation: " + event.event_id
    return None


def trigger_price(trigger: Trigger, quote: Quote, plan: LifecyclePlan,
                  now: datetime) -> float | None:
    if trigger.basis == "last":
        return quote.last
    if quote.close_at is None or quote.close is None or quote.close_at < plan.created_at:
        return None
    local = quote.close_at.astimezone(ET)
    current = now.astimezone(ET)
    expected = current.date()
    if not is_trading_day(expected) or current.time() < regular_close(expected):
        expected -= timedelta(days=1)
        while not is_trading_day(expected):
            expected -= timedelta(days=1)
    if (local.date() != expected or local.time() != regular_close(local.date())
            or quote.close_at > now):
        return None
    return quote.close


def limit_for(plan: LifecyclePlan, price: float, side: str) -> float:
    bps = Decimal(plan.max_slippage_bps) / Decimal(10000)
    value = Decimal(str(price)) * (1 + bps if side == "buy" else 1 - bps)
    if side == "buy":
        value = min(value, Decimal(str(plan.entry_high)))
    return float(value.quantize(Decimal("0.01"), rounding=(
        ROUND_FLOOR if side == "buy" else ROUND_CEILING
    )))


def decide(plan: LifecyclePlan, book: LifecycleBook, market: MarketSnapshot,
           state: LifecycleState, config: AppConfig, now: datetime) -> Decision:
    fingerprint = plan.fingerprint()
    result = Decision(plan_id=plan.plan_id, plan_hash=fingerprint, symbol=plan.symbol,
                      action="hold", reason="no exit trigger")
    key = account_hash(market.snapshot.account_id)
    approval = next((a for a in state.approvals if a.plan_hash == fingerprint
                     and a.account_hash == key and not a.revoked), None)
    permitted = approval is not None and approval.approved_at <= now
    requests = [r for r in state.reservations if r.account_hash == key
                and r.plan_hash == fingerprint]
    held = market.snapshot.position(plan.symbol)
    held_qty = held.quantity if held else 0
    owned = (approval.adopted_quantity if approval else 0) + sum(
        r.filled_quantity * (1 if r.side == "buy" else -1) for r in requests
    )
    problem = review_problem(plan, book, now)
    if problem:
        result.warnings.append(problem)
    quote = next((q for q in market.quotes if q.symbol == plan.symbol), None)
    spot_fresh = quote is not None and fresh(quote.at, now, plan.quote_max_age_seconds)
    quote_usable = spot_fresh and quote.tradable
    exit_reason = state.latched_exits.get(fingerprint)
    review = next((r for r in book.reviews if r.plan_hash == fingerprint), None)
    if review and review.verdict == "invalidated" and fresh(
        review.reviewed_at, now, plan.review_max_age_minutes * 60
    ) and plan.created_at <= review.reviewed_at < review.valid_until and now < review.valid_until:
        exit_reason = "thesis_invalidated"
        state.latched_exits[fingerprint] = exit_reason
    if held_qty:
        if now >= plan.exit_deadline:
            exit_reason = "holding_deadline"
        stop = trigger_price(plan.stop, quote, plan, now) if quote and (
            spot_fresh or plan.stop.basis == "daily_close"
        ) else None
        target = trigger_price(plan.take_profit, quote, plan, now) if quote and (
            spot_fresh or plan.take_profit.basis == "daily_close"
        ) else None
        if ((plan.stop.basis == "daily_close" and stop is None)
                or (plan.take_profit.basis == "daily_close" and target is None)):
            result.warnings.append("completed daily-close evidence unavailable for this lifecycle")
        if target is not None and target >= plan.take_profit.price:
            exit_reason = exit_reason or "take_profit"
        if stop is not None and stop <= plan.stop.price:
            exit_reason = "stop_loss"
        if exit_reason:
            # Detection is durable even after hours. Submission still requires RTH.
            state.latched_exits[fingerprint] = exit_reason
        if not permitted or owned <= 0:
            result.action, result.reason = "review", "held position has no approved lifecycle ownership"
            return result
        if held_qty != owned:
            result.warnings.append("broker holding differs from attributed quantity; no new entries")
        if not quote_usable:
            result.action, result.reason = "blocked", "quote missing, stale, future-dated or suspended"
            return result
        if not exit_reason:
            result.action = "review" if problem else "hold"
            result.reason = problem or "no exit trigger"
            return result
        result.action, result.reason = "sell", exit_reason
        result.quantity = min(owned, held_qty, market.available.get(plan.symbol, 0))
    else:
        if any(o.symbol == plan.symbol and not o.complete for o in market.orders) or any(
            r.symbol == plan.symbol and r.account_hash == key and not r.complete
            for r in state.reservations
        ):
            result.action, result.reason = "blocked", "pending or uncertain order; reconcile/cancel review first"
            return result
        if requests or (approval and approval.adopted_quantity):
            result.action, result.reason = "closed", "no broker holding; this lifecycle cannot re-enter"
            return result
        if plan.mode == "adopt_position":
            result.action, result.reason = "blocked", "adoption plan cannot open a new position"
            return result
        if fingerprint in state.latched_exits or now >= plan.entry_expires_at:
            result.action, result.reason = "blocked", "entry expired or lifecycle invalidated"
            return result
        if problem:
            result.action, result.reason = "review", problem
            return result
        if market.halted:
            result.action, result.reason = "blocked", "halt blocks entries, not protective exits"
            return result
        if not quote_usable:
            result.action, result.reason = "blocked", "quote missing, stale, future-dated or suspended"
            return result
        if not plan.entry_low <= quote.last <= plan.entry_high:
            result.action, result.reason = "hold", "outside approved entry zone"
            return result
        from tyche.pipeline import rules_hash
        if rules_hash(config.root, plan.strategy_id) != plan.rules_hash:
            result.action, result.reason = "blocked", "strategy rules changed; re-plan and re-approve"
            return result
        if not config.strategy_enabled(plan.strategy_id):
            result.action, result.reason = "blocked", "strategy disabled"
            return result
        from tyche.pipeline import act_wait
        sleeve = config.sleeve_map(plan.strategy_id).get(plan.symbol)
        if act_wait(Side.BUY, sleeve, market.conviction, False) == "wait":
            result.action, result.reason = "blocked", "low-conviction act/wait gate"
            return result
        result.action, result.reason, result.quantity = "buy", "entry_valid", plan.quantity

    pending = [o for o in market.orders if o.symbol == plan.symbol and not o.complete]
    unresolved = [r for r in state.reservations if r.symbol == plan.symbol
                  and r.account_hash == key and not r.complete]
    if pending or unresolved:
        result.action, result.reason = "blocked", "pending or uncertain order; reconcile/cancel review first"
        return result
    gate = evaluate(now)
    if gate.phase not in RTH or (result.action == "buy" and not gate.strategy.new_entries):
        result.action, result.reason = "blocked", "outside permitted session; exit trigger remains latched"
        return result
    if not permitted:
        result.action, result.reason = "blocked", "exact lifecycle requires operator approval"
        return result
    if result.quantity <= 0:
        result.action, result.reason = "blocked", "no available attributed shares; reconcile broker state"
        return result
    result.limit_price = limit_for(plan, quote.last, result.action)
    if result.limit_price <= 0:
        result.action, result.reason = "blocked", "invalid limit price"
        return result
    # Broker history (all pages) is authoritative for daily counters, including
    # non-lifecycle orders. Reservations absent from it are counted additionally.
    today_orders = [o for o in market.orders
                    if o.created_at.astimezone(ET).date() == now.astimezone(ET).date()]
    orders_today = len(today_orders)
    broker_ids = {o.order_id for o in market.orders}
    unknown_today = sum(1 for r in state.reservations if r.account_hash == key
                        and r.reserved_at.astimezone(ET).date() == now.astimezone(ET).date()
                        and r.order_id not in broker_ids)
    intent = OrderIntent(symbol=plan.symbol, side=Side(result.action), quantity=result.quantity,
                         strategy_id=plan.strategy_id,
                         limit_price=result.limit_price, stop_price=(
                             plan.stop.price if result.action == "buy" else None
                         ), reason=result.reason)
    pending_intents = []
    if result.action == "buy":
        for order in market.orders:
            if not order.complete:
                pending_intents.append(OrderIntent(
                    symbol=order.symbol, option=order.option, side=Side(order.side),
                    quantity=max(1, order.quantity - order.filled_quantity),
                    limit_price=order.limit_price, reason="unresolved broker exposure",
                ))
        for request in state.reservations:
            if request.account_hash == key and not request.complete and request.order_id not in broker_ids:
                pending_intents.append(OrderIntent(
                    symbol=request.symbol, side=Side(request.side), quantity=request.quantity,
                    limit_price=request.limit_price, reason="unresolved reserved exposure",
                ))
    risk_state = RiskState(nav=market.broker_nav, prior_close_nav=market.prior_close_nav,
                           high_water_nav=market.high_water_nav, halted=market.halted,
                           orders_today=orders_today + unknown_today,
                           pending_orders=pending_intents,
                           traded_notional_today=sum(
                               o.quantity * o.limit_price * o.multiplier for o in today_orders if o.side == "buy"
                           ) + sum(
                               r.quantity * r.limit_price for r in state.reservations
                               if r.side == "buy" and r.account_hash == key
                               and r.order_id not in broker_ids
                               and r.reserved_at.astimezone(ET).date() == now.astimezone(ET).date()
                           ))
    if result.action == "buy":
        strategy = config.strategy_by_id(plan.strategy_id)
        # ADR 0017: a scoped lane is capped and attributed over its own symbols, never the ballast's.
        symbols = config.scope_symbols(plan.strategy_id)
        held_notional = sum(p.market_value for p in market.snapshot.positions if p.underlying in symbols)
        pending_notional = sum(o.notional for o in pending_intents if o.side == Side.BUY and o.underlying in symbols)
        if held_notional + pending_notional + intent.notional > strategy.allocation_cap * market.broker_nav:
            result.action, result.reason = "blocked", "risk gate: strategy allocation cap"
            return result
        asset = config.universe.by_symbol().get(plan.symbol)
        name_cap = None
        if asset is not None:
            name_cap = min(strategy.max_weight, asset.max_weight)
        elif plan.symbol in symbols:
            name_cap = strategy.max_weight
        if name_cap is not None:
            name_notional = sum(p.market_value for p in market.snapshot.positions if p.underlying == plan.symbol)
            name_notional += sum(o.notional for o in pending_intents if o.side == Side.BUY and o.underlying == plan.symbol)
            if name_notional + intent.notional > name_cap * market.broker_nav:
                result.action, result.reason = "blocked", "risk gate: strategy asset cap"
                return result
    policy = config.risk
    if result.action == "buy" and gate.strategy.event_caution:
        policy = policy.model_copy(update={
            "risk_per_trade_pct": policy.risk_per_trade_pct / 2,
            "max_order_notional_pct": policy.max_order_notional_pct / 2,
        })
    verdict = evaluate_intent(intent, market.snapshot, policy, risk_state, quote.last,
                              config.scope_symbols(plan.strategy_id), config.sleeve_map(plan.strategy_id),
                              config.strategy_by_id(plan.strategy_id).sleeve_caps[
                                  market.regime.value
                              ].as_dict() if result.action == "buy" else None)
    if not verdict.allowed or verdict.adjusted_quantity != result.quantity:
        result.action = "blocked"
        result.reason = "risk gate: " + (", ".join(b.rule for b in verdict.breaches)
                                         or "quantity adjustment requires re-plan")
        return result
    if result.action == "buy":
        sleeve = config.sleeve_map(plan.strategy_id).get(plan.symbol)
        phase_orders = sum(evaluate(o.created_at).phase == gate.phase for o in today_orders)
        phase_orders += sum(
            r.account_hash == key and r.order_id not in broker_ids
            and r.reserved_at.astimezone(ET).date() == now.astimezone(ET).date()
            and evaluate(r.reserved_at).phase == gate.phase for r in state.reservations
        )
        if sleeve not in gate.strategy.sleeves or phase_orders >= gate.strategy.max_orders:
            result.action, result.reason = "blocked", "calendar sleeve or phase entry budget exhausted"
            return result
    result.authorized = True
    return result


def tick(book: LifecycleBook, market: MarketSnapshot, state: LifecycleState,
         config: AppConfig, now: datetime) -> dict:
    validate_market(market, config, now)
    reconcile(state, market)
    gaps = []
    if state.last_tick_at and (now - state.last_tick_at).total_seconds() > 75 * 60:
        gaps.append("monitor coverage gap: last check over 75 minutes ago")
    if state.last_tick_at and now < state.last_tick_at:
        raise ValueError("clock moved backwards relative to lifecycle state")
    plans = list(book.plans)
    present_hashes = {p.fingerprint() for p in plans}
    key = account_hash(market.snapshot.account_id)
    for approval in state.approvals:
        if (not approval.revoked and approval.account_hash == key
                and approval.plan_hash not in present_hashes
                and market.snapshot.position(approval.contract.symbol)):
            # A scout refresh cannot delete protection for an existing position.
            plans.append(approval.contract)
    # A bad/unavailable proposal must not stop a different position's protection.
    plans.sort(key=lambda p: market.snapshot.position(p.symbol) is None)
    decisions = []
    for plan in plans:
        try:
            decisions.append(decide(plan, book, market, state, config, now))
        except (ValueError, OSError, KeyError) as exc:
            decisions.append(Decision(
                plan_id=plan.plan_id, plan_hash=plan.fingerprint(), symbol=plan.symbol,
                action="blocked", reason="invalid lifecycle inputs or unavailable strategy; operator review required",
                warnings=[type(exc).__name__],
            ))
    covered = {p.symbol for p in plans}
    for position in market.snapshot.positions:
        if position.symbol not in covered:
            gaps.append(f"{position.symbol}: held position missing a complete lifecycle plan")
    state.last_tick_at = now
    return {"checked_at": now.isoformat(), "cadence_minutes": 60, "gaps": gaps,
            "decisions": [d.model_dump(mode="json") for d in decisions]}
