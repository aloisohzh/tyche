"""Create the permanent three-fire Qoder Cloud Automation card for the tyche paper desk.

One card, no end date: 08:05 premarket plan fire, 12:05 midday watch-and-shout protection check,
15:05 close fire, every Monday to Friday in America/New_York. The cron knows nothing about NYSE
holidays; the in-run `tyche calendar` gate is the holiday filter, so a holiday fire exits read-only.
This replaced the one-card-per-month design (trading days listed in the cron, a new card each month)
on 2026-11-22. The midday fire shares the card and may never submit anything.

Reads QODER_PAT and the three runtime secret values from gitignored .env and sends
them directly to the Cloud API. Never prints secret values.

Run: .venv/Scripts/python.exe scripts/deploy_two_fire_automation.py [--start 2026-11-24] [--pin 35] [--apply]
  --pin names the exact compiled desk version the card runs (default: the agent's current version).
  --agent <id> targets another Managed desk agent than AGENT_ID (when the desk is recreated).
  --apply refuses to create a second active desk card unless --allow-overlap is given: two cards
  that both fire are two writers (STATE below), so pause the old card first, then create.
Update a live card's prompt only: ... --apply-update <deployment_id>
  (its cron and metadata are re-sent exactly as the platform holds them; only initial_events moves)
Copy a secret from .env into the desk environment: ... --set-env TYCHE_GITHUB_PAT [--card <deployment_id>]
  (merges into the environment's variables, or with --card into the live card's own variables, the way the
  Telegram secrets were set; prints key names only, never values). A publish token (TYCHE_GITHUB_PAT /
  TYCHE_GIT_PAT) is checked against GitHub first and refused if GitHub rejects it or it cannot push.
Check without writing: ... --check [--card <deployment_id>]
  (environment key names, the card's key names, and for the card's publish token GitHub's verdict on the
  very value the desk runs with: kind, length, status and whether it may push; never the value)
Any card write lands between fires only, with the operator's explicit go: the 2026-11-22 PROPOSAL
APPROVAL paragraph (Telegram wait-for-reply) is in this file but is NOT on the live cards until that write.
The two-mode wording (ASK ME / WITHIN MY BOUNDS, 2026-11-22) likewise waits for the operator's go between fires.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

BASE = "https://api.qoder.com/api/v1/cloud"
AGENT_ID = "agent_00w96vnmjp81t0rfdqun"
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
# Repo token the PUBLISH clause relies on (either name; see scripts/publish_desk_data.py).
PUBLISH_TOKEN_KEYS = ("TYCHE_GITHUB_PAT", "TYCHE_GIT_PAT")
GITHUB_REPO = "aloisohzh/tyche"  # the repo the publish step pushes to; the token check asks GitHub about it


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


def card_agent(argv: list[str]) -> str:
    """The Managed desk agent the card runs: --agent <id>, else AGENT_ID. The override exists for the
    day the desk is recreated as a fresh agent (2026-11-22) and the card must be born on the new id
    before the constant catches up; an id that is not an agent id is refused."""
    if "--agent" not in argv:
        return AGENT_ID
    agent_id = argv[argv.index("--agent") + 1]
    if not agent_id.startswith("agent_") or len(agent_id) < 12:
        raise SystemExit(f"--agent must be a Managed agent id (agent_...), got {agent_id!r}")
    return agent_id


def card_pin(argv: list[str], agent: dict) -> int:
    """The exact compiled desk version the card runs: --pin N, else the agent's current version.

    `--pin` exists because a roster re-pin or a template archive can recompile the desk and leave a spare
    "current" version nobody reviewed (L-045/L-046); the operator names the number that was verified. It
    must still be a version the platform has: a pin above the current one does not exist yet.
    """
    current = agent.get("version")
    if not isinstance(current, int):
        raise SystemExit("agent version unavailable; refusing to create an unpinned card")
    if "--pin" not in argv:
        return current
    pin = argv[argv.index("--pin") + 1]
    if not pin.isdigit() or int(pin) < 1:
        raise SystemExit(f"--pin must be a positive integer version, got {pin!r}")
    if int(pin) > current:
        raise SystemExit(f"--pin {pin} is above the agent's current version {current}; it does not exist")
    return int(pin)


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

NAV REFERENCES (2026-11-23): the drawdown ladder measures from the challenge's verified 100,000.00 starting
NAV (18 Nov) until a verified broker close NAV (total_asset at the close fire) exceeds it; then that close
is the new high-water mark. The 102,208.99 figure was never verified against a broker read and is retired;
never carry an unverified high-water pin forward. prior_close_nav is the previous session's verified close
NAV from the Drive nav-refs, refreshed at every close fire. The operator owns the start figure; a run may
raise the mark only from a verified close, never lower it.

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
is true, the executor may submit paper orders under today's operator authority; when either is false,
entries are proposals only. The authority has exactly two modes, read from data/approvals.json at the
fire: WITHIN MY BOUNDS when a same-day envelope exists (submit inside it, no Telegram ask), otherwise
ASK ME (no envelope: an entry is submitted only after the operator's Telegram /approve N in this run,
journaled with `tyche approve-telegram`). Never write, edit or re-date the envelope. Options stay
disabled until their own entry/exit validation. Broker writes follow the PB-001 lifecycle contract:
the executor is the only writer; require a same-day exact setup/config/account-bound entry AND exit
authorization (the envelope's lines, or the approved proposal's `order` block with its exit_floor), a
fresh independent exact-order audit and a successful tyche reserve persisted before ONE paper
regular-session limit order with request_id as text strictly before submit_before. Paper only; live
trading is forbidden; no shorts, spreads, naked options, scaling or automatic re-entry. A receipt is
not a fill; reconcile afterwards. Timeouts, partial fills and uncertain statuses block retry and
escalate to the digest. Cancel and modify need separate per-action operator confirmation. When the
authority lacks an exit line, no entry. Never widen the universe, raise caps or flip a gate in a run;
config changes are operator-only.

PROPOSAL APPROVAL (TELEGRAM WAIT, 2026-11-22): in ASK ME mode (no same-day data/approvals.json), at
the 08:05 and 15:05 fires, an entry proposal may be submitted only after the operator approves it on
Telegram during this run. Write the proposals to a private run-local JSON following
templates/proposal-approval.example.json with the complete package - entry, size, value, stop, target,
exit-by, thesis, invalidation - and the `order` block (symbol, side, qty, limit, exit_floor, and
setup_hash when the lane binds one) naming the exact order the approve authorizes; preview with
`python scripts/telegram.py render-proposal <file>`, then run
`python scripts/telegram.py wait-for-reply <file>` (10-minute window; never pass a longer --timeout).
The command's JSON result is the only authority: a number listed under `approved` authorizes
`tyche approve-telegram <file>` (which journals that yes as today's order authorization), then the
exact-order audit, reserve and ONE paper order for exactly that proposal, and nothing else does -
`denied`, `timed_out`, `pending`, `conflict`, a non-zero exit or any free-text reply is a no. A
question comes back as outcome `reply`: answer it with `send` and run the same wait-for-reply command
again (it resumes the same window). A requested change is a no: record it, rebuild the proposal under
a new number, re-audit and send the fresh preview. Never reuse a number within a fire, never approve
on the operator's behalf, never submit after the window, and list every proposal with its decision in
the digest's Proposals section. In WITHIN MY BOUNDS mode (same-day envelope) skip this step: trade
inside the envelope without asking, and still list the entries in the digest. The 12:05 fire never
runs this step. Cancel and modify asks stay on the console/bridge path unchanged.

PB-007 FIB PULLBACK (2026-11-23): the swing lane trades only while `tyche strategies --json` lists
PB-007 as enabled (the operator's switch file decides; never edit it in a run). When it is on, at the
08:05 fire the executor pulls daily klines (quote_cur_kline, ktype day, num=370) for the PB-007 scope
symbols, runs `python scripts/mcp_prices.py <tool-outputs> --ohlc --out data/ohlc.csv`, then
`tyche fib-scan --bars data/ohlc.csv --account <snapshot> --book <run>/pb007-book.json --flat-by
<the window's last session> --record`. Each proposal takes the normal path: preview, researcher review
of the plan hash with evidence, exact-order audit, and the operator's Telegram /approve under PROPOSAL
APPROVAL (or `tyche lifecycle approve` per hash from the console). 12:05 never scans or trades it.
15:05 runs exits first, then `tyche lifecycle tick` / `reserve` for approved plans whose quote is inside
the entry zone; fills are recorded with strategy id PB-007. A scan that finds no setup is a normal
outcome, not a problem: the SMA50/200 filter is meant to produce nothing in a downtrend. When the switch
is off, skip this block entirely and say so in one line of the digest.

BUDGET: PB-001 ballast 25%, tactical stock cap 25% (cut from 45% on 2026-11-23), PB-007 swing 20% (only while its switch is on),
aggregate option premium cap 25%, cash >=5%, gross <=95% on every order.

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
approval that did not occur.

PUBLISH (2026-11-23): the hosted desk page reads its numbers from the repo, so the very last step of
every run - a skip run and a run with problems included, after the digest is sent - is
`python scripts/publish_desk_data.py` from the repo root. It restores the journal from the longest
verified Drive run bundle when the checkout's is missing or shorter, copies every Drive run bundle git does
not hold yet into docs/performance/<run>/ through the sanitize gate (a bundle that still carries a secret
is withheld and named), rebuilds the sanitized feed behind the secret guard, regenerates the day's
performance pack (docs/performance/<date>-metrics.md, read from that journal and the run's price files; a
pack that cannot be built is skipped, never a reason to stop), commits only the three feed files, the new
bundles and that pack, and pushes them to main. So this run's bundle must already be on Drive under
/data/drive/tyche-raw/<run>/ (snapshot.json and the broker reads) before this step. Run it once. If it fails,
put its first error line under Problems with the action "operator: run the publish script" and move
on: never retry in a loop, never edit the feed files by hand, never print a token, and never let it
delay or replace risk work or the digest. It places no order and changes no rule."""


