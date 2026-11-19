"""Tyche desk dashboard - local desk server.

Serves the single-page dashboard and two JSON endpoints:
  /api/state       journal-derived desk state (truth = journal/events.jsonl)
  /api/automation  live Qoder Forward schedules + sessions (PAT server-side only)

Operator controls (local desk only): kill-switch and approval-envelope arm/disarm.
No order entry. Full account ids are redacted to ***NNN before anything leaves
this process.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
from datetime import UTC, date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

from tyche.approvals import ApprovalBatch, envelope_usage  # noqa: E402
from tyche.halt import effective_halt, set_halt  # noqa: E402
from tyche.journal import append_event, read_events, verify_chain  # noqa: E402
from tyche.market_calendar import (
    ET,
    SessionPhase,
    earnings_season,
    evaluate,
    events_on,
    generate_hourly_schedules,
    holiday_name,
    is_half_day,
    is_trading_day,
    session_timeline,
    strategy_for,
)
from tyche.pipeline import rules_hash  # noqa: E402
from tyche.trade_risk import compute_expectancy  # noqa: E402
from tyche.watchlist import Watchlist  # noqa: E402


# ---------------------------------------------------------------------------
# Deterministic contract derivation. Fields the plan/journal does not carry are
# derived honestly from journaled inputs + pinned config, tagged "derived" so
# they are never mistaken for journaled ground truth. Genuinely-unbuildable
# fields stay "gap". Nothing is fabricated.
# ---------------------------------------------------------------------------
def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash12(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode()).hexdigest()[:12]


STRATEGY_CFG = yaml.safe_load((ROOT / "config" / "strategies" / "pb-001.yaml").read_text())
UNIVERSE_CFG = yaml.safe_load((ROOT / "config" / "universe.yaml").read_text())
SLEEVE_BY_SYMBOL = {a["symbol"]: a["sleeve"] for a in UNIVERSE_CFG["assets"]}
MAXW_BY_SYMBOL = {a["symbol"]: a["max_weight"] for a in UNIVERSE_CFG["assets"]}
ETF_SYMBOLS = set(SLEEVE_BY_SYMBOL)  # v0.1 universe is all ETFs
PLAYBOOK = STRATEGY_CFG["id"]
RULES_HASH = rules_hash(ROOT, PLAYBOOK)
OUTLOOK_MAP = {"risk_on": "bullish", "neutral": "range", "risk_off": "bearish"}
CONTRACT_FIELDS = [
    "thesis_ref", "inputs_ref", "outlook", "vehicle", "expected_edge",
    "invalidation", "protection_type", "roll_plan", "sizing", "initial_risk", "realized",
]


def _conviction(score: int, total: int) -> str:
    if score >= total:
        return "high"
    if score == total - 1:
        return "medium-high"
    if score == total - 2:
        return "medium"
    return "low"


def derive_contract(card: dict, plan: dict | None, order_pipeline: dict | None = None) -> dict:
    plan = plan or {}
    plan_pipe = plan.get("pipeline")
    checks = plan.get("regime_checks", {})
    score = sum(1 for v in checks.values() if v)
    total = len(checks) or 4
    regime = plan.get("regime", "neutral")
    inputs_hash = _hash12({
        "as_of": plan.get("as_of", card.get("as_of")),
        "signals": plan.get("signals", {}),
        "targets": plan.get("targets", {}),
    })
    sleeve = SLEEVE_BY_SYMBOL.get(card["symbol"], "-")
    vehicle = "etf" if card["symbol"] in ETF_SYMBOLS else "stock"
    maxw = MAXW_BY_SYMBOL.get(card["symbol"])
    f: dict[str, dict] = {}
    if plan_pipe:
        f["thesis_ref"] = {
            "value": plan_pipe["thesis_ref"], "provenance": "journaled",
            "note": "Playbook id + frozen rules hash carried by the plan kernel (plan.pipeline).",
        }
        iref = plan_pipe["inputs_ref"]
        brief = f" · brief {iref['brief']}" if iref.get("brief") else ""
        f["inputs_ref"] = {
            "value": f"prices sha256 {iref['prices_sha256'][:12]}…{brief}", "provenance": "journaled",
            "note": "Price-input hash pinned by the plan kernel; research brief path when provided via --brief.",
        }
        f["outlook"] = {
            "value": f"{plan_pipe['outlook']} · conviction {plan_pipe['conviction']} "
                     f"({plan_pipe['checks_score']}/{plan_pipe['checks_total']} checks)",
            "provenance": "journaled",
            "note": f"Act/wait gate: {plan_pipe['act_wait_rule']}",
        }
    else:
        f["thesis_ref"] = {
            "value": f"{PLAYBOOK} · rules {RULES_HASH}", "provenance": "derived",
            "note": "Legacy plan without pipeline fields; derived from the pinned strategy/universe config.",
        }
        f["inputs_ref"] = {
            "value": f"inputs {inputs_hash}", "provenance": "derived",
            "note": "Legacy plan: deterministic hash of the signal/target snapshot.",
        }
        f["outlook"] = {
            "value": f"{OUTLOOK_MAP.get(regime, 'range')} · conviction {_conviction(score, total)} ({score}/{total} checks)",
            "provenance": "derived",
            "note": "Legacy plan: market-level regime mapped to outlook + conviction from the check score.",
        }
    if order_pipeline:
        f["vehicle"] = {
            "value": f"{order_pipeline['vehicle']} · {order_pipeline['vehicle_rationale']}",
            "provenance": "journaled",
            "note": "Vehicle + rationale carried per order by the plan kernel.",
        }
        edge = order_pipeline.get("expected_edge") or {}
        if edge.get("r") is not None or edge.get("pct") is not None:
            f["expected_edge"] = {
                "value": f"R {edge.get('r')} · {edge.get('pct')}% ({edge.get('label', '')})",
                "provenance": "journaled", "note": "Pre-trade edge estimate from the plan.",
            }
        else:
            f["expected_edge"] = {
                "value": None, "provenance": "gap",
                "note": edge.get("label") or "No pre-trade edge estimate - never fabricated.",
            }
        f["invalidation"] = {
            "value": order_pipeline["invalidation"], "provenance": "journaled",
            "note": "Rule-based invalidation carried per order; researcher price levels live in the brief.",
        }
        f["protection_type"] = {
            "value": order_pipeline["protection_type"], "provenance": "journaled",
            "note": "v0.1 ballast: drift-band rebalance + risk-kernel drawdown ladder; synthetic monitor is P2.",
        }
        f["roll_plan"] = {
            "value": order_pipeline.get("roll_plan") or "none - no option legs",
            "provenance": "journaled",
            "note": "Option leg groups + roll plans are P2.",
        }
    else:
        f["vehicle"] = {
            "value": f"{vehicle} · {sleeve} sleeve -{card.get('reason', '')}", "provenance": "derived",
            "note": "Vehicle type from the pinned universe; the rationale is the journaled order reason.",
        }
        f["expected_edge"] = {
            "value": None, "provenance": "gap",
            "note": "Pre-trade win-probability edge still absent; initial R per trade is carried in initial_risk (ADR 0016).",
        }
        f["invalidation"] = {
            "value": f"regime flip {regime}→risk_off if checks<2; de-risk if equity_trend fails (SPY<200-SMA)",
            "provenance": "derived",
            "note": "Regime-level invalidation derived from the regime rules. Explicit per-trade price/time/event invalidation is pending.",
        }
        f["protection_type"] = {
            "value": "synthetic_stop", "provenance": "derived",
            "note": "Sim broker has no native stops; the deterministic monitor is the protection (disclosed divergence). Heartbeat is P2.",
        }
        f["roll_plan"] = {
            "value": "none - ETF/stock leg, no option expiry", "provenance": "derived",
            "note": "No option legs in v0.1. Option leg groups + roll plans are P2.",
        }
    stop = card.get("stop_price")
    nav = plan.get("nav")
    if stop and card.get("side") == "buy":
        risk_usd = card["quantity"] * (card["limit_price"] - stop)
        pct = f" · {risk_usd / nav:.2%} NAV" if nav else ""
        f["initial_risk"] = {
            "value": f"${risk_usd:,.0f}{pct} · stop ${stop:,.2f}",
            "provenance": "journaled",
            "note": "Initial R = entry − stop (ADR 0016): the max loss this trade is sized to take, not an edge estimate.",
        }
    else:
        f["initial_risk"] = {
            "value": None, "provenance": "gap",
            "note": "No plan stop on this order (legacy plan or sell); initial R undefined — never fabricated.",
        }
    headroom = f" · sleeve cap {maxw:.0%}" if maxw else ""
    f["sizing"] = {
        "value": f"{card['quantity']}→{card['effective_quantity']} eff · ${card['notional']:,.0f} · limit ${card['limit_price']:,.2f}{headroom}",
        "provenance": "journaled",
        "note": "Quantity, effective quantity, notional and limit from the journaled plan; sleeve cap from config.",
    }
    rt = card.get("round_trip")
    o = card.get("order") or {}
    if rt is not None:
        sign = "+" if rt >= 0 else "−"
        f["realized"] = {"value": f"{sign}${abs(rt):,.2f} gross round-trip", "provenance": "journaled",
                         "note": "Reconciled drill fills (validation doc)."}
    elif o.get("fill_price") is not None:
        f["realized"] = {"value": f"filled {o.get('fill_qty', o.get('quantity'))} @ ${o['fill_price']:,.2f}",
                         "provenance": "journaled", "note": "Reconciled fill."}
    else:
        f["realized"] = {"value": None, "provenance": "gap",
                         "note": "No reconciled fill yet - realized edge renders when the trade closes."}
    filled = sum(1 for x in f.values() if x["provenance"] in ("journaled", "derived") and x["value"] is not None)
    return {"fields": f, "completeness": round(filled / len(CONTRACT_FIELDS), 3),
            "filled": filled, "total": len(CONTRACT_FIELDS)}


def build_instrumentation(cards: list[dict]) -> dict:
    rows = []
    for field in CONTRACT_FIELDS:
        provs = [c["contract"]["fields"][field]["provenance"] for c in cards if c.get("contract")]
        status = "journaled" if "journaled" in provs else "derived" if "derived" in provs else "gap"
        note = next((c["contract"]["fields"][field]["note"] for c in cards if c.get("contract")), "")
        rows.append({"field": field, "status": status, "note": note})
    cross = [
        {"field": "macro / sentiment / seasonality", "status": "gap",
         "note": "Researcher-child briefs are not wired into the plan yet (P1)."},
        {"field": "protection heartbeat / roll state", "status": "gap",
         "note": "Synthetic-monitor heartbeat + option roll state panels (P2)."},
        {"field": "fee-net performance series", "status": "gap",
         "note": "EOD performance generator → docs/performance/<date>-metrics.md (P1)."},
    ]
    comps = [c["contract"]["completeness"] for c in cards if c.get("contract")]
    avg = sum(comps) / len(comps) if comps else 0.0
    counts = {"journaled": 0, "derived": 0, "gap": 0}
    for c in cards:
        for x in c.get("contract", {}).get("fields", {}).values():
            counts[x["provenance"]] += 1
    return {"fields": rows, "cross_cutting": cross, "completeness_avg": round(avg, 3),
            "cards_n": len(comps), "field_counts": counts}

STATIC = Path(__file__).resolve().parent / "static"
JOURNAL = ROOT / "journal" / "events.jsonl"
HALT = ROOT / "journal" / "halt.json"
REPO_HALT = ROOT / "data" / "halt.json"
APPROVALS = ROOT / "data" / "approvals.json"
DRILL_DIR = ROOT / "plans" / "drill-2026-11-18"
VALIDATION = ROOT / "docs" / "validation" / "2026-11-18-kill-switch-drill.md"
PORT = 8765

REGIME_OUTLOOK = {"risk_on": "bullish", "neutral": "range", "risk_off": "bearish"}


# ---------------------------------------------------------------- redaction
def _sensitive_ids() -> set[str]:
    ids: set[str] = set()
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYCHE_ALLOWED_ACCOUNT_IDS="):
                for part in line.split("=", 1)[1].split(","):
                    part = part.strip()
                    if part.isdigit() and len(part) >= 6:
                        ids.add(part)
    accounts = DRILL_DIR / "accounts.json"
    if accounts.is_file():
        ids.update(re.findall(r"\b\d{6,}\b", accounts.read_text(encoding="utf-8")))
    return ids


SENSITIVE = _sensitive_ids()


def mask_id(value: str) -> str:
    return "***" + value[-3:] if re.fullmatch(r"\d{6,}", value) else value


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        out = obj
        for sid in SENSITIVE:
            out = out.replace(sid, mask_id(sid))
        return out
    return obj


# ---------------------------------------------------------------- drill doc
def parse_validation() -> dict:
    out = {"pass": None, "fills": {}, "cancelled": [], "realized_gross": None, "source": None}
    if not VALIDATION.is_file():
        return out
    text = VALIDATION.read_text(encoding="utf-8")
    out["source"] = "docs/validation/2026-11-18-kill-switch-drill.md"
    out["pass"] = bool(re.search(r"^# .*PASS", text, re.M))
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        oid = re.search(r"\b(\d{6,})\b", cells[-1]) if cells else None
        if not oid:
            continue
        oid = oid.group(1)
        if re.search(r"cancelled", line, re.I):
            out["cancelled"].append(oid)
        elif re.search(r"(?<!un)filled", line, re.I):
            px = re.search(r"@\s*\*{0,2}([\d.]+)", line)
            qty = re.search(r"filled\s+(\d+)", line, re.I)
            out["fills"][oid] = {
                "price": float(px.group(1)) if px else None,
                "qty": int(qty.group(1)) if qty else None,
            }
    realized = re.search(r"realized\s*\+?([\d.]+)", text)
    if realized:
        out["realized_gross"] = float(realized.group(1))
    return out


# ---------------------------------------------------------------- state
def latest_plans(events: list[dict]) -> dict[str, dict]:
    plans: dict[str, dict] = {}
    for ev in events:
        if ev["type"] != "plan.created":
            continue
        plan = ev["payload"]["plan"]
        acct = mask_id(str(plan["account_id"]))
        if acct not in plans or ev["ts"] > plans[acct]["ts"]:
            plans[acct] = {"ts": ev["ts"], "plan": plan, "hash": ev["hash"]}
    return plans


def nav_marks(events: list[dict], snapshot: dict | None) -> dict[str, list[dict]]:
    marks: dict[str, list[dict]] = {}
    for ev in events:
        if ev["type"] != "plan.created":
            continue
        plan = ev["payload"]["plan"]
        acct = mask_id(str(plan["account_id"]))
        marks.setdefault(acct, []).append(
            {"ts": ev["ts"], "as_of": plan["as_of"], "nav": plan["nav"], "source": "plan.created"}
        )
    if snapshot:
        acct = mask_id(str(snapshot["account"]))
        ts = datetime.fromtimestamp((DRILL_DIR / "snapshot.json").stat().st_mtime, UTC).isoformat()
        marks.setdefault(acct, []).append(
            {"ts": ts, "as_of": "snapshot", "nav": snapshot["nav"], "source": "snapshot"}
        )
    for acct, series in marks.items():
        marks[acct] = _dedupe_marks(series)
    return marks


def build_orders(events: list[dict], validation: dict) -> list[dict]:
    orders: list[dict] = []
    for ev in events:
        if ev["type"] != "order.requested":
            continue
        p = ev["payload"]
        orders.append(
            {
                "remark": p.get("remark"),
                "symbol": p["symbol"],
                "side": p["side"],
                "quantity": p["quantity"],
                "account": p.get("account", ""),
                "purpose": p.get("purpose"),
                "requested_ts": ev["ts"],
                "submitted_ts": None,
                "order_id": None,
                "limit_price": p.get("limit_price"),
                "order_type": p.get("order_type", "limit"),
                "supersedes": p.get("supersedes_order_id"),
                "note": p.get("note"),
                "status": "requested",
                "fill_price": None,
                "fill_qty": None,
                "events": [{"ts": ev["ts"], "type": ev["type"], "hash": ev["hash"]}],
            }
        )
    for ev in events:
        if ev["type"] != "order.submitted":
            continue
        p = ev["payload"]
        candidates = [
            o for o in orders
            if o["order_id"] is None and o["symbol"] == p["symbol"]
            and o["side"] == p["side"] and o["quantity"] == p["quantity"]
            and o["requested_ts"] <= ev["ts"]
        ]
        exact = [o for o in candidates if o["limit_price"] == p.get("limit_price")]
        rec = (exact or candidates or [None])[-1]
        if rec is None:
            continue
        rec["submitted_ts"] = ev["ts"]
        rec["order_id"] = p.get("order_id")
        rec["status"] = "submitted"
        rec["events"].append({"ts": ev["ts"], "type": ev["type"], "hash": ev["hash"]})
    for rec in orders:
        oid = rec["order_id"]
        if oid and oid in validation["fills"]:
            rec["status"] = "filled"
            rec["fill_price"] = validation["fills"][oid]["price"]
            rec["fill_qty"] = validation["fills"][oid]["qty"]
        elif oid and oid in validation["cancelled"]:
            rec["status"] = "cancelled"
        elif rec["status"] == "requested" and rec["order_type"] == "market":
            rec["status"] = "broker-rejected"
    return sorted(orders, key=lambda r: r["requested_ts"] or "")


def build_rejections(events: list[dict], orders: list[dict]) -> list[dict]:
    out: list[dict] = []
    for ev in events:
        if ev["type"] != "plan.created":
            continue
        plan = ev["payload"]["plan"]
        acct = mask_id(str(plan["account_id"]))
        for order in plan["orders"]:
            verdict = order["verdict"]
            if verdict["allowed"]:
                continue
            for breach in verdict["breaches"]:
                out.append(
                    {
                        "ts": ev["ts"],
                        "kind": "risk-kernel",
                        "rule": breach["rule"],
                        "symbol": order["intent"]["symbol"],
                        "side": order["intent"]["side"],
                        "quantity": order["intent"]["quantity"],
                        "detail": breach["detail"],
                        "account": acct,
                        "as_of": plan["as_of"],
                    }
                )
    for ev in events:
        if ev["type"] == "halt.skip":
            p = ev["payload"]
            out.append(
                {
                    "ts": ev["ts"],
                    "kind": "halt",
                    "rule": "halt.active",
                    "symbol": p["symbol"],
                    "side": p["side"],
                    "quantity": p["quantity"],
                    "detail": p["reason"],
                    "account": "***748",
                    "as_of": None,
                }
            )
    for rec in orders:
        if rec["status"] == "broker-rejected":
            out.append(
                {
                    "ts": rec["requested_ts"],
                    "kind": "broker",
                    "rule": "backend.ret_code_-5",
                    "symbol": rec["symbol"],
                    "side": rec["side"],
                    "quantity": rec["quantity"],
                    "detail": rec["note"] or "rejected by broker backend",
                    "account": rec["account"],
                    "as_of": None,
                }
            )
    out.sort(key=lambda r: r["ts"] or "")
    return out


def stage_track(plan: dict, symbol: str, realized: float | None) -> dict:
    regime = plan["regime"]
    checks = plan.get("regime_checks", {})
    passed = sum(1 for v in checks.values() if v)
    signal = plan.get("signals", {}).get(symbol, {})
    return {
        "thesis": {
            "state": "partial",
            "text": f"v0.1 regime rotation -{regime}, checks {passed}/{len(checks)}",
            "gap": "per-trade thesis_ref not instrumented",
        },
        "multifactor": {
            "state": "partial",
            "momentum": signal.get("momentum"),
            "score": signal.get("score"),
            "volatility": signal.get("volatility"),
            "selected": signal.get("selected"),
            "covered": ["technical"],
            "missing": ["macro", "sentiment & flow", "seasonality"],
            "note": "fundamental = eligibility filter (cap, price, liquidity)",
        },
        "outlook": {
            "state": "partial",
            "regime": regime,
            "mapped": REGIME_OUTLOOK.get(regime, regime),
            "gap": "per-setup outlook + conviction not instrumented (market-level only)",
        },
        "vehicle": {"state": "ok", "type": "etf", "rationale": None},
        "edge": {
            "state": "gap" if realized is None else "partial",
            "expected": None,
            "realized": realized,
            "gap": "pre-trade expected edge not instrumented",
        },
    }


def build_cards(plans: dict[str, dict], orders: list[dict], validation: dict) -> list[dict]:
    cards: list[dict] = []
    live_accts = [a for a in plans if not a.startswith("SIM-")]
    for acct in live_accts:
        plan = plans[acct]["plan"]
        for order in plan["orders"]:
            intent, verdict = order["intent"], order["verdict"]
            symbol = intent["symbol"]
            matched = next(
                (o for o in orders if o["symbol"] == symbol and o["side"] == intent["side"]
                 and o["quantity"] == intent["quantity"] and o.get("account") == acct
                 and o.get("purpose") != "drill-seed"),
                None,
            )
            halted = any(
                ev["type"] == "halt.skip" and ev["payload"]["symbol"] == symbol
                for ev in EVENTS
            )
            if matched and matched["status"] == "filled":
                status = "filled"
            elif not verdict["allowed"]:
                status = "blocked"
            elif halted:
                status = "halt-skipped"
            elif verdict["allowed"]:
                status = "approved"
            else:
                status = "pending"
            realized = validation["realized_gross"] if matched and matched["status"] == "filled" else None
            card = {
                "id": f"plan:{acct}:{symbol}:{intent['side']}",
                "symbol": symbol,
                "side": intent["side"],
                "quantity": intent["quantity"],
                "effective_quantity": order["effective_quantity"],
                "limit_price": intent["limit_price"],
                "stop_price": intent.get("stop_price"),
                "notional": intent["notional"],
                "account": acct,
                "as_of": plan["as_of"],
                "status": status,
                "verdict": verdict,
                "reason": intent["reason"],
                "stages": stage_track(plan, symbol, realized),
                "order": matched,
                "protection": "synthetic stop monitor (P2) - sim has no broker-native stops",
                "roll_plan": None,
                "band": "execution",
            }
            card["stages"]["vehicle"]["rationale"] = intent["reason"]
            card["contract"] = derive_contract(card, plan, order.get("pipeline"))
            cards.append(card)
    for rec in orders:
        if rec.get("purpose") in ("drill-seed", "drill-seed-resubmit") and rec["side"] == "buy" and rec["status"] == "filled":
            plan = plans.get(rec["account"], {}).get("plan")
            if plan is None:
                continue
            realized = validation["realized_gross"] if rec["status"] == "filled" else None
            card = {
                "id": f"order:{rec['remark']}",
                "symbol": rec["symbol"],
                "side": rec["side"],
                "quantity": rec["quantity"],
                "effective_quantity": rec["quantity"],
                "limit_price": rec["limit_price"],
                "notional": round((rec["fill_price"] or rec["limit_price"] or 0) * rec["quantity"], 2),
                "account": rec["account"],
                "as_of": "drill 2026-11-18",
                "status": "closed" if realized is not None else rec["status"],
                "verdict": {"allowed": True, "breaches": [], "adjusted_quantity": rec["quantity"], "notes": ["operator-authorized drill seed"]},
                "reason": rec.get("note") or "kill-switch drill seed position",
                "stages": stage_track(plan, rec["symbol"], realized),
                "order": rec,
                "protection": "defined-risk drill - closed same session",
                "roll_plan": None,
                "band": "execution",
                "round_trip": realized,
            }
            card["contract"] = derive_contract(card, plan)
            cards.append(card)
    for acct, entry in plans.items():
        if not acct.startswith("SIM-"):
            continue
        plan = entry["plan"]
        for order in plan["orders"]:
            intent, verdict = order["intent"], order["verdict"]
            card = {
                "id": f"plan:{acct}:{intent['symbol']}:{intent['side']}",
                "symbol": intent["symbol"],
                "side": intent["side"],
                "quantity": intent["quantity"],
                "effective_quantity": order["effective_quantity"],
                "limit_price": intent["limit_price"],
                "stop_price": intent.get("stop_price"),
                "notional": intent["notional"],
                "account": acct,
                "as_of": plan["as_of"],
                "status": "approved" if verdict["allowed"] else "blocked",
                "verdict": verdict,
                "reason": intent["reason"],
                "stages": stage_track(plan, intent["symbol"], None),
                "order": None,
                "protection": "synthetic stop monitor (P2)",
                "roll_plan": None,
                "band": "stage4",
                "dry_run": True,
            }
            card["stages"]["vehicle"]["rationale"] = intent["reason"]
            card["contract"] = derive_contract(card, plan, order.get("pipeline"))
            cards.append(card)
    return cards


def load_snapshot() -> dict | None:
    path = DRILL_DIR / "snapshot.json"
    if not path.is_file():
        return None
    snap = json.loads(path.read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    raw = DRILL_DIR / "positions.json"
    if raw.is_file():
        try:
            payload = json.loads(raw.read_text(encoding="utf-8"))
            for pos in payload.get("data", {}).get("positions", []):
                names["US." + pos["symbol"]] = pos.get("stock_name", "")
        except (json.JSONDecodeError, KeyError):
            pass
    nav = snap["nav"]
    positions = []
    for pos in snap["positions"]:
        mv = pos["market_value"]
        cost = pos["avg_cost"] * pos["quantity"]
        positions.append(
            {
                "symbol": pos["symbol"],
                "name": names.get(pos["symbol"], ""),
                "quantity": pos["quantity"],
                "avg_cost": pos["avg_cost"],
                "last_price": pos["last_price"],
                "market_value": round(mv, 2),
                "weight": mv / nav if nav else 0,
                "pl": round(mv - cost, 2),
                "pl_pct": (mv - cost) / cost if cost else 0,
            }
        )
    positions.sort(key=lambda p: p["market_value"], reverse=True)
    return {
        "account": mask_id(str(snap["account_id"])),
        "env": snap.get("env"),
        "cash": snap["cash"],
        "nav": nav,
        "gross_exposure": snap["gross_exposure"],
        "gross_weight": snap["gross_exposure"] / nav if nav else 0,
        "cash_weight": snap["cash"] / nav if nav else 0,
        "positions": positions,
        "as_of": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "source": "plans/drill-2026-11-18/snapshot.json (broker sim_list)",
    }


# ---------------------------------------------------------------------------
# Cloud-run feed. The cloud desk pushes sanitized run bundles to
# docs/performance/<run>/ (kernel snapshot + broker MCP reads, ids redacted
# upstream). The challenge account (account_type 2, US paper) is the desk's
# primary feed; the local drill snapshot is only a fallback.
PERF_DIR = ROOT / "docs" / "performance"
CHALLENGE_ACCOUNT_TYPE = 2

# Moomoo OpenD OrderStatus -> desk vocabulary. A submit is not a fill.
_CLOUD_ORDER_STATUS = {
    1: "requested", 2: "submitted", 3: "broker-rejected", 4: "filled",
    5: "part-filled", 6: "cancelled", 7: "cancelled", 8: "submitted",
    9: "cancelled", 10: "part-filled",
}


def challenge_mask() -> str:
    path = DRILL_DIR / "accounts.json"
    if path.is_file():
        try:
            accounts = json.loads(path.read_text(encoding="utf-8"))["data"]["accounts"]
            for acct in accounts:
                if acct.get("account_type") == CHALLENGE_ACCOUNT_TYPE and acct.get("market_id") == 100:
                    return mask_id(str(acct["account_id"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return "challenge"


def _broker_ts(value) -> str | None:
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000, UTC).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def load_cloud_runs() -> list[dict]:
    runs = []
    if not PERF_DIR.is_dir():
        return runs
    for path in PERF_DIR.glob("*/snapshot.json"):
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(snap, dict) or "nav" not in snap:
            continue
        # git checkout resets mtimes, so prefer the newest broker timestamp in
        # the bundle when present; fall back to file mtime.
        ts = path.stat().st_mtime
        history = path.parent / "mcp" / "sim_trade_history_order_list.json"
        if history.is_file():
            try:
                orders = json.loads(history.read_text(encoding="utf-8")).get("data", {}).get("orders", [])
                stamps = [int(o["update_time"]) / 1_000_000 for o in orders if o.get("update_time")]
                if stamps:
                    ts = max(ts, max(stamps))
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
                pass
        runs.append({
            "run": path.parent.name,
            "ts": datetime.fromtimestamp(ts, UTC).isoformat(),
            "snapshot": snap,
            "dir": path.parent,
        })
    runs.sort(key=lambda r: (r["ts"], r["run"]))
    return runs


def _challenge_runs(runs: list[dict]) -> list[dict]:
    return [r for r in runs if r["snapshot"].get("account_type") == CHALLENGE_ACCOUNT_TYPE]


def cloud_snapshot(runs: list[dict]) -> dict | None:
    challenge = _challenge_runs(runs)
    if not challenge:
        return None
    run = challenge[-1]
    snap = run["snapshot"]
    names: dict[str, str] = {}
    raw = run["dir"] / "positions.json"
    if raw.is_file():
        try:
            for pos in json.loads(raw.read_text(encoding="utf-8")).get("data", {}).get("positions", []):
                names["US." + pos["symbol"]] = pos.get("stock_name", "")
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    nav = snap["nav"]
    positions = []
    for pos in snap.get("positions", []):
        mv = pos["market_value"]
        cost = pos["avg_cost"] * pos["quantity"]
        positions.append(
            {
                "symbol": pos["symbol"],
                "name": names.get(pos["symbol"], ""),
                "quantity": pos["quantity"],
                "avg_cost": pos["avg_cost"],
                "last_price": pos["last_price"],
                "market_value": round(mv, 2),
                "weight": mv / nav if nav else 0,
                "pl": round(mv - cost, 2),
                "pl_pct": (mv - cost) / cost if cost else 0,
            }
        )
    positions.sort(key=lambda p: p["market_value"], reverse=True)
    hold, total_asset = None, None
    cash_path = run["dir"] / "cash.json"
    if cash_path.is_file():
        try:
            data = json.loads(cash_path.read_text(encoding="utf-8")).get("data", {})
            hold = float(data["hold"]) if data.get("hold") is not None else None
            total_asset = float(data["total_asset"]) if data.get("total_asset") is not None else None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return {
        "account": challenge_mask(),
        "env": snap.get("env", "paper"),
        "cash": snap["cash"],
        "nav": nav,
        "order_hold": hold,
        "broker_total_asset": total_asset,
        "gross_exposure": snap["gross_exposure"],
        "gross_weight": snap["gross_exposure"] / nav if nav else 0,
        "cash_weight": snap["cash"] / nav if nav else 0,
        "positions": positions,
        "as_of": run["ts"],
        "source": f"cloud run {run['run']} (broker sim_list)",
        "run": run["run"],
    }


def cloud_orders(runs: list[dict]) -> list[dict]:
    challenge = _challenge_runs(runs)
    if not challenge:
        return []
    run = challenge[-1]
    path = run["dir"] / "mcp" / "sim_trade_history_order_list.json"
    if not path.is_file():
        return []
    try:
        orders = json.loads(path.read_text(encoding="utf-8")).get("data", {}).get("orders", [])
    except (json.JSONDecodeError, OSError):
        return []
    acct = challenge_mask()
    out = []
    for o in orders:
        status = _CLOUD_ORDER_STATUS.get(o.get("status"), "submitted")
        has_fill = status in ("filled", "part-filled")
        ts = _broker_ts(o.get("create_time"))
        out.append(
            {
                "remark": o.get("text"),
                "symbol": "US." + o["symbol"],
                "side": "buy" if o.get("side") == 1 else "sell",
                "quantity": int(o["qty"]),
                "account": acct,
                "purpose": "cloud",
                "requested_ts": ts,
                "submitted_ts": ts,
                "order_id": str(o.get("order_id")),
                "limit_price": float(o["price"]) if o.get("price") else None,
                "order_type": "limit",
                "supersedes": None,
                "note": f"cloud run {run['run']}",
                "status": status,
                "fill_price": float(o["avg_fill_price"]) if has_fill and o.get("avg_fill_price") else None,
                "fill_qty": int(o["cum_qty"]) if has_fill else None,
                "events": [],
                "source": "cloud",
            }
        )
    return out


def _dedupe_marks(series: list[dict]) -> list[dict]:
    series = sorted(series, key=lambda m: m["ts"])
    deduped: list[dict] = []
    for mark in series:
        if deduped and deduped[-1]["nav"] == mark["nav"] and deduped[-1]["as_of"] == mark["as_of"]:
            deduped[-1]["count"] = deduped[-1].get("count", 1) + 1
            deduped[-1]["ts"] = mark["ts"]
        else:
            deduped.append(dict(mark))
    return deduped


def cloud_nav_marks(runs: list[dict]) -> dict[str, list[dict]]:
    series = [
        {"ts": r["ts"], "as_of": r["run"][:10], "nav": r["snapshot"]["nav"], "source": "cloud:" + r["run"]}
        for r in _challenge_runs(runs)
    ]
    return {challenge_mask(): _dedupe_marks(series)} if series else {}


def sentinel_fallback() -> list[dict]:
    out = []
    for path in sorted((ROOT / "plans" / "sentinel").glob("sched_*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "id": d["id"],
                "name": d["name"],
                "description": d.get("description"),
                "status": d.get("status"),
                "trigger_policy": d.get("trigger_policy"),
                "initial_events_version": d.get("initial_events_version"),
                "template_id": d.get("template_id"),
            }
        )
    return out


EVENTS: list[dict] = []


def build_approvals() -> dict:
    """Operator approval state from the existing envelope system (single source of truth).

    armed  = a valid same-day envelope exists -> executor auto-submits within bounds.
    manual = no valid envelope -> every order needs per-order operator confirmation.
    The kill-switch overrides auto: halted => no new entries regardless of envelope.
    """
    today = datetime.now(ET).date()
    halt = effective_halt(JOURNAL.parent, ROOT)
    halted = bool(halt.get("halted"))
    used = envelope_usage(JOURNAL, today)
    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "today_et": today.isoformat(),
        "halted": halted,
        "used": used,
        "max_orders": 0,
        "envelope": None,
        "mode": "manual",
        "auto_active": False,
        "reason": "No pre-approved envelope - every order needs per-order operator confirmation at the desk console.",
    }
    if not APPROVALS.is_file():
        return scrub(out)
    try:
        batch = ApprovalBatch.model_validate_json(APPROVALS.read_text(encoding="utf-8"))
    except ValueError as exc:
        out["reason"] = "Envelope invalid - falling back to per-order confirmation."
        out["error"] = str(exc)[:200]
        return scrub(out)
    env = batch.model_dump(mode="json")
    env["valid_today"] = batch.valid_on(today)
    out["envelope"] = env
    out["max_orders"] = batch.max_orders
    if not batch.valid_on(today):
        out["reason"] = f"Envelope dated {batch.as_of} is not valid today ({today}) - per-order confirmation only."
    elif halted:
        out["mode"] = "armed"
        out["reason"] = "Envelope valid today, but kill-switch engaged - no new entries."
    else:
        out["mode"] = "armed"
        out["auto_active"] = True
        out["reason"] = f"Envelope armed for {today}: auto-submit within approved bounds ({used}/{batch.max_orders} used)."
    return scrub(out)


def build_state() -> dict:
    global EVENTS
    EVENTS = read_events(JOURNAL)
    exp_report = compute_expectancy(EVENTS, SLEEVE_BY_SYMBOL)
    sleeve_report = {s.sleeve: s for s in exp_report.sleeves}
    ok, count, error = verify_chain(JOURNAL)
    halt = effective_halt(JOURNAL.parent, ROOT)
    risk = yaml.safe_load((ROOT / "config" / "risk.yaml").read_text(encoding="utf-8"))
    validation = parse_validation()
    plans = latest_plans(EVENTS)
    runs = load_cloud_runs()
    cloud = cloud_snapshot(runs)
    drill_snapshot = load_snapshot()
    snapshot = cloud or drill_snapshot
    snapshots: dict[str, dict] = {}
    for snap in (cloud, drill_snapshot):
        if snap and snap["account"] not in snapshots:
            snapshots[snap["account"]] = snap
    orders = build_orders(EVENTS, validation)
    known_ids = {o["order_id"] for o in orders if o["order_id"]}
    orders.extend(o for o in cloud_orders(runs) if o["order_id"] not in known_ids)
    orders.sort(key=lambda r: r["requested_ts"] or "")
    rejections = build_rejections(EVENTS, orders)
    cards = build_cards(plans, orders, validation)
    marks = nav_marks(EVENTS, drill_snapshot)
    marks.update(cloud_nav_marks(runs))
    journal_acct = next((a for a in plans if not a.startswith("SIM-")), None)
    primary = cloud["account"] if cloud else (journal_acct or (drill_snapshot or {}).get("account"))
    if primary in marks:
        marks = {primary: marks[primary], **{a: m for a, m in marks.items() if a != primary}}
    plan_acct = primary if primary in plans else journal_acct
    latest_plan = plans.get(plan_acct, {}).get("plan") if plan_acct else None
    feed = {
        "primary_account": primary,
        "source": "cloud-run bundles (docs/performance)" if cloud else "local drill snapshot",
        "run": cloud["run"] if cloud else None,
        "as_of": snapshot["as_of"] if snapshot else None,
        "cloud_runs": len(_challenge_runs(runs)),
        "plan_account": mask_id(str(latest_plan["account_id"])) if latest_plan else None,
    }
    divergences = [
        "The simulator has no broker stop orders, so protection uses monitored exit plans and defined-risk options instead.",
        "No direct shorting (margin costs and forced-liquidation risk) - defined-risk puts are used instead.",
    ]
    if cloud and plan_acct != primary:
        divergences.append(
            f"Challenge plans stay in the private Drive locker; the public feed carries sanitized snapshots and broker order history. "
            f"The Strategy view shows the latest journal plan (account {plan_acct}) until challenge plans are published."
        )
    halt_timeline = [
        {"ts": ev["ts"], "type": ev["type"], "payload": ev["payload"]}
        for ev in EVENTS
        if ev["type"] in ("halt.engaged", "halt.skip", "halt.released")
    ]
    return scrub(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "chain": {"ok": ok, "count": count, "error": error},
            "halt": halt,
            "approvals": build_approvals(),
            "halt_timeline": halt_timeline,
            "risk": risk,
            "feed": feed,
            "snapshot": snapshot,
            "snapshots": snapshots,
            "drill_snapshot": drill_snapshot if cloud else None,
            "latest_plan": latest_plan,
            "plans": {a: {"ts": e["ts"], "plan": e["plan"]} for a, e in plans.items()},
            "nav_marks": marks,
            "orders": orders,
            "rejections": rejections,
            "cards": cards,
            "instrumentation": build_instrumentation(cards),
            "drill": validation,
            "expectancy": {
                "formula": exp_report.formula,
                "closed_n": exp_report.closed_n,
                "r_n": exp_report.r_n,
                "win_rate": exp_report.win_rate,
                "avg_win_r": exp_report.avg_win_r,
                "avg_loss_r": exp_report.avg_loss_r,
                "expectancy_r": exp_report.expectancy_r,
                "expectancy_pct": exp_report.expectancy_pct,
                "pnl_net": exp_report.pnl_net,
                "fees_total": exp_report.fees_total,
                "unattributed_fills": exp_report.unattributed_fills,
                "open_lots": [lot.model_dump(mode="json") for lot in exp_report.open_lots],
                "sleeves": [
                    {
                        "name": name.replace("_", " ").title(),
                        "closed_n": s.closed_n if s else 0,
                        "win_rate": s.win_rate if s else None,
                        "avg_win_r": s.avg_win_r if s else None,
                        "avg_loss_r": s.avg_loss_r if s else None,
                        "expectancy_r": s.expectancy_r if s else None,
                        "expectancy_pct": s.expectancy_pct if s else None,
                        "pnl_net": s.pnl_net if s else 0.0,
                    }
                    for name, s in (
                        (n, sleeve_report.get(n)) for n in sorted(set(SLEEVE_BY_SYMBOL.values()))
                    )
                ] + [
                    {"name": "Event sleeves (stocks)", "closed_n": 0},
                    {"name": "Defined-risk options", "closed_n": 0},
                ],
                "realized_gross": validation["realized_gross"],
                "fees_note": (
                    f"Net of modeled fees: {exp_report.closed_n} closed round trips, "
                    f"${exp_report.fees_total:,.2f} in fees. The drill round-trip is shown separately."
                ),
                "provisional": exp_report.provisional,
            },
            "divergences": divergences,
            "gaps": [
                {"field": "thesis_ref / inputs_ref", "state": "gap", "note": "per-trade playbook + research-brief refs not in plan/journal yet"},
                {"field": "outlook + conviction", "state": "partial", "note": "market regime only; per-setup outlook and act/wait gate pending"},
                {"field": "expected_edge", "state": "partial", "note": "initial R per trade from plan stop (ADR 0016); pre-trade win-probability model still absent"},
                {"field": "protection heartbeat", "state": "gap", "note": "P2 - synthetic stop monitor"},
                {"field": "roll_plan", "state": "gap", "note": "P2 - option leg groups"},
                {"field": "macro / sentiment / seasonality", "state": "partial", "note": "researcher child designed, not yet in plan artifacts"},
            ],
            "sentinel_fallback": sentinel_fallback(),
        }
    )


# ---------------------------------------------------------------- automation
AUTOMATION_CACHE: dict = {"at": 0.0, "payload": None}
AUTOMATION_LOCK = threading.Lock()


def slim_schedule(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "name": d.get("name"),
        "description": d.get("description"),
        "status": d.get("status"),
        "trigger_policy": d.get("trigger_policy"),
        "initial_events_version": d.get("initial_events_version"),
        "template_id": d.get("template_id"),
        "updated_at": d.get("updated_at"),
    }


def slim_session(d: dict) -> dict:
    template = d.get("template") or {}
    return {
        "id": d.get("id"),
        "title": d.get("title"),
        "status": d.get("status"),
        "source_type": d.get("source_type"),
        "template": {"id": template.get("id"), "name": template.get("name")},
        "stats": d.get("stats"),
        "usage": d.get("usage"),
        "metadata": d.get("metadata"),
        "created_at": d.get("created_at"),
    }


CALENDAR_WINDOW = (date(2026, 11, 17), date(2026, 11, 28))
_PHASE_ORDER = [
    SessionPhase.PRE_MARKET,
    SessionPhase.OPENING_DRIVE,
    SessionPhase.MIDDAY,
    SessionPhase.CLOSING_DRIVE,
    SessionPhase.AFTER_HOURS,
]


def build_watchlist() -> dict | None:
    path = ROOT / "data" / "watchlist.json"
    if not path.is_file():
        return None
    try:
        book = Watchlist.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    today = datetime.now(ET).date()
    payload = book.model_dump(mode="json")
    payload.update(stale=book.stale(today), active_count=len(book.active(today)))
    return payload


def build_calendar() -> dict:
    """Deterministic market-calendar gate + session-phase routing (local, no API)."""
    now = datetime.now(UTC)
    gate = evaluate(now)
    today = gate.now_et.date()
    timeline_day = today
    if not gate.trading_day and gate.next_run:
        timeline_day = gate.next_run.et.date()
    start, end = CALENDAR_WINDOW
    upcoming: list[dict] = []
    for offset in range(1, 45):
        if len(upcoming) >= 5:
            break
        cursor = today + timedelta(days=offset)
        if is_trading_day(cursor):
            upcoming.append({
                "date": cursor.isoformat(),
                "half_day": is_half_day(cursor),
                "events": [e.name for e in events_on(cursor)],
                "earnings_season": earnings_season(cursor),
            })
        elif holiday_name(cursor):
            upcoming.append({"date": cursor.isoformat(), "closed": holiday_name(cursor)})
    return {
        "now_utc": gate.now_utc.isoformat(),
        "now_et": gate.now_et.isoformat(),
        "et_label": gate.now_et.strftime("%Z"),
        "trading_day": gate.trading_day,
        "half_day": gate.half_day,
        "holiday": gate.holiday,
        "phase": gate.phase.value,
        "run": gate.run,
        "reason": gate.reason,
        "strategy": gate.strategy.model_dump(mode="json"),
        "events": [e.model_dump(mode="json") for e in gate.events],
        "earnings_season": earnings_season(today),
        "next_run": gate.next_run.model_dump(mode="json") if gate.next_run else None,
        "timeline_day": timeline_day.isoformat(),
        "timeline": session_timeline(timeline_day),
        "phase_strategies": [strategy_for(p).model_dump(mode="json") for p in _PHASE_ORDER],
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "schedules": [d.model_dump(mode="json") for d in generate_hourly_schedules(start, end)],
        "watchlist": build_watchlist(),
        "upcoming": upcoming,
    }


def build_automation() -> dict:
    with AUTOMATION_LOCK:
        now = time.time()
        if AUTOMATION_CACHE["payload"] and now - AUTOMATION_CACHE["at"] < 20:
            return AUTOMATION_CACHE["payload"]
        calendar = build_calendar()
        try:
            import forward

            schedules = forward.req("GET", "/schedules?limit=20").get("data") or []
            sessions = forward.req("GET", "/sessions?limit=12").get("data") or []
            payload = {
                "ok": True,
                "source": "live - api.qoder.com/api/v1/forward",
                "fetched_at": datetime.now(UTC).isoformat(),
                "schedules": [slim_schedule(s) for s in schedules],
                "sessions": [slim_session(s) for s in sessions],
                "calendar": calendar,
            }
        except Exception as exc:  # noqa: BLE001 - degrade to local export
            payload = {
                "ok": False,
                "source": "cached local export (plans/sentinel) - Forward API unreachable",
                "error": str(exc)[:300],
                "fetched_at": datetime.now(UTC).isoformat(),
                "schedules": sentinel_fallback(),
                "sessions": [],
                "calendar": calendar,
            }
        AUTOMATION_CACHE.update(at=now, payload=payload)
        return payload


# ---------------------------------------------------------------- http
def disarm_envelope() -> dict:
    """Revert to manual: remove the envelope and propagate to the cloud mount via git.

    Path-limited commit so concurrent in-progress files are never swept in. A backup
    copy is kept locally (untracked) so the operator can re-arm by re-committing it.
    """
    if not APPROVALS.is_file():
        return {"ok": True, "disarmed": False, "note": "no envelope to disarm", "approvals": build_approvals()}
    backup = APPROVALS.with_name("approvals.disarmed.json")
    backup.write_text(APPROVALS.read_text(encoding="utf-8"), encoding="utf-8")
    APPROVALS.unlink()
    pushed, git_error = False, None
    try:
        subprocess.run(["git", "add", "--", "data/approvals.json"], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Disarm auto approval envelope (operator via dashboard)", "--", "data/approvals.json"],
            cwd=ROOT, check=True, capture_output=True,
        )
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True, capture_output=True)
        pushed = True
    except subprocess.CalledProcessError as exc:
        git_error = (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()[:300]
    return {"ok": True, "disarmed": True, "pushed": pushed, "git_error": git_error, "approvals": build_approvals()}


def _git_push_paths(message: str, paths: list[str]) -> tuple[bool, str | None]:
    try:
        subprocess.run(["git", "add", "--", *paths], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message, "--", *paths], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True, capture_output=True)
        return True, None
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()[:300]


def _git_push_approvals(message: str) -> tuple[bool, str | None]:
    return _git_push_paths(message, ["data/approvals.json"])


def arm_envelope(body: dict) -> dict:
    """Operator pre-approval from the desk: write a bounded same-day envelope.

    reuse_last re-dates the last disarmed envelope (the operator re-approves its
    bounds for today); otherwise the body must carry explicit order lines.
    Propagates to the cloud mount via a path-limited commit, mirroring disarm.
    """
    today = datetime.now(ET).date()
    if body.get("reuse_last"):
        backup = APPROVALS.with_name("approvals.disarmed.json")
        source = backup if backup.is_file() else APPROVALS
        if not source.is_file():
            return {"ok": False, "error": "No previous envelope to re-arm. Use Pre-approve to define bounds."}
        try:
            candidate = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"ok": False, "error": "Previous envelope backup is unreadable."}
        candidate["as_of"] = today.isoformat()
        candidate["approved_at"] = datetime.now(UTC).isoformat()
        candidate["approved_by"] = "operator (dashboard auto re-arm)"
        candidate["note"] = ((candidate.get("note") or "") + " | re-armed for today via dashboard").strip(" |")
    else:
        candidate = {
            "as_of": today.isoformat(),
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_by": "operator (dashboard)",
            "max_orders": body.get("max_orders"),
            "max_notional": body.get("max_notional"),
            "note": str(body.get("note") or "")[:200],
            "orders": body.get("orders"),
        }
    try:
        batch = ApprovalBatch.model_validate(candidate)
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": f"Envelope invalid: {str(exc)[:300]}"}
    APPROVALS.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    pushed, git_error = _git_push_approvals("Arm auto approval envelope (operator via dashboard)")
    return {"ok": True, "armed": True, "pushed": pushed, "git_error": git_error, "approvals": build_approvals()}


def halt_control(body: dict) -> dict:
    """Kill-switch from the desk: journal flag + shared repo flag pushed to the cloud mount."""
    halted = body.get("halted")
    if not isinstance(halted, bool):
        return {"ok": False, "error": "halted must be a boolean"}
    reason = str(body.get("reason") or "").strip()[:200]
    if not reason:
        reason = "operator kill-switch via dashboard" if halted else "operator resume via dashboard"
    state = set_halt(JOURNAL.parent, halted, reason)
    append_event(JOURNAL, "halt.engaged" if halted else "halt.released", state)
    REPO_HALT.parent.mkdir(parents=True, exist_ok=True)
    REPO_HALT.write_text(json.dumps({**state, "set_by": "operator (dashboard)"}, indent=2), encoding="utf-8")
    pushed, git_error = _git_push_paths(
        "Engage kill-switch (operator via dashboard)" if halted else "Release kill-switch (operator via dashboard)",
        ["data/halt.json"],
    )
    return {"ok": True, "halt": state, "pushed": pushed, "git_error": git_error, "approvals": build_approvals()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):  # quieter logs
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            try:
                self._json(build_state())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
            return
        if path == "/api/automation":
            self._json(build_automation())
            return
        if path.startswith("/api/"):
            self._json({"error": "not found"}, 404)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 64_000:
            raise ValueError("empty or oversized request body")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/approvals/disarm":
            try:
                self._json(disarm_envelope())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
            return
        if path == "/api/approvals/arm":
            try:
                self._json(arm_envelope(self._body()))
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/halt":
            try:
                self._json(halt_control(self._body()))
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 400)
            return
        self._json({"error": "not found"}, 404)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"tyche desk dashboard -> http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()