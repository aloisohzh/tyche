from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def last_hash(path: Path) -> str:
    events = read_events(path)
    return events[-1]["hash"] if events else GENESIS_HASH


def append_event(path: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "type": event_type,
        "payload": payload,
        "prev_hash": last_hash(path),
    }
    record["hash"] = _digest(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(record) + "\n")
    return record


def verify_chain(path: Path) -> tuple[bool, int, str | None]:
    events = read_events(path)
    previous = GENESIS_HASH
    for index, record in enumerate(events):
        if record.get("prev_hash") != previous:
            return False, len(events), f"event {index}: prev_hash mismatch"
        if record.get("hash") != _digest(record):
            return False, len(events), f"event {index}: hash mismatch"
        previous = record["hash"]
    return True, len(events), None
