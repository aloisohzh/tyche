"""The `rules.refrozen` producer: freeze provenance as a journal row, not git archaeology (L-035).

The interesting property here is refusal. A writer that journals whatever hash the bytes currently
produce would happily record a rules change nobody reviewed - which is the exact failure L-030 caught,
where a hand-written hash laundered two sizing changes. So most of these tests check that the command
declines to write, and that a check run leaves the chain byte-identical.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner

from tyche.cli import app
from tyche.freeze import FROZEN, REFROZEN, lane_states, recorded_freezes, registration_events
from tyche.journal import append_event, journal_lock, read_events, verify_chain
from tyche.pipeline import rules_hash

PB = "PB-001"
DOC = "playbook/PB-001-etf-rotation-ballast.md"


def repo(tmp_path: Path, *, declared: str | None = None, stop: float = 0.08) -> Path:
    """A minimal checkout-shaped root: one lane's rules file, the universe, and an optional doc."""
    (tmp_path / "config" / "strategies").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "strategies" / "pb-001.yaml").write_text(
        f"id: PB-001\ninitial_stop_pct: {stop}\n", encoding="utf-8")
    (tmp_path / "config" / "universe.yaml").write_text(
        "symbols: [US.SPY, US.QQQ]\n", encoding="utf-8")
    if declared is not None:
        (tmp_path / "playbook").mkdir(parents=True, exist_ok=True)
        (tmp_path / DOC).write_text(
            "# PB-001\n\n- **Rules hash:** `" + declared + "` (computed by the kernel)\n",
            encoding="utf-8")
    return tmp_path


def run(*args) -> tuple[int, str]:
    result = CliRunner().invoke(app, list(args))
    # rich wraps to the console width, and CI's 80 columns is not this machine's, so a sentence can be
    # broken across a line here and whole there. Assert on the words, not on the wrapping (L-044).
    return result.exit_code, " ".join(result.output.split())


def tick(tmp_path: Path, *, record: bool = False, reason: str = "re-registered") -> tuple[int, str]:
    journal = tmp_path / "journal" / "events.jsonl"
    args = ["rules-freeze", "--config-root", str(tmp_path), "--journal", str(journal)]
    if record:
        args += ["--record", "--reason", reason]
    return run(*args)


def states(tmp_path: Path, journal: Path):
    return lane_states(tmp_path, read_events(journal))[0]


def rows(journal: Path) -> list[dict]:
    return [event for event in read_events(journal) if event["type"] in (FROZEN, REFROZEN)]


# ---------------------------------------------------------------- the check


