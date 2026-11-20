"""The desk's cadence and Scout lane: cloud reads, operator switches, and what may never leave the box.

The network is always stubbed here - these tests assert the desk's decisions and its journal, not the
platform's behaviour. The whitelist test is the exception: it runs the real `card_view`/`session_view`
over a payload shaped like the live one, because a secret leaking into a browser is the failure that
matters most and it is the one a stub could hide.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cloud():
    spec = importlib.util.spec_from_file_location("cloud_api_under_test", ROOT / "scripts" / "cloud_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("desk_server_schedule_test", ROOT / "dashboard" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "data").mkdir()
    (tmp_path / "journal").mkdir()
    return tmp_path


@pytest.fixture
def desk(srv, repo, monkeypatch):
    monkeypatch.setattr(srv, "ROOT", repo)
    monkeypatch.setattr(srv, "JOURNAL", repo / "journal" / "events.jsonl")
    monkeypatch.setattr(srv, "_git_push_paths", lambda message, paths: (False, "git disabled in test"))
    srv.SCHEDULE_CACHE.update(at=0.0, payload=None)
    srv.SCOUT_CACHE.update(at=0.0, payload=None)
    return repo


def _card(card_id="dep_nov", window="2026-11-01..2026-11-30", status="active", cron="5 8,12,15 19-20 11 *"):
    return {
        "id": card_id,
        "name": "Tyche desk - premarket and close",
        "status": status,
        "paused": status == "paused",
        "paused_reason": None,
        "cron": cron,
        "timezone": "America/New_York",
        "next_runs": ["2026-11-20T17:05:00Z", "2026-11-23T13:05:00Z"],
        "last_run": "2026-11-20T13:05:00Z",
        "window": window,
        "agent": {"id": "agent_desk", "version": 28},
        "updated_at": "2026-11-20T13:05:00Z",
    }


class FakeCloud:
    """Stands in for scripts/cloud_api.py with the same surface the desk uses."""

    CloudError = Exception
    RESEARCHER_AGENT = "agent_researcher"

    def __init__(self, cards=None, runs=None, activity=None):
        self._cards = cards if cards is not None else [_card()]
        self._runs = runs or [{"id": "drun_1", "at": "2026-11-20T13:05:00Z", "trigger": "schedule",
                               "scheduled_at": "2026-11-20T13:05:00Z", "session_id": "sess_1", "error": None}]
        self._activity = activity or {"running": None, "stale": None}
        self.paused_calls = []
        self.ran = []
        self.started = []

    def cards(self):
        return list(self._cards)

    def pick_card(self, rows, day):
        return next((c for c in rows if c["window"].split("..")[0] <= day.isoformat() <= c["window"].split("..")[1]),
                    None)

    def current_card(self, day):
        return self.pick_card(self._cards, day)

    def card_runs(self, card_id, limit=8):
        return list(self._runs)

    def set_paused(self, card_id, paused):
        self.paused_calls.append((card_id, paused))
        return _card(card_id, status="paused" if paused else "active")

    def run_card_now(self, card_id):
        self.ran.append(card_id)
        return {"id": "drun_manual"}

    def scout_activity(self, now=None):
        return dict(self._activity)

    def scout_runs(self, limit=12):
        return []

    def start_scout_run(self, brief):
        self.started.append(brief)
        return {"id": "sess_scout", "title": "tyche scout", "status": "idle", "kind": "tyche-scout"}


class _FixedNow(datetime):
    """One frozen clock for the cadence tests: 2026-11-20 22:00 ET, inside the November card window.

    Without it these tests would pass until the 30th of November and fail the month after.
    """

    MOMENT = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.MOMENT.astimezone(tz) if tz else cls.MOMENT.replace(tzinfo=None)


@pytest.fixture
def fake(srv, monkeypatch):
    def _install(cards=None, activity=None):
        stub = FakeCloud(cards=cards, activity=activity)
        monkeypatch.setitem(sys.modules, "cloud_api", stub)
        monkeypatch.setattr(srv, "datetime", _FixedNow)
        srv.SCHEDULE_CACHE.update(at=0.0, payload=None)
        srv.SCOUT_CACHE.update(at=0.0, payload=None)
        return stub

    return _install


def _journal(repo):
    lines = (repo / "journal" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ------------------------------------------------------------------ cadence reading
def test_fire_times_reads_the_real_card_cron(srv):
    assert srv.fire_times("5 8,12,15 19-20,23-25,27,30 11 *") == ["08:05", "12:05", "15:05"]
    assert srv.fire_times("5 8 1 1 *") == ["08:05"]


def test_fire_times_says_nothing_it_cannot_parse(srv):
    for cron in (None, "", "5 8 1 1", "*/5 * * * *", "x 8 1 1 *"):
        assert srv.fire_times(cron) == []


def test_build_schedule_shows_only_the_card_that_owns_today(srv, desk, fake):
    fake(cards=[_card("dep_dec", window="2026-12-01..2026-12-31"), _card("dep_nov")])
    view = srv.build_schedule(force=True)
    assert view["ok"] is True
    assert view["card"]["id"] == "dep_nov"
    assert len(view["cards"]) == 2
    assert view["fire_times"] == ["08:05", "12:05", "15:05"]
    assert view["timezone"] == "America/New_York"


def test_next_runs_never_include_a_time_already_past(srv, desk, fake):
    fake()  # frozen at 2026-11-21T03:00Z: the 20th's fires are history
    view = srv.build_schedule(force=True)
    assert view["next_runs"] == ["2026-11-23T13:05:00Z"]


def test_an_unowned_date_is_reported_not_guessed(srv, desk, fake):
    fake(cards=[_card("dep_dec", window="2026-12-01..2026-12-31")])
    view = srv.build_schedule(force=True)
    assert view["ok"] is True and view["card"] is None and view["orphan_date"] is True


def test_an_unreachable_platform_leaves_the_desk_readable(srv, desk, monkeypatch):
    class Boom(FakeCloud):
        def cards(self):
            raise RuntimeError("HTTP 503: cloud on fire")

    monkeypatch.setitem(sys.modules, "cloud_api", Boom())
    srv.SCHEDULE_CACHE.update(at=0.0, payload=None)
    view = srv.build_schedule(force=True)
    assert view["ok"] is False and "503" in view["problem"]
    assert view["card"] is None and view["runs"] == []


def test_the_cadence_is_offered_read_only_with_a_reason(srv, desk, fake):
    fake()
    view = srv.build_schedule(force=True)
    assert view["editable"] is False
    assert "deploy_two_fire_automation.py" in view["edit_note"]


# ------------------------------------------------------------------ cadence switching
def test_an_unknown_action_is_refused(srv, desk, fake):
    stub = fake()
    out = srv.schedule_control({"action": "reboot"})
    assert out["ok"] is False and "pause" in out["error"]
    assert stub.paused_calls == []
    assert not (desk / "journal" / "events.jsonl").exists()


def test_pausing_journals_and_re_reads_the_platform(srv, desk, fake):
    stub = fake()
    out = srv.schedule_control({"action": "pause", "reason": "operator drill"})
    assert out["ok"] is True and out["verified"] is True
    assert stub.paused_calls == [("dep_nov", True)]
    event = _journal(desk)[-1]
    assert event["type"] == "schedule.paused"
    assert event["payload"]["reason"] == "operator drill"
    assert event["payload"]["verified"] is True


class _LyingCloud(FakeCloud):
    def set_paused(self, card_id, paused):
        return _card(card_id, status="active")  # the platform never took the pause


def test_a_pause_the_platform_did_not_apply_is_reported_as_unverified(srv, desk, monkeypatch):
    monkeypatch.setitem(sys.modules, "cloud_api", _LyingCloud())
    srv.SCHEDULE_CACHE.update(at=0.0, payload=None)
    out = srv.schedule_control({"action": "pause"})
    assert out["ok"] is True and out["verified"] is False
    assert _journal(desk)[-1]["payload"]["verified"] is False


def test_firing_now_works_while_paused_and_says_so(srv, desk, fake):
    stub = fake(cards=[_card(status="paused")])
    out = srv.schedule_control({"action": "run_now"})
    assert out["ok"] is True and stub.ran == ["dep_nov"]
    payload = _journal(desk)[-1]["payload"]
    assert payload["was_paused"] is True and payload["run_id"] == "drun_manual"


def test_no_card_owns_the_date_means_nothing_to_control(srv, desk, fake):
    stub = fake(cards=[_card("dep_dec", window="2026-12-01..2026-12-31")])
    out = srv.schedule_control({"action": "pause"})
    assert out["ok"] is False and "owns today" in out["error"]
    assert stub.paused_calls == []
    assert not (desk / "journal" / "events.jsonl").exists()


# ------------------------------------------------------------------ Scout lane
def test_the_brief_names_only_the_lanes_that_are_live(srv, desk, fake):
    fake()
    (desk / "data" / "strategies.json").write_text(
        json.dumps({"enabled": {"PB-001": False, "PB-004": False}}), encoding="utf-8"
    )
    lines = srv.scout_brief()["brief"].splitlines()
    lane_line = next(line for line in lines if line.startswith("Playbooks live for this run:"))
    assert "PB-002" in lane_line
    for off in ("PB-001", "PB-003", "PB-004"):
        assert off not in lane_line
    assert "untrusted data" in srv.scout_brief()["brief"]
    assert "write no files" in srv.scout_brief()["brief"]


def test_the_brief_reads_as_prose_a_model_can_act_on(srv, desk, fake):
    """The frozen clock is 2026-11-20 22:00 ET. The brief opens with that date: an un-called
    `{today.isoformat}` interpolates a bound-method repr (memory address and all) into the prompt."""
    fake()
    brief = srv.scout_brief()["brief"]
    assert "on 2026-11-20" in brief
    assert "built-in method" not in brief and "object at 0x" not in brief
    assert srv.scout_brief()["as_of"] == "2026-11-20"


def test_a_journal_the_desk_cannot_read_degrades_the_brief_not_the_run(srv, desk, fake, monkeypatch):
    """Plan history is colour: the brief says continuity is unknown rather than failing the operator's click."""
    fake()

    def _broken(_path):
        raise OSError("journal unreadable")

    monkeypatch.setattr(srv, "read_events", _broken)
    brief = srv.scout_brief()["brief"]
    assert "treat continuity as unknown" in brief and "journal unreadable" in brief
    assert "Playbooks live for this run:" in brief


