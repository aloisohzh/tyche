"""Persistent halt / kill-switch flag.

A halted agent blocks buys but still allows de-risking sells. The flag lives beside
the journal and is written only by the CLI (never by hand), and every transition is
journaled so the kill-switch drill is auditable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

HALT_FILE = "halt.json"


def halt_path(journal_dir: Path) -> Path:
    return Path(journal_dir) / HALT_FILE


def read_halt(journal_dir: Path) -> dict | None:
    path = halt_path(journal_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_halted(journal_dir: Path) -> bool:
    state = read_halt(journal_dir)
    return bool(state and state.get("halted"))


def set_halt(journal_dir: Path, halted: bool, reason: str) -> dict:
    path = halt_path(journal_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"halted": halted, "reason": reason, "ts": datetime.now(UTC).isoformat()}
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def repo_halt_path(root: Path) -> Path:
    return Path(root) / "data" / "halt.json"


def read_repo_halt(root: Path) -> dict | None:
    """Shared kill-switch flag committed to git so cloud mounts see it too."""
    path = repo_halt_path(root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def effective_halt(journal_dir: Path, root: Path) -> dict:
    """The operator's most recent kill-switch decision, across both flags.

    The journal flag is desk-local (Drive-persisted); the repo flag rides the git
    mount into every cloud session. The flag with the newest timestamp governs: a
    halt written after the last release blocks buys, and a release written after the
    last halt lets buys through again. Until 2026-11-23 an active flag always won,
    which left no way to release a cloud-journaled halt from the repo (the dashboard's
    Release button and a committed data/halt.json were silently ignored while the
    Drive journal still said halted). Sells pass in every state.
    """
    candidates: list[dict] = []
    local = read_halt(journal_dir)
    if local:
        candidates.append({**local, "source": "journal"})
    repo = read_repo_halt(root)
    if repo:
        candidates.append({**repo, "source": "repo"})
    if not candidates:
        return {"halted": False}
    newest = max(candidates, key=lambda c: c.get("ts") or "")
    return {**newest, "halted": bool(newest.get("halted"))}
