"""Create, update, pause or fire the 15-minute card: the desk's second Qoder card.

The desk card fires three times a day. That is too slow for anything that has to react inside the
session, so this card wakes at minutes 07, 22, 37 and 52 of every hour from 09:00 to 15:59 New York
time, Monday to Friday, and runs THE CYCLE once: `tyche cycle`, the one command that decides every
order for every lane (stock and option entries from the day's watchlist, the PB-004 scalp, and every
exit). It carries the desk brief's CYCLE text word for word, imported from
deploy_two_fire_automation.py, so the two briefs cannot drift apart. The minutes are chosen so that:
  - 09:07 and 09:22 rest the day's stock buys before the open,
  - 09:37 is the first run that has five 1-minute bars after the open (the scalp breakout needs them),
  - 15:37 (12:37 on a 13:00 early close) lands after the scalp's flatten line and is the stock lane's
    last check before its exit time, so every lot is sold there, with 15:52 (12:52) as the second chance,
  - no run starts on the desk card's :05 minute.

It began on 2026-11-24 as the PB-004 scalp card, which is why its name still says so: a live card's
name cannot be changed by a prompt update, and `--apply-update` recognises the card by that name.
It runs on the same desk agent, environment, vault and repo mount as the desk card, and writes the same
Drive ledger. Until 2026-11-25 it ran the scalp lane only, by hand-run steps, and placed no order.

Run from the laptop repo root (reads QODER_PAT and the desk secrets from the gitignored .env):
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py            dry run: shows the card, writes nothing
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py --apply    creates the card
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py --pause <deployment_id>
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py --apply-update <deployment_id>   prompt only
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py --run-now <deployment_id>        one run now
Never prints secret values.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("desk_card", HERE / "deploy_two_fire_automation.py")
desk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(desk)

CARD_NAME = "Tyche scalp - PB-004 every 15 minutes"
PROFILE = "scalp-15min-weekday"
SCALP_CRON = "7,22,37,52 9-15 * * 1-5"
STOP_AFTER = "2026-11-30"
DESCRIPTION = ("Tyche paper desk, the 15-minute cycle: every lane's entries and exits (stocks and options "
               "from the day's watchlist, the PB-004 scalp) from one command, every 15 minutes in the "
               "session, until " + STOP_AFTER + ".")

PROMPT = """TYCHE 15-MINUTE CYCLE RUN (PAPER ONLY; ALL LANES; REBUILT 2026-11-25; ENDS AFTER {{STOP_AFTER}}).

OPERATOR, 25 Nov 2026: "No trades were placed. No point having a beautiful set of guardrails but
nothing works." This card used to run the scalp lane by hand-run steps and refused its own data as too
old. It now has ONE job: run THE CYCLE below once, for every lane, and stop. Where this brief differs
from your own instructions, a skill or an older brief, this brief wins (see RULINGS).

WHAT THIS RUN IS: this card fires at minutes 07, 22, 37 and 52 from 09:07 to 15:52 New York time,
Monday to Friday. The desk card (08:05, 12:05 and 15:05 ET) does the research, writes the day's
watchlist and runs the same cycle on the same ledger. It is expected, never a second writer to stop
for. Runs that overlap are safe: the command never reserves a second order for a symbol while one is
on its way or working. What a run does at each time is the command's business, not yours: before
09:30 it rests the day's stock buys, in the session it trades the stock, option and scalp lanes and
every exit, the 15:37 run (12:37 on an early close) sells every stock and scalp lot, and the 15:52
run (12:52) is the second chance for a sell that did not fill.

GATE: if the New York date is after {{STOP_AFTER}}, end the run with one log line and nothing else.

TIME LIMIT: this run owns 13 minutes from its scheduled start (minute :07, :22, :37 or :52). Note the
start first. Once 13 minutes have passed, stop where you are: the next run is already on its way and
reads the broker's own order list. An order is never sent after its `submit_before`.