def test_the_brief_carries_no_account_identifier(srv, desk, fake):
    """The same guard scripts/export_dashboard.py applies before publishing a feed. Membership of the real
    configured ids is the test, not a digit-shape regex: rules-hash prefixes are hex and legitimately look
    like digit runs. A machine with no .env has no ids configured, so there is nothing to leak."""
    fake()
    if not srv.SENSITIVE:
        pytest.skip("no account ids configured on this machine")
    text = json.dumps(srv.scout_brief())
    assert not [sid for sid in srv.SENSITIVE if sid in text]


def test_scout_needs_an_explicit_confirmation(srv, desk, fake):
    stub = fake()
    out = srv.start_scout({})
    assert out["ok"] is False and "confirm" in out["error"].lower()
    assert stub.started == []


def test_a_second_concurrent_scout_is_refused(srv, desk, fake):
    running = {"id": "sess_busy", "status": "running", "created_at": "2026-11-21T02:00:00Z"}
    stub = fake(activity={"running": running, "stale": None})
    out = srv.start_scout({"confirmed": True})
    assert out["ok"] is False and "already in flight" in out["error"]
    assert stub.started == []


def test_starting_scout_journals_the_research_only_intent(srv, desk, fake):
    stub = fake()
    out = srv.start_scout({"confirmed": True})
    assert out["ok"] is True and out["session"]["id"] == "sess_scout"
    assert len(stub.started) == 1
    payload = _journal(desk)[-1]
    assert payload["type"] == "scout.requested"
    assert payload["payload"]["session_id"] == "sess_scout"
    assert "no sizing" in payload["payload"]["note"]
    assert set(payload["payload"]["live_playbooks"]) == {"PB-001", "PB-002", "PB-004"}


