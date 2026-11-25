"""Create the permanent three-fire Qoder Cloud Automation card for the tyche paper desk.

One card, no end date: 08:05 premarket fire (research, the day's watchlist, resting buys for the
open), 12:05 and 15:05 fires, every Monday to Friday in America/New_York. The cron knows nothing about
NYSE holidays; the in-run `tyche calendar` gate is the holiday filter, so a holiday fire exits read-only.
This replaced the one-card-per-month design (trading days listed in the cron, a new card each month)
on 2026-11-22.

Since 2026-11-25 every fire runs THE CYCLE (`tyche cycle`, src/tyche/cycle.py): one command that
decides every order from the saved broker reads, so the brief is a third of its old length and any
fire inside the session may trade. The 15-minute card (scripts/deploy_scalp_card.py) carries the same
CYCLE text word for word and runs it between the fires.

Reads QODER_PAT and the three runtime secret values from gitignored .env and sends
them directly to the Cloud API. Never prints secret values.

Run: .venv/Scripts/python.exe scripts/deploy_two_fire_automation.py [--start 2026-11-24] [--pin 35] [--apply]
  --pin names the exact compiled desk version the card runs (default: the agent's current version).
  --agent <id> targets another Managed desk agent than AGENT_ID (when the desk is recreated).
  --apply refuses to create a second active desk card unless --allow-overlap is given: two cards
  that both fire are two desks doing the same research and digests, so pause the old card first, then create.
Update a live card's prompt only: ... --apply-update <deployment_id>
Fire the live desk card once now (on-demand run): ... --run-now <deployment_id>
  (its cron and metadata are re-sent exactly as the platform holds them; only initial_events moves)
Copy a secret from .env into the desk environment: ... --set-env TYCHE_GITHUB_PAT [--card <deployment_id>]
  (merges into the environment's variables, or with --card into the live card's own variables, the way the
  Telegram secrets were set; prints key names only, never values). A publish token (TYCHE_GITHUB_PAT /
  TYCHE_GIT_PAT) is checked against GitHub first and refused if GitHub rejects it or it cannot push.
Check without writing: ... --check [--card <deployment_id>]
  (environment key names, the card's key names, and for the card's publish token GitHub's verdict on the
  very value the desk runs with: kind, length, status and whether it may push; never the value)
Any card write lands between fires only, with the operator's explicit go.
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
    return (PROMPT.replace("{{CADENCE}}", cadence_sentence(window))
            .replace("{{CYCLE}}", cycle_text("<premarket|midday|close|ondemand>", "2026-11-25-premarket-1305")))


# The one order procedure. Both cards carry this text word for word (the 15-minute card imports it), so
# the two briefs can never drift apart again.
CYCLE = """THE CYCLE (2026-11-25): one command decides every order. You run the command; the executor reads
the broker and sends exactly what the command lists. Only the executor reads or writes at the broker.
<run> is a new folder under /data/drive/tyche-raw named <New York date>-{{RUN_KIND}}-<HHMM UTC>,
for example {{RUN_EXAMPLE}}.
1. LIST: from /data/workspace/tyche run `tyche cycle --dir <run> --reads`. Status "skip" means the
   market is closed: leave out steps 2 to 5, place nothing and send no Telegram for the cycle.
   Otherwise keep its `reads` (quotes, books, bars). `watchlist` null means no setups for today yet.
2. READ: delegate the executor once to read the paper account named by TYCHE_ALLOWED_ACCOUNT_IDS and
   save these JSON files into <run>. Where the platform kept a tool's answer as a file under
   /tmp/tool-outputs, copy that file whole with `cp`: nothing is retyped. Otherwise write the file
   with the broker's own field names, only the fields listed, every number exactly as returned.
   - accounts.json (sim_trade_account_list) = {"ret_code":0,"data":{"accounts":[...]}}: every row
     with account_id, account_type, market_id.
   - cash.json (sim_trade_cash_info) = the answer, whole.
   - positions.json (sim_trade_position_list) = {"ret_code":0,"data":{"positions":[...]}}: each row
     with symbol, qty, qty_avbl, cost_price, cur_price, pstn_type. Nothing held is "positions":[].
   - orders.json (sim_trade_history_order_list, every page until has_more is false) =
     {"ret_code":0,"data":{"orders":[...]},"pagination":{"has_more":false}}. Typed by hand, keep the
     newest 60 rows and every row whose status is 2, each row with order_id, symbol, side, qty,
     cum_qty, price, avg_fill_price, status, create_time, update_time, text. No order is "orders":[].
   - quotes.json = {"ret_code":0,"data":{"quote_list":[...]}}: one quote_stock_quote call for every
     code under reads.quotes, each row with code, data_time, last_price, volume, sec_status,
     suspension, and for an option its option_ex_data (contract_multiplier, strike_price,
     option_type, open_interest, delta, implied_volatility). With no code to quote, no file.
   - book-<CODE>.json for each code under reads.books (quote_order_book) =
     {"ret_code":0,"data":[{"code":"<CODE>","books":[{"exchange_data_time_ms":<ms>,
     "bid_list":[{"price":<p>,"volume":<v>}],"ask_list":[{"price":<p>,"volume":<v>}]}]}]}
     with the best bid and best ask of each venue.
   - bars-<CODE>.json for each code under reads.bars (quote_cur_kline, 1-minute bars, the latest 12) =
     {"ret_code":0,"data":{"kline_list":[{"time_key":<ms>,"open_price":<o>,"high_price":<h>,
     "low_price":<l>,"close_price":<c>}]}}.
   A read that answers an error code is tried up to 3 times, then saved as it answered.