def test_an_unregistered_lane_is_reported_rather_than_silently_frozen(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    lane, notes = states(tmp_path, journal)[0], lane_states(tmp_path, [])[1]
    assert lane.strategy_id == PB and lane.recorded is None and lane.needs_record
    assert lane.event_type == FROZEN and lane.blocked is None
    assert any("no playbook declares" in note for note in notes)
    assert not journal.exists()


def test_check_exits_one_on_drift_and_leaves_the_chain_untouched(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    append_event(journal, "plan.created", {"note": "unrelated row"})
    before = journal.read_bytes()
    code, out = tick(tmp_path)
    assert code == 1 and "need registering" in out
    assert journal.read_bytes() == before and verify_chain(journal)[0]


def test_a_chain_that_does_not_verify_is_never_certified_as_registered(tmp_path):
    """Calling a lane registered is a claim about provenance, and an edited chain proves no such thing."""
    repo(tmp_path)
    assert tick(tmp_path, record=True)[0] == 0
    journal = tmp_path / "journal" / "events.jsonl"
    lines = journal.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"reason":"re-registered"', '"reason":"edited after the fact"')
    tampered = ("\n".join(lines) + "\n").encode("utf-8")
    journal.write_bytes(tampered)
    assert journal.read_bytes() == tampered and verify_chain(journal)[0] is False
    code, out = tick(tmp_path)
    assert code == 2 and "does not verify" in out
    assert journal.read_bytes() == tampered, "a check run must not append, even to a broken chain"


def test_a_lane_the_chain_already_holds_reports_registered_and_exits_zero(tmp_path):
    repo(tmp_path)
    assert tick(tmp_path, record=True)[0] == 0
    code, out = tick(tmp_path)
    assert code == 0 and "every lane's current rules hash is on the chain" in out
    assert len(rows(tmp_path / "journal" / "events.jsonl")) == 1


# ---------------------------------------------------------------- recording


def test_recording_writes_the_hash_the_bytes_actually_carry(tmp_path):
    repo(tmp_path)
    code, _ = tick(tmp_path, record=True, reason="first provenance row")
    journal = tmp_path / "journal" / "events.jsonl"
    assert code == 0
    event = rows(journal)[0]
    payload = event["payload"]
    assert event["type"] == FROZEN
    assert payload["strategy"] == PB
    assert payload["new_hash"] == rules_hash(tmp_path, PB)
    assert payload["old_hash"] is None and payload["previous_from"] == "none"
    assert payload["reason"] == "first provenance row"
    assert payload["rules_source"] == "config/strategies/pb-001.yaml"
    assert set(payload["source_hashes"]) == {"config/strategies/pb-001.yaml", "config/universe.yaml"}
    assert payload["recorded_by"] == "tyche rules-freeze"
    assert verify_chain(journal)[0]


def test_changed_bytes_re_freeze_carrying_the_hash_the_journal_last_held(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    tick(tmp_path, record=True)
    first = rows(journal)[0]["payload"]["new_hash"]
    repo(tmp_path, stop=0.12)
    code, _ = tick(tmp_path, record=True, reason="stop widened 8% -> 12%")
    event = rows(journal)[-1]
    assert code == 0 and event["type"] == REFROZEN
    assert event["payload"]["old_hash"] == first
    assert event["payload"]["new_hash"] == rules_hash(tmp_path, PB) != first
    assert event["payload"]["previous_event_hash"] == rows(journal)[0]["hash"]


def test_old_hash_never_comes_from_anywhere_but_the_chain(tmp_path):
    """A doc full of freeze history must not lend the journal a lineage it does not have."""
    journal = tmp_path / "journal" / "events.jsonl"
    computed = rules_hash(repo(tmp_path), PB)
    repo(tmp_path, declared=computed)
    (tmp_path / DOC).write_text(
        (tmp_path / DOC).read_text(encoding="utf-8")
        + "- **Freeze history:**\n  - `aabbccddeeff` - frozen some time ago, per git.\n",
        encoding="utf-8")
    assert tick(tmp_path, record=True)[0] == 0
    payload = rows(journal)[0]["payload"]
    assert payload["old_hash"] is None and payload["previous_from"] == "none"
    assert payload["declared"] == computed


def test_recording_refuses_a_reason_that_is_blank_or_whitespace(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    for blank in ("", "   "):
        code, out = tick(tmp_path, record=True, reason=blank)
        assert code == 2 and "--reason" in out
    assert not journal.exists()


# ---------------------------------------------------------------- the refusals


def test_a_lane_whose_doc_disagrees_with_the_bytes_is_refused_and_writes_nothing(tmp_path):
    """L-030, made unrepeatable: the doc edit is the review, so never journal around it."""
    repo(tmp_path, declared="deadbeefcafe")
    journal = tmp_path / "journal" / "events.jsonl"
    code, out = tick(tmp_path, record=True)
    assert code == 2 and "REFUSED" in out and "deadbeefcafe" in out
    assert rows(journal) == [] and read_events(journal) == []
    assert tick(tmp_path)[0] == 2  # and a check run says so too, rather than exiting 1


def test_the_check_passes_once_the_doc_is_brought_round_to_match(tmp_path):
    computed = rules_hash(repo(tmp_path, declared="deadbeefcafe"), PB)
    repo(tmp_path, declared=computed)
    code, _ = tick(tmp_path, record=True)
    assert code == 0
    assert rows(tmp_path / "journal" / "events.jsonl")[0]["payload"]["declared"] == computed


def test_a_universe_edit_is_recorded_as_the_same_lane_change_with_both_sources_named(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    tick(tmp_path, record=True)
    before = rows(journal)[0]["payload"]["source_hashes"]
    (tmp_path / "config" / "universe.yaml").write_text("symbols: [US.SPY]\n", encoding="utf-8")
    assert tick(tmp_path, record=True)[0] == 0
    payload = rows(journal)[-1]["payload"]
    assert payload["source_hashes"]["config/universe.yaml"] != before["config/universe.yaml"]
    assert payload["source_hashes"]["config/strategies/pb-001.yaml"] == \
        before["config/strategies/pb-001.yaml"]


def test_a_broken_chain_blocks_the_record_before_anything_is_appended(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    append_event(journal, "plan.created", {"note": "row one"})
    journal.write_text(
        journal.read_text(encoding="utf-8").replace('"note":"row one"', '"note":"row one edited"'),
        encoding="utf-8")
    code, out = tick(tmp_path, record=True)
    assert code == 2 and "journal invalid" in out
    assert rows(journal) == []


def test_a_contended_journal_skips_rather_than_writing_out_of_order(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    append_event(journal, "plan.created", {"note": "someone else holds the lock"})
    with journal_lock(journal):
        code, out = tick(tmp_path, record=True)
    assert code == 2 and "not written" in out
    assert rows(journal) == [] and verify_chain(journal)[0]


# ---------------------------------------------------------------- the reading side


def test_a_replay_of_the_chain_sees_exactly_the_latest_recorded_hash(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    tick(tmp_path, record=True)
    repo(tmp_path, stop=0.12)
    tick(tmp_path, record=True)
    recorded = recorded_freezes(read_events(journal))
    assert recorded[PB]["new_hash"] == rules_hash(tmp_path, PB)
    assert states(tmp_path, journal)[0].needs_record is False


def test_a_malformed_freeze_row_is_ignored_rather_than_guessing_a_lane(tmp_path):
    events = [{"type": REFROZEN, "payload": {"new_hash": "abc"}},
              {"type": REFROZEN, "payload": {"strategy": PB}}]
    assert recorded_freezes(events) == {}


def test_json_mode_shows_the_would_be_rows_without_writing_them(tmp_path):
    repo(tmp_path)
    journal = tmp_path / "journal" / "events.jsonl"
    code, out = run("rules-freeze", "--config-root", str(tmp_path), "--journal", str(journal),
                    "--json")
    report = json.loads(out)
    assert code == 1 and report["status"] == "pending"
    assert [row["type"] for row in report["would_record"]] == [FROZEN]
    assert not journal.exists()


def test_no_lane_at_all_is_a_no_go_not_an_empty_all_clear(tmp_path):
    (tmp_path / "config").mkdir(parents=True)
    code, out = tick(tmp_path)
    assert code == 2 and "not the same as" in out


def test_registration_events_keys_off_the_journal_rather_off_the_doc(tmp_path):
    repo(tmp_path)
    current = states(tmp_path, tmp_path / "journal" / "events.jsonl")[0]
    registered = replace(current, recorded=current.computed, recorded_event_hash="e" * 64)
    assert registration_events([registered], "already on the chain") == []
    assert registration_events([replace(current, recorded=None)], "first row")[0][0] == FROZEN
    assert registration_events([replace(current, recorded="aaaaaaaaaaaa")], "moved")[0][0] == REFROZEN