class _DeadCloud(FakeCloud):
    def scout_activity(self, now=None):
        raise RuntimeError("QODER_PAT missing from .env")


def test_a_broken_cloud_leaves_scout_stalled_but_described(srv, desk, monkeypatch):
    monkeypatch.setitem(sys.modules, "cloud_api", _DeadCloud())
    srv.SCOUT_CACHE.update(at=0.0, payload=None)
    view = srv.build_scout(force=True)
    assert view["ok"] is False and "QODER_PAT" in view["problem"]
    assert view["history"] == []


# ------------------------------------------------------------------ what may not leave
def test_card_view_drops_secrets_prompts_and_mounts(cloud):
    raw = {
        "id": "dep_1", "name": "card", "status": "paused",
        "paused_reason": {"type": "manual"},
        "environment_variables": "TELEGRAM_BOT_TOKEN=supersecret\nTYCHE_ALLOWED_ACCOUNT_IDS=1234567",
        "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": "the whole prompt"}]}],
        "resources": [{"type": "github_repository", "url": "https://github.com/x/y", "authorization_token": "ghp_x"}],
        "vault_ids": ["vault_1"],
        "schedule": {"expression": "5 8 * * 1", "timezone": "America/New_York", "upcoming_runs_at": ["2026-12-01T13:05:00Z"]},
        "metadata": {"window": "2026-12-01..2026-12-31", "source": "operator"},
        "agent": {"id": "agent_1", "version": 28, "system": "the prompt again"},
    }
    view = cloud.card_view(raw)
    text = json.dumps(view)
    for forbidden in ("supersecret", "ghp_x", "vault_1", "the whole prompt", "the prompt again", "1234567"):
        assert forbidden not in text
    assert view["paused_reason"] == "manual"
    assert view["cron"] == "5 8 * * 1"
    assert view["window"] == "2026-12-01..2026-12-31"


