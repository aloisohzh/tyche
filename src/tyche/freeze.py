"""Freeze provenance: the journal row that says a lane's rules changed (ADR 0014, L-035).

`rules_hash` (`pipeline.py:39`) gives every lane a 12-hex identity, and
`test_declared_playbook_rules_hash_matches_the_kernel` makes the playbook document and the bytes agree.
That proves the *present*. It proves nothing about the *transition*: PB-001's rules moved through six hashes in
three days (2026-11-18 to 2026-11-20) and the chain holds exactly one row about it - the hand-written
`569eb2c341e0`, which named bytes it never matched. That is how a freeze hash silently launders a rules change
(L-030), and the lineage in the playbook had to be excavated from git blobs after the fact.

This module is the producer that gap needed. It is deliberately small and boring:

- it reads config bytes and the journal, and it compares them. It decides nothing about trading;
- it never writes without being told to, and it refuses to record a lane whose playbook document
  disagrees with the kernel - the doc edit is the review, and journaling around it is the failure mode;
- `old_hash` is only ever what the chain last recorded for that lane, or null. A git-archaeology hash
  cannot enter this payload unless an operator types it, and then it is labelled as their claim.

The chain vocabulary is two types, keyed by lane in the same `strategy` field the one existing
`rules.refrozen` row uses: `rules.frozen` for the first row the chain holds about a lane, and
`rules.refrozen` for each change after it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tyche.config import PLAYBOOK_LANES, rules_path_for
from tyche.pipeline import rules_hash

FROZEN = "rules.frozen"
REFROZEN = "rules.refrozen"
FREEZE_TYPES = (FROZEN, REFROZEN)

RULES_HASH_LINE = re.compile(r"\*\*Rules hash:\*\*\s*`([0-9a-f]{12})`")
PLAYBOOK_ID = re.compile(r"^(PB-\d{3})-")
UNIVERSE_REL = "config/universe.yaml"
RECORDED_BY = "tyche rules-freeze"


@dataclass(frozen=True)
class LaneState:
    """One lane's identity right now: what the bytes say, what the doc claims, what the chain knows."""

    strategy_id: str
    computed: str
    rules_source: str
    universe_source: str
    source_hashes: tuple[tuple[str, str], ...]
    declared: str | None = None
    declared_in: str | None = None
    recorded: str | None = None
    recorded_ts: str | None = None
    recorded_event_hash: str | None = None
    blocked: str | None = None

    @property
    def needs_record(self) -> bool:
        """True when the chain does not currently hold this lane's hash."""
        return self.blocked is None and self.recorded != self.computed

    @property
    def event_type(self) -> str:
        return REFROZEN if self.recorded else FROZEN

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id, "computed": self.computed,
            "declared": self.declared, "declared_in": self.declared_in,
            "recorded": self.recorded, "recorded_ts": self.recorded_ts,
            "needs_record": self.needs_record, "blocked": self.blocked,
            "would_record": self.event_type if self.needs_record else None,
            "rules_source": self.rules_source, "source_hashes": dict(self.source_hashes),
        }


def playbook_declared_hashes(root: Path) -> dict[str, tuple[str, str]]:
    """strategy_id -> (declared hash, playbook file relative to root) for every doc that declares one.

    The playbook body is the single place a human declares a freeze; `playbook/INDEX.yaml` claims to
    hold none, and this is the parser the CI assertion should read from too, so the two never drift.
    """
    found: dict[str, tuple[str, str]] = {}
    for path in sorted((root / "playbook").glob("PB-*.md")):
        matched = PLAYBOOK_ID.match(path.name)
        if matched is None or not path.is_file():
            continue
        declared = RULES_HASH_LINE.search(path.read_text(encoding="utf-8"))
        if declared:
            found[matched.group(1)] = (declared.group(1), f"playbook/{path.name}")
    return found


def lane_ids(root: Path) -> tuple[list[str], list[str]]:
    """Lane ids whose rules can be hashed today, and the reasons anything is missing."""
    ids = set(PLAYBOOK_LANES)
    for path in sorted((root / "config" / "strategies").glob("*.yaml")):
        named = re.fullmatch(r"pb-(\d{3})", path.stem)
        if named:
            ids.add(f"PB-{named.group(1)}")
    frozen, notes = [], []
    for strategy_id in sorted(ids):
        try:
            source = rules_path_for(root, strategy_id)
        except ValueError:
            notes.append(f"{strategy_id}: no rules file to hash (planned playbook with no lane mapped)")
            continue
        if not source.is_file():
            notes.append(f"{strategy_id}: {source} is the freeze source but does not exist")
            continue
        frozen.append(strategy_id)
    return frozen, notes


