"""Create the two-fire Qoder Cloud Automation card for the tyche paper desk.

Reads QODER_PAT and the three runtime secret values from gitignored .env and sends
them directly to the Cloud API. Never prints secret values.

Run: .venv/Scripts/python.exe scripts/deploy_two_fire_automation.py [--apply]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.qoder.com/api/v1/cloud"
AGENT_ID = "agent_00vtt1wjgm22o20s8ykz"
ENVIRONMENT_ID = "env_00vtw0llz5kw0jxmu4hl"
VAULT_ID = "vault_00vs6gjsbcxkw661ka7o"
MEMORY_STORE_ID = "memstore_00vtw0mkv8irmz3cmpkd"
NAME = "Tyche desk - premarket and close"
DESCRIPTION = (
    "Tyche paper desk: ETF ballast plus catalyst stocks and standard long options; "
    "two-fire premarket/close runs, independent audits and retained position-protection review."
)
SECRET_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TYCHE_ALLOWED_ACCOUNT_IDS")
PROMPT = """TYCHE TWO-FIRE PAPER DESK RUN (ARMED 2026-11-19).

CLOCK: this automation fires at 08:05 and 15:05 America/New_York on weekdays. At the very start run
tyche calendar --json from the repo. Exit 1 means skip: weekend, NYSE holiday or outside 04:00-20:00
ET; finish read-only with a one-line note and submit nothing. Exit 0 reports trading_day, half_day,
session phase and events; obey them. 08:05 is the premarket plan fire. 15:05 is the close fire; on a
13:00 early close it is AFTER_HOURS, so it may reconcile only and never submit. The option exit cutoff
is session close minus 45 minutes (15:15 ET normally, 12:15 ET on early closes). A late or skipped fire
never authorizes catch-up with stale quotes.

BOOTSTRAP: repo mount /data/workspace/tyche. Install editable --no-deps if tyche is missing; run
tyche journal-verify and tyche halt-status --json. halted=true blocks buys while approved de-risking
sells may still run. Restore the verified Drive journal lineage at
/data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl, checking later descendants first. Lifecycle
state belongs under /data/drive/tyche-raw/lifecycle; missing state is a reconciliation task, never
proof there were no holdings. Never create adoption grants from current holdings alone.

PHASES: at both fires reconcile account positions, order history, pending orders and protection gaps
FIRST through the executor. Premarket: run the researcher's broad source-backed discovery and produce
approval-ready plans. Close: focused revalidation of holdings, approved plans and open proposals; no
broad re-scout unless a held name has fresh material news. Later fires revalidate; they may add new
candidates only as unapproved proposals through the same preview/audit/approval path; never scale,
re-enter or silently modify approved plans. Any approved change needs the operator's exact approval
again.

ROSTER GATING: always delegate the executor. Delegate the researcher at the premarket fire, or when
holdings or open entry proposals need narrow revalidation. Delegate the auditor only when an
executable proposal or contract revision needs independent exact-order review. If there are no
positions, no open proposals, no pending orders and no discovery due, finish with the executor alone
and say so.

ORDERS: config/tactical.yaml keeps execution_enabled=false until the controlled drill passes; while
closed, tactical entries are proposals only. Broker writes follow the PB-001 lifecycle contract: the
executor is the only writer; require a same-day exact setup/config/account-bound entry AND exit
envelope, a fresh independent exact-order audit and a successful tyche reserve persisted before ONE
paper regular-session limit order with request_id as text strictly before submit_before. Paper only;
live trading is forbidden; no shorts, spreads, naked options, scaling or automatic re-entry. A
receipt is not a fill; reconcile afterwards. Timeouts, partial fills and uncertain statuses block
retry. Cancel and modify need separate per-action operator confirmation.

BUDGET: PB-001 ballast 25%, tactical stock cap 45%, aggregate option premium cap 25%, cash >=5%,
gross <=95%.

STATE: this automation is the only scheduled execution owner. The paused Forward schedule and every
other desk schedule must remain paused; never run two writers. Verify ownership first; if ownership
cannot be verified, block.

PERSIST: keep the hash-chained journal; persist plans, snapshots and state to Drive; redact account
ids and tokens from plans, logs, digests and attachments.

TELEGRAM: send a compact digest prefixed "PAPER ARMED": date/fire, market state, reconciliation
(positions, pending, protection gaps), new or modified proposals, orders submitted (state none if
none), reserve/audit references, blockers. Never include account ids, tokens or secrets.