def test_session_view_drops_the_agent_definition_and_env(cloud):
    raw = {
        "id": "sess_1", "title": "tyche scout 2026-11-21 (from desk)", "status": "idle",
        "created_at": "2026-11-21T02:00:00Z", "updated_at": "2026-11-21T02:04:00Z",
        "environment_variables": {"TELEGRAM_BOT_TOKEN": "supersecret"},
        "resources": [{"type": "memory_store", "memory_store_id": "memstore_1"}],
        "agent": {"id": "agent_1", "version": 16, "system": "a very long prompt"},
        "metadata": {"kind": "tyche-scout", "forward_owner_id": "owner-1"},
        "deployment_id": None, "stats": {"tokens": 999999},
    }
    text = json.dumps(cloud.session_view(raw))
    for forbidden in ("supersecret", "a very long prompt", "memstore_1", "owner-1", "999999"):
        assert forbidden not in text
    assert json.loads(text)["agent"] == "agent_1"


def test_only_the_window_covering_the_day_is_picked(cloud):
    rows = [
        cloud.card_view({"id": "dec", "metadata": {"window": "2026-12-01..2026-12-31"}}),
        cloud.card_view({"id": "nov", "metadata": {"window": "2026-11-19..2026-11-30"}}),
    ]
    assert cloud.pick_card(rows, datetime(2026, 11, 21).date())["id"] == "nov"
    assert cloud.pick_card(rows, datetime(2026, 12, 5).date())["id"] == "dec"
    assert cloud.pick_card(rows, datetime(2027, 1, 4).date()) is None


def test_an_unparseable_window_never_owns_a_day(cloud):
    rows = [cloud.card_view({"id": "odd", "metadata": {"window": "Nov to Dec"}}),
            cloud.card_view({"id": "none", "metadata": {}})]
    assert cloud.pick_card(rows, datetime(2026, 11, 21).date()) is None


def test_a_fresh_session_blocks_a_second_scout_even_while_idle(cloud, monkeypatch):
    """The platform leaves a finished session at idle, so recency has to carry the duplicate guard."""
    now = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
    recent = {"id": "s1", "status": "idle", "created_at": (now - timedelta(minutes=4)).isoformat()}
    old = {"id": "s2", "status": "idle", "created_at": (now - timedelta(hours=5)).isoformat()}
    monkeypatch.setattr(cloud, "scout_runs", lambda limit=12: [recent, old])
    assert cloud.scout_activity(now)["running"]["id"] == "s1"
    monkeypatch.setattr(cloud, "scout_runs", lambda limit=12: [old])
    assert cloud.scout_activity(now) == {"running": None, "stale": None}


def test_a_wedged_session_is_reported_rather_than_blocking_forever(cloud, monkeypatch):
    now = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
    wedged = {"id": "s3", "status": "running", "created_at": (now - timedelta(hours=9)).isoformat()}
    monkeypatch.setattr(cloud, "scout_runs", lambda limit=12: [wedged])
    assert cloud.scout_activity(now) == {"running": None, "stale": wedged}
