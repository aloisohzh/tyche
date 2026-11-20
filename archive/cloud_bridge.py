"""Cloud bridge wiring: Forward webhook endpoint + Telegram setWebhook.

Secrets are generated/read locally and written to gitignored .env; values are
never printed. The operator copies them into Sites Settings (Secrets) by hand.
Commands: gen-secret, create-endpoint <site-url>, list-endpoints, test-endpoint,
set-webhook <site-url>, webhook-info, delete-webhook, delete-endpoint.
"""
from __future__ import annotations

import json
import secrets
import sys

import forward
from telegram import api, env

ROOT = forward.ROOT
EVENTS = [
    "session.status_run_started",
    "session.thread_created",
    "session.thread_idled",
    "session.status_idled",
    "forward.schedule_run.succeeded",
    "forward.schedule_run.failed",
]


def set_env(key: str, value: str) -> None:
    path = ROOT / ".env"
    lines = [l for l in path.read_text().splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


def endpoint_id() -> str:
    value = env().get("FORWARD_WEBHOOK_ENDPOINT_ID")
    if not value:
        raise SystemExit("FORWARD_WEBHOOK_ENDPOINT_ID missing from .env; run create-endpoint first")
    return value


def main() -> None:
    command = sys.argv[1]
    if command == "gen-secret":
        set_env("TELEGRAM_WEBHOOK_SECRET", secrets.token_hex(32))
        print("TELEGRAM_WEBHOOK_SECRET written to .env (64 hex chars). Copy it into Sites Settings.")
    elif command == "create-endpoint":
        url = sys.argv[2].rstrip("/") + "/functions/v1/app/forward"
        existing = forward.req("GET", "/webhook/endpoints", check=False)
        for endpoint in existing.get("data", []):
            if endpoint.get("url") == url:
                raise SystemExit(f"endpoint already exists for {url}: {endpoint.get('id')} "
                                 "(signing_secret is not retrievable; delete it first if lost)")
        result = forward.req("POST", "/webhook/endpoints", {
            "url": url,
            "description": "tyche bridge: desk session/thread idle + schedule run results",
            "events": EVENTS,
            "metadata": {"purpose": "tyche-bridge"},
        })
        secret = result.get("signing_secret") or ""
        if not secret.startswith("whsec_"):
            raise SystemExit(f"unexpected create response: {json.dumps(result)[:300]}")
        set_env("FORWARD_SIGNING_SECRET", secret)
        set_env("FORWARD_WEBHOOK_ENDPOINT_ID", result["id"])
        print(json.dumps({k: result.get(k) for k in ("id", "url", "events", "active")}, indent=1))
        print("FORWARD_SIGNING_SECRET written to .env (returned once). Copy it into Sites Settings.")
    elif command == "list-endpoints":
        result = forward.req("GET", "/webhook/endpoints", check=False)
        for endpoint in result.get("data", []):
            print(json.dumps({k: endpoint.get(k) for k in ("id", "url", "events", "active")}))
    elif command == "test-endpoint":
        result = forward.req("POST", f"/webhook/endpoints/{endpoint_id()}/test", {})
        print(json.dumps(result, indent=1)[:500])
    elif command == "set-webhook":
        url = sys.argv[2].rstrip("/") + "/functions/v1/app/telegram"
        secret = env().get("TELEGRAM_WEBHOOK_SECRET")
        if not secret:
            raise SystemExit("TELEGRAM_WEBHOOK_SECRET missing from .env; run gen-secret first")
        result = api("setWebhook", {
            "url": url, "secret_token": secret,
            "allowed_updates": json.dumps(["message"]), "drop_pending_updates": "false",
        })
        print("setWebhook ok:", result.get("result"), "->", url)
    elif command == "webhook-info":
        info = api("getWebhookInfo", {})["result"]
        print(json.dumps({k: info.get(k) for k in
                          ("url", "has_custom_certificate", "pending_update_count",
                           "last_error_date", "last_error_message", "max_connections")}, indent=1))
    elif command == "delete-webhook":
        result = api("deleteWebhook", {"drop_pending_updates": "false"})
        print("deleteWebhook ok:", result.get("result"), "(local getUpdates bridge can resume)")
    elif command == "delete-endpoint":
        result = forward.req("DELETE", f"/webhook/endpoints/{endpoint_id()}", check=False)
        print(json.dumps(result)[:300])
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()