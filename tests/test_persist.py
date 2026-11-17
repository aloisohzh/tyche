from __future__ import annotations

from pathlib import Path

from tyche.persist import persist_run, sanitize


def test_sanitize_redacts_ids_and_tokens() -> None:
    text = "account 9000001 ok Bearer abc123.XYZ end"
    out = sanitize(text, ["9000001"])
    assert "9000001" not in out
    assert "abc123.XYZ" not in out
    assert "[REDACTED]" in out


def test_persist_run_raw_intact_sanitized_git(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "plan.json").write_text('{"account_id":"9000001"}', encoding="utf-8")
    (raw / "blob.bin").write_bytes(b"\xff\xfe")
    git = tmp_path / "git"
    bucket = tmp_path / "bucket"

    manifest = persist_run(raw, git, ["9000001"], bucket)

    assert (bucket / "plan.json").read_text(encoding="utf-8") == '{"account_id":"9000001"}'
    assert (bucket / "blob.bin").read_bytes() == b"\xff\xfe"
    assert "9000001" not in (git / "plan.json").read_text(encoding="utf-8")
    assert not (git / "blob.bin").exists()
    assert "plan.json" in manifest["sanitized"]
    assert "blob.bin" in manifest["raw"]


def test_persist_run_without_bucket(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "note.md").write_text("id 9000001", encoding="utf-8")
    git = tmp_path / "git"
    manifest = persist_run(raw, git, ["9000001"], None)
    assert manifest["bucket"] is None
    assert manifest["raw"] == []
    assert "9000001" not in (git / "note.md").read_text(encoding="utf-8")


def test_persist_autodiscovers_ids_across_files(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "snapshot.json").write_text('{"account_id": "9000001"}', encoding="utf-8")
    (raw / "receipt.md").write_text("submitted for 9000001", encoding="utf-8")
    git = tmp_path / "git"
    persist_run(raw, git, [], None)
    assert "9000001" not in (git / "snapshot.json").read_text(encoding="utf-8")
    assert "9000001" not in (git / "receipt.md").read_text(encoding="utf-8")