"""Arm the hourly paper desk: lift the 2026-11-19 validation-mode hold.

Reads each live template/schedule, removes the hold clauses, pins the reviewed release,
updates the six-fire cron, and (phase resume) resumes tyche-hourly. Default is a
read-only check; --apply mutates one named phase at a time.

Run: .venv/Scripts/python.exe scripts/arm_hourly_desk.py [--apply] [--phase PHASE]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import forward
from deploy_hourly_workflow import MODE, PROTECTED
from deploy_token_policy import desired_executor, desired_researcher

from tyche.market_calendar import generate_hourly_schedules

RELEASE = "3312287ce282cedacdafab552b40678e386ea90d"
TEMPLATES = {
    "desk": "tmpl_004fa008901a6c256bd0ed3f",
    "researcher": "tmpl_875834770244a9e35c7f6499",
    "auditor": "tmpl_ae317cc0626a4fcc8fa8fad6",
    "executor": "tmpl_bc25a5c313827d53894fd7ff",
}
SCHEDULE = "sched_2dc7702e4f005d04235c078a"
WINDOW = (date(2026, 11, 18), date(2026, 11, 28))
PINS = Path(tempfile.gettempdir()) / "tyche-arm-pins.json"
OLD_RELEASES = (
    "119d4e57a84b4509200fe84731f230dd5dd9cade",
    "7288d68758ec2fedcee137622fee472be5d9a41d",
)

COMMON = [
    ("HOURLY INTEGRATED WORKFLOW V2\n" + MODE, "HOURLY INTEGRATED WORKFLOW V2 (ARMED 2026-11-19)"),
    ("Only its one executor may perform execution-state writes after release;",
     "Only its one executor may perform execution-state writes;"),
    (("A controlled operator-assigned validation owner must finish and relinquish ownership "
      "before the scheduled owner takes over. "), ""),
]

BY_ROLE = {
    "desk": [
        ("No broker writes during hold.", "Broker writes follow the reservation and audit contract."),
        ("No execution-approved Audit JSON during hold, no fabricated review times or references.",
         ("Execution-approved Audit JSON requires a fresh exact-order review inside its validity window; "
          "never fabricate review times or references.")),
        ("Advice never overrides the kernel, auditor, operator or hold.",
         "Advice never overrides the kernel, auditor, operator or halt."),
        ("Validation mode alone does not authorize a write.",
         "Deployment alone does not authorize a write."),
        ("'PREVIEW ONLY - NOT ARMED'", "'PAPER ARMED'"),
    ],
    "researcher": [],
    "auditor": [
        (("When explicitly requested for a future executable tactical proposal after rollout release, "
          "also write"), "When requested for an executable tactical proposal, also write"),
        ("Under rollout hold do not issue an execution-approved JSON.",
         "Issue an execution-approved JSON only for a fresh exact-order review inside its validity window."),
        ("Your verdict cannot release rollout hold or grant operator consent.",
         "Your verdict is evidence, not operator consent."),
        ("Both lanes remain unarmed, and duplicate symbol ownership or unverified shared state is a blocker.",
         "Duplicate symbol ownership or unverified shared state is a blocker."),
    ],
    "executor": [
        ("without --record during rollout hold.", "without --record; tick is inspection only."),
        ("ONE-SHOT SUBMISSION AFTER RELEASE ONLY:", "ONE-SHOT SUBMISSION:"),
        ("is necessary, never sufficient to override rollout hold.",
         ("is necessary, never sufficient: submit only the exact previewed order authorized by the "
          "active contract.")),
        ("Validation mode alone does not authorize a write.",
         "Deployment alone does not authorize a write."),
    ],
}

SCHEDULE_REPLACEMENTS = [
    ("TYCHE HOURLY DESK RUN - VALIDATION MODE. " + MODE, "TYCHE HOURLY DESK RUN (ARMED 2026-11-19)."),
    ("plus PREVIEW ONLY - NOT ARMED", "plus PAPER ARMED"),
    (("No production recorded tactical ticks or reservations until durable single-writer ownership "
      "for BOTH lanes is proven; use read-only tick and separate synthetic test state."),
     ("Confirm durable single-writer ownership for BOTH lanes before recorded tactical ticks or "
      "reservations; otherwise use read-only tick and separate synthetic test state.")),
    ("No execution-approved Audit JSON during hold.",
     "Execution-approved Audit JSON requires a fresh exact-order review inside its validity window."),
    ("No order may submit in any phase until the hold is explicitly released after operational validation.",
     ("An order may submit only through the executor's exact reservation/audit/grant contract; live "
      "trading is forbidden.")),
    ("Install editable --no-deps if tyche is missing.",
     ("Install editable --no-deps if tyche is missing. Run tyche journal-verify and tyche halt-status "
      "--json; halted=true blocks buys while approved de-risking sells may still run.")),
]


def replace_exact(text: str, old: str, new: str, expected: int, label: str) -> str:
    found = text.count(old)
    if found != expected:
        raise ValueError(f"{label}: expected {expected} occurrence(s) of {old[:60]!r}, found {found}")
    return text.replace(old, new)


def replace_hashes(text: str) -> str:
    for old in OLD_RELEASES:
        if old in text:
            text = text.replace(old, RELEASE)
    return text


def transform(text: str, role: str) -> str:
    if role == "schedule":
        for old, new in SCHEDULE_REPLACEMENTS:
            found = text.count(old)
            if found < 1:
                raise ValueError(f"schedule: expected clause {old[:60]!r}, found none")
            text = text.replace(old, new)
        text = replace_exact(text, COMMON[0][0], COMMON[0][1], 1, "schedule workflow heading")
        text = replace_exact(text, COMMON[1][0], COMMON[1][1], 1, "schedule state sentence")
        text = replace_exact(text, COMMON[2][0], COMMON[2][1], 1, "schedule validation-owner sentence")
        verify(replace_hashes(text), role)
        return replace_hashes(text)
    repeated = 2 if role == "executor" else 1
    text = replace_exact(text, COMMON[0][0], COMMON[0][1], 1, role + " workflow heading")
    text = replace_exact(text, "\n\n" + MODE + "\n\n", "\n\n", 1, role + " hold paragraph")
    text = replace_exact(text, COMMON[1][0], COMMON[1][1], repeated, role + " state sentence")
    text = replace_exact(text, COMMON[2][0], COMMON[2][1], repeated, role + " validation-owner sentence")
    for old, new in BY_ROLE[role]:
        found = text.count(old)
        if found < 1:
            raise ValueError(f"{role}: expected clause {old[:60]!r}, found none")
        text = text.replace(old, new)
    text = replace_hashes(text)
    verify(text, role)
    return text


def verify(text: str, role: str) -> None:
    bad = [
        "HOURLY VALIDATION MODE", "rollout hold", "Rollout hold", "PREVIEW ONLY",
        "ONE-SHOT SUBMISSION AFTER RELEASE", "Validation mode alone", "NOT RELEASED",
        "operator-approved validation contract", "validation-hold",
    ]
    hits = [needle for needle in bad if needle in text]
    if hits:
        raise ValueError(f"{role}: hold language remains: {hits}")
    if "NOT ARMED" in text and role != "schedule":
        raise ValueError(f"{role}: stale NOT ARMED label")
    if role in ("desk", "schedule") and "PAPER ARMED" not in text:
        raise ValueError(f"{role}: armed Telegram label missing")
    if RELEASE not in text:
        raise ValueError(f"{role}: reviewed release not pinned")
    if any(old in text for old in OLD_RELEASES):
        raise ValueError(f"{role}: stale release pin remains")


def update_template(role: str, before: dict, body: dict, apply: bool) -> dict | None:
    changed = {key: value for key, value in body.items() if before.get(key) != value}
    print(json.dumps({"template": role, "fields": list(changed), "apply": apply}))
    if not changed or not apply:
        return None
    result = forward.req("POST", f"/templates/{TEMPLATES[role]}", changed)
    print(json.dumps({"template": role, "response_keys": sorted(result.keys()),
                      "response_version": result.get("version")}))
    after = forward.req("GET", f"/templates/{TEMPLATES[role]}")
    if any(after.get(key) != value for key, value in changed.items()):
        raise RuntimeError(f"{role}: post-write verification differs; stop and inspect")
    for key in PROTECTED:
        if key in body:
            continue
        if after.get(key) != before.get(key):
            raise RuntimeError(f"{role}: protected field {key} changed; stop and inspect")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write live templates/schedule.")
    parser.add_argument("--phase", choices=["all", "members", "desk", "schedule", "resume"],
                        default="all", help="Apply one verified phase at a time.")
    args = parser.parse_args()
    if args.phase == "resume" and not args.apply:
        parser.error("resume writes the schedule; pass --apply")

    if args.phase in ("all", "members"):
        pins: dict[str, int] = {}
        desk_before = forward.req("GET", f"/templates/{TEMPLATES['desk']}")
        roster_before = {row["template_id"]: row["version"]
                         for row in desk_before["multiagent"]["agents"] if row.get("type") == "agent"}
        for role in ("researcher", "auditor", "executor"):
            before = forward.req("GET", f"/templates/{TEMPLATES[role]}")
            body = {"system": transform(before["system"], role)}
            if role == "researcher":
                body["tools"] = [desired_researcher(t) if t.get("type") == "mcp_toolset" else t
                                 for t in before["tools"]]
            if role == "executor":
                body["tools"] = [desired_executor(t) if t.get("type") == "mcp_toolset" else t
                                 for t in before["tools"]]
            result = update_template(role, before, body, args.apply)
            if args.apply:
                version = (result or {}).get("version")
                pins[role] = (int(version) if isinstance(version, int)
                              else roster_before[TEMPLATES[role]] + 1)
        if args.apply:
            PINS.write_text(json.dumps(pins), encoding="utf-8")
            print(json.dumps({"member_pins": pins}))

    if args.phase in ("all", "desk"):
        desk_before = forward.req("GET", f"/templates/{TEMPLATES['desk']}")
        roster = json.loads(json.dumps(desk_before["multiagent"]))
        if args.apply:
            if not PINS.is_file():
                raise SystemExit("run the members phase first")
            pins = json.loads(PINS.read_text(encoding="utf-8"))
            for row in roster["agents"]:
                for role, tid in TEMPLATES.items():
                    if role != "desk" and row.get("template_id") == tid:
                        row["version"] = pins[role]
            body = {"system": transform(desk_before["system"], "desk"), "multiagent": roster}
            update_template("desk", desk_before, body, True)
            check = forward.req("GET", f"/templates/{TEMPLATES['desk']}")
            got = {row["template_id"]: row["version"] for row in check["multiagent"]["agents"]
                   if row.get("type") == "agent"}
            for role, tid in TEMPLATES.items():
                if role != "desk" and got.get(tid) != pins[role]:
                    raise RuntimeError(f"desk roster pin for {role} did not take effect")
            print(json.dumps({"desk_pins": pins}))
        else:
            print(json.dumps({"desk": "would update prompt and roster pins",
                              "pins_source": "members-phase response version, else previous + 1"}))

    if args.phase in ("all", "schedule"):
        schedule = forward.req("GET", f"/schedules/{SCHEDULE}")
        events = schedule["initial_events"]
        if len(events) != 1 or events[0]["type"] != "user.message":
            raise ValueError("unexpected schedule event structure")
        content = transform(events[0]["content"], "schedule")
        specs = generate_hourly_schedules(*WINDOW)
        if len(specs) != 1:
            raise ValueError(f"expected one hourly cron, got {len(specs)}")
        policy = dict(schedule.get("trigger_policy") or {})
        policy["expression"] = specs[0].cron
        body = {
            "initial_events": [{"type": "user.message", "content": content}],
            "description": ("Hourly integrated paper screening and protection, armed 2026-11-19; "
                            "per-order confirmations and validation contracts still govern submissions."),
            "trigger_policy": policy,
        }
        print(json.dumps({"schedule": {"fields": ["initial_events", "description", "trigger_policy"],
                                       "cron": specs[0].cron, "status": schedule.get("status"),
                                       "apply": args.apply}}))
        if args.apply:
            changed = {k: v for k, v in body.items() if schedule.get(k) != v}
            if changed:
                request = urllib.request.Request(
                    forward.BASE + f"/schedules/{SCHEDULE}", method="POST",
                    data=json.dumps(changed).encode(),
                    headers={"Authorization": "Bearer " + forward.pat(),
                             "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    response.read()
            after = forward.req("GET", f"/schedules/{SCHEDULE}")
            if after["initial_events"][0]["content"] != content:
                raise RuntimeError("schedule prompt update did not take effect")
            if (after.get("trigger_policy") or {}).get("expression") != specs[0].cron:
                raise RuntimeError("schedule cron update did not take effect")
            for key in ("execution", "template_id", "identity_id", "environment_id", "sinks", "status"):
                if after.get(key) != schedule.get(key):
                    raise RuntimeError(f"schedule protected field {key} changed; stop and inspect")
            print(json.dumps({"schedule_verified": True}))

    if args.phase == "resume":
        schedule = forward.req("GET", f"/schedules/{SCHEDULE}")
        if schedule.get("status") != "active":
            forward.req("POST", f"/schedules/{SCHEDULE}/unpause", {})
        resumed = forward.req("GET", f"/schedules/{SCHEDULE}")
        if resumed.get("status") != "active":
            raise RuntimeError("resume did not take effect")
        print(json.dumps({"resumed": True, "status": resumed.get("status"),
                          "cron": (resumed.get("trigger_policy") or {}).get("expression")}))


if __name__ == "__main__":
    main()
