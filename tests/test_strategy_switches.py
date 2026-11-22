"""Operator strategy switches: precedence, freeze safety, and the two desk endpoints."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from tyche.config import load_config
from tyche.lanes import read_overrides, read_state, set_enabled
from tyche.pipeline import rules_hash

ROOT = Path(__file__).resolve().parents[1]
LANE_IDS = ("PB-001", "PB-002", "PB-003", "PB-004", "PB-007")


@pytest.fixture
def repo(tmp_path):
    """A mini repo: the real config bytes, but an isolated data/ so nothing lands in the working tree."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "data").mkdir()
    return tmp_path


def _write_switches(repo: Path, enabled: dict[str, bool]) -> None:
    (repo / "data" / "strategies.json").write_text(
        json.dumps({"enabled": enabled, "updated_by": "test", "updated_at": "2026-11-21T00:00:00+00:00"}),
        encoding="utf-8",
    )


def test_lane_config_decides_until_an_override_exists(repo):
    config = load_config(repo)
    assert config.strategy_enabled("PB-003") is False
    assert read_overrides(repo) == ({}, None)


def test_override_wins_in_both_directions(repo):
    _write_switches(repo, {"PB-001": False, "PB-003": True})
    config = load_config(repo)
    assert config.strategy_enabled("PB-001") is False
    assert config.strategy_enabled("PB-003") is True
    enabled, source, problem = config.strategy_switch("PB-001")
    assert (enabled, source, problem) == (False, "data/strategies.json", None)
    assert config.enabled_playbook_ids() == ["PB-002", "PB-003", "PB-004"]


def test_a_toggle_never_moves_a_freeze_hash(repo):
    """The switch file exists so an operator decision is not a rule change (L-037)."""
    before = {pid: rules_hash(ROOT, pid) for pid in LANE_IDS}
    for pid in LANE_IDS:
        set_enabled(repo, pid, not load_config(repo).strategy_enabled(pid))
        assert {other: rules_hash(ROOT, other) for other in LANE_IDS} == before


def test_switch_rows_expose_what_decided_each_lane(repo):
    _write_switches(repo, {"PB-004": False})
    rows = {row["strategy_id"]: row for row in load_config(repo).playbook_switches()}
    assert rows["PB-004"]["source"] == "data/strategies.json"
    assert rows["PB-004"]["operator_override"] is False
    assert rows["PB-004"]["lane_config_enabled"] is True
    assert rows["PB-001"]["operator_override"] is None
    assert all(row["rules_file"].startswith("config/") for row in rows.values())


def test_malformed_switch_file_falls_back_and_says_so(repo):
    (repo / "data" / "strategies.json").write_text("{not json", encoding="utf-8")
    overrides, problem = read_overrides(repo)
    assert overrides == {} and problem and "strategies.json" in problem
    config = load_config(repo)
    assert config.strategy_enabled("PB-001") is True
    assert config.playbook_switches()[0]["switch_file_problem"] == problem


def test_a_non_boolean_switch_is_not_applied(repo):
    """A hand-edited file must not enable a lane the operator never approved."""
    (repo / "data" / "strategies.json").write_text(
        json.dumps({"enabled": {"PB-003": "yes"}}), encoding="utf-8"
    )
    overrides, problem = read_overrides(repo)
    assert overrides == {} and "boolean" in (problem or "")


def test_set_enabled_refuses_to_clobber_an_unreadable_file(repo):
    (repo / "data" / "strategies.json").write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        set_enabled(repo, "PB-001", False)
    assert (repo / "data" / "strategies.json").read_text(encoding="utf-8") == "[]"


@pytest.mark.parametrize("bad_id", ["PB-1", "scalp", "", "PB-0011"])
def test_only_playbook_ids_can_be_switched(repo, bad_id):
    with pytest.raises(ValueError, match="PB-"):
        set_enabled(repo, bad_id, True)