def _publish_module():
    """scripts/publish_desk_data.py, loaded by path so the two scripts share one token check."""
    spec = importlib.util.spec_from_file_location("publish_desk_data", ROOT / "scripts" / "publish_desk_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_dotenv(text: str) -> tuple[dict[str, str], list[str]]:
    """KEY=VALUE lines -> values, plus warnings. A value keeps no surrounding quotes (KEY="x" is a .env
    habit that GitHub would read as a bad credential), and a key written twice is reported, because the
    last line silently wins and a rotated token pasted above the old one would never reach the card."""
    values: dict[str, str] = {}
    seen: dict[str, int] = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].strip()
            values[key] = value
            seen[key] = seen.get(key, 0) + 1
    warnings = [f"WARNING: {key} appears {count} times in .env; the LAST line wins - delete the stale one"
                for key, count in seen.items() if count > 1]
    return values, warnings


def env() -> dict[str, str]:
    values, warnings = parse_dotenv((ROOT / ".env").read_text())
    for warning in warnings:
        print(warning, file=sys.stderr)
    if not values.get("QODER_PAT"):
        raise SystemExit("missing from .env: QODER_PAT")
    return values


def publish_token_check(token: str) -> dict:
    """What GitHub says about a publish token, with nothing of the value itself: kind, length, status,
    whether it may push, and a plain sentence. Shared with the publish step so both report the same way."""
    publish = _publish_module()
    clean = publish.clean_token(token)
    probe = publish.github_token_probe(clean, GITHUB_REPO)
    return {"shape": publish.token_shape(clean), "status": probe["status"], "push": probe["push"],
            "ok": probe["ok"], "detail": probe["detail"]}