def recorded_freezes(events: list[dict]) -> dict[str, dict[str, Any]]:
    """The newest freeze record the chain holds per lane, read in order so later rows win."""
    recorded: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") not in FREEZE_TYPES:
            continue
        payload = event.get("payload") or {}
        strategy_id = payload.get("strategy") or payload.get("strategy_id")
        new_hash = payload.get("new_hash")
        if not isinstance(strategy_id, str) or not isinstance(new_hash, str):
            continue
        recorded[strategy_id] = {
            "new_hash": new_hash, "ts": event.get("ts"), "hash": event.get("hash"),
        }
    return recorded


def _sha256(path: Path) -> str:
    """Hash the bytes the freeze covers, with checkout newline conversion normalised away."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def lane_states(root: Path, events: list[dict]) -> tuple[list[LaneState], list[str]]:
    """Compare bytes, documents and chain for every freezable lane. Pure: no writes, no clock."""
    declared = playbook_declared_hashes(root)
    recorded = recorded_freezes(events)
    ids, notes = lane_ids(root)
    states: list[LaneState] = []
    for strategy_id in ids:
        source = rules_path_for(root, strategy_id)
        universe = root / UNIVERSE_REL
        if not universe.is_file():
            notes.append(f"{strategy_id}: {UNIVERSE_REL} is a freeze input but does not exist")
            continue
        computed = rules_hash(root, strategy_id)
        claim, declared_in = declared.get(strategy_id, (None, None))
        if claim is None:
            notes.append(f"{strategy_id}: no playbook declares this lane's hash, so the row records "
                         f"bytes with no document to review them against")
        lane = recorded.get(strategy_id) or {}
        blocked = None
        if claim is not None and claim != computed:
            blocked = (f"{strategy_id}: {declared_in} declares {claim} but the kernel computes "
                       f"{computed}. Re-register the rules in the playbook first - this tool will not "
                       f"journal a freeze over a document that disagrees (L-030).")
        states.append(LaneState(
            strategy_id=strategy_id, computed=computed,
            rules_source=str(source.relative_to(root)).replace("\\", "/"),
            universe_source=UNIVERSE_REL,
            source_hashes=((str(source.relative_to(root)).replace("\\", "/"), _sha256(source)),
                           (UNIVERSE_REL, _sha256(universe))),
            declared=claim, declared_in=declared_in,
            recorded=lane.get("new_hash"), recorded_ts=lane.get("ts"),
            recorded_event_hash=lane.get("hash"), blocked=blocked,
        ))
    return states, notes


def registration_events(states: list[LaneState], reason: str) -> list[tuple[str, dict[str, Any]]]:
    """The events a `--record` run would append, in lane order.

    `old_hash` is what the chain last said, never a hash inferred from history: a null here means "the
    chain has no earlier row for this lane", which is a fact about the journal rather than a claim about
    the strategy's past.
    """
    events: list[tuple[str, dict[str, Any]]] = []
    for state in states:
        if not state.needs_record:
            continue
        events.append((state.event_type, {
            "strategy": state.strategy_id,
            "old_hash": state.recorded,
            "new_hash": state.computed,
            "reason": reason,
            "rules_source": state.rules_source,
            "universe_source": state.universe_source,
            "source_hashes": dict(state.source_hashes),
            "declared": state.declared,
            "declared_in": state.declared_in,
            "previous_from": "journal" if state.recorded else "none",
            "previous_event_hash": state.recorded_event_hash,
            "recorded_by": RECORDED_BY,
        }))
    return events


def verdict(states: list[LaneState]) -> Literal["registered", "pending", "blocked"]:
    """What a runner reports: everything recorded, work pending, or a lane refused."""
    if any(state.blocked for state in states):
        return "blocked"
    if any(state.needs_record for state in states):
        return "pending"
    return "registered"


__all__ = [
    "FREEZE_TYPES",
    "FROZEN",
    "RECORDED_BY",
    "REFROZEN",
    "UNIVERSE_REL",
    "LaneState",
    "lane_ids",
    "lane_states",
    "playbook_declared_hashes",
    "recorded_freezes",
    "registration_events",
    "verdict",
]
