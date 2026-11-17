from __future__ import annotations

import json
from pathlib import Path

from tyche.journal import append_event, last_hash, verify_chain


def test_chain_verifies(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_event(path, "plan.created", {"nav": 100_000})
    append_event(path, "order.submitted", {"order_id": "PAPER-0001"})

    ok, count, error = verify_chain(path)
    assert ok, error
    assert count == 2
    assert len(last_hash(path)) == 64


def test_tampering_breaks_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_event(path, "plan.created", {"nav": 100_000})
    append_event(path, "order.submitted", {"order_id": "PAPER-0001"})

    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["payload"]["order_id"] = "PAPER-9999"
    lines[1] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, count, error = verify_chain(path)
    assert not ok
    assert count == 2
    assert "hash mismatch" in (error or "")


def test_missing_journal_is_valid(tmp_path: Path) -> None:
    ok, count, error = verify_chain(tmp_path / "absent.jsonl")
    assert ok
    assert count == 0
    assert error is None