def environment_keys(values: dict[str, str]) -> set[str]:
    response = req(values, "GET", f"/environments/{ENVIRONMENT_ID}")
    environment_variables = response.get("environment_variables")
    if isinstance(environment_variables, dict):
        return set(environment_variables)
    if isinstance(environment_variables, str):
        return {row.split("=", 1)[0].strip() for row in environment_variables.splitlines() if "=" in row}
    return set()


def set_environment_variables(values: dict[str, str], new: dict[str, str]) -> set[str]:
    """Merge `new` into the environment's variables, in whatever shape the platform returned them
    (a dict, or "KEY=VALUE" lines), and return the key names the platform holds afterwards."""
    current = req(values, "GET", f"/environments/{ENVIRONMENT_ID}")
    existing = current.get("environment_variables")
    if isinstance(existing, str):
        merged = dict(row.split("=", 1) for row in existing.splitlines() if "=" in row)
        merged.update(new)
        payload: dict | str = "\n".join(f"{k}={v}" for k, v in merged.items())
    else:
        merged = dict(existing or {})
        merged.update(new)
        payload = merged
    req(values, "POST", f"/environments/{ENVIRONMENT_ID}", {"environment_variables": payload})
    return environment_keys(values)


def _parse_env_string(raw) -> dict[str, str]:
    """Card/environment variables as the platform returns them: a dict, or KEY=VALUE pairs joined by ';' or newlines."""
    if isinstance(raw, dict):
        return dict(raw)
    out: dict[str, str] = {}
    for row in re.split(r"[;\n]", str(raw or "")):
        if "=" in row:
            key, value = row.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def set_card_variables(values: dict[str, str], deployment_id: str, new: dict[str, str]) -> set[str]:
    """Merge `new` into a live desk card's environment_variables. The card's schedule, metadata and brief
    are re-sent exactly as the platform holds them (same contract as a prompt write), and the post-write
    check insists that nothing but the variables moved. Values are never printed."""
    before = req(values, "GET", f"/deployments/{deployment_id}")
    if not str(before.get("name", "")).startswith("Tyche desk"):
        raise SystemExit("refusing to touch a deployment that is not the Tyche desk card")
    events = before.get("initial_events") or []
    try:
        prompt_text = events[0]["content"][0]["text"]
    except (IndexError, KeyError, TypeError):
        raise SystemExit(f"{deployment_id}: cannot read the live brief; refusing to re-send an empty one") from None
    merged = _parse_env_string(before.get("environment_variables"))
    merged.update(new)
    payload = update_payload(before, prompt_text)
    payload["environment_variables"] = ";".join(f"{k}={v}" for k, v in merged.items())
    req(values, "POST", f"/deployments/{deployment_id}", payload)
    after = req(values, "GET", f"/deployments/{deployment_id}")
    keep = ("name", "description", "status", "agent", "environment_id", "vault_ids", "metadata", "resources", "schedule")
    drift = [k for k in keep if json.dumps(before.get(k), sort_keys=True) != json.dumps(after.get(k), sort_keys=True)]
    if drift:
        raise SystemExit(f"{deployment_id}: fields {drift} moved under a variables write; inspect the cloud state")
    if json.dumps(after.get("initial_events")) != json.dumps(before.get("initial_events")):
        raise SystemExit(f"{deployment_id}: the brief changed under a variables write; inspect the cloud state")
    return set(_parse_env_string(after.get("environment_variables")))


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
        "has_proposal_approval": ("PROPOSAL APPROVAL (TELEGRAM WAIT" in events
                                  and "wait-for-reply" in events),
        "has_feed_publish": "scripts/publish_desk_data.py" in events,
        "has_performance_pack": "performance pack" in events,
        "has_fib_pullback": "PB-007 FIB PULLBACK" in events and "tyche fib-scan" in events,
        "has_nav_references": "NAV REFERENCES" in events and "100,000.00 starting" in events,
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
        out = {"environment_keys": sorted(inherited), "missing_secret_keys": missing}
        if "--card" in sys.argv:
            # Key names only, never values: the card's own variables are where the desk's secrets live.
            deployment_id = sys.argv[sys.argv.index("--card") + 1]
            card = req(values, "GET", f"/deployments/{deployment_id}")
            card_vars = _parse_env_string(card.get("environment_variables"))
            keys = set(card_vars)
            out["card"] = deployment_id
            out["card_env_keys"] = sorted(keys)
            out["card_has_publish_token"] = any(k in keys for k in PUBLISH_TOKEN_KEYS)
            token_key = next((k for k in PUBLISH_TOKEN_KEYS if card_vars.get(k)), None)
            if token_key:
                # The value the desk actually runs with, checked against GitHub; only its verdict is printed.
                out["card_publish_token_check"] = {"key": token_key, **publish_token_check(card_vars[token_key])}
        print(json.dumps(out, indent=2))
        return
    if "--set-env" in sys.argv:
        # Copy named keys from the gitignored .env into the desk environment's variables. Values never
        # reach stdout: only the key names after the write are printed. Used once for TYCHE_GITHUB_PAT.
        keys = []
        for arg in sys.argv[sys.argv.index("--set-env") + 1:]:
            if arg.startswith("--"):
                break  # the next option (e.g. --card <id>) ends the key list
            keys.append(arg)
        if not keys:
            raise SystemExit("--set-env needs at least one key name, e.g. --set-env TYCHE_GITHUB_PAT")
        for key in keys:
            if not values.get(key):
                raise SystemExit(f"{key} missing from .env - add a line {key}=... to .env first")
        secrets = {key: values[key] for key in keys}
        checks = {}
        for key in keys:
            if key in PUBLISH_TOKEN_KEYS:
                # Never write a publish token the far end will refuse: ask GitHub first, from the laptop.
                check = publish_token_check(secrets[key])
                checks[key] = check
                if not check["ok"]:
                    raise SystemExit(f"{key} not written: {check['detail']} ({check['shape']}). "
                                     "Make a fine-grained token for the repo with Contents: read and write, "
                                     f"replace the {key}= line in .env (one line only), and run this again.")
        if "--card" in sys.argv:
            # The Telegram secrets reached the desk this way (card-level environment_variables at create
            # time), so the card is the proven place; the environment object is the alternative.
            deployment_id = sys.argv[sys.argv.index("--card") + 1]
            after = set_card_variables(values, deployment_id, secrets)
            print(json.dumps({"deployment_id": deployment_id, "card_env_keys": sorted(after), "set": keys,
                              "token_checks": checks}, indent=2))
            return
        after = set_environment_variables(values, secrets)
        print(json.dumps({"environment_id": ENVIRONMENT_ID, "environment_keys": sorted(after),
                          "set": keys, "token_checks": checks}, indent=2))
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
    agent_id = card_agent(sys.argv)
    agent = req(values, "GET", f"/agents/{agent_id}")
    version = card_pin(sys.argv, agent)
    start = card_start(sys.argv)
    name = card_name()
    window = card_window(start)
    cron = desk_cron()
    prompt_text = card_prompt(window)
    envs = ";".join(f"{key}={values[key]}" for key in missing)
    payload = {
        "name": name,
        "description": DESCRIPTION,
        "agent": {"id": agent_id, "type": "agent", "version": version},
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
        # The PUBLISH clause needs a repo token where the desk runs: the card's own variables (where the
        # Telegram secrets live) or the environment. A missing one is a brief that reports a failed publish
        # every run, so say so before writing (a warning, not a refusal).
        inherited = environment_keys(values)
        card_keys_before = set(_parse_env_string(before.get("environment_variables")))
        if not any(key in inherited | card_keys_before for key in PUBLISH_TOKEN_KEYS):
            print(f"WARNING: none of {PUBLISH_TOKEN_KEYS} is set on card {deployment_id} or in environment "
                  f"{ENVIRONMENT_ID}; the PUBLISH step will fail until the repo token is added "
                  f"(--card {deployment_id} --set-env TYCHE_GITHUB_PAT)")
        req(values, "POST", f"/deployments/{deployment_id}",
            update_payload(before, card_prompt(live_window(before))))
        after = req(values, "GET", f"/deployments/{deployment_id}")
        # A prompt write carries no environment_variables; the platform must keep the card's own. If it
        # did not, the desk has just lost its Telegram and repo secrets, which is worth a loud line.
        card_keys_after = set(_parse_env_string(after.get("environment_variables")))
        if card_keys_after != card_keys_before:
            print(f"WARNING: card variables changed under the prompt write: before {sorted(card_keys_before)}, "
                  f"after {sorted(card_keys_after)}; re-run --card {deployment_id} --set-env for the missing keys")
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
            "card_env_keys": sorted(card_keys_after),
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
        print(json.dumps({"dry_run": True, "name": name, "window": window, "agent_id": agent_id,
                          "agent_version": version,
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