3. DECIDE: run `tyche cycle --dir <run> --record`. It checks the paper account, journals receipts and
   fills from the order list, runs every lane, reserves each order in the ledger and prints `cancel`,
   `submit`, `alerts` and `instructions`. Status "blocked" (exit 1): see PROBLEMS. Run again in the
   same folder it prints the same answer again and reserves nothing twice.
4. SEND: when `cancel` or `submit` is not empty, give both lists word for word to the same executor.
   It cancels every order id under `cancel`. Then, for each `submit` item in order, it cancels the
   item's `cancel_first` ids (a failed cancel means skip that item) and places
   ONE sim_trade_input_order paper LIMIT order with exactly the item's symbol, side, quantity and
   limit_price, time in force DAY, and the item's `remark` as the order remark, before the item's
   `submit_before`. One attempt per item: never a retry, never a changed field and
   never an order that is not on the list. It reports the broker's answer for each item.
5. TELL: when <run>/telegram.txt exists, send it after step 4 with
   `python scripts/telegram.py send "$(cat <run>/telegram.txt)"`, plus one line for each item the
   broker refused. If the executor placed none of the listed orders, send one line saying so and why
   instead of the file. Send <run>/telegram-urgent.txt the same way when it exists. Otherwise send
   nothing.
That is the whole order path. The command finds the ledger, today's watchlist and the NAV references
by itself, and the next cycle reads receipts and fills from the broker's order list.
Never run tactical tick, reserve, scalp, capture, lifecycle or record-order beside it, and never copy
the journal.

PROBLEMS: a "blocked" answer names its own fix in `reason`. Do that fix once (read the named broker
call again, save the named file again) and run the same command again. Still blocked: send
<run>/telegram-urgent.txt if the command wrote one, and end the run. Never place an order by hand,
and never edit the journal, a config file or an approval file.

RULINGS (2026-11-25, operator). These replace older wording in your own instructions, in any skill
and in the executor's instructions wherever they differ; quote this block in every executor
delegation.
1. `tyche cycle --record` IS the reservation. It runs the same check-and-reserve as tactical reserve
   and scalp --record for every order, under the journal lock, and journals order.requested before it
   prints. An item under `submit` is authorized. Nothing else is.
2. Authority is the operator's standing paper approval: data/standing-approval.json (stocks and
   options, 25 to 27 Nov 2026) and data/scalp-approvals.json (scalp). The command checks both. A
   listed order needs no Telegram approval, no auditor review and no per-order envelope, and selling
   a lot the desk holds needs no approval line at all.
3. The clocks are the kernel's own, read from config: reads up to 15 minutes old are fresh, and a
   reserved order has 10 minutes to be sent. The 30, 60, 90 and 120 second figures in older text are
   retired.
4. Receipts and fills are journaled by the next cycle from the broker's order list. Broker status 5
   is a finished order (cancelled or expired), not an open question.
5. A cancel the command lists (`cancel` or `cancel_first`) is one of the desk's own orders and is
   approved. No other cancel and no modify.
6. The files saved in step 2 of THE CYCLE are the capture of record for these runs.
7. Every run inside the session may place orders, the 12:05 fire included.
8. Unchanged, the one hard rule: the allowlisted US paper account only, and the command refuses
   anything else. Never a live account, a market order, a short sale or an order the command did not
   list."""


def cycle_text(kind: str, example: str) -> str:
    """THE CYCLE, PROBLEMS and RULINGS for one card: only the run-folder name differs."""
    return CYCLE.replace("{{RUN_KIND}}", kind).replace("{{RUN_EXAMPLE}}", example)


PROMPT = """TYCHE DESK RUN (PAPER ONLY; REBUILT 2026-11-25 SO THAT ORDERS ARE ACTUALLY PLACED).

OPERATOR, 25 Nov 2026: "No trades were placed. No point having a beautiful set of guardrails but
nothing works." A run used to need about 45 hand steps and then refused its own data as too old.
Every order decision now lives in one command, `tyche cycle`, and this brief is the whole job. Where
it differs from your own instructions, a skill or an older brief, this brief wins (see RULINGS).