BOOTSTRAP: `cd /data/workspace/tyche`, run `pip install -e . --no-deps -q`, then `tyche cycle --help`.
If that does not print the command's help, use `PYTHONPATH=src python -m tyche.cli` in place of
`tyche` for the whole run. Nothing is restored or looked up by hand.

{{CYCLE}}

NOTHING ELSE: no research, no watchlist edit, no digest, no publish step and no lock file. When the
cycle answers "skip" or lists nothing, end the run with one log line; a quiet run sends no Telegram.
"""


def card_prompt() -> str:
    return (PROMPT.replace("{{STOP_AFTER}}", STOP_AFTER)
            .replace("{{CYCLE}}", desk.cycle_text("cycle", "2026-11-25-cycle-1437")))


def prompt_markers(events: str) -> dict[str, bool]:
    """What a live 15-minute brief must contain; `--apply-update` refuses to finish without every one."""
    return {"has_one_job": "ONE job: run THE CYCLE below once" in events,
            "has_stop_after": f"after {STOP_AFTER}" in events,
            "has_time_limit": "TIME LIMIT: this run owns 13 minutes" in events,
            "has_cycle_reads": "tyche cycle --dir <run> --reads" in events,
            "has_cycle_record": "tyche cycle --dir <run> --record" in events,
            "has_exact_submit": ("ONE sim_trade_input_order paper LIMIT order" in events
                                 and "never an order that is not on the list" in events),
            "has_no_hand_steps": "Never run tactical tick, reserve, scalp, capture, lifecycle or record-order" in events,
            "has_problems": "PROBLEMS:" in events and "Never place an order by hand" in events,
            "has_rulings": ("RULINGS (2026-11-25, operator)" in events
                            and "IS the reservation" in events and "data/scalp-approvals.json" in events),
            "has_paper_only": "the allowlisted US paper account only" in events and "Never a live account" in events}


def scalp_cards(values: dict[str, str]) -> list[dict]:
    rows = desk.req(values, "GET", "/deployments?limit=50")
    items = rows.get("data") or rows.get("items") or []
    return [{"id": i.get("id"), "name": i.get("name"), "status": i.get("status")}
            for i in items if isinstance(i, dict) and str(i.get("name", "")).startswith("Tyche scalp")
            and i.get("status") != "paused"]


def payload(values: dict[str, str], version: int, agent_id: str) -> dict:
    out = {
        "name": CARD_NAME,
        "description": DESCRIPTION,
        "agent": {"id": agent_id, "type": "agent", "version": version},
        "environment_id": desk.ENVIRONMENT_ID,
        "vault_ids": [desk.VAULT_ID],
        "resources": [
            {"type": "github_repository", "url": "https://github.com/aloisohzh/tyche",
             "authorization_token": "public-repo-anonymous", "mount_path": "/data/workspace/tyche"},
            {"type": "memory_store", "memory_store_id": desk.MEMORY_STORE_ID, "access": "read_write"},
        ],
        "schedule": {"type": "cron", "expression": SCALP_CRON, "timezone": "America/New_York"},
        # No `window` on purpose: the dashboard and the hosted Function pick "today's desk card" by that
        # field (scripts/cloud_api.py pick_card), and a dated window here would win over the desk card.
        "metadata": {"source": "operator", "profile": PROFILE, "ends": STOP_AFTER},
        "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": card_prompt()}]}],
    }
    # The desk's secrets live on its card, not the environment: give this card its own copies from .env.
    secrets = [k for k in desk.SECRET_KEYS if values.get(k)]
    if secrets:
        out["environment_variables"] = ";".join(f"{k}={values[k]}" for k in secrets)
    return out


def main() -> None:
    values = desk.env()
    if "--pause" in sys.argv:
        deployment_id = sys.argv[sys.argv.index("--pause") + 1]
        before = desk.req(values, "GET", f"/deployments/{deployment_id}")
        if not str(before.get("name", "")).startswith("Tyche scalp"):
            raise SystemExit("refusing to pause a deployment that is not the Tyche scalp card")
        desk.req(values, "POST", f"/deployments/{deployment_id}/pause")
        after = desk.req(values, "GET", f"/deployments/{deployment_id}")
        print(json.dumps({"paused": deployment_id, "status": after.get("status")}, indent=2))
        return
    if "--run-now" in sys.argv:
        # One run of the 15-minute card now: THE CYCLE once on fresh reads (a closed market is a skip).
        deployment_id = sys.argv[sys.argv.index("--run-now") + 1]
        before = desk.req(values, "GET", f"/deployments/{deployment_id}")
        if not str(before.get("name", "")).startswith("Tyche scalp"):
            raise SystemExit("refusing to run a deployment that is not the Tyche scalp card")
        events = json.dumps(before.get("initial_events") or [])
        if "tyche cycle --dir <run> --record" not in events:
            raise SystemExit("the live brief has no THE CYCLE clause yet; run --apply-update first")
        item = desk.req(values, "POST", f"/deployments/{deployment_id}/run")
        item = item.get("item") or item
        print(json.dumps({"run_requested": deployment_id, "run_id": item.get("id"),
                          "session_id": item.get("session_id"), "status": item.get("status")}, indent=2))
        return
    if "--apply-update" in sys.argv:
        import hashlib
        deployment_id = sys.argv[sys.argv.index("--apply-update") + 1]
        before = desk.req(values, "GET", f"/deployments/{deployment_id}")
        if not str(before.get("name", "")).startswith("Tyche scalp"):
            raise SystemExit("refusing to update a deployment that is not the Tyche scalp card")
        keys_before = set(desk._parse_env_string(before.get("environment_variables")))
        desk.req(values, "POST", f"/deployments/{deployment_id}", desk.update_payload(before, card_prompt()))
        after = desk.req(values, "GET", f"/deployments/{deployment_id}")
        keys_after = set(desk._parse_env_string(after.get("environment_variables")))
        keep = ("name", "status", "agent", "environment_id", "vault_ids", "metadata", "resources", "schedule")
        drift = [k for k in keep
                 if json.dumps(before.get(k), sort_keys=True) != json.dumps(after.get(k), sort_keys=True)]
        events = json.dumps(after.get("initial_events") or [])
        print(json.dumps({"updated": deployment_id, "status": after.get("status"),
                          "agent_pin": (after.get("agent") or {}).get("version"),
                          "card_env_keys": sorted(keys_after), "env_keys_unchanged": keys_after == keys_before,
                          "drift": drift, "prompt_sha256": hashlib.sha256(events.encode()).hexdigest()[:16],
                          **prompt_markers(events)}, indent=2))
        if drift or not all(prompt_markers(events).values()):
            raise SystemExit("scalp card update incomplete; inspect cloud state")
        return
    agent_id = desk.card_agent(sys.argv)
    agent = desk.req(values, "GET", f"/agents/{agent_id}")
    version = desk.card_pin(sys.argv, agent)
    body = payload(values, version, agent_id)
    missing = [k for k in desk.SECRET_KEYS if not values.get(k)]
    summary = {"name": CARD_NAME, "agent_version": version, "cron": body["schedule"],
               "stop_after": STOP_AFTER, "prompt_chars": len(card_prompt()),
               "card_secret_keys": [k for k in desk.SECRET_KEYS if values.get(k)],
               "missing_from_dotenv": missing, "other_active_scalp_cards": scalp_cards(values)}
    if "--apply" not in sys.argv:
        print(json.dumps({"dry_run": True, **summary}, indent=2))
        return
    if missing:
        raise SystemExit(f"missing from .env: {missing}")
    if summary["other_active_scalp_cards"]:
        raise SystemExit("a scalp card is already active (two writers): " + json.dumps(summary["other_active_scalp_cards"]))
    result = desk.req(values, "POST", "/deployments", body)
    print(json.dumps(desk.sanitize(result), indent=2))


if __name__ == "__main__":
    main()
