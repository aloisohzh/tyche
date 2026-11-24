"""Create (or pause) the PB-004 scalp card: a second Qoder card that runs only the scalp lane.

The desk card fires three times a day, which is too slow for a scalp whose trades last at most 20
minutes and must be flat 10 minutes before the close. This card wakes at minutes 07, 22, 37 and 52 of
every hour from 09:00 to 15:59 New York time, Monday to Friday, and its brief ends the run at once
outside the regular session or after STOP_AFTER. The minutes are chosen so that:
  - 09:37 is the first run that has five 1-minute bars after the open (the breakout needs them),
  - 15:52 (12:52 on a 13:00 early close) lands after the flatten line, so every lot is sold,
  - no run starts on the desk card's :05 minute.

It runs on the same desk agent, environment, vault and repo mount as the desk card, and writes the same
Drive ledger journal. It may only arm and submit PB-004 orders inside data/scalp-approvals.json.

Run from the laptop repo root (reads QODER_PAT and the desk secrets from the gitignored .env):
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py            dry run: shows the card, writes nothing
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py --apply    creates the card
  .venv\\Scripts\\python.exe scripts\\deploy_scalp_card.py --pause <deployment_id>
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
DESCRIPTION = ("Tyche paper desk, PB-004 intraday scalp only: 1-minute breakout entries and exits on "
               "NVDA, AMD, AVGO, MU and SMH every 15 minutes in the regular session, until " + STOP_AFTER + ".")

PROMPT = """TYCHE PB-004 SCALP RUN (PAPER ONLY; ONE LANE; ADDED 2026-11-24, ENDS AFTER {{STOP_AFTER}}).

You are the scalp card, not the desk. You run ONLY the PB-004 intraday scalp on US.NVDA, US.AMD, US.AVGO,
US.MU and US.SMH. The desk card (08:05/12:05/15:05 ET) owns everything else; you are the one expected
second writer, limited to PB-004 orders. Never touch another lane, plan, lot, envelope or config file.

GATE (stop at the first that fails, with one line in the run log and nothing else - no Telegram):
1. ET date after {{STOP_AFTER}}: stop; the operator pauses this card.
2. `tyche calendar --json` exit 1, or a phase other than the regular session: stop.
3. `tyche strategies --json` does not list PB-004 as enabled: stop.
4. `tyche journal-verify` on the ledger fails: stop and send ONE Telegram line "SCALP BLOCKED: journal".

LEDGER: repo mount /data/workspace/tyche (install editable --no-deps if tyche is missing). Use the same
Drive ledger journal the desk card uses (its BOOTSTRAP lineage under /data/drive/tyche-raw, latest
verified descendant), never a fresh or local journal. prior_close_nav and high_water_nav come from the
Drive nav-refs exactly as the desk reads them; never invent one. The account id is the paper account in
TYCHE_ALLOWED_ACCOUNT_IDS; never print it.

FEED: delegate the executor to save raw MCP payloads, verbatim, into a run directory <run>:
accounts.json (sim_trade_account_list), cash.json (sim_trade_cash_info), positions.json
(sim_trade_position_list), quotes.json (quote_stock_quote for the five symbols), book-<US.SYMBOL>.json
(quote_order_book each), bars-<US.SYMBOL>.json (quote_cur_kline, 1-minute bars, num=30, each) and
orders.json (sim_trade_order_list plus sim_trade_history_order_list for today).

FILLS FIRST: for every broker order whose remark is a `tyche-scl-` request_id, journal what the broker
shows and the journal lacks: `tyche record-order order.submitted|order.filled|order.rejected --data
{...,"request_id":..,"strategy_id":"PB-004"} --journal <ledger>` (order.filled needs symbol, side,
quantity, price). Never journal a fill the broker does not show.

CYCLE: run
`tyche tactical scalp --feed <run> --dir <run> --orders <run>/orders.json --envelope
data/scalp-approvals.json --account-id <id> --prior-close-nav <n> --high-water-nav <n> --journal
<ledger> --record`. Exits come before entries inside the command; the halt switch blocks buys only.
For each item under `requests`, the executor submits ONE sim_trade_input_order paper LIMIT order with
exactly that symbol, side, quantity and limit_price, the request_id as the remark, strictly before its
submit_before, then journals `tyche record-order order.submitted`. Items marked `skipped` or `denied`
are not submitted; list them in the log. A blocked or failed submit is journaled as gate.wait for that
request_id; the next run re-arms exits itself. Never retry within the run, never cancel or modify, never
place an order the command did not return, never trade anything outside the five symbols.

TELEGRAM: send one short line only when an order was submitted or filled this run
(`python scripts/telegram.py send`, e.g. "SCALP: bought 10 AMD @ 541.20, stop 539.85, target 543.90"),
and an urgent line when a lot is still open at or after the flatten time. Silent otherwise.

PERSIST: the journal on Drive; redact account ids and tokens everywhere. Paper only; live trading is
forbidden.
"""


def card_prompt() -> str:
    return PROMPT.replace("{{STOP_AFTER}}", STOP_AFTER)


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
