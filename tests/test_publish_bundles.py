"""The publish step restores the ledger and carries Drive run bundles into git itself.

2026-11-23: three fires wrote their bundles to /data/drive/tyche-raw and nothing copied them to
docs/performance/, so the hosted page kept the 2026-11-18 account snapshot and the feed was built from
0 journal events. The step must not depend on the desk remembering to restore or persist.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tyche.journal import append_event


def _load():
    spec = importlib.util.spec_from_file_location("publish_desk_data", ROOT / "scripts" / "publish_desk_data.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("publish_desk_data", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def publish():
    return _load()


def _journal(path: Path, n: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        append_event(path, "test.event", {"i": i})
    return path


def test_restore_picks_the_longest_verified_drive_chain(publish, tmp_path):
    drive = tmp_path / "drive"
    _journal(drive / "2026-11-18-eod" / "journal" / "events.jsonl", 3)
    _journal(drive / "2026-11-23-close" / "journal" / "events.jsonl", 7)
    broken = _journal(drive / "2026-11-24-bad" / "journal" / "events.jsonl", 9)
    rows = broken.read_text().splitlines()
    tampered = json.loads(rows[4])
    tampered["payload"] = {"i": 44}  # a tampered row: the chain no longer verifies
    rows[4] = json.dumps(tampered)
    broken.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (drive / "lifecycle").mkdir()
    target = tmp_path / "repo" / "journal" / "events.jsonl"
    message = publish.restore_journal(drive, target)
    assert message == "journal: restored 7 verified events from Drive run 2026-11-23-close"
    assert len(target.read_text().splitlines()) == 7
    assert [row[1] for row in publish.ledger_candidates(drive)] == ["2026-11-23-close", "2026-11-18-eod"]


def test_restore_never_overwrites_a_longer_local_chain(publish, tmp_path):
    drive = tmp_path / "drive"
    _journal(drive / "run" / "journal" / "events.jsonl", 2)
    target = _journal(tmp_path / "repo" / "journal" / "events.jsonl", 5)
    before = target.read_text()
    message = publish.restore_journal(drive, target)
    assert "kept the checkout's" in message and target.read_text() == before


def test_restore_without_a_drive_mount_is_a_no_op(publish, tmp_path):
    target = tmp_path / "journal" / "events.jsonl"
    assert "no Drive mount" in publish.restore_journal(tmp_path / "absent", target)
    assert not target.exists()


def test_run_bundle_means_a_snapshot_or_broker_reads(publish, tmp_path):
    run = tmp_path / "2026-11-23-premarket"
    run.mkdir()
    assert not publish.is_run_bundle(run)
    (run / "snapshot.json").write_text("{}")
    assert publish.is_run_bundle(run)
    freeze = tmp_path / "2026-11-23-operator-freeze" / "journal"
    freeze.mkdir(parents=True)
    assert not publish.is_run_bundle(freeze.parent)  # a journal-only ledger copy is not a run
    lifecycle = tmp_path / "lifecycle" / "mcp"
    lifecycle.mkdir(parents=True)
    assert not publish.is_run_bundle(lifecycle.parent)


def test_bundles_are_sanitized_and_only_new_ones_are_staged(publish, tmp_path, monkeypatch):
    monkeypatch.setenv("TYCHE_ALLOWED_ACCOUNT_IDS", "9000001")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(publish, "redact_ids", lambda: ["9000001"])
    monkeypatch.setattr(publish, "guard_values", dict)
    drive = tmp_path / "drive"
    new = drive / "2026-11-23-close"
    new.mkdir(parents=True)
    (new / "snapshot.json").write_text(json.dumps({"nav": 101000.0, "account_id": "9000001", "account_type": 2}))
    (new / "mcp").mkdir()
    (new / "mcp" / "accounts.json").write_text(json.dumps({"data": {"accounts": [{"acc_id": "9000001"}]}}))
    old = drive / "2026-11-18-eod"
    old.mkdir()
    (old / "snapshot.json").write_text(json.dumps({"nav": 100000.0}))
    perf = tmp_path / "docs" / "performance"
    (perf / "2026-11-18-eod").mkdir(parents=True)
    (perf / "2026-11-18-eod" / "snapshot.json").write_text("history, untouched")
    staged = publish.publish_run_bundles(drive, perf)
    assert staged == [perf / "2026-11-23-close"]
    copied = json.loads((perf / "2026-11-23-close" / "snapshot.json").read_text())
    assert copied["nav"] == 101000.0 and copied["account_id"] == "[REDACTED]"
    assert "9000001" not in (perf / "2026-11-23-close" / "mcp" / "accounts.json").read_text()
    assert (perf / "2026-11-18-eod" / "snapshot.json").read_text() == "history, untouched"


def test_a_bundle_that_still_leaks_a_secret_is_withheld(publish, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(publish, "redact_ids", list)
    monkeypatch.setattr(publish, "guard_values", lambda: {"TELEGRAM_BOT_TOKEN": "123456:ABCDEF-secret"})
    drive = tmp_path / "drive"
    run = drive / "2026-11-23-midday"
    run.mkdir(parents=True)
    (run / "snapshot.json").write_text(json.dumps({"nav": 1.0}))
    (run / "log.txt").write_text("sent with 123456:ABCDEF-secret")
    perf = tmp_path / "perf"
    assert publish.publish_run_bundles(drive, perf) == []
    assert not (perf / "2026-11-23-midday").exists()
    out = capsys.readouterr().out
    assert "WITHHELD 2026-11-23-midday" in out and "TELEGRAM_BOT_TOKEN" in out and "secret" not in out.split("carries")[1]


def test_leaks_in_names_keys_and_masked_ids_never_values(publish, tmp_path):
    (tmp_path / "a.json").write_text('{"token": "Bearer zzz", "acc": "77700123"}')
    leaks = publish.leaks_in(tmp_path, {"QODER_PAT": "zzz", "TYCHE_GIT_PAT": "short"}, ["77700123"])
    assert leaks == ["account_id:***123"]  # a value under 6 chars is not matched, ids are masked
    leaks = publish.leaks_in(tmp_path, {"QODER_PAT": "Bearer zzz"}, [])
    assert leaks == ["QODER_PAT"]
