"""Create the permanent three-fire Qoder Cloud Automation card for the tyche paper desk.

One card, no end date: 08:05 premarket plan fire, 12:05 midday watch-and-shout protection check,
15:05 close fire, every Monday to Friday in America/New_York. The cron knows nothing about NYSE
holidays; the in-run `tyche calendar` gate is the holiday filter, so a holiday fire exits read-only.
This replaced the one-card-per-month design (trading days listed in the cron, a new card each month)
on 2026-11-22. The midday fire shares the card and may never submit anything.

Reads QODER_PAT and the three runtime secret values from gitignored .env and sends
them directly to the Cloud API. Never prints secret values.

Run: .venv/Scripts/python.exe scripts/deploy_two_fire_automation.py [--start 2026-11-24] [--apply]
  --apply refuses to create a second active desk card unless --allow-overlap is given: two cards
  that both fire are two writers (STATE below), so pause the old card first, then create.
Update a live card's prompt only: ... --apply-update <deployment_id>
  (its cron and metadata are re-sent exactly as the platform holds them; only initial_events moves)
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

BASE = "https://api.qoder.com/api/v1/cloud"
AGENT_ID = "agent_00vtt1wjgm22o20s8ykz"
ENVIRONMENT_ID = "env_00vtw0llz5kw0jxmu4hl"
VAULT_ID = "vault_00vs6gjsbcxkw661ka7o"
MEMORY_STORE_ID = "memstore_00vtw0mkv8irmz3cmpkd"
ET = ZoneInfo("America/New_York")
# Minute 5 past 08, 12 and 15 ET, Monday to Friday, forever. Holidays are not in the cron on purpose:
# a day list has to be regenerated every month and a stale one is a silent miss (the Nov/Dec cards), while
# a holiday fire under this cron costs one read-only session that `tyche calendar --json` ends at once.
DESK_CRON = "5 8,12,15 * * 1-5"
CARD_NAME = "Tyche desk - premarket, midday and close"
PROFILE = "three-fire-weekday"
DESCRIPTION = (
    "Tyche paper desk: ETF ballast plus catalyst stocks and standard long options; "
    "three-fire premarket/midday/close runs, independent audits and retained position-protection review."
)
SECRET_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TYCHE_ALLOWED_ACCOUNT_IDS")


def desk_cron() -> str:
    """The permanent weekday cron: 08:05/12:05/15:05 ET Monday to Friday; holidays are gated in-run."""
    return DESK_CRON


def card_start(argv: list[str], today: date | None = None) -> date:
    """First day the new card owns: --start YYYY-MM-DD, else the first weekday after today (ET)."""
    if "--start" in argv:
        return date.fromisoformat(argv[argv.index("--start") + 1])
    day = (today or datetime.now(ET).date()).toordinal() + 1
    while date.fromordinal(day).weekday() >= 5:
        day += 1
    return date.fromordinal(day)


def card_name() -> str:
    return CARD_NAME


def card_window(start: date) -> str:
    """Open-ended `metadata.window`: `YYYY-MM-DD..` means from that day on, no end. The desk and the
    hosted Function select today's card by this field (scripts/cloud_api.py pick_card)."""
    return f"{start}.."


def cadence_sentence(window: str) -> str:
    """The CLOCK clause's first sentence, true for the card it is written onto.

    A legacy monthly card (bounded window, trading-day list in its cron) may still receive a prompt
    update, so its sentence keeps describing its own cron rather than the permanent one.
    """
    start, _, end = window.partition("..")
    if end:
        return (f"this automation fires at 08:05, 12:05 and 15:05 America/New_York only on NYSE trading "
                f"days in the card window {start}..{end}; the cron day list already excludes weekends and "
                f"holidays, and the calendar gate below is the backstop")
    return (f"this automation fires at 08:05, 12:05 and 15:05 America/New_York every Monday to Friday "
            f"from {start} with no end date; the cron knows nothing about NYSE holidays, so the calendar "
            f"gate below is the only holiday filter and a holiday fire ends read-only")


def card_prompt(window: str) -> str:
    return PROMPT.replace("{{CADENCE}}", cadence_sentence(window))