REPORT: end with a short digest; state explicitly if no orders were submitted; list coverage gaps.
Never invent references and never claim a fill or approval that did not occur."""


def env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if not values.get("QODER_PAT"):
        raise SystemExit("missing from .env: QODER_PAT")
    return values


def environment_keys(values: dict[str, str]) -> set[str]:
    response = req(values, "GET", f"/environments/{ENVIRONMENT_ID}")
    environment_variables = response.get("environment_variables")
    if isinstance(environment_variables, dict):
        return set(environment_variables)
    if isinstance(environment_variables, str):
        return {row.split("=", 1)[0].strip() for row in environment_variables.splitlines() if "=" in row}
    return set()


def missing_secret_keys(values: dict[str, str], inherited: set[str]) -> list[str]:
    return [key for key in SECRET_KEYS if key not in inherited]


def req(values: dict[str, str], method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": "Bearer " + values["QODER_PAT"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        raise SystemExit(f"HTTP {error.code} on {method} {path}: {error.read().decode()[:800]}")


def sanitize(result: dict) -> dict:
    keep = {
        key: result.get(key)
        for key in ("id", "name", "status", "schedule", "next_run_at", "created_at", "agent",
                    "environment_id", "vault_ids", "resources", "metadata")
    }
    return keep


def main() -> None:
    values = env()
    inherited = environment_keys(values)
    missing = missing_secret_keys(values, inherited)
    if "--check" in sys.argv:
        print(json.dumps({"environment_keys": sorted(inherited),
                          "missing_secret_keys": missing}, indent=2))
        return
    if "--verify" in sys.argv:
        deployment_id = sys.argv[sys.argv.index("--verify") + 1]
        import hashlib
        deployment = req(values, "GET", f"/deployments/{deployment_id}")
        events = json.dumps(deployment.get("initial_events") or [])
        schedule = deployment.get("schedule") or {}
        print(json.dumps({
            "id": deployment.get("id"),
            "status": deployment.get("status"),
            "cron": f"{schedule.get('expression')} {schedule.get('timezone')}",
            "prompt_sha256": hashlib.sha256(events.encode()).hexdigest()[:16],
            "prompt_chars": len(events),
            "has_calendar_gate": "tyche calendar --json" in events,
            "has_half_day_cutoff": "12:15 ET" in events,
            "has_after_hours_guard": "AFTER_HOURS" in events,
        }, indent=2))
        return
    if "--sanitize" in sys.argv:
        result = json.loads(Path(sys.argv[sys.argv.index("--sanitize") + 1]).read_text())
        for path in (Path(sys.argv[sys.argv.index("--sanitize") + 1]),
                     Path(sys.argv[sys.argv.index("--sanitize") + 2]),
                     Path(sys.argv[sys.argv.index("--sanitize") + 3])):
            path.unlink(missing_ok=True)
        print(json.dumps(sanitize(result), indent=2))
        return
    for key in missing:
        if not values.get(key):
            raise SystemExit(f"missing from .env: {key}")
    agent = req(values, "GET", f"/agents/{AGENT_ID}")
    version = agent.get("version")
    if not isinstance(version, int):
        raise SystemExit("agent version unavailable; refusing to create an unpinned card")
    envs = ";".join(f"{key}={values[key]}" for key in missing)
    payload = {
        "name": NAME,
        "description": DESCRIPTION,
        "agent": {"id": AGENT_ID, "type": "agent", "version": version},
        "environment_id": ENVIRONMENT_ID,
        "vault_ids": [VAULT_ID],
        "resources": [
            {
                "type": "github_repository",
                "url": "https://github.com/aloisohzh/tyche",
                "authorization_token": "public-repo-anonymous",
                "mount_path": "/data/workspace/tyche",
            },
            {"type": "memory_store", "memory_store_id": MEMORY_STORE_ID, "access": "read_write"},
        ],
        "schedule": {"type": "cron", "expression": "5 8,15 * * 1-5", "timezone": "America/New_York"},
        "metadata": {"source": "operator", "profile": "two-fire", "window": "2026-11-19..2026-11-28"},
        "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": PROMPT}]}],
    }
    if envs:
        payload["environment_variables"] = envs
    if "--emit" in sys.argv:
        payload_path = Path(sys.argv[sys.argv.index("--emit") + 1])
        config_path = Path(sys.argv[sys.argv.index("--emit") + 2])
        payload_path.write_text(json.dumps(payload))
        config_path.write_text(
            'url = "https://api.qoder.com/api/v1/cloud/deployments"\n'
            'header = "Authorization: Bearer ' + values["QODER_PAT"] + '"\n'
            'header = "Content-Type: application/json"\n'
            'data-binary = "@' + payload_path.as_posix() + '"\n'
        )
        print(json.dumps({"staged": True, "payload_file": str(payload_path),
                          "curl_config": str(config_path), "name": NAME,
                          "agent_version": version, "cron": payload["schedule"],
                          "prompt_chars": len(PROMPT),
                          "environment_carries": sorted(inherited & set(SECRET_KEYS)),
                          "from_dotenv": missing}, indent=2))
        return
    if "--emit-update" in sys.argv:
        deployment_id = sys.argv[sys.argv.index("--emit-update") + 1]
        payload_path = Path(sys.argv[sys.argv.index("--emit-update") + 2])
        config_path = Path(sys.argv[sys.argv.index("--emit-update") + 3])
        payload_path.write_text(json.dumps({
            "initial_events": [{"type": "user.message",
                                "content": [{"type": "text", "text": PROMPT}]}]
        }))
        config_path.write_text(
            'url = "https://api.qoder.com/api/v1/cloud/deployments/' + deployment_id + '"\n'
            'header = "Authorization: Bearer ' + values["QODER_PAT"] + '"\n'
            'header = "Content-Type: application/json"\n'
            'data-binary = "@' + payload_path.as_posix() + '"\n'
        )
        print(json.dumps({"staged": True, "deployment_id": deployment_id,
                          "payload_file": str(payload_path), "curl_config": str(config_path),
                          "prompt_chars": len(PROMPT)}, indent=2))
        return
    if "--apply" not in sys.argv:
        print(json.dumps({"dry_run": True, "name": NAME, "agent_version": version,
                          "cron": payload["schedule"], "prompt_chars": len(PROMPT),
                          "environment_carries": sorted(inherited & set(SECRET_KEYS)),
                          "from_dotenv": missing}, indent=2))
        return
    result = req(values, "POST", "/deployments", payload)
    print(json.dumps(sanitize(result), indent=2))
    deployment_id = result.get("id")
    if not deployment_id:
        raise SystemExit("deployment id missing from response; inspect cloud state")
    after = req(values, "GET", f"/deployments/{deployment_id}")
    print(json.dumps({"verified": sanitize(after)}, indent=2))


if __name__ == "__main__":
    main()
