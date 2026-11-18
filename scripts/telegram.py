"""Telegram Bot API helper for the tyche sentinel. Token from gitignored .env."""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env() -> dict:
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def api(method: str, params: dict) -> dict:
    token = env().get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN missing from .env")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=urllib.parse.urlencode(params).encode(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if not payload.get("ok"):
        raise SystemExit(f"telegram error: {payload.get('description')}")
    return payload


def main() -> None:
    command = sys.argv[1]
    if command == "chat-id":
        updates = api("getUpdates", {})["result"]
        chats = {}
        for update in updates:
            chat = (update.get("message") or update.get("channel_post") or {}).get("chat") or {}
            if chat.get("id"):
                chats[str(chat["id"])] = chat.get("type")
        if not chats:
            raise SystemExit("no updates yet: send the bot a message first")
        print(json.dumps(chats, indent=2))
        if len(chats) == 1:
            chat_id = next(iter(chats))
            path = ROOT / ".env"
            lines = [l for l in path.read_text().splitlines()
                     if not l.startswith("TELEGRAM_CHAT_ID=")]
            lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
            path.write_text("\n".join(lines) + "\n")
            print(f"TELEGRAM_CHAT_ID={chat_id} written to .env")
    elif command == "send":
        chat_id = env().get("TELEGRAM_CHAT_ID")
        if not chat_id:
            raise SystemExit("TELEGRAM_CHAT_ID missing from .env; run chat-id first")
        result = api("sendMessage", {"chat_id": chat_id, "text": sys.argv[2]})["result"]
        print("sent message_id", result["message_id"])
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()