PROMPT = """TYCHE THREE-FIRE PAPER DESK RUN (ARMED 2026-11-20: PER-TRADE THESES, RETRIED EXITS; MIDDAY IS ALERT-ONLY).

CLOCK: {{CADENCE}}. At the very start always run
tyche calendar --json from the repo. Exit 1 means skip: weekend, NYSE holiday or outside 04:00-20:00
ET; finish read-only with a one-line note and submit nothing. Exit 0 reports trading_day, half_day,
session phase and events; obey them. 08:05 is the premarket plan fire. 12:05 is the midday protection
fire and submits nothing (see MIDDAY). 15:05 is the close fire; on a
13:00 early close it is AFTER_HOURS, so it may reconcile only and never submit. The option exit cutoff
is session close minus 45 minutes (15:15 ET normally, 12:15 ET on early closes). On an early-close day
the 12:05 fire is the last check inside the session, and its alert is notice for the operator, not an
order. A late or skipped fire never authorizes catch-up with stale quotes.

CALENDAR DRIFT (08:05 premarket only, once per day, alert-only): the gate above reads the pinned
calendar tables, which can go stale against what NYSE publishes. At the first premarket fire of the day
WebFetch https://www.nyse.com/trade/hours-calendars, save the readable output to data/nyse-calendar.txt
(gitignored scratch, never committed), and run
`tyche calendar-check --source data/nyse-calendar.txt --json`. Exit 0 means the tables still match: put
one IN SYNC line in the run report and nothing more. Exit 1 is drift or an uncertain parse: put the
report's `changes` and `new_years` - or its `warnings` when the parse was incomplete - in the digest's
Problems section with the operator action "review and re-pin via scripts/refresh_calendar.py", and
journal one `calendar.check` event for the run. Never edit config or the card's cron from a run, never
invent a closure date the page did not state, and never let a finding change today's gate: the pinned
tables govern until the operator re-pins them, so drift is a note on the run, not a reason to skip or to
trade. An unavailable or unreadable page is UNCERTAIN, not a pass: say so and carry on. Skip at the 12:05
and 15:05 fires.

BOOTSTRAP: repo mount /data/workspace/tyche. Install editable --no-deps if tyche is missing; run
tyche journal-verify and tyche halt-status --json. halted=true blocks buys while approved de-risking
sells may still run. Restore the verified Drive journal lineage at
/data/drive/tyche-raw/2026-11-18-eod/journal/events.jsonl, checking later descendants first. Lifecycle
state belongs under /data/drive/tyche-raw/lifecycle; missing state is a reconciliation task, never
proof there were no holdings. Never create adoption grants from current holdings alone.

PHASES: at the premarket and close fires reconcile account positions, order history, pending orders
and protection gaps FIRST through the executor, and re-arm any exit that never reached the broker
before planning anything new. Premarket: run the researcher's broad source-backed discovery and produce
approval-ready plans. Close: focused revalidation of holdings, approved plans and open proposals; no
broad re-scout unless a held name has fresh material news. Later fires revalidate; they may add new
candidates only as unapproved proposals through the same preview/audit/approval path; never scale,
re-enter or silently modify approved plans. Any approved change needs the operator's exact approval
again.

MIDDAY (12:05 ET, WATCH AND SHOUT ONLY): this fire is a protection check, not a trading decision, and
is the one exception to the submission parts of PROTECTION and ORDERS. It may not open, change or close
any position. Ask the executor for fresh broker reads of positions, every order-history page and quotes;
normalize them with `tyche lifecycle capture`, then run `tyche lifecycle tick`, `tyche tactical tick`
and, for the PB-004 lane, `tyche tactical scalp` with --record omitted (dry run: evaluation only, no
latch, no reservation). Report every open position, lot and lifecycle grant: whether a live exit request
exists, its submit_before, the stop/target/deadline versus the current quote, and the outcome of the most
recent exit request. When an approved exit has no live request and its window has passed, journal ONE
protection.gap for that request_id (resolution gate.wait or expired, never invented); if the broker still
shows that order live, journal nothing and say so. If any level is breached or a lot is uncovered, send
the URGENT RISK ALERT digest first: the title must carry the ` - URGENT RISK ALERT` suffix (the
renderer's urgent field) and the Protection section must name the symbol, quantity, level versus current
quote and the exact operator action. Then stop - the close fire and the operator decide the exit.
Never at this fire: reserve, submit, cancel, modify, approve, revoke, write or edit an envelope or any
config file, run `tyche lifecycle approve`, `revoke`, `reserve` or `execute-exit`, `tyche tactical
reserve`, or `tyche tactical scalp --record` (the arm path); propose a new entry, a new plan or a new
candidate; run broad discovery; delegate the researcher or the auditor; revalidate a thesis; re-arm an
exit; widen a level; send the example template as a live report; or send a routine digest when nothing
is open and nothing is wrong. With an empty watchlist and no gap, record the reconciliation in the
journal only - no Telegram message, because a heartbeat nobody needs is noise.

THESIS: the per-trade thesis is the unit of work, not decoration. Every entry proposal, and the
plan.created event it is journaled in, must carry the scout's thesis block: thesis, synthesis, edge,
bear_case, invalidation, horizon, direction (bullish|bearish), factors [{name, axis, state, why,
detail}] with axis in technical|fundamental|macro|flow|sentiment|seasonality|catalyst|liquidity and
state pass|fail|unknown, outlook {regime, conviction high|medium|low, alignment per axis}, and
thesis_ref when the scout journaled one. A missing input is state unknown with the reason; never
omit a factor, never upgrade unknown to pass, never invent an edge or a source. tyche watchlist and
the tactical planner build this block; keep it verbatim through audit, approval and the journal, and
put a one-line thesis summary in the digest. A proposal without a thesis is incomplete: do not
audit, approve or submit it. The PB-001 rotation plan carries its own rule-based reasoning instead;
never fabricate a scout thesis for it.

PROTECTION: exits come before entries at the premarket and close fires; the 12:05 midday fire only
checks and shouts (see MIDDAY). Reconcile open lots against the journal and broker order history and
name every lot with no live exit path. A triggered exit (stop, target,
exit_at/timeout, option expiry or session flatten) is submitted through the same entry/exit
envelope, fresh audit and reserve before any new entry. Entry requests carry a short submit_before
(30s tactical, 90s scalp); an exit request's submit_before is whatever its submitter set - the
PB-004 scalp lane sets exit_submit_window_seconds (900s) and re-arms its own exits, while a tactical
exit has no automatic re-arm, so you re-arm it by hand at the next fire with a fresh quote, audit
and reserve. When a submit is blocked by client policy, a classifier, a transport error or gate.wait,
journal one protection.gap event for that request_id (resolution gate.wait or expired) and re-arm
only after checking both the journal and the broker order history: if the broker still shows that
request live or an order live, do not submit a second sell, and never journal a second gap for the
same request_id. Synthetic exits are not resting broker stops; a blocked or late exit leaves the
lot unprotected and must be reported as such, not implied filled.

ROSTER GATING: always delegate the executor. Delegate the researcher at the premarket fire, or when
holdings or open entry proposals need narrow revalidation. Delegate the auditor only when an
executable proposal or contract revision needs independent exact-order review. If there are no
positions, no open proposals, no pending orders and no discovery due, finish with the executor alone
and say so.

ORDERS: re-read config/tactical.yaml at every fire. When the lane is enabled and execution_enabled
is true, the executor may submit paper orders under the approved envelope; when either is false,
entries are proposals only. Options stay disabled until their own entry/exit validation. Broker
writes follow the PB-001 lifecycle contract: the executor is the only writer; require a same-day
exact setup/config/account-bound entry AND exit envelope, a fresh independent exact-order audit and
a successful tyche reserve persisted before ONE paper regular-session limit order with request_id
as text strictly before submit_before. Paper only; live trading is forbidden; no shorts, spreads,
naked options, scaling or automatic re-entry. A receipt is not a fill; reconcile afterwards.
Timeouts, partial fills and uncertain statuses block retry and escalate to the digest. Cancel and
modify need separate per-action operator confirmation. When the envelope lacks an exit line, no
entry. Never widen the universe, raise caps or flip a gate in a run; config changes are operator-only.

BUDGET: PB-001 ballast 25%, tactical stock cap 45%, aggregate option premium cap 25%, cash >=5%,
gross <=95%.

STATE: this automation is the only scheduled execution owner. The paused Forward schedule and every
other desk schedule must remain paused; never run two writers. Verify ownership first; if ownership
cannot be verified, block.

PERSIST: keep the hash-chained journal; persist plans, snapshots and state to Drive; redact account
ids and tokens from plans, logs, digests and attachments.

TELEGRAM (SENTINEL FORMAT V1, 2026-11-20): presentation only. Trading permissions, risk gates,
schedules, recipients and secret bindings are unchanged. Use ONE shared layout for routine digests,
no-order runs and urgent risk alerts - never a plain-text wall or an unformatted table.
Preferred path is the mounted renderer: fill a private run-local JSON from
templates/sentinel-digest.example.json with VERIFIED facts only, preview it with
`python scripts/telegram.py render-digest <file>`, then deliver with
`python scripts/telegram.py send-digest <file>`. Never send the example file as a live report. A
render error means nothing was sent: shorten the prose while keeping every material risk fact, then
validate again. If that renderer is not yet published in the mounted repo, compose the identical
layout as escaped Telegram HTML (<b> headings and a <pre>ACTION SYMBOL QTY</pre> table) and pass it
to the existing `send` command through a Python argument array - never raw curl, never shell
interpolation, never dropping formatting as a fallback.
Layout: bold `TYCHE <PHASE>` title, plus ` - URGENT RISK ALERT` when urgent; date with UTC/ET/SGT
clocks; bold `PAPER ARMED` followed by the verified current state (observe-only, kill-switch, halt) -
never imply an uncovered lot is protected; one plain-English sentence on market mood and what the desk
did. Then bold sections in this order: **Orders** starts with the verified submission count and states
"No orders submitted by this run" when true, the monospace table holds only ACTION SYMBOL QTY, and
each symbol's VALUE, STATUS and a short plain-English REASON appear grouped below the table (a held
position is never a new order; with no rows omit the table but keep the factual summary); **Account**
puts NAV, cash, positions and kill-switch on separate lines; **Protection** names every uncovered lot,
pending or uncertain order and any re-armed exit; **Problems** uses short bullets plus the operator
action, and unverified means `Not verified`, never `None`; optional **Proposals** keeps each one-line
thesis and invalidation, and **Next check** must be verified, never promised. Stay under 3500
characters without dropping a material risk fact. Explain technical codes in ordinary words first
("another process placed orders", "no shares filled", "approval missing"), keep brief rule, audit and
reserve references, never equate a receipt with a fill, and put long evidence trails in the private
run report. Use hyphens, not em dashes. Preserve the helper's masking, content-ref and at-least-once
delivery behavior: exit code 2 means UNCONFIRMED, so never blindly retry an unknown delivery result.
Never include account ids, tokens or secrets. Delivery failure is recorded and never blocks risk work.
This formatting contract authorizes no extra run, test message or trade.

REPORT: end with a short digest; state explicitly if no orders were submitted; list coverage gaps
and every lot that still has no live exit path. Never invent references and never claim a fill or
approval that did not occur."""


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


