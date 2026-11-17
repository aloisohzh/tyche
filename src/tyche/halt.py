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