CLOCK: {{CADENCE}}. At the very start always run
tyche calendar --json from the repo. Exit 1 means skip: weekend, NYSE holiday or outside 04:00-20:00
ET; finish with a one-line note and submit nothing. Exit 0 reports trading_day, half_day and the
session phase. On a 13:00 early close the 15:05 fire is AFTER_HOURS and places nothing; the last
stock exit that day goes out by 12:50 ET and options are out by 12:15 ET.

FIRES:
- 08:05 ET premarket: BOOTSTRAP, RESEARCH, THE CYCLE once (stock setups within reach rest as DAY
  limit orders for the open), DIGEST, PUBLISH.
- 12:05 ET: BOOTSTRAP, RESEARCH only if today's watchlist is missing, THE CYCLE once, PUBLISH.
- 15:05 ET: BOOTSTRAP, THE CYCLE once, DIGEST, PUBLISH.
A fire whose cycle answers "skip" still sends its DIGEST and runs PUBLISH.
Between these fires the 15-minute card ("Tyche scalp - PB-004 every 15 minutes") runs THE CYCLE at
minutes 07, 22, 37 and 52 from 09:07 to 15:52 ET, with the same command on the same ledger. It places
the stock, option and scalp orders and every exit. It is expected, never a second desk and never a
reason to block. Runs that overlap are safe: the command never reserves a second order for a symbol
while one is on its way or working.

ON-DEMAND RUN (2026-11-24, operator): a run that does not start within 10 minutes after 08:05, 12:05
or 15:05 ET was started by the operator (desk "Run now" or --run-now). It does BOOTSTRAP, RESEARCH
only if today's watchlist is missing, THE CYCLE once on fresh reads, a DIGEST titled "ON-DEMAND RUN",
and PUBLISH. Outside the session the cycle answers "skip" and the run only reports.

BOOTSTRAP: `cd /data/workspace/tyche`, run `pip install -e . --no-deps -q`, then `tyche cycle --help`.
If that does not print the command's help, use `PYTHONPATH=src python -m tyche.cli` in place of
`tyche` for the whole run. Then `tyche halt-status --json`: halted=true needs nothing from you, the
command holds buys back and still sends exits; say so in the digest. Nothing is restored or looked up
by hand.

RESEARCH: delegate the researcher for today's long stock setups on the `symbols` of
config/tactical.yaml, then write them yourself to /data/drive/tyche-raw/watchlist.json as
{"as_of": "<New York date>", "entries": [...]}. At most one entry per symbol, each with:
- symbol ("US.KO"), sleeve ("defensive" or "equity"), strategy (a few words), direction "bullish";
- entry_low, entry_high, stop, target, with stop < entry_low <= entry_high < target and the reward
  (target - entry_high) at least 1.5 times the risk (entry_high - stop);
- thesis, catalyst, sources (at least one URL) and market_cap_usd;
- factors: at least one {"name","axis":"technical","state":"pass","why"} and one with axis
  "fundamental" and state "pass". They must be true; a setup without both does not trade;
- max_quantity: the shares that about 5,000 dollars buys at entry_high.
Leave out setup_id, expiry, reviewed_at and exit_at for a stock: the command fills them in, and the
lot leaves at the session's exit time.
How a setup trades: a live price inside the zone is bought at once at the ask; a price up to 3% above
the zone rests a DAY limit at entry_high; further away, nothing happens. So pick a zone the price is
in now or can reach today, with entry_high no more than about 1% below the last price. A level far
below the market only waits, and a desk that only waits places no trade. No setup for a symbol is a
valid answer when the evidence is not there. Then run `tyche cycle --dir <run> --reads`: its `setups`
must list your symbols, and an alert "left out: ..." names a setup and the field to fix. Fix the file
and run it again. After step 3 of THE CYCLE read `stocks.decisions`: a "wait" whose reason is about
the setup itself (evidence, market cap, reward/risk, factors) is fixed in the file straight away, so
the next 15-minute cycle trades it.

PB-003 OPTION (2026-11-24 test; optional; only while `tyche strategies --json` lists PB-003 enabled):
at the 08:05 fire of Wed 25 Nov the researcher may add at most ONE long call on a symbol that also
has a stock setup. Use quote_option_chain (standard contracts, expiry after 2026-11-27 and within 30
days) and take the call nearest 0.55 delta with open interest of at least 100. Its watchlist entry
has symbol = the option code (like "US.KO261218C97000"), an `option` block {"underlying","expiry",
"right":"call","strike"}, premium_limit (the ask per share now), the UNDERLYING's entry_low,
entry_high, stop and target, expiry "2026-11-27", exit_at "2026-11-27T12:10:00-05:00", and every
other field a stock setup has. The command buys it at the live ask inside the lane's own limits and
sells it on the underlying's stop or target, a 40% premium loss or exit_at.
Never sell an option to open, never a spread. If any field is in doubt, leave the option out: the
stock setups do not depend on it.

