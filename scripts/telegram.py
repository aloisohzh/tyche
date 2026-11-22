"""Telegram Bot API helper for the tyche sentinel. Token from gitignored .env.

Commands: chat-id, send, render-digest, send-digest, render-proposal, wait-for-reply, listen.
`render-digest <json-file|->` is offline; `send-digest` uses the same template.
`render-proposal <json-file|->` is offline; `wait-for-reply <json-file> [--timeout S]` sends the
same numbered previews and waits (10 minutes by default, 15 at most) for the operator's explicit
`/approve N` or `/deny N`. Silence is a timeout, a free-text reply (question or change) is handed
back to the desk unapproved, and nothing but `/approve N` from the allowlisted chat ever approves.
`listen` is the inbound bridge: it relays
operator questions to a desk session and surfaces pending always_ask tool
approvals (e.g. paper order submissions) for explicit /approve or /deny.
It NEVER auto-approves; only the allowlisted chat can drive it.
Only one program may read the bot's updates at a time: `wait-for-reply` and `listen` must never
run together.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cloud_api

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".telegram-bridge.json"
# The two live desk cards, both authored by scripts/deploy_two_fire_automation.py. Their runs are the
# only source of a session id worth binding to: the Forward schedules listed here before are paused,
# fire nothing, and 404 on the sessions a card started (queue.md W7).
DESK_CARD_IDS = ("dep_00vzb9h4ezawwl4thnva", "dep_00vzd8d5rdfr4w0denqh")
ASK_EVENTS = {"agent.tool_use", "agent.mcp_tool_use"}
RESOLUTION_EVENTS = {"user.tool_confirmation", "agent.tool_result", "agent.mcp_tool_result"}
MAX_PREVIEW = 1500
MAX_MESSAGE = 3900
SEND_TIMEOUT = 60
# Injection points for the wait loop's clock; tests replace them, production never does.
_now = time.time


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
    with urllib.request.urlopen(request, timeout=SEND_TIMEOUT) as response:
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


MAX_DIGEST = 3500


def _digest_object(value: object, required: set[str], optional: set[str] | None = None) -> dict:
    """Reject missing/unknown fields rather than silently dropping risk information."""
    if not isinstance(value, dict):
        raise TypeError("Digest sections and order rows must be JSON objects")
    if required - value.keys():
        raise ValueError("Missing digest fields: " + ", ".join(sorted(required - value.keys())))
    if value.keys() - required - (optional or set()):
        raise ValueError("Unexpected digest fields; use the documented template")
    return value


def _digest_text(value: object, limit: int = 240) -> str:
    """Plain text only: preserve facts, escape markup, normalize user-facing punctuation."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Digest values must be non-empty plain-text strings")
    text = value.strip().replace("\u2014", "-").replace("\u2013", "-")
    if any(ord(char) < 32 for char in text) or len(text) > limit:
        raise ValueError(f"Digest values must be single-line and at most {limit} characters")
    return mask_ids(text)


