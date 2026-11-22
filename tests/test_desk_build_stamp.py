"""The hosted Function may only be stamped (and so published) from a clean checkout of origin/main."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stamp_desk_build.py"
BUILD_REL = "desk-site/functions/build.ts"


def _load():
    spec = importlib.util.spec_from_file_location("stamp_desk_build", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A clone whose origin/main is known, with the committed blank stamp in place."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-q", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    stamp = work / BUILD_REL
    stamp.parent.mkdir(parents=True)
    stamp.write_text((ROOT / BUILD_REL).read_text(encoding="utf-8"), encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "blank stamp")
    _git(work, "push", "-q", "-u", "origin", "main")
    return work


def test_committed_stamp_is_blank() -> None:
    """A fresh clone must not claim a provenance it does not have."""
    text = (ROOT / BUILD_REL).read_text(encoding="utf-8")
    assert 'sha: "unstamped"' in text
    assert "dirty: null" in text


def test_clean_main_is_stamped_with_its_sha(repo: Path) -> None:
    mod = _load()
    info = mod.write(repo, fetch=False)
    text = (repo / BUILD_REL).read_text(encoding="utf-8")
    assert info["on_main"] and not info["dirty"]
    assert f'sha: "{info["sha"]}"' in text
    assert 'branch: "main"' in text
    assert "dirty: false" in text
    mod.restore(repo)
    assert 'sha: "unstamped"' in (repo / BUILD_REL).read_text(encoding="utf-8")


def test_a_branch_ahead_of_main_is_refused(repo: Path) -> None:
    """The 22 Nov case: commits on a merged branch, deployed while main still had the old handler."""
    mod = _load()
    _git(repo, "checkout", "-q", "-b", "phase1/role-skills")
    (repo / "note.txt").write_text("stranded\n")
    _git(repo, "add", "note.txt")
    _git(repo, "commit", "-q", "-m", "stranded")
    with pytest.raises(mod.Refused, match="not origin/main"):
        mod.write(repo, fetch=False)
    assert 'sha: "unstamped"' in (repo / BUILD_REL).read_text(encoding="utf-8")
    info = mod.write(repo, fetch=False, allow_off_main=True)
    assert not info["on_main"]
    assert 'branch: "phase1/role-skills"' in (repo / BUILD_REL).read_text(encoding="utf-8")


def test_a_dirty_tree_is_refused_even_on_main(repo: Path) -> None:
    mod = _load()
    (repo / "note.txt").write_text("tracked\n")
    _git(repo, "add", "note.txt")
    _git(repo, "commit", "-q", "-m", "tracked")
    _git(repo, "push", "-q", "origin", "main")
    (repo / "note.txt").write_text("edited but not committed\n")
    with pytest.raises(mod.Refused, match="uncommitted changes: note.txt"):
        mod.check(repo, fetch=False)


def test_a_stale_stamp_alone_does_not_count_as_dirty(repo: Path) -> None:
    """The tool's own output must not lock the next publish out."""
    mod = _load()
    mod.write(repo, fetch=False)
    info = mod.check(repo, fetch=False)
    assert not info["dirty"]


def test_handler_reports_the_stamp_on_health() -> None:
    handler = (ROOT / "desk-site" / "functions" / "handler.ts").read_text(encoding="utf-8")
    assert 'import { BUILD } from "./build.ts";' in handler
    assert "build: BUILD," in handler