def test_the_switch_file_is_the_shape_the_cloud_reads(repo):
    set_enabled(repo, "PB-002", False, actor="operator (dashboard)")
    state = read_state(repo)
    assert state["enabled"] == {"PB-002": False}
    assert state["updated_by"] == "operator (dashboard)"
    assert "updated_at" in state


# ------------------------------------------------------------------ desk endpoints
@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("desk_server_switches_test", ROOT / "dashboard" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def desk(srv, repo, monkeypatch):
    (repo / "journal").mkdir()
    monkeypatch.setattr(srv, "ROOT", repo)
    monkeypatch.setattr(srv, "JOURNAL", repo / "journal" / "events.jsonl")
    monkeypatch.setattr(srv, "_git_push_paths", lambda message, paths: (False, "git disabled in test"))
    return repo


def test_build_strategies_lists_every_lane_with_its_frozen_hash(srv, desk):
    view = srv.build_strategies()
    assert [row["strategy_id"] for row in view["strategies"]] == list(LANE_IDS)
    assert view["live"] == ["PB-001", "PB-002", "PB-004"]
    assert view["switch_file"]["present"] is False
    assert all(row["rules_hash"] for row in view["strategies"])


def test_toggle_writes_the_shared_file_and_journals_the_transition(srv, desk):
    out = srv.toggle_strategy({"strategy_id": "PB-004", "enabled": False})
    assert out["ok"] and out["pushed"] is False and out["git_error"] == "git disabled in test"
    saved = json.loads((desk / "data" / "strategies.json").read_text(encoding="utf-8"))
    assert saved["enabled"] == {"PB-004": False}
    events = [json.loads(line) for line in
              (desk / "journal" / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events[-1]["type"] == "strategy.disabled"
    assert events[-1]["payload"]["strategy_id"] == "PB-004"
    assert srv.build_strategies()["live"] == ["PB-001", "PB-002"]


def test_toggle_back_on_records_the_other_transition(srv, desk):
    srv.toggle_strategy({"strategy_id": "PB-003", "enabled": True})
    srv.toggle_strategy({"strategy_id": "PB-003", "enabled": True})
    srv.toggle_strategy({"strategy_id": "PB-003", "enabled": False})
    types = [json.loads(line)["type"] for line in
             (desk / "journal" / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert types == ["strategy.enabled", "strategy.enabled", "strategy.disabled"]


@pytest.mark.parametrize("body, error", [
    ({"strategy_id": "PB-999", "enabled": False}, "not a playbook"),
    ({"strategy_id": "PB-001"}, "boolean"),
    ({"enabled": True}, "not a playbook"),
])
def test_toggle_rejects_bodies_it_cannot_act_on(srv, desk, body, error):
    out = srv.toggle_strategy(body)
    assert out["ok"] is False and error in out["error"]
    assert not (desk / "data" / "strategies.json").exists()
    assert not (desk / "journal" / "events.jsonl").exists()


def test_a_switch_never_touches_a_configured_file(srv, desk):
    """Byte-for-byte: the desk must not be able to re-register a strategy by toggling it."""
    before = {p: p.read_bytes() for p in sorted((desk / "config").rglob("*")) if p.is_file()}
    srv.toggle_strategy({"strategy_id": "PB-001", "enabled": False})
    srv.toggle_strategy({"strategy_id": "PB-002", "enabled": False})
    assert {p: p.read_bytes() for p in sorted((desk / "config").rglob("*")) if p.is_file()} == before


def test_a_broken_switch_file_is_visible_instead_of_dead_silent(srv, desk):
    srv.toggle_strategy({"strategy_id": "PB-001", "enabled": False})
    (desk / "data" / "strategies.json").write_text("{oops", encoding="utf-8")
    view = srv.build_strategies()
    assert view["problem"] and "strategies.json" in view["problem"]
    assert view["live"] == ["PB-001", "PB-002", "PB-004"]
    assert srv.toggle_strategy({"strategy_id": "PB-002", "enabled": False})["ok"] is False
