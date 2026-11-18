"""Deploy the operator approval envelope + SGT digest timestamps.

Option 2 (operator-approved): the executor may submit paper orders without a
per-order confirmation popup ONLY within the operator's same-day pre-approved
envelope (data/approvals.json, git-tracked, mount-synced), checked by the
deterministic 'tyche authorize' CLI gate. sim_trade_input_order moves from
always_ask to always_allow; cancel/modify stay always_ask. Digest headers gain
SGT (UTC+8). Every prompt edit is an exact single-occurrence replacement on the
LIVE content, with pre-change snapshots under gitignored plans/ and GET-after
verification. After running, re-pin the desk roster's executor version (the
compiled agent bumps on template edit).

Run: MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe scripts/deploy_envelope_sgt.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import forward

DESK = "tmpl_004fa008901a6c256bd0ed3f"
EXECUTOR = "tmpl_bc25a5c313827d53894fd7ff"
SCHEDULE = "sched_2dc7702e4f005d04235c078a"
SNAP_DIR = ROOT / "plans"

APPROVALS_CONTRACT = (
    "APPROVALS CONTRACT (operator pre-approved envelope): data/approvals.json in the repo "
    "mount is the operator's signed intent for TODAY (ET date), committed operator-side and "
    "synced by the mount. Validate with 'tyche approvals --json' (exit 1 = missing/invalid => "
    "no envelope). Before EVERY sim_trade_input_order call without a live per-order "
    "confirmation, the executor runs 'tyche authorize --symbol S --side buy|sell --qty N "
    "--limit P' (exit 0 = authorized). Submit only on exit 0, verbatim within the approved "
    "bounds; journal order.requested with payload.authorization {kind: envelope, as_of}. The "
    "envelope budget (max_orders) is counted from the journal; exhausted or out-of-bounds => "
    "per-order confirmation or skip. Envelope orders are limit orders on the challenge paper "
    "account only; cancel/modify writes stay always_ask. If the envelope is missing, stale "
    "(as_of != today ET) or invalid: fall back to per-order operator confirmation; never "
    "improvise approval. "
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 occurrence, found {count} — aborting, nothing written")
    return text.replace(old, new)


def snapshot(name: str, obj: dict) -> None:
    SNAP_DIR.mkdir(exist_ok=True)
    path = SNAP_DIR / name
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print("snapshot:", path.name)


def update_schedule() -> None:
    sched = forward.req("GET", f"/schedules/{SCHEDULE}")
    snapshot("cloud-schedule-pre-envelope.json", sched)
    content = sched["initial_events"][0]["content"]
    if "APPROVALS CONTRACT" in content:
        print("schedule already carries the envelope contract — skipping")
        return
    content = replace_once(
        content,
        "No order submissions without per-order operator confirmation. ",
        "No order submissions at pre-market; instead propose the evening approval batch in "
        "the digest (symbol, side, max qty, limit bound per name) so the operator can "
        "pre-approve before the drives. ",
        "schedule pre_market",
    )
    content = replace_once(
        content,
        "executor submits ONLY via MCP sim_trade_input_order with per-order operator "
        "confirmation (always_ask).",
        "executor submits ONLY via MCP sim_trade_input_order, each order first passing "
        "'tyche authorize' against the operator's same-day envelope (APPROVALS CONTRACT) or "
        "carrying an explicit per-order operator confirmation; neither => no submission.",
        "schedule drives",
    )
    content = replace_once(
        content,
        "act ONLY on a drift breach or risk halt, with per-order operator confirmation; "
        "otherwise submit no orders.",
        "act ONLY on a drift breach or risk halt, with envelope authorization or per-order "
        "operator confirmation; otherwise submit no orders.",
        "schedule midday",
    )
    content = replace_once(
        content,
        "PHASE PLAYBOOK (follow the gate's live phase):",
        APPROVALS_CONTRACT + "PHASE PLAYBOOK (follow the gate's live phase):",
        "schedule approvals insert",
    )
    content = replace_once(
        content,
        "paste HH:MM UTC into every delegation message (members have no clock tool).",
        "paste HH:MM UTC into every delegation message (members have no clock tool). "
        "SGT = UTC+8 (operator's home clock); show UTC and SGT in the digest header.",
        "schedule clock",
    )
    content = replace_once(
        content,
        "<HH:MM> UTC; line 2 one plain-English sentence",
        "<HH:MM> UTC / <HH:MM> SGT; line 2 one plain-English sentence",
        "schedule digest header",
    )
    description = replace_once(
        sched["description"],
        "orders require per-order operator confirmation via executor always_ask.",
        "orders require operator authorization: same-day pre-approved envelope "
        "(tyche authorize) or per-order confirmation; cancel/modify stay always_ask.",
        "schedule description",
    )
    forward.req("POST", f"/schedules/{SCHEDULE}", {
        "initial_events": [{"type": "user.message", "content": content}],
        "description": description,
    })
    check = forward.req("GET", f"/schedules/{SCHEDULE}")
    live = check["initial_events"][0]["content"]
    for marker in ("APPROVALS CONTRACT", "tyche authorize", "<HH:MM> UTC / <HH:MM> SGT"):
        if marker not in live:
            raise SystemExit(f"schedule update missing marker: {marker}")
    print("schedule updated: envelope contract + SGT header, version", check.get("initial_events_version"))


def update_desk() -> None:
    template = forward.req("GET", f"/templates/{DESK}")
    snapshot("cloud-desk-pre-envelope.json", template)
    system = template["system"]
    if "APPROVALS:" in system:
        print("desk template already carries the envelope clause — skipping")
        return
    system = replace_once(
        system,
        "Every order write is gated by an operator confirmation prompt; never ask it to "
        "bypass the gate.",
        "Every order write requires operator authorization: a fresh 'tyche authorize' exit-0 "
        "pass against the same-day envelope (data/approvals.json) or an explicit per-order "
        "confirmation; never ask it to bypass the gate.",
        "desk delegation",
    )
    system = replace_once(
        system,
        "execution only when the operator confirms each order (executor sim writes are "
        "always_ask)",
        "execution only with operator authorization — a valid same-day pre-approved envelope "
        "(data/approvals.json, 'tyche authorize' per order) or per-order operator confirmation",
        "desk daily flow",
    )
    system = replace_once(
        system,
        "HARD RULES:",
        "APPROVALS: data/approvals.json is the operator's pre-approved bounded batch for "
        "today (ET date), committed operator-side and synced by the mount; the executor runs "
        "'tyche authorize' before every unconfirmed submit (exit 0 required) and journals "
        "payload.authorization {kind: envelope, as_of}; missing/stale/invalid envelope => "
        "per-order confirmation only, never improvise approval. Pre-market digests propose "
        "the batch for evening approval (SGT). HARD RULES:",
        "desk approvals insert",
    )
    forward.req("POST", f"/templates/{DESK}", {"system": system})
    check = forward.req("GET", f"/templates/{DESK}")
    live = check["system"]
    if "APPROVALS:" not in live or live.count("HARD RULES:") != 1 or live.count("DAILY FLOW") != 1:
        raise SystemExit("desk template verification failed")
    print("desk template updated: envelope authorization clause")


EXECUTOR_OLD_HITL = (
    "HUMAN-IN-THE-LOOP: every order write (sim_trade_input_order, sim_trade_cancel_order, "
    "sim_trade_modify_order) is gated by an always_ask permission policy. Before each such "
    "call, present an order preview to the operator: symbol, side, qty, order type, limit "
    "price, estimated notional and fees, the auditor verdict, and the plan hash. Wait for "
    "the operator's explicit confirmation; the platform enforces this gate. Never batch "
    "multiple orders into one confirmation. Paper orders still require this preview-and-"
    "confirm step on this desk."
)
EXECUTOR_NEW_AUTH = (
    "OPERATOR AUTHORIZATION: every order write needs operator authorization by one of two "
    "paths. (A) PRE-APPROVED ENVELOPE: data/approvals.json in the repo mount is the "
    "operator's bounded batch for today (ET date). Before each sim_trade_input_order call, "
    "run 'tyche authorize --symbol S --side buy|sell --qty N --limit P' from the repo root; "
    "submit ONLY on exit 0, verbatim within the approved bounds, and include authorization "
    "{kind: envelope, as_of: <date>} in the order.requested journal payload. Exit 1 "
    "(missing/stale envelope, no line, qty/limit out of bounds, budget exhausted) => do NOT "
    "submit on the envelope path. (B) PER-ORDER CONFIRMATION: sim_trade_cancel_order and "
    "sim_trade_modify_order remain always_ask, and any input order without an envelope pass "
    "falls back to the platform confirmation prompt: present an order preview (symbol, side, "
    "qty, order type, limit price, estimated notional and fees, auditor verdict, plan hash) "
    "and wait for the operator's explicit confirmation. Never batch multiple orders into one "
    "confirmation; never treat the envelope as approval for cancel/modify; envelope orders "
    "are limit orders on the challenge paper account only."
)


def update_executor() -> None:
    template = forward.req("GET", f"/templates/{EXECUTOR}")
    snapshot("cloud-executor-pre-envelope.json", template)
    system = template["system"]
    if "OPERATOR AUTHORIZATION" in system:
        print("executor template already carries the envelope clause — skipping")
        return
    system = replace_once(system, EXECUTOR_OLD_HITL, EXECUTOR_NEW_AUTH, "executor HITL paragraph")
    system = replace_once(
        system,
        "(3) the operator has armed execution in this session.",
        "(3) the order carries operator authorization: a fresh 'tyche authorize' exit-0 pass "
        "against data/approvals.json (same-day envelope) or an explicit per-order operator "
        "confirmation.",
        "executor precondition 3",
    )
    tools = json.loads(json.dumps(template["tools"]))
    flipped = 0
    for toolset in tools:
        for config in toolset.get("configs", []):
            if config.get("name") == "sim_trade_input_order":
                if config.get("permission_policy", {}).get("type") != "always_ask":
                    raise SystemExit("sim_trade_input_order is not always_ask — aborting")
                config["permission_policy"] = {"type": "always_allow"}
                flipped += 1
            if (
                config.get("name") in {"sim_trade_cancel_order", "sim_trade_modify_order"}
                and config.get("permission_policy", {}).get("type") != "always_ask"
            ):
                raise SystemExit("cancel/modify policy unexpected — aborting")
    if flipped != 1:
        raise SystemExit(f"expected 1 input_order policy flip, got {flipped}")
    forward.req("POST", f"/templates/{EXECUTOR}", {"system": system, "tools": tools})
    check = forward.req("GET", f"/templates/{EXECUTOR}")
    live = check["system"]
    if "OPERATOR AUTHORIZATION" not in live or "HUMAN-IN-THE-LOOP" in live:
        raise SystemExit("executor prompt verification failed")
    policies = {
        c["name"]: c.get("permission_policy", {}).get("type")
        for ts in check["tools"] for c in ts.get("configs", [])
        if c["name"].startswith("sim_trade_") and "permission_policy" in c
    }
    if policies.get("sim_trade_input_order") != "always_allow":
        raise SystemExit("input_order policy did not flip")
    if policies.get("sim_trade_cancel_order") != "always_ask" or policies.get("sim_trade_modify_order") != "always_ask":
        raise SystemExit("cancel/modify policies changed unexpectedly")
    if check.get("vaults") != template.get("vaults") or check.get("environment_id") != template.get("environment_id"):
        raise SystemExit("executor vault/env bindings changed unexpectedly")
    print("executor updated: envelope path + input_order always_allow; cancel/modify stay always_ask")
    print("NEXT: re-pin the desk roster executor to the new compiled version (get_agent agent_00vtx8mfbxerk6vxmny5)")


def main() -> None:
    update_schedule()
    update_desk()
    update_executor()


if __name__ == "__main__":
    main()