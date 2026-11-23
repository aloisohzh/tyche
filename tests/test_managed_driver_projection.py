"""The before/after guard has to be able to see the field a write changes (L-047).

These are pure projection tests: no network, no credentials. They exist because `attach` reported
"changed fields: (none reported)" on a skill re-pin that had in fact moved, since the compared shape kept
skill ids but dropped the version - an alarm that cannot fire trains you to wave the guard past exactly
like an alarm that fires wrongly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import deploy_managed_agents as driver


def agent(skill_version: str = "1795250715940121", tools: list | None = None) -> dict:
    return {
        "id": "agent_test",
        "version": 10,
        "name": "tyche risk auditor",
        "archived_at": None,
        "model": "qmodel_38max",
        "tools": tools if tools is not None else [{"enabled_tools": ["Read", "Grep"]}],
        "mcp_servers": [],
        "skills": [{"type": "custom", "skill_id": "skill_test", "version": skill_version}],
        "multiagent": None,
        "system": "an audit prompt",
    }


def test_a_skill_repin_moves_the_projection():
    before = driver._view(agent())
    after = driver._view(agent(skill_version="1795256506833674"))
    assert before["skills"] != after["skills"], "a re-pin has to be visible to the guard"
    assert before["skills"] == ["skill_test@1795250715940121"]
    assert [k for k in before if before[k] != after[k]] == ["skills"], "and nothing else may move"


def test_reordering_tool_rows_is_not_reported_as_a_change():
    one = driver._view(agent(tools=[{"enabled_tools": ["Read", "Grep"]}]))
    other = driver._view(agent(tools=[{"enabled_tools": ["Grep", "Read"]}]))
    assert one == other


def test_the_baseline_row_projects_to_itself():
    """A stored row and a live object must land in one shape, or the guard compares two different things."""
    live = driver._view(agent())
    stored = dict(live, id="agent_test", version=10)
    assert driver._view(stored) == live


def test_prompt_files_lose_only_their_export_header(tmp_path):
    """templates/prompts/live/*.md carries an HTML comment header (retrieved-at or PROPOSED) that is
    not part of the system prompt; diff and apply-system must compare and write the body alone, or
    every apply would push the header into the live prompt and every export would stack another."""
    body = "You are the Desk Head.\n\nBOOTSTRAP: <!-- an inline comment that stays --> use the repo.\n"
    with_header = tmp_path / "desk.md"
    with_header.write_text("<!-- PROPOSED 2026-11-23 | agent_x\n     two lines -->\n\n" + body,
                           encoding="utf-8")
    assert driver._prompt_text(str(with_header)) == body
    bare = tmp_path / "bare.md"
    bare.write_text(body, encoding="utf-8")
    assert driver._prompt_text(str(bare)) == body
    for live in (Path(__file__).resolve().parents[1] / "templates" / "prompts" / "live").glob("*.md"):
        text = driver._prompt_text(str(live))
        assert not text.startswith("<!--"), live.name
        assert text.startswith("You are the "), live.name