def _digest_lines(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError("Digest detail sections must be lists of at most 12 short lines")
    return [_digest_text(line) for line in value]


def render_digest(digest: dict) -> str:
    """One deterministic layout for routine digests and urgent alerts; no broker access.

    Required facts are supplied by the caller, never inferred from holdings. Table
    cells stay compact; values, statuses, reasons and rule references live below it.
    Oversize input is rejected before sending, never sliced through a risk warning.
    """
    data = _digest_object(digest, {
        "phase", "timestamp", "mode", "stance", "orders_summary", "orders",
        "account", "protection", "problems",
    }, {"urgent", "proposals", "next_check"})
    urgent = data.get("urgent", False)
    if not isinstance(urgent, bool):
        raise TypeError("urgent must be a JSON boolean")
    phase = _digest_text(data["phase"], 40).upper()
    title = "TYCHE " + phase + (" - URGENT RISK ALERT" if urgent else "")
    out = [
        f"<b>{esc(title)}</b>",
        esc(_digest_text(data["timestamp"], 120)),
        f"<b>{esc(_digest_text(data['mode'], 100))}</b>",
        "", esc(_digest_text(data["stance"])),
        "", "<b>Orders</b>", esc(_digest_text(data["orders_summary"])),
    ]
    orders = data["orders"]
    if not isinstance(orders, list) or len(orders) > 12:
        raise ValueError("orders must be a list of at most 12 rows")
    rows = [["ACTION", "SYMBOL", "QTY"]]
    details = []
    for order in orders:
        item = _digest_object(order, {"action", "symbol", "qty", "value", "status", "reason"})
        action = _digest_text(item["action"], 8)
        symbol = _digest_text(item["symbol"], 24)
        qty = _digest_text(item["qty"], 12)
        rows.append([action, symbol, qty])
        value = esc(_digest_text(item["value"], 40))
        status = esc(_digest_text(item["status"], 80))
        reason = esc(_digest_text(item["reason"]))
        details.append(f"<b>{esc(symbol)}</b>: {value} | {status}\n{reason}")
    if orders:
        widths = [max(len(row[i]) for row in rows) for i in range(3)]
        table = "\n".join(
            "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
            for row in rows
        )
        out.extend(["<pre>" + esc(table) + "</pre>", "", "\n\n".join(details)])

    account = _digest_object(data["account"], {"nav", "cash", "positions", "kill_switch"})
    out.extend(["", "<b>Account</b>"])
    for key, label in [("nav", "NAV"), ("cash", "Cash"),
                       ("positions", "Positions"), ("kill_switch", "Kill-switch")]:
        out.append(f"{label}: {esc(_digest_text(account[key]))}")
    for key, heading in [("protection", "Protection"), ("problems", "Problems")]:
        lines = _digest_lines(data[key])
        # Absence is not evidence of safety or absence of problems.
        out.extend(["", f"<b>{heading}</b>"])
        out.extend("- " + esc(line) for line in lines or ["Not reported."])
    if "proposals" in data:
        lines = _digest_lines(data["proposals"])
        if lines:
            out.extend(["", "<b>Proposals</b>"])
            out.extend("- " + esc(line) for line in lines)
    if "next_check" in data:
        out.extend(["", "<b>Next check</b>", esc(_digest_text(data["next_check"]))])
    rendered = "\n".join(out)
    if len(rendered.encode("utf-16-le")) // 2 > MAX_DIGEST:
        raise ValueError("Digest exceeds 3500 characters; shorten prose, retain all risk facts")
    return rendered


def send_digest(digest: dict, chat_id: str) -> None:
    rendered = render_digest(digest)
    # Already escaped: do not reinterpret underscores/asterisks in data as Markdown.
    _send_html(rendered, chat_id, digest_ref(rendered))


def digest_ref(text: str) -> str:
    """Stable content ref: identical digests carry the same ref, so a
    retry-after-timeout duplicate is recognizable at a glance."""
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def send(text: str, chat_id: str) -> None:
    _send_html(to_telegram_html(mask_ids(text)), chat_id, digest_ref(text))


def _send_html(html_text: str, chat_id: str, ref: str) -> None:
    """Shared transport; rendering never changes timeout, recipient or retry behavior."""
    if len(html_text) > MAX_MESSAGE:
        html_text = html_text[:MAX_MESSAGE] + "\n... (truncated)"
    html_text += f"\n<i>ref: {ref}</i>"
    try:
        result = api(
            "sendMessage",
            {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"},
        )["result"]
    except (OSError, ValueError) as error:
        # A read timeout cannot distinguish "delivered, response lost" from
        # "never delivered"; the retry protocol may duplicate. Same ref both copies.
        print(
            f"send UNCONFIRMED ({error}); message may have been delivered - "
            f"a retry duplicates it (ref {ref} unchanged)",
            flush=True,
        )
        raise SystemExit(2)
    print("sent message_id", result["message_id"], "ref", ref)


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


def newest_desk_run() -> dict | None:
    """The newest session any desk card started, with its card and trigger, or None when the cards
    have no runs. A card that could not be read goes to stderr, so 'no session found' is never a lie
    about a run that exists."""
    found = cloud_api.newest_run(DESK_CARD_IDS)
    if not found:
        return None
    if found["failed_cards"]:
        print(f"card runs unread: {', '.join(found['failed_cards'])}", flush=True)
    return found["run"]


def latest_session_id() -> str | None:
    run = newest_desk_run()
    return run["session_id"] if run else None


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
        try:
            rows = cloud_api.thread_rows(session_id)
        except cloud_api.CloudError as error:
            print(f"thread list failed: {error}", flush=True)
            return False
        self.state["threads"] = {
            row["id"]: {"role": row["role"], "name": row["name"], "archived": row["archived"]}
            for row in rows
        }
        return True

    def thread_events(self, thread_id: str) -> list[dict]:
        """Drain new events for one thread; tag them with their thread id."""
        events: list[dict] = []
        cursor = self.state["cursors"].get(thread_id)
        for _ in range(300):
            try:
                page = cloud_api.thread_events(self.state["session_id"], thread_id, cursor)
            except cloud_api.CloudError as error:
                print(f"thread events failed: {error}", flush=True)
                break
            batch = page["events"]
            events.extend(batch)
            cursor = page["last_id"] or cursor
            if not page["has_more"]:
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
        try:
            cloud_api.post_session_event(self.state["session_id"], body)
        except cloud_api.CloudError as error:
            self.say(f"Confirmation failed: {esc(str(error)[:200])}")
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
                "/session latest — bind the newest desk-card session\n"
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
                run = newest_desk_run()
                if not run:
                    self.say("No desk-card session found yet.")
                    return
                target = run["session_id"]
                self.say(f'Latest desk run: card <code>{esc(run["card"])}</code> at '
                         f'{esc(str(run.get("at")))} ({esc(str(run.get("trigger")))}).')
            if not target:
                self.say(f'Current: <code>{esc(self.state["session_id"] or "unbound")}</code>')
                return
            self.bind(target)
        elif command == "/status":
            if not self.state["session_id"]:
                self.say("Not bound. Use /session latest.")
                return
            try:
                session = cloud_api.session_status(self.state["session_id"])
            except cloud_api.CloudError as error:
                self.say(f"Status failed: {esc(str(error)[:200])}")
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
            try:
                cloud_api.post_session_event(self.state["session_id"], {"type": "user.interrupt"})
            except cloud_api.CloudError as error:
                self.say(f"Interrupt failed: {esc(str(error)[:200])}")
                return
            self.say("Interrupt sent.")
        else:
            if not self.state["session_id"]:
                self.say("Not bound. Use /session latest first.")
                return
            body = {"type": "user.message", "content": [{"type": "text", "text": text}]}
            try:
                cloud_api.post_session_event(self.state["session_id"], body)
            except cloud_api.CloudError as error:
                if error.status == 409:
                    # Never retried: a queued second message would read as two operator instructions.
                    self.say("Desk is mid-turn; message NOT sent. Retry when idle (/status).")
                else:
                    self.say(f"Relay failed: {esc(str(error)[:200])}")
                return
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


# ------------------------------------------------------------- proposal approval (wait-for-reply)
#
# The desk card sends an entry proposal here and waits for the operator's answer during the fire. The
# platform never asks about a paper submit (only cancel/modify are always_ask), so this is the only
# place an explicit, numbered, allowlisted yes exists for a new entry. The contract is deliberately
# narrow: `/approve N` is the one approving input; `/deny N`, silence past the deadline, a free-text
# reply, a transport failure and a second getUpdates consumer all leave the proposal unapproved.

PROPOSAL_REQUIRED = {"n", "lane", "action", "symbol", "qty", "entry", "value", "stop", "target",
                     "exit_by", "thesis", "invalidation"}
PROPOSAL_OPTIONAL = {"direction", "horizon", "edge", "bear_case", "risk", "notes"}
MAX_PROPOSALS = 6
WAIT_DEFAULT = 600
WAIT_MAX = 900
WAIT_POLL = 20
WAIT_SKEW = 5
WAIT_COMMANDS = {"/approve", "/deny", "/pending", "/help", "/start"}


def load_proposals(data: object) -> list[dict]:
    """Validate the proposal file: the full package or nothing. A proposal without its exit plan
    (stop, target and exit-by) is rejected before anything reaches the operator, so a preview can
    never show less than what approval would authorize."""
    rows = data.get("proposals") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows or len(rows) > MAX_PROPOSALS:
        raise ValueError(f"proposals must be a list of 1 to {MAX_PROPOSALS} objects")
    out: list[dict] = []
    seen: set[int] = set()
    for row in rows:
        item = _digest_object(row, PROPOSAL_REQUIRED, PROPOSAL_OPTIONAL)
        n = item["n"]
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 999:
            raise ValueError("proposal n must be an integer from 1 to 999")
        if n in seen:
            raise ValueError(f"proposal number {n} is used twice")
        seen.add(n)
        clean: dict = {"n": n}
        for key in sorted(PROPOSAL_REQUIRED - {"n"}):
            clean[key] = _digest_text(item[key], 24 if key == "symbol" else
                                      12 if key in ("action", "qty") else 240)
        for key in sorted(PROPOSAL_OPTIONAL & item.keys()):
            clean[key] = _digest_lines(item[key]) if key == "notes" else _digest_text(item[key])
        out.append(clean)
    return out


def proposal_ref(proposals: list[dict]) -> str:
    """Content ref over the validated proposals: an approval is bound to exactly this text."""
    return digest_ref(json.dumps(proposals, sort_keys=True, ensure_ascii=False))


def _clock_text(epoch: float) -> str:
    moment = datetime.fromtimestamp(epoch, UTC)
    sgt = moment + timedelta(hours=8)
    return f"{moment:%H:%M} UTC / {sgt:%H:%M} SGT"


def render_proposal(proposal: dict, deadline: float | None = None, ref: str | None = None) -> str:
    """One numbered preview per proposal, always with the exit plan. Approval wording is fixed."""
    p = proposal
    n = p["n"]
    out = [
        f"<b>TYCHE PROPOSAL #{n} - APPROVAL REQUIRED</b>",
        f"<b>{esc(p['action'])} {esc(p['qty'])} {esc(p['symbol'])}</b>",
        f"<b>Strategy</b>: {esc(p['lane'])}",
        f"Entry: {esc(p['entry'])} | Value: {esc(p['value'])}",
    ]
    if "direction" in p or "horizon" in p:
        out.append(" | ".join(f"{k.capitalize()}: {esc(p[k])}" for k in ("direction", "horizon") if k in p))
    out += ["", "<b>Exit plan</b>",
            f"- Stop: {esc(p['stop'])}", f"- Target: {esc(p['target'])}", f"- Exit by: {esc(p['exit_by'])}"]
    if "risk" in p:
        out.append(f"- Risk: {esc(p['risk'])}")
    out += ["", f"<b>Thesis</b>: {esc(p['thesis'])}", f"<b>Invalidation</b>: {esc(p['invalidation'])}"]
    for key in ("edge", "bear_case"):
        if key in p:
            out.append(f"<b>{key.replace('_', ' ').capitalize()}</b>: {esc(p[key])}")
    if p.get("notes"):
        out += ["", "<b>Notes</b>"] + ["- " + esc(line) for line in p["notes"]]
    by = f"by {_clock_text(deadline)}" if deadline else "within the window"
    out += ["", (f"Reply <code>/approve {n}</code> or <code>/deny {n} [reason]</code> {by}. "
                 "Ask a question in plain text and the desk answers here. A requested change counts as "
                 "a no: the desk rebuilds, re-audits and sends a fresh preview with a new number. "
                 "No reply by the deadline is a no. Nothing is submitted without your explicit "
                 "/approve.")]
    if ref:
        out.append(f"<i>proposal ref: {ref}</i>")
    rendered = mask_ids("\n".join(out))
    if len(rendered.encode("utf-16-le")) // 2 > MAX_DIGEST:
        raise ValueError(f"Proposal #{n} preview exceeds {MAX_DIGEST} characters; shorten the prose")
    return rendered


def wait_state_path(source: Path) -> Path:
    return source.with_name(source.name + ".wait.json")


def _notify(chat_id: str, text: str) -> None:
    """Best-effort chat feedback; a failed acknowledgement never changes a decision."""
    try:
        api("sendMessage", {"chat_id": chat_id, "text": text[:MAX_MESSAGE], "parse_mode": "HTML"})
    except (OSError, ValueError, SystemExit) as error:
        print(f"telegram send failed: {error}", flush=True)


def _decide(state: dict, n: int, result: str, reason: str | None) -> None:
    state["decisions"][str(n)] = {
        "result": result, "reason": reason,
        "at": datetime.fromtimestamp(_now(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _pending(state: dict, proposals: list[dict]) -> list[int]:
    return [p["n"] for p in proposals if str(p["n"]) not in state["decisions"]]


def handle_wait_message(state: dict, proposals: list[dict], chat_id: str, text: str) -> str | None:
    """Apply one allowlisted message. Returns the free-text reply when the message was neither a
    command nor a decision, so the caller can hand it back to the desk."""
    parts = text.split(maxsplit=2)
    command = parts[0].lower().split("@")[0] if parts else ""
    pending = _pending(state, proposals)
    if command in ("/approve", "/deny"):
        verb = "Approved" if command == "/approve" else "Denied"
        if len(parts) < 2 or not parts[1].isdigit():
            _notify(chat_id, f"Usage: {command} N - the number is required, nothing is {verb.lower()} "
                             f"without it. Pending: {', '.join(map(str, pending)) or 'none'}.")
            return None
        n = int(parts[1])
        if n in pending:
            result = "approved" if command == "/approve" else "denied"
            reason = parts[2] if command == "/deny" and len(parts) > 2 else None
            _decide(state, n, result, reason)
            _notify(chat_id, f"{verb} #{n}" + (f" ({esc(reason)})" if reason else "") + ". "
                    + ("The desk now runs the exact-order audit and reserve before one paper order; "
                       "a submit is not a fill." if result == "approved"
                       else "The desk records your no and submits nothing for it."))
        elif str(n) in state["decisions"]:
            _notify(chat_id, f"Proposal #{n} is already {state['decisions'][str(n)]['result']}; "
                             "a fresh preview carries a new number.")
        else:
            _notify(chat_id, f"No pending proposal #{n}. Pending: "
                             f"{', '.join(map(str, pending)) or 'none'}.")
        return None
    if command in ("/pending", "/help", "/start") or command.startswith("/"):
        _notify(chat_id, f"Pending: {', '.join(map(str, pending)) or 'none'}. Reply /approve N or "
                         "/deny N [reason]; plain text is a question or a change and approves nothing.")
        return None
    state["replies"].append({"text": text, "at": datetime.fromtimestamp(_now(), UTC)
                             .strftime("%Y-%m-%dT%H:%M:%SZ")})
    _notify(chat_id, "Noted. The desk will answer, or rebuild the proposal if you asked for a change. "
                     f"Proposal(s) {', '.join(map(str, pending)) or 'none'} stay unapproved until you "
                     "send /approve N.")
    return text


def wait_result(state: dict, proposals: list[dict], outcome: str) -> dict:
    decisions = state["decisions"]

    def by(kind: str) -> list[int]:
        return sorted(int(n) for n, d in decisions.items() if d["result"] == kind)

    return {
        "outcome": outcome,
        "ref": state["ref"],
        "approved": by("approved"),
        "denied": by("denied"),
        "timed_out": by("timeout"),
        "pending": _pending(state, proposals),
        "reply": state["replies"][-1] if state["replies"] else None,
        "deadline": datetime.fromtimestamp(state["deadline"], UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decisions": decisions,
    }


def wait_for_reply(source: Path, chat_id: str, timeout: int = WAIT_DEFAULT) -> dict:
    """Send the previews (once) and wait for numbered decisions from the allowlisted chat.

    State lives next to the proposal file, keyed by the proposals' content ref, so running the same
    command again resumes the same window without a second preview (the desk does that after
    answering a question), while a rebuilt proposal starts a fresh window with a fresh preview.
    Outcomes: decided (every proposal answered), reply (free text handed back; pending stay
    pending), timeout (undecided proposals recorded as timeout, which the desk treats as a no),
    conflict (another getUpdates consumer; nothing decided, exit 2).
    """
    if not isinstance(timeout, int) or not 30 <= timeout <= WAIT_MAX:
        raise ValueError(f"timeout must be 30..{WAIT_MAX} seconds")
    proposals = load_proposals(json.loads(source.read_text(encoding="utf-8-sig")))
    ref = proposal_ref(proposals)
    state_path = wait_state_path(source)
    state = None
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        if previous.get("ref") == ref:
            state = previous
    if state is None:
        # Forget every update the bot has queued: an old "/approve 1" must never answer this preview.
        stale = api("getUpdates", {"offset": -1, "timeout": 0})["result"]
        offset = max(u["update_id"] for u in stale) + 1 if stale else 0
        sent_at = _now()
        state = {"ref": ref, "offset": offset, "sent_at": sent_at, "deadline": sent_at + timeout,
                 "decisions": {}, "replies": []}
        for proposal in proposals:
            _send_html(render_proposal(proposal, state["deadline"], ref), chat_id, ref)
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    outcome = None
    while outcome is None:
        remaining = state["deadline"] - _now()
        if not _pending(state, proposals):
            outcome = "decided"
            break
        if remaining <= 0:
            for n in _pending(state, proposals):
                _decide(state, n, "timeout", None)
                _notify(chat_id, f"No reply by the deadline: proposal #{n} is treated as denied. "
                                 "Nothing was submitted for it.")
            outcome = "timeout"
            break
        try:
            updates = api("getUpdates", {"offset": state["offset"],
                                         "timeout": max(1, min(WAIT_POLL, int(remaining)))})["result"]
        except SystemExit as error:
            if "conflict" in str(error).lower():
                print("another getUpdates consumer is running (listen?); nothing decided", flush=True)
                outcome = "conflict"
                break
            raise
        except OSError as error:
            print(f"getUpdates failed ({error}); retrying", flush=True)
            continue
        for update in updates:
            state["offset"] = update["update_id"] + 1
            message = update.get("message") or {}
            if str((message.get("chat") or {}).get("id")) != str(chat_id):
                continue
            if message.get("date", 0) < state["sent_at"] - WAIT_SKEW:
                continue
            text = (message.get("text") or "").strip()
            if text and handle_wait_message(state, proposals, chat_id, text) is not None:
                outcome = "reply"
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return wait_result(state, proposals, outcome)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: telegram.py chat-id|send|render-digest|send-digest|"
                         "render-proposal|wait-for-reply|listen")
    command = sys.argv[1]
    if command == "render-proposal":
        if len(sys.argv) != 3:
            raise SystemExit("Usage: telegram.py render-proposal <json-file|->")
        try:
            source = (sys.stdin.read() if sys.argv[2] == "-"
                      else Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
            proposals = load_proposals(json.loads(source))
            ref = proposal_ref(proposals)
            print("\n\n".join(render_proposal(p, None, ref) for p in proposals))
        except (ValueError, TypeError, OSError) as error:
            raise SystemExit(f"Invalid proposals (nothing sent): {error}") from error
        return
    if command == "wait-for-reply":
        args = sys.argv[2:]
        timeout = WAIT_DEFAULT
        if "--timeout" in args:
            timeout = int(args[args.index("--timeout") + 1])
            args = [a for i, a in enumerate(args)
                    if i not in (args.index("--timeout"), args.index("--timeout") + 1)]
        if len(args) != 1:
            raise SystemExit("Usage: telegram.py wait-for-reply <json-file> [--timeout seconds]")
        chat_id = env().get("TELEGRAM_CHAT_ID")
        if not chat_id:
            raise SystemExit("TELEGRAM_CHAT_ID missing from .env; run chat-id first")
        try:
            result = wait_for_reply(Path(args[0]), chat_id, timeout)
        except (ValueError, TypeError, OSError) as error:
            raise SystemExit(f"Invalid proposals (nothing sent, nothing approved): {error}") from error
        print(json.dumps(result, indent=1))
        if result["outcome"] == "conflict":
            raise SystemExit(2)
        return
    if command in {"render-digest", "send-digest"}:
        if len(sys.argv) != 3:
            raise SystemExit(f"Usage: telegram.py {command} <json-file|->")
        try:
            source = (sys.stdin.read() if sys.argv[2] == "-"
                      else Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
            data = json.loads(source)
            rendered = render_digest(data)
        except (ValueError, TypeError, OSError) as error:
            raise SystemExit(f"Invalid digest (nothing sent): {error}") from error
        if command == "render-digest":
            print(rendered)
        else:
            chat_id = env().get("TELEGRAM_CHAT_ID")
            if not chat_id:
                raise SystemExit("TELEGRAM_CHAT_ID missing from .env; run chat-id first")
            _send_html(rendered, chat_id, digest_ref(rendered))
    elif command == "chat-id":
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
        send(sys.argv[2], chat_id)
    elif command == "listen":
        listen()
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()