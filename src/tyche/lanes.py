"""Operator strategy switches, kept outside the frozen lane files.

A lane's `enabled:` key sits in the bytes its playbook is registered against, so toggling it there would
re-freeze the strategy and add a lineage entry for a change that altered no rule (L-037). This file is the
operator surface instead: the desk writes it, the kernel and Scout read it, and it rides the git mount
into every cloud session exactly like `data/halt.json`.

Precedence is one-way: a switch present here wins, anything absent falls back to the lane config.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_FILE = "strategies.json"
SOURCE_LABEL = "data/strategies.json"
PLAYBOOK_ID = re.compile(r"^PB-\d{3}$")


def state_path(root: Path) -> Path:
    return Path(root) / "data" / STATE_FILE


def _read_raw(path: Path) -> dict[str, Any]:
    """Parse the switch file, raising on anything that would make a switch ambiguous."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path.name} must hold a JSON object")
    entries = payload.get("enabled")
    if not isinstance(entries, dict):
        raise TypeError(f"{path.name} has no 'enabled' object")
    for key, value in entries.items():
        if not isinstance(key, str) or not PLAYBOOK_ID.match(key.strip().upper()):
            raise ValueError(f"{path.name} carries an unknown switch key {key!r}")
        if not isinstance(value, bool):
            raise TypeError(f"{path.name} switch {key!r} must be a boolean")
    return payload


def read_overrides(root: Path) -> tuple[dict[str, bool], str | None]:
    """Return (overrides, problem). A missing file is normal; a broken one is reported and ignored.

    Failing to the lane config rather than to "everything on" keeps a corrupt write from enabling a lane
    nobody approved, and `problem` makes the same corruption visible to the desk instead of silent.
    """
    path = state_path(root)
    if not path.is_file():
        return {}, None
    try:
        payload = _read_raw(path)
    except (TypeError, ValueError, OSError) as exc:
        return {}, f"{SOURCE_LABEL}: {str(exc)[:160]}"
    return {key.strip().upper(): value for key, value in payload["enabled"].items()}, None


def read_state(root: Path) -> dict[str, Any]:
    """The whole switch file, for the desk and `tyche strategies`."""
    path = state_path(root)
    if not path.is_file():
        return {}
    try:
        return _read_raw(path)
    except (TypeError, ValueError, OSError):
        return {}


def effective(
    strategy_id: str, lane_default: bool, root: Path
) -> tuple[bool, str, str | None]:
    """(enabled, source, problem) for one playbook id."""
    overrides, problem = read_overrides(root)
    key = strategy_id.strip().upper()
    if key in overrides:
        return overrides[key], SOURCE_LABEL, problem
    return lane_default, "lane config", problem


def set_enabled(root: Path, strategy_id: str, enabled: bool, actor: str = "operator") -> dict[str, Any]:
    """Flip one switch and return the stored payload. Unknown ids are rejected, not ignored."""
    key = strategy_id.strip().upper()
    if not PLAYBOOK_ID.match(key):
        raise ValueError(f"{strategy_id!r} is not a playbook id (expected PB-<digits>)")
    path = state_path(root)
    payload: dict[str, Any] = {"enabled": {}}
    if path.is_file():
        payload = _read_raw(path)  # never clobber a file we cannot parse
    payload["enabled"][key] = bool(enabled)
    payload["updated_at"] = datetime.now(UTC).isoformat()
    payload["updated_by"] = actor
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload
