from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def _digest(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def last_hash(path: Path) -> str:
    events = read_events(path)
    return events[-1]["hash"] if events else GENESIS_HASH


@contextmanager
def journal_lock(path: Path):
    """Cross-process lock on ONE shared journal; never a distributed Drive lock.

    Nonblocking: overlapping jobs must skip rather than evaluate stale budgets.
    Cloud rollouts must use one state owner, not parallel sandbox journal copies.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("journal busy; skip overlapping run") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("journal busy; skip overlapping run") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_locked(path: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append while the caller holds journal_lock (for atomic check-and-reserve)."""
    ok, _, error = verify_chain(path)
    if not ok:
        raise ValueError(f"journal invalid: {error}")
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(), "type": event_type,
        "payload": payload, "prev_hash": last_hash(path),
    }
    record["hash"] = _digest(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def append_event(path: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    with journal_lock(path):
        return append_locked(path, event_type, payload)


def verify_chain(path: Path) -> tuple[bool, int, str | None]:
    try:
        events = read_events(path)
        previous = GENESIS_HASH
        for index, record in enumerate(events):
            if record.get("prev_hash") != previous:
                return False, len(events), f"event {index}: prev_hash mismatch"
            if record.get("hash") != _digest(record):
                return False, len(events), f"event {index}: hash mismatch"
            previous = record["hash"]
        return True, len(events), None
    except (ValueError, KeyError, TypeError) as exc:
        return False, 0, f"unreadable journal: {exc}"
