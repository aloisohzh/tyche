"""Read-only verification of the envelope + SGT deploy (no secrets printed)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward

SCHEDULE = "sched_2dc7702e4f005d04235c078a"
EXECUTOR = "tmpl_bc25a5c313827d53894fd7ff"
DESK = "tmpl_004fa008901a6c256bd0ed3f"

s = forward.req("GET", f"/schedules/{SCHEDULE}")
c = s["initial_events"][0]["content"]
print("SCHEDULE", s["name"], "status", s["status"], "events_version", s["initial_events_version"])
print("  cron:", s["trigger_policy"]["expression"], s["trigger_policy"]["timezone"])
print("  next:", s["trigger_policy"].get("upcoming_runs_at"))
for marker in ("APPROVALS CONTRACT", "tyche authorize", "<HH:MM> UTC / <HH:MM> ET / <HH:MM> SGT",
               "propose the evening approval batch"):
    print(f"  [{'OK' if marker in c else 'MISSING'}] {marker}")

e = forward.req("GET", f"/templates/{EXECUTOR}")
pol = {cfg["name"]: cfg.get("permission_policy", {}).get("type")
       for ts in e["tools"] for cfg in ts.get("configs", [])
       if cfg["name"].startswith("sim_trade_") and "permission_policy" in cfg}
print("EXECUTOR policies:", pol)
print("  envelope clause:", "OPERATOR AUTHORIZATION" in e["system"])
print("  act/wait gate intact:", "ACT/WAIT GATE" in e["system"])

d = forward.req("GET", f"/templates/{DESK}")
pins = [(a.get("template_id"), a.get("version")) for a in d["multiagent"]["agents"]]
print("DESK roster pins:", pins)
print("  desk APPROVALS clause:", "APPROVALS:" in d["system"])