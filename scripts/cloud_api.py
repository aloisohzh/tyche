"""Qoder Cloud Agents client for the desk's schedule and Scout controls.

PAT from gitignored .env, server-side only - the browser never sees it. This module is deliberately
narrow: read the cards, pause or resume one, run one now, read run history, start a researcher session
and read sessions. It has no create, edit or delete path for a card, because the card's prompt and cron
are authored by scripts/deploy_two_fire_automation.py (L-019: cadence and prompt must not drift apart).

Every response is reduced to a whitelist before it leaves this module. `environment_variables` comes
back in plaintext from the API and holds the Telegram token and the account allowlist, so it is dropped
here rather than filtered downstream (L-038).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.qoder.com/api/v1/cloud"

# Same ids the card deploy script uses; that script remains the only writer of a card.
RESEARCHER_AGENT = "agent_00vs9v3dg0rnkr4740x3"
ENVIRONMENT_ID = "env_00vtw0llz5kw0jxmu4hl"

SCOUT_KIND = "tyche-scout"
SCOUT_TITLE = "tyche scout"
FINISHED_SESSIONS = {"idle", "completed", "failed", "cancelled", "error", "archived"}
STALE_RUN_AFTER = timedelta(hours=2)
# A session still reports idle after it finishes, so recency has to carry the duplicate guard too:
# anything the desk started this recently is treated as in flight even before its status moves.
SCOUT_FRESH = timedelta(minutes=20)


class CloudError(RuntimeError):
    """A cloud call that failed. Carries the HTTP status when there was one."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _pat() -> str:
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("QODER_PAT="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    # RuntimeError, not SystemExit: the desk serves requests in threads and one bad call must not
    # look like the process deciding to quit.
    raise RuntimeError("QODER_PAT missing from .env")


def req(method: str, path: str, body: dict | None = None, timeout: int = 20) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {_pat()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:200]
        raise CloudError(f"HTTP {error.code}: {detail}", status=error.code) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise CloudError(f"cloud API unreachable: {error}") from error


def _items(payload: dict) -> list[dict]:
    rows = payload.get("data") or payload.get("items") or []
    return [row for row in rows if isinstance(row, dict)]


def card_view(item: dict) -> dict:
    """The card as the desk may show it: schedule and status, never prompt, mounts or secrets."""
    schedule = item.get("schedule") or {}
    metadata = item.get("metadata") or {}
    agent = item.get("agent") or {}
    reason = item.get("paused_reason")
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "status": item.get("status"),
        "paused": item.get("status") == "paused",
        # The platform reports {"type": "manual"}, not prose, so flatten it for the UI.
        "paused_reason": (reason.get("type") if isinstance(reason, dict) else reason),
        "cron": schedule.get("expression"),
        "timezone": schedule.get("timezone"),
        "next_runs": schedule.get("upcoming_runs_at") or [],
        "last_run": schedule.get("last_run_at"),
        "window": metadata.get("window"),
        "agent": {"id": agent.get("id"), "version": agent.get("version")},
        "updated_at": item.get("updated_at"),
    }


def cards() -> list[dict]:
    return [card_view(item) for item in _items(req("GET", "/deployments?limit=50"))]


