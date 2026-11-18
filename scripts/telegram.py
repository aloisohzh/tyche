"""Telegram Bot API helper for the tyche sentinel. Token from gitignored .env.

Commands: chat-id, send, listen. `listen` is the inbound bridge: it relays
operator questions to a desk session and surfaces pending always_ask tool
approvals (e.g. paper order submissions) for explicit /approve or /deny.
It NEVER auto-approves; only the allowlisted chat can drive it.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import forward

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".telegram-bridge.json"
IDENTITY_ID = "idn_1d7b9ab60a1bcc934d4a1d8f"
SCHEDULE_IDS = [
    "sched_52f7a8a04e4bf656e25fac47",  # tyche-premarket
    "sched_f522c892f2a72e77dd7c590f",  # tyche-eod
    "sched_7d7dcb7101f048b8b4df159f",  # tyche-eod-halfday
]
ASK_EVENTS = {"agent.tool_use", "agent.mcp_tool_use"}
RESOLUTION_EVENTS = {"user.tool_confirmation", "agent.tool_result", "agent.mcp_tool_result"}
MAX_PREVIEW = 1500
MAX_MESSAGE = 3900


def env() -> dict:
    # Session env vars win (cloud desk has no .env); local .env is the fallback.
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(key):
            values[key] = os.environ[key]
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
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.loads(response.read())
    if not payload.get("ok"):
        raise SystemExit(f"telegram error: {payload.get('description')}")
    return payload


def mask_ids(text: str) -> str:
    # Account ids are 7+ digits; NAV/price figures stay below that.
    return re.sub(r"\d{7,}", lambda m: "..." + m.group()[-3:], text)


def esc(text: str) -> str:
    return html.escape(str(text), quote=False)


_HTML_TAG = re.compile(r"</?(?:b|i|u|s|code|pre|br|a)(?:\s[^>]*)?>")


def _inline(line: str) -> str:
    """Escape free text and turn Markdown inline marks into Telegram HTML.

    Existing Telegram HTML tags are stashed so compliant input is not
    double-escaped or stripped.
    """
    tags: list[str] = []

    def stash(match: re.Match) -> str:
        tags.append(match.group(0))
        return f"\x00{len(tags) - 1}\x00"

    s = _HTML_TAG.sub(stash, line)
    s = re.sub(r"&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);", stash, s)
    s = esc(s)
    s = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", s)
    s = re.sub(r"^#{1,6}\s+(.*)$", r"<b>\1</b>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: tags[int(m.group(1))], s)


def _table(block: list[str]) -> str:
    """Render a Markdown pipe table as an aligned monospace <pre> block."""
    rows = []
    for line in block:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        rows.append([re.sub(r"\*\*|`", "", c) for c in cells])
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    widths = [max(len(r[i]) for r in rows) for i in range(ncols)]
    aligned = [
        "  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip() for r in rows
    ]
    return "<pre>" + esc("\n".join(aligned)) + "</pre>"


def to_telegram_html(text: str) -> str:
    """Normalize a digest (Markdown or HTML) to Telegram-safe HTML.

    Telegram never renders Markdown pipe tables or **bold**; left as-is they
    show literally. Markdown is converted; existing HTML (incl. multi-line
    <pre> blocks) passes through unchanged so compliant digests are untouched.
    """
    out: list[str] = []
    in_pre = False
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if in_pre:
            out.append(line)
            if "</pre>" in line:
                in_pre = False
            i += 1
            continue
        if "<pre>" in line:
            out.append(line)
            in_pre = "</pre>" not in line
            i += 1
            continue
        if line.strip().startswith("|") and line.count("|") >= 2:
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_table(block))
            continue
        out.append(_inline(line))
        i += 1
    return "\n".join(out)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"offset": 0, "session_id": None, "cursors": {}, "threads": {},
            "pending": {}, "next_n": 1, "decisions": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")


def is_ask(event: dict) -> bool:
    if event.get("type") not in ASK_EVENTS:
        return False
    if event.get("evaluated_permission") == "ask":
        return True
    evaluation = event.get("evaluation") or {}
    return evaluation.get("type") == "always_ask" and "evaluated_permission" not in event


def resolution_id(event: dict) -> str | None:
    if event.get("type") not in RESOLUTION_EVENTS:
        return None
    return event.get("tool_use_id") or event.get("mcp_tool_use_id")


def update_pending(state: dict, events: list[dict]) -> list[dict]:
    """Track asks awaiting confirmation; return newly seen ask events."""
    fresh = []
    for event in events:
        resolved = resolution_id(event)
        if resolved:
            state["pending"].pop(resolved, None)
        if is_ask(event) and event["id"] not in state["pending"]:
            state["pending"][event["id"]] = {
                "n": state["next_n"],
                "name": event.get("name"),
                "server": event.get("mcp_server_name"),
                "input": event.get("input") or {},
                "thread": event.get("session_thread_id"),
                "seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            state["next_n"] += 1
            fresh.append(event)
    return fresh


def format_preview(ask: dict) -> str:
    tool = ask["name"] or "tool"
    if ask.get("server"):
        tool = f'{ask["server"]}/{tool}'
    body = json.dumps(ask["input"], indent=1, ensure_ascii=False)
    if len(body) > MAX_PREVIEW:
        body = body[:MAX_PREVIEW] + "\n... (truncated)"
    thread = ask.get("thread_name") or ask.get("thread") or "?"
    return (
        f'<b>Approval required #{ask["n"]}</b> — a member thread asks to run '
        f"<code>{esc(tool)}</code>\n<pre>{esc(mask_ids(body))}</pre>\n"
        f"Reply <code>/approve {ask['n']}</code> or <code>/deny {ask['n']} [reason]</code>. "
        f"Nothing runs without your explicit approve. (thread {esc(thread)})"
    )


def find_pending(state: dict, token: str) -> tuple[str, dict] | None:
    if not token.isdigit():
        return None
    for tool_use_id, ask in state["pending"].items():
        if ask["n"] == int(token):
            return tool_use_id, ask
    return None


def latest_session_id() -> str | None:
    best = None
    for schedule_id in SCHEDULE_IDS:
        result = forward.req(
            "GET", f"/schedule_runs?identity_id={IDENTITY_ID}&schedule_id={schedule_id}&limit=1",
            check=False,
        )
        for run in result.get("data", []):
            if run.get("session_id") and (best is None or run["created_at"] > best[0]):
                best = (run["created_at"], run["session_id"])
    return best[1] if best else None


class Bridge:
    def __init__(self, state: dict, chat_id: str):
        self.state = state
        self.chat_id = chat_id

    def say(self, text: str) -> None:
        if len(text) > MAX_MESSAGE:
            text = text[:MAX_MESSAGE] + "\n... (truncated)"
        try:
            api("sendMessage", {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"})
            print(f"sent: {text[:100]}", flush=True)
        except (OSError, ValueError, SystemExit) as error:
            print(f"telegram send failed: {error}", flush=True)

    def refresh_threads(self) -> bool:
        session_id = self.state["session_id"]
        threads = forward.req("GET", f"/sessions/{session_id}/threads", check=False)
        if threads.get("http_error"):
            print(f"thread list HTTP {threads['http_error']}", flush=True)
            return False
        self.state["threads"] = {
            t["id"]: {"role": t.get("role"), "name": t.get("name"),
                      "archived": bool(t.get("archived_at"))}
            for t in threads.get("data", [])
        }
        return True

    def thread_events(self, thread_id: str) -> list[dict]:
        """Drain new events for one thread; tag them with their thread id."""
        events: list[dict] = []
        cursor = self.state["cursors"].get(thread_id)
        for _ in range(300):
            path = f'/sessions/{self.state["session_id"]}/threads/{thread_id}/events?limit=100'
            if cursor:
                path += f"&after_id={cursor}"
            page = forward.req("GET", path, check=False)
            if page.get("http_error"):
                print(f"thread events HTTP {page['http_error']}", flush=True)
                break
            batch = page.get("data", [])
            for event in batch:
                event.setdefault("session_thread_id", thread_id)
            events.extend(batch)
            cursor = page.get("last_id") or cursor
            if not page.get("has_more"):
                break
        self.state["cursors"][thread_id] = cursor
        return events

    def label_fresh(self, fresh: list[dict]) -> None:
        for event in fresh:
            ask = self.state["pending"][event["id"]]
            info = self.state["threads"].get(ask.get("thread")) or {}
            ask["thread_name"] = info.get("name")

    def bind(self, session_id: str) -> None:
        self.state["session_id"] = session_id
        self.state["pending"] = {}
        self.state["cursors"] = {}
        if not self.refresh_threads():
            self.say(f"Cannot bind {esc(session_id)}: thread list unavailable.")
            return
        # Scan history once so already-pending approvals surface immediately.
        for thread_id in self.state["threads"]:
            fresh = update_pending(self.state, self.thread_events(thread_id))
            self.label_fresh(fresh)
        self.say(
            f"Bound to session <code>{esc(session_id)}</code>. "
            f"{len(self.state['pending'])} pending approval(s). "
            "Send any question to relay it to the desk; /help for commands."
        )
        for ask in self.state["pending"].values():
            self.say(format_preview(ask))

    def poll_events(self) -> None:
        if not self.state["session_id"]:
            return
        if not self.refresh_threads():
            return
        for thread_id, info in self.state["threads"].items():
            if info.get("archived"):
                continue
            events = self.thread_events(thread_id)
            if not events:
                continue
            fresh = update_pending(self.state, events)
            self.label_fresh(fresh)
            for event in fresh:
                self.say(format_preview(self.state["pending"][event["id"]]))
            if info.get("role") != "coordinator":
                continue
            for event in events:
                if event.get("type") == "agent.message":
                    text = "\n".join(
                        block.get("text", "") for block in event.get("content", [])
                        if block.get("type") == "text"
                    ).strip()
                    if text:
                        self.say(to_telegram_html(mask_ids(text)))
                elif event.get("type") == "session.error":
                    self.say(f"<b>Session error</b>: {esc(mask_ids(json.dumps(event.get('error'))))}")

    def confirm(self, token: str, result: str, reason: str | None) -> None:
        found = find_pending(self.state, token)
        if not found:
            self.say(f"No pending approval #{esc(token)}. Use /pending to list.")
            return
        tool_use_id, ask = found
        body = {"type": "user.tool_confirmation", "tool_use_id": tool_use_id, "result": result}
        if reason:
            body["deny_message"] = reason
        response = forward.req(
            "POST", f'/sessions/{self.state["session_id"]}/events', {"events": [body]}, check=False
        )
        if response.get("http_error"):
            self.say(f"Confirmation failed: HTTP {response['http_error']} {esc(response['body'][:200])}")
            return
        self.state["pending"].pop(tool_use_id, None)
        self.state["decisions"].append({
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n": ask["n"], "tool": ask["name"], "result": result, "reason": reason,
        })
        self.state["decisions"] = self.state["decisions"][-200:]
        verb = "Approved" if result == "allow" else "Denied"
        self.say(
            f"{verb} #{ask['n']} <code>{esc(ask['name'])}</code>. "
            + ("A submit is not a fill — watch for the broker order state."
               if result == "allow" else "The desk will see your denial.")
        )

    def handle(self, text: str) -> None:
        parts = text.split(maxsplit=2)
        command = parts[0].lower().split("@")[0]
        if command in ("/start", "/help"):
            self.say(
                "<b>Tyche bridge</b>\n"
                "/session latest — bind the newest schedule-run session\n"
                "/session &lt;sess_id&gt; — bind a specific session\n"
                "/status — session status and credits\n"
                "/pending — list approvals waiting for you\n"
                "/approve N — allow pending approval N\n"
                "/deny N [reason] — deny pending approval N\n"
                "/interrupt — stop the current desk turn\n"
                "Any other text is relayed to the desk as a question.\n"
                "Approvals are never automatic; only this chat can issue them."
            )
        elif command == "/session":
            target = parts[1] if len(parts) > 1 else None
            if target == "latest":
                target = latest_session_id()
                if not target:
                    self.say("No schedule-run session found yet.")
                    return
            if not target:
                self.say(f'Current: <code>{esc(self.state["session_id"] or "unbound")}</code>')
                return
            self.bind(target)
        elif command == "/status":
            if not self.state["session_id"]:
                self.say("Not bound. Use /session latest.")
                return
            session = forward.req("GET", f'/sessions/{self.state["session_id"]}', check=False)
            if session.get("http_error"):
                self.say(f"Status failed: HTTP {session['http_error']}")
                return
            usage = session.get("usage") or {}
            self.say(
                f'<b>{esc(session.get("title") or session.get("id"))}</b>\n'
                f'Status: {esc(session.get("status"))} | credits: {usage.get("total_credits", "?")}\n'
                f'Pending approvals: {len(self.state["pending"])}'
            )
        elif command == "/pending":
            if not self.state["pending"]:
                self.say("No pending approvals.")
            for ask in self.state["pending"].values():
                self.say(format_preview(ask))
        elif command == "/approve":
            if len(parts) < 2:
                self.say("Usage: /approve N (see /pending). Never approving without a number.")
                return
            self.confirm(parts[1], "allow", None)
        elif command == "/deny":
            if len(parts) < 2:
                self.say("Usage: /deny N [reason]")
                return
            self.confirm(parts[1], "deny", parts[2] if len(parts) > 2 else None)
        elif command == "/interrupt":
            if not self.state["session_id"]:
                self.say("Not bound.")
                return
            response = forward.req(
                "POST", f'/sessions/{self.state["session_id"]}/events',
                {"events": [{"type": "user.interrupt"}]}, check=False,
            )
            self.say("Interrupt sent." if not response.get("http_error")
                     else f'Interrupt failed: HTTP {response["http_error"]}')
        else:
            if not self.state["session_id"]:
                self.say("Not bound. Use /session latest first.")
                return
            response = forward.req(
                "POST", f'/sessions/{self.state["session_id"]}/events',
                {"events": [{"type": "user.message", "content": [{"type": "text", "text": text}]}]},
                check=False,
            )
            if response.get("http_error") == 409:
                self.say("Desk is mid-turn; message NOT sent. Retry when idle (/status).")
            elif response.get("http_error"):
                self.say(f'Relay failed: HTTP {response["http_error"]} {esc(response["body"][:200])}')
            else:
                self.say("Relayed to the desk; the reply will appear here.")


def listen() -> None:
    values = env()
    chat_id = values.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise SystemExit("TELEGRAM_CHAT_ID missing from .env; run chat-id first")
    if not values.get("QODER_PAT"):
        raise SystemExit("QODER_PAT missing from .env")
    state = load_state()
    bridge = Bridge(state, chat_id)
    print(f"bridge online; chat allowlist={chat_id}; session={state.get('session_id')}", flush=True)
    if not state["offset"]:
        stale = api("getUpdates", {})["result"]
        if stale:
            state["offset"] = max(u["update_id"] for u in stale) + 1
            save_state(state)
    if state.get("session_id"):
        bridge.bind(state["session_id"])
    bridge.say("Bridge online. /help for commands. Approvals stay manual: /approve N or /deny N.")
    while True:
        try:
            updates = api("getUpdates", {"offset": state["offset"], "timeout": 5})["result"]
            for update in updates:
                state["offset"] = update["update_id"] + 1
                message = update.get("message") or {}
                if str((message.get("chat") or {}).get("id")) != str(chat_id):
                    continue
                text = (message.get("text") or "").strip()
                if text:
                    bridge.handle(text)
            bridge.poll_events()
        except KeyboardInterrupt:
            save_state(state)
            print("bridge stopped", flush=True)
            return
        except (OSError, ValueError, SystemExit, KeyError) as error:
            print(f"loop error: {error}", flush=True)
            time.sleep(5)
        save_state(state)


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
        text = to_telegram_html(mask_ids(sys.argv[2]))
        if len(text) > MAX_MESSAGE:
            text = text[:MAX_MESSAGE] + "\n... (truncated)"
        result = api(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )["result"]
        print("sent message_id", result["message_id"])
    elif command == "listen":
        listen()
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()