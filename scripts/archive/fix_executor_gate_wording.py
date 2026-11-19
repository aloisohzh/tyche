# ARCHIVED 2026-11-19: one-shot live-prompt patch; do not run.
"""Correct the executor path-B wording for always_allow (no platform pause).

After the envelope deploy, sim_trade_input_order is always_allow: calling it
executes immediately. The prior wording ("falls back to the platform
confirmation prompt") could lead the model to call the tool expecting a pause
that no longer exists. This makes the gate explicit and fail-closed for
unattended no-envelope runs. System-only edit; tools/vault/env preserved.
Re-pin the roster afterwards (compiled version bumps).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward

EXECUTOR = "tmpl_bc25a5c313827d53894fd7ff"
OLD = (
    "any input order without an envelope pass falls back to the platform confirmation "
    "prompt: present an order preview (symbol, side, qty, order type, limit price, "
    "estimated notional and fees, auditor verdict, plan hash) and wait for the operator's "
    "explicit confirmation."
)
NEW = (
    "sim_trade_input_order is always_allow, so calling it executes IMMEDIATELY with no "
    "platform pause — never call it until authorized. Any input order without an envelope "
    "pass needs conversational per-order confirmation: present an order preview (symbol, "
    "side, qty, order type, limit price, estimated notional and fees, auditor verdict, plan "
    "hash) in your reply and call the tool ONLY after the operator's approving message; in "
    "an unattended run with no valid envelope, do NOT submit (journal it as awaiting "
    "authorization and report)."
)

t = forward.req("GET", f"/templates/{EXECUTOR}")
system = t["system"]
if "executes IMMEDIATELY with no platform pause" in system:
    print("already corrected — skipping")
    raise SystemExit(0)
if system.count(OLD) != 1:
    raise SystemExit(f"expected 1 occurrence of path-B wording, found {system.count(OLD)}")
system = system.replace(OLD, NEW)
forward.req("POST", f"/templates/{EXECUTOR}", {"system": system})
chk = forward.req("GET", f"/templates/{EXECUTOR}")
s = chk["system"]
assert "executes IMMEDIATELY with no platform pause" in s
assert "platform confirmation prompt" not in s
assert "ACT/WAIT GATE" in s and "OPERATOR AUTHORIZATION" in s
pol = {c["name"]: c.get("permission_policy", {}).get("type")
       for ts in chk["tools"] for c in ts.get("configs", [])
       if c["name"].startswith("sim_trade_") and "permission_policy" in c}
assert pol == {"sim_trade_input_order": "always_allow",
               "sim_trade_cancel_order": "always_ask",
               "sim_trade_modify_order": "always_ask"}, pol
print("executor path-B wording corrected; policies intact:", pol)
print("NEXT: re-pin desk roster executor to the new compiled version")