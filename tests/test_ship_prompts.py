"""`ship-prompts`: one paste that makes the agents' own instructions agree with the card briefs.

No network and no credentials: the cloud is a small in-memory fake that versions an agent on every
write the way the platform does. What is proven here is the order of the writes, that each write
carries one field group, that a second run changes nothing, and that a prompt this repo did not
write is never replaced blind.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import deploy_managed_agents as driver

EXECUTOR, DESK = driver.ROLE_AGENTS["executor"], driver.ROLE_AGENTS["coordinator"]
OLD = {"executor": "You are the Executor. Old gates.", "coordinator": "You are the Desk Head. Old gates."}


class FakeCloud:
    def __init__(self, executor_pin=5):
        def agent(agent_id, version, system, multiagent=None):
            return {"id": agent_id, "version": version, "name": agent_id, "archived_at": None, "model": "efficient",
                    "tools": [], "mcp_servers": [], "skills": [], "multiagent": multiagent, "system": system}
        roster = {"agents": [
            {"id": driver.ROLE_AGENTS["researcher"], "type": "agent", "version": 4},
            {"id": driver.ROLE_AGENTS["auditor"], "type": "agent", "version": 3},
            {"id": EXECUTOR, "type": "agent", "version": executor_pin},
            {"model": "advisor-model", "type": "advisor"},
        ]}
        self.agents = {EXECUTOR: agent(EXECUTOR, 5, OLD["executor"]),
                       DESK: agent(DESK, 12, OLD["coordinator"], roster)}
        self.cards = {card: {"id": card, "name": "Tyche card", "status": "active", "description": "d",
                             "environment_id": "env", "vault_ids": ["v"], "metadata": {}, "resources": [],
                             "schedule": {"expression": "5 8 * * 1-5", "timezone": "America/New_York"},
                             "agent": {"id": DESK, "type": "agent", "version": 12},
                             "initial_events": [{"type": "user.message"}],
                             "environment_variables": "TELEGRAM_BOT_TOKEN=x"}
                      for card in driver.CARD_IDS}
        self.writes: list[tuple[str, tuple]] = []
        self.fail: str | None = None

    def req(self, method, path, body=None, timeout=20):
        kind, _, ident = path.strip("/").partition("/")
        store = self.agents if kind == "agents" else self.cards
        if method == "GET":
            return copy.deepcopy(store[ident])
        fields = tuple(sorted(k for k in body if k != "version"))
        if self.fail and self.fail in fields:
            raise driver.cloud_api.CloudError("HTTP 400: refused", status=400)
        self.writes.append((ident, fields))
        if kind == "agents":
            assert body["version"] == store[ident]["version"], "a write must carry the version it just read"
            assert len(fields) == 1, "one field group per write"
            store[ident].update({k: copy.deepcopy(v) for k, v in body.items() if k != "version"})
            store[ident]["version"] += 1
        else:
            store[ident]["agent"] = dict(body["agent"])
        return {"item": copy.deepcopy(store[ident])}


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    fake = FakeCloud()
    monkeypatch.setattr(driver.cloud_api, "req", fake.req)
    monkeypatch.setattr(driver, "BASELINE", tmp_path / "agents-live.json")
    monkeypatch.setattr(driver, "EXPORT_DIR", tmp_path)
    monkeypatch.setattr(driver, "KNOWN_LIVE_PROMPTS", {role: {driver._sha(text)} for role, text in OLD.items()})
    return fake


def _ship(apply=True, force=False):
    driver.cmd_ship_prompts(argparse.Namespace(apply=apply, force=force))


def _file(role: str) -> str:
    return driver._prompt_text(str(driver.LIVE_PROMPTS / f"{driver.EXPORT_STEM[role]}.md"))


def test_one_paste_writes_both_prompts_and_repins_all_the_way_to_both_cards(cloud, capsys):
    _ship()
    assert cloud.agents[EXECUTOR]["system"] == _file("executor") and cloud.agents[EXECUTOR]["version"] == 6
    assert cloud.agents[DESK]["system"] == _file("coordinator")
    # Executor prompt, desk prompt, the roster's executor pin, then each card's desk pin: in that order.
    assert cloud.writes == [(EXECUTOR, ("system",)), (DESK, ("system",)), (DESK, ("multiagent",)),
                            *((card, ("agent",)) for card in driver.CARD_IDS)]
    assert driver._roster_pin(cloud.agents[DESK], "executor") == 6
    assert cloud.agents[DESK]["version"] == 14          # one bump for the prompt, one for the roster
    assert all(card["agent"]["version"] == 14 for card in cloud.cards.values())
    # Nothing but the pin moved on a card, and the advisor row was carried as it was.
    assert all(card["environment_variables"] == "TELEGRAM_BOT_TOKEN=x" for card in cloud.cards.values())
    assert cloud.agents[DESK]["multiagent"]["agents"][-1] == {"model": "advisor-model", "type": "advisor"}
    assert "shipped: both cards run desk v14" in capsys.readouterr().out


def test_a_second_run_writes_no_prompt_and_moves_no_pin(cloud):
    _ship()
    cloud.writes.clear()
    _ship()
    assert [w for w in cloud.writes if w[0] in (EXECUTOR, DESK)] == []
    assert cloud.agents[DESK]["version"] == 14 and cloud.agents[EXECUTOR]["version"] == 6
    assert all(card["agent"]["version"] == 14 for card in cloud.cards.values())


def test_the_dry_run_sends_nothing(cloud, capsys):
    _ship(apply=False)
    assert cloud.writes == []
    out = capsys.readouterr().out
    assert "will be written" in out and "DRY RUN" in out


def test_a_prompt_edited_outside_the_repo_is_never_replaced_blind(cloud):
    cloud.agents[EXECUTOR]["system"] = "You are the Executor. Somebody edited this in the console."
    with pytest.raises(SystemExit, match="edited outside this repo"):
        _ship()
    assert cloud.writes == []
    _ship(force=True)                                   # the operator looked and said replace it
    assert cloud.agents[EXECUTOR]["system"] == _file("executor")


def test_a_roster_that_follows_the_latest_executor_needs_no_repin(cloud):
    cloud.agents[DESK]["multiagent"]["agents"][2]["version"] = "latest"
    _ship()
    assert (DESK, ("multiagent",)) not in cloud.writes
    assert all(card["agent"]["version"] == 13 for card in cloud.cards.values())


def test_a_failed_roster_write_still_moves_the_cards_and_says_so(cloud):
    cloud.fail = "multiagent"
    with pytest.raises(SystemExit, match="NOT complete: roster re-pin"):
        _ship()
    # The desk prompt is live on both cards; only the executor's pin is still the older version.
    assert all(card["agent"]["version"] == 13 for card in cloud.cards.values())
    cloud.fail = None
    _ship()                                             # the same paste again finishes the job
    assert driver._roster_pin(cloud.agents[DESK], "executor") == 6
    assert all(card["agent"]["version"] == 14 for card in cloud.cards.values())


def test_the_prompt_files_are_the_aligned_text_and_not_a_text_already_live():
    for role in driver.SHIP_PROMPT_ROLES:
        text = _file(role)
        assert "CYCLE RUNS (operator ruling 2026-11-25)" in text, role
        assert driver._sha(text) not in driver.KNOWN_LIVE_PROMPTS[role], role
        assert text.startswith("You are the "), role