{{CYCLE}}

OTHER LANES: PB-001 ballast and PB-007 place no order from this brief. The account has held no
ballast since the operator's 24 Nov exits and PB-007 is switched off. They come back only when the
operator asks.

OPERATOR EXIT (2026-11-24): only when the operator asked today, on Telegram or with a sell line in a
same-day data/approvals.json, to sell a lot the desk holds. After step 3 of THE CYCLE, for each such
lot take limit = the higher of the approved floor and the bid less 0.5% and run `tyche exit-now
--account <run>/snapshot.json --symbol <S> --qty <Q> --limit <L> --orders <run>/orders.json --journal
<ledger>`, where <ledger> is the `ledger` path the cycle printed. Exit 0 is the whole authority for
ONE limit sell with exactly those fields and its request_id as the remark; exit 1 is a refusal to
report, never to retry. Paper account only, always.

DIGEST (08:05, 15:05 and on-demand runs): ONE Telegram message in the SENTINEL FORMAT V1 layout (skill
`sentinel-digest`; fill a run-local JSON from templates/sentinel-digest.example.json and deliver it
with `python scripts/telegram.py send-digest <file>`), built only from this run's <run>/cycle.json:
NAV, cash and positions from `account`; the orders placed and the fills seen; each stock setup with
its `stocks.decisions` reason in plain words; every alert. Say plainly when no order was placed. Never
claim a fill or an approval the report does not show, never include an account id or a token. Exit
code 2 from the sender means UNCONFIRMED: do not send it again. The 12:05 fire sends no digest.

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
    """What a live desk brief must contain; `--apply-update` refuses to finish without every one."""
    return {
        "has_calendar_gate": "tyche calendar --json" in events,
        "has_after_hours_guard": "AFTER_HOURS" in events,
        "has_holiday_note": ("the only holiday filter" in events
                             or "the cron day list already excludes" in events),
        "has_three_fires": "08:05 ET premarket" in events and "12:05 ET" in events and "15:05 ET" in events,
        "has_cycle_reads": "tyche cycle --dir <run> --reads" in events,
        "has_cycle_record": "tyche cycle --dir <run> --record" in events,
        "has_exact_submit": ("ONE sim_trade_input_order paper LIMIT order" in events
                             and "never an order that is not on the list" in events),
        "has_no_hand_steps": "Never run tactical tick, reserve, scalp, capture, lifecycle or record-order" in events,
        "has_problems": "PROBLEMS:" in events and "Never place an order by hand" in events,
        "has_rulings": ("RULINGS (2026-11-25, operator)" in events
                        and "IS the reservation" in events and "data/standing-approval.json" in events),
        "has_paper_only": "the allowlisted US paper account only" in events and "Never a live account" in events,
        "has_research": "/data/drive/tyche-raw/watchlist.json" in events and "left out" in events,
        "has_long_options": "PB-003 OPTION" in events and "Never sell an option to open" in events,
        "has_on_demand": "ON-DEMAND RUN (2026-11-24, operator)" in events,
        "has_operator_exit": "OPERATOR EXIT" in events and "tyche exit-now" in events,
        "has_sentinel_format_v1": "SENTINEL FORMAT V1" in events,
        "has_renderer_path": "send-digest" in events,
        "has_feed_publish": "scripts/publish_desk_data.py" in events,
        "has_performance_pack": "performance pack" in events,
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
    """Other desk cards that would still fire on or after `start`: a second desk card."""
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
    if "--run-now" in sys.argv:
        # On-demand run: fire the live desk card once now. The brief's ON-DEMAND RUN clause makes it a
        # full run (research if the day's watchlist is missing, then THE CYCLE once on fresh reads).
        deployment_id = sys.argv[sys.argv.index("--run-now") + 1]
        before = req(values, "GET", f"/deployments/{deployment_id}")
        if not str(before.get("name", "")).startswith("Tyche desk"):
            raise SystemExit("refusing to run a deployment that is not the Tyche desk card")
        events = json.dumps(before.get("initial_events") or [])
        if "ON-DEMAND RUN (2026-11-24, operator)" not in events:
            raise SystemExit("the live brief has no ON-DEMAND RUN clause yet; run --apply-update first")
        item = req(values, "POST", f"/deployments/{deployment_id}/run")
        item = item.get("item") or item
        print(json.dumps({"run_requested": deployment_id, "run_id": item.get("id"),
                          "session_id": item.get("session_id"), "status": item.get("status")}, indent=2))
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