def prompt_markers(events: str) -> dict:
    return {
        "has_calendar_gate": "tyche calendar --json" in events,
        "has_calendar_drift_check": "tyche calendar-check --source" in events,
        "has_half_day_cutoff": "12:15 ET" in events,
        "has_after_hours_guard": "AFTER_HOURS" in events,
        "has_execution_gate": "execution_enabled" in events,
        "has_per_trade_thesis": "the per-trade thesis is the unit of work" in events,
        "has_exit_retry": "exit_submit_window_seconds" in events,
        "has_protection_gap": "protection.gap" in events,
        "has_sentinel_format_v1": "SENTINEL FORMAT V1" in events,
        "has_renderer_path": "send-digest" in events,
        "has_midday_watch": ("MIDDAY (12:05 ET, WATCH AND SHOUT ONLY)" in events
                             and "08:05, 12:05 and 15:05" in events),
        "has_holiday_note": ("the only holiday filter" in events
                             or "the cron day list already excludes" in events),
    }


def live_window(deployment: dict) -> str:
    window = (deployment.get("metadata") or {}).get("window")
    if not isinstance(window, str) or ".." not in window:
        raise SystemExit(f"{deployment.get('id')}: metadata.window is {window!r}; refusing to write a "
                         "prompt whose CLOCK clause cannot name the card's own window")
    return window