def _window_covers(window: str | None, day: date) -> bool:
    if not window:
        return False
    match = re.match(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$", window.strip())
    if not match:
        return False
    start, end = (date.fromisoformat(match.group(i)) for i in (1, 2))
    return start <= day <= end


def pick_card(rows: list[dict], day: date) -> dict | None:
    """The card from `rows` whose window covers `day`, or None when no card owns this date.

    No match is reported as such rather than guessed: silently controlling last month's card would be a
    no-op that looks like a pause.
    """
    for card in rows:
        if _window_covers(card.get("window"), day):
            return card
    return None


def current_card(day: date) -> dict | None:
    return pick_card(cards(), day)


def set_paused(card_id: str, paused: bool) -> dict:
    """Pause or resume a card. No reason is sent: the platform reports its own `paused_reason` object
    and discards anything else, so the operator's reason belongs in the journal, not the request."""
    verb = "pause" if paused else "unpause"
    item = req("POST", f"/deployments/{card_id}/{verb}")
    return card_view(item.get("item") or item)


def run_card_now(card_id: str) -> dict:
    item = req("POST", f"/deployments/{card_id}/run")
    return item.get("item") or item


def card_runs(card_id: str, limit: int = 8) -> list[dict]:
    rows = _items(req("GET", f"/deployments/{card_id}/runs?limit={int(limit)}"))
    return [
        {
            "id": row.get("id"),
            "at": row.get("created_at"),
            "trigger": (row.get("trigger_context") or {}).get("type"),
            "scheduled_at": (row.get("trigger_context") or {}).get("scheduled_at"),
            "session_id": row.get("session_id"),
            "error": row.get("error"),
        }
        for row in rows
    ]


def session_view(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "agent": (item.get("agent") or {}).get("id"),
        "kind": (item.get("metadata") or {}).get("kind"),
        "deployment_id": item.get("deployment_id"),
    }


def sessions(limit: int = 12) -> list[dict]:
    """Recent sessions, newest first. Kept small on purpose: each row embeds its agent definition."""
    return [session_view(item) for item in _items(req("GET", f"/sessions?limit={int(limit)}"))]


def _is_scout(row: dict) -> bool:
    """A desk-started Scout session, matched on metadata or - redundantly - on its title prefix.

    The metadata key is the tag; the title is the fallback that survives a platform that files metadata
    somewhere else, and it is what an operator recognises in the Qoder session list anyway.
    """
    return row.get("kind") == SCOUT_KIND or str(row.get("title") or "").startswith(SCOUT_TITLE)


def scout_runs(limit: int = 12) -> list[dict]:
    return [row for row in sessions(limit) if _is_scout(row)]


def _moment(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        started = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return started if started.tzinfo else started.replace(tzinfo=UTC)


def _is_stale(iso: str | None, now: datetime) -> bool:
    started = _moment(iso)
    return bool(started) and now - started > STALE_RUN_AFTER


def scout_activity(now: datetime | None = None) -> dict:
    """What is in flight right now: a run to wait for, a wedged one, or neither.

    Two researchers writing ideas into the same morning is confusion the operator has to untangle, so a
    fresh run blocks a second one. Because the platform leaves a finished session at `idle`, recency counts
    as in flight too - otherwise a double click would start two runs. A session older than
    `STALE_RUN_AFTER` is reported separately rather than locking the button forever.
    """
    now = now or datetime.now(UTC)
    running = stale = None
    for row in scout_runs():
        started = _moment(row.get("created_at"))
        fresh = bool(started) and now - started < SCOUT_FRESH
        if row.get("status") in FINISHED_SESSIONS and not fresh:
            continue
        if _is_stale(row.get("created_at"), now):
            stale = stale or row
        else:
            running = running or row
    return {"running": running, "stale": stale}


def start_scout_run(brief: str) -> dict:
    """Start the researcher alone and hand it the brief. No executor, no envelope, nothing to submit.

    No agent version is pinned: a manual Scout should get the current researcher, and hard-coding a number
    here is how a prompt and a pin drift apart. The scheduled cards keep their own numeric pins.
    """
    session = req(
        "POST",
        "/sessions",
        {
            "agent": {"id": RESEARCHER_AGENT, "type": "agent"},
            "environment_id": ENVIRONMENT_ID,
            "title": f"{SCOUT_TITLE} {date.today():%Y-%m-%d} (from desk)",
            "metadata": {"kind": SCOUT_KIND},
        },
    )
    item = session.get("item") or session
    session_id = item.get("id")
    if not session_id:
        raise CloudError("session created without an id")
    try:
        req(
            "POST",
            f"/sessions/{session_id}/events",
            {"events": [{"type": "user.message", "content": [{"type": "text", "text": brief}]}]},
        )
    except CloudError as exc:
        # The session exists and is waiting with no task; say which one, or the operator has an
        # unexplained idle session in Qoder and no way to find it.
        raise CloudError(f"{exc} - session {session_id} was created without the brief; stop it in Qoder") from exc
    return session_view(item)