def update_payload(deployment: dict, prompt_text: str) -> dict:
    """A prompt write for a live card: its schedule and metadata are re-sent exactly as the platform
    holds them, so the post-write drift check can insist that only `initial_events` moved. A cadence
    change is never an update - it is a new card (L-019: the card is the live object)."""
    schedule = deployment.get("schedule") or {}
    return {
        "schedule": {"type": schedule.get("type") or "cron", "expression": schedule.get("expression"),
                     "timezone": schedule.get("timezone")},
        "metadata": dict(deployment.get("metadata") or {}),
        "initial_events": [{"type": "user.message",
                            "content": [{"type": "text", "text": prompt_text}]}],
    }


def active_desk_cards(values: dict[str, str], start: date) -> list[dict]:
    """Other desk cards that would still fire on or after `start`: a second writer (STATE in PROMPT)."""
    rows = req(values, "GET", "/deployments?limit=50")
    return other_writers(rows.get("data") or rows.get("items") or [], start)


def other_writers(items: list, start: date) -> list[dict]:
    found = []
    for item in items:
        if not isinstance(item, dict) or not str(item.get("name", "")).startswith("Tyche desk"):
            continue
        if item.get("status") == "paused":
            continue
        window = str((item.get("metadata") or {}).get("window") or "")
        _, _, end = window.partition("..")
        if end and date.fromisoformat(end) < start:
            continue
        found.append({"id": item.get("id"), "name": item.get("name"), "status": item.get("status"),
                      "window": window or None})
    return found


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
            "name": deployment.get("name"),
            "status": deployment.get("status"),
            "agent_pin": (deployment.get("agent") or {}).get("version"),
            "cron": f"{schedule.get('expression')} {schedule.get('timezone')}",
            "permanent_weekday_cron": schedule.get("expression") == DESK_CRON,
            "window": (deployment.get("metadata") or {}).get("window"),
            "upcoming_runs_at": schedule.get("upcoming_runs_at"),
            "prompt_sha256": hashlib.sha256(events.encode()).hexdigest()[:16],
            "prompt_chars": len(events),
            **prompt_markers(events),
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
    # Secrets are a create-path requirement: an update payload carries no environment_variables, so
    # the card keeps the ones it was built with and this script must not demand local copies of
    # values it will never send (L-023: it could not even read them back).
    if "--apply-update" not in sys.argv and "--emit-update" not in sys.argv:
        for key in missing:
            if not values.get(key):
                raise SystemExit(f"missing from .env: {key}")
    agent = req(values, "GET", f"/agents/{AGENT_ID}")
    version = agent.get("version")
    if not isinstance(version, int):
        raise SystemExit("agent version unavailable; refusing to create an unpinned card")
    start = card_start(sys.argv)
    name = card_name()
    window = card_window(start)
    cron = desk_cron()
    prompt_text = card_prompt(window)
    envs = ";".join(f"{key}={values[key]}" for key in missing)
    payload = {
        "name": name,
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
        "schedule": {"type": "cron", "expression": cron, "timezone": "America/New_York"},
        "metadata": {"source": "operator", "profile": PROFILE, "window": window},
        "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": prompt_text}]}],
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
                          "curl_config": str(config_path), "name": name, "window": window,
                          "agent_version": version, "cron": payload["schedule"],
                          "prompt_chars": len(prompt_text),
                          "environment_carries": sorted(inherited & set(SECRET_KEYS)),
                          "from_dotenv": missing}, indent=2))
        return
    if "--emit-update" in sys.argv:
        deployment_id = sys.argv[sys.argv.index("--emit-update") + 1]
        payload_path = Path(sys.argv[sys.argv.index("--emit-update") + 2])
        config_path = Path(sys.argv[sys.argv.index("--emit-update") + 3])
        before = req(values, "GET", f"/deployments/{deployment_id}")
        payload_path.write_text(json.dumps(update_payload(before, card_prompt(live_window(before)))))
        config_path.write_text(
            'url = "https://api.qoder.com/api/v1/cloud/deployments/' + deployment_id + '"\n'
            'header = "Authorization: Bearer ' + values["QODER_PAT"] + '"\n'
            'header = "Content-Type: application/json"\n'
            'data-binary = "@' + payload_path.as_posix() + '"\n'
        )
        print(json.dumps({"staged": True, "deployment_id": deployment_id,
                          "payload_file": str(payload_path), "curl_config": str(config_path),
                          "cron": (before.get("schedule") or {}).get("expression"),
                          "window": live_window(before)}, indent=2))
        return
    if "--apply-update" in sys.argv:
        import hashlib
        deployment_id = sys.argv[sys.argv.index("--apply-update") + 1]
        before = req(values, "GET", f"/deployments/{deployment_id}")
        if not str(before.get("name", "")).startswith("Tyche desk"):
            raise SystemExit("refusing to update a deployment that is not the Tyche desk card")
        pinned = (before.get("agent") or {}).get("version")
        if not isinstance(pinned, int):
            raise SystemExit(f"{deployment_id}: agent pin is {pinned!r}, not an exact compiled "
                             "version; refusing to write a brief onto a card whose build we cannot name")
        req(values, "POST", f"/deployments/{deployment_id}",
            update_payload(before, card_prompt(live_window(before))))
        after = req(values, "GET", f"/deployments/{deployment_id}")
        keep = ("name", "description", "status", "agent", "environment_id", "vault_ids", "metadata",
                "resources", "schedule")
        drift = [k for k in keep
                 if json.dumps(before.get(k), sort_keys=True) != json.dumps(after.get(k), sort_keys=True)]
        if drift:
            raise SystemExit(f"{deployment_id}: fields {drift} moved under a prompt write - only "
                             "initial_events may change; inspect the cloud state before the next fire")
        events = json.dumps(after.get("initial_events") or [])
        schedule = after.get("schedule") or {}
        checks = prompt_markers(events)
        print(json.dumps({
            "updated": deployment_id,
            "name": after.get("name"),
            "status": after.get("status"),
            "agent_pin": (after.get("agent") or {}).get("version"),
            "cron": f"{schedule.get('expression')} {schedule.get('timezone')}",
            "upcoming_runs_at": schedule.get("upcoming_runs_at"),
            "prompt_sha256": hashlib.sha256(events.encode()).hexdigest()[:16],
            "prompt_chars": len(events),
            **checks,
        }, indent=2))
        if not all(checks.values()):
            raise SystemExit("prompt markers missing after update; inspect cloud state")
        return
    others = active_desk_cards(values, start)
    if "--apply" not in sys.argv:
        print(json.dumps({"dry_run": True, "name": name, "window": window, "agent_version": version,
                          "cron": payload["schedule"], "prompt_chars": len(prompt_text),
                          "environment_carries": sorted(inherited & set(SECRET_KEYS)),
                          "from_dotenv": missing, "other_active_desk_cards": others}, indent=2))
        return
    if others and "--allow-overlap" not in sys.argv:
        raise SystemExit("refusing to create a second active desk card (two writers): pause these first "
                         "or pass --allow-overlap: " + json.dumps(others))
    result = req(values, "POST", "/deployments", payload)
    print(json.dumps(sanitize(result), indent=2))
    deployment_id = result.get("id")
    if not deployment_id:
        raise SystemExit("deployment id missing from response; inspect cloud state")
    after = req(values, "GET", f"/deployments/{deployment_id}")
    print(json.dumps({"verified": sanitize(after)}, indent=2))


if __name__ == "__main__":
    main()
