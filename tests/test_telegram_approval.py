"""The Telegram proposal-approval step: only an explicit, numbered /approve from the allowlisted chat
approves anything; silence, free text, a second consumer and transport failures leave it unapproved."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import telegram as bridge

ROOT = Path(__file__).resolve().parents[1]
CHAT = "123"


def proposal(n: int = 1, **overrides) -> dict:
    base = {
        "n": n, "lane": "PB-004 scalp", "action": "BUY", "symbol": "US.SPY", "qty": "10",
        "entry": "limit 672.40", "value": "USD 6,724", "stop": "668.90", "target": "677.60",
        "exit_by": "15:15 ET session flatten", "thesis": "Pullback with breadth positive.",
        "invalidation": "Close below 668.90.",
    }
    base.update(overrides)
    return base


def write(tmp_path: Path, *proposals: dict) -> Path:
    path = tmp_path / "proposals.json"
    path.write_text(json.dumps({"proposals": list(proposals)}), encoding="utf-8")
    return path


class FakeTelegram:
    """Stands in for `api`: scripted getUpdates pages, a fake clock that advances by the long-poll
    timeout when a page is empty, and a record of everything sent."""

    def __init__(self, pages: list[list[dict]], start: float = 1_000_000.0, conflict_after=None):
        self.pages = list(pages)
        self.clock = start
        self.sent: list[dict] = []
        self.calls: list[dict] = []
        self.conflict_after = conflict_after

    def now(self) -> float:
        return self.clock

    def __call__(self, method: str, params: dict) -> dict:
        self.calls.append({"method": method, **params})
        if method == "sendMessage":
            self.sent.append(params)
            return {"result": {"message_id": len(self.sent)}}
        assert method == "getUpdates"
        if params.get("offset") == -1:
            return {"result": [{"update_id": 40, "message": {"chat": {"id": int(CHAT)},
                                                             "date": self.clock - 100,
                                                             "text": "/approve 1"}}]}
        if self.conflict_after is not None and len(self.calls) > self.conflict_after:
            raise SystemExit("telegram error: Conflict: terminated by other getUpdates request")
        page = self.pages.pop(0) if self.pages else []
        if not page:
            self.clock += params.get("timeout", 0)
        return {"result": page}

    def message(self, text: str, chat: str = CHAT, update_id: int = 41, age: float = 0.0) -> dict:
        return {"update_id": update_id,
                "message": {"chat": {"id": int(chat)}, "date": self.clock - age, "text": text}}


def run(monkeypatch, fake: FakeTelegram, path: Path, timeout: int = 600) -> dict:
    monkeypatch.setattr(bridge, "api", fake)
    monkeypatch.setattr(bridge, "_now", fake.now)
    return bridge.wait_for_reply(path, CHAT, timeout)


def texts(fake: FakeTelegram) -> str:
    return "\n".join(s["text"] for s in fake.sent)


# ------------------------------------------------------------------------- the proposal package


def test_proposal_without_exit_plan_is_rejected() -> None:
    for missing in ("stop", "target", "exit_by", "thesis", "invalidation"):
        row = proposal()
        del row[missing]
        with pytest.raises(ValueError, match="Missing"):
            bridge.load_proposals({"proposals": [row]})


def test_duplicate_or_bad_numbers_and_oversize_lists_are_rejected() -> None:
    with pytest.raises(ValueError, match="twice"):
        bridge.load_proposals([proposal(1), proposal(1)])
    with pytest.raises(ValueError, match="integer"):
        bridge.load_proposals([proposal(n="1")])
    with pytest.raises(ValueError, match="1 to 6"):
        bridge.load_proposals([proposal(n) for n in range(1, 8)])
    with pytest.raises(ValueError, match="Unexpected"):
        bridge.load_proposals([proposal(submit=True)])


def test_preview_shows_full_package_including_exits_and_masks_ids() -> None:
    rows = bridge.load_proposals([proposal(notes=["account 9000001 paper"])])
    text = bridge.render_proposal(rows[0], 1_000_600.0, bridge.proposal_ref(rows))
    for fact in ("BUY 10 US.SPY", "Strategy</b>: PB-004 scalp", "limit 672.40", "USD 6,724", "Stop: 668.90", "Target: 677.60",
                 "Exit by: 15:15 ET", "Thesis", "Invalidation", "/approve 1", "/deny 1",
                 "No reply by the deadline is a no", "UTC", "SGT"):
        assert fact in text, fact
    assert "9000001" not in text and "...001" in text


def test_example_template_renders_offline(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["telegram.py", "render-proposal",
                                      str(ROOT / "templates/proposal-approval.example.json")])
    monkeypatch.setattr(bridge, "api", lambda *_a, **_k: pytest.fail("render must stay offline"))
    bridge.main()
    out = capsys.readouterr().out
    assert "EXAMPLE ONLY" in out and "Exit plan" in out


def test_ref_changes_with_any_proposal_detail() -> None:
    a = bridge.proposal_ref(bridge.load_proposals([proposal()]))
    b = bridge.proposal_ref(bridge.load_proposals([proposal(stop="668.00")]))
    assert a != b


# ------------------------------------------------------------------------- the wait loop


def test_numbered_approve_from_allowlisted_chat_approves(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([[]], start=1_000_000.0)
    fake.pages = [[fake.message("/approve 1")]]
    result = run(monkeypatch, fake, path)
    assert result["outcome"] == "decided" and result["approved"] == [1]
    assert result["pending"] == [] and result["denied"] == []
    # Stale queue forgotten first: the old "/approve 1" (update 40) never counted, offset moved past it.
    assert fake.calls[0] == {"method": "getUpdates", "offset": -1, "timeout": 0}
    polls = [c for c in fake.calls if c["method"] == "getUpdates" and c["offset"] != -1]
    assert polls[0]["offset"] == 41
    assert "APPROVAL REQUIRED" in fake.sent[0]["text"] and "Stop: 668.90" in fake.sent[0]["text"]
    assert "Approved #1" in texts(fake) and "a submit is not a fill" in texts(fake)
    saved = json.loads(bridge.wait_state_path(path).read_text())
    assert saved["decisions"]["1"]["result"] == "approved" and saved["offset"] == 42


def test_other_chats_and_stale_messages_never_approve(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("/approve 1", chat="999", update_id=41),
                   fake.message("/approve 1", update_id=42, age=60)]]
    result = run(monkeypatch, fake, path, timeout=30)
    assert result["approved"] == [] and result["outcome"] == "timeout"
    assert result["timed_out"] == [1]


def test_free_text_never_approves_and_is_handed_back(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("yes go ahead, approve it")]]
    result = run(monkeypatch, fake, path)
    assert result["outcome"] == "reply" and result["approved"] == []
    assert result["pending"] == [1] and result["reply"]["text"] == "yes go ahead, approve it"
    assert "stay unapproved" in texts(fake)


def test_change_request_is_a_reply_with_proposal_still_pending(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("stop at 667 instead")]]
    result = run(monkeypatch, fake, path)
    assert result["outcome"] == "reply" and result["approved"] == [] and result["pending"] == [1]


def test_deny_with_reason_is_recorded(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal(1), proposal(2))
    fake = FakeTelegram([])
    fake.pages = [[fake.message("/deny 2 too wide", update_id=41)],
                  [fake.message("/approve 1", update_id=42)]]
    result = run(monkeypatch, fake, path)
    assert result["outcome"] == "decided"
    assert result["approved"] == [1] and result["denied"] == [2]
    assert result["decisions"]["2"]["reason"] == "too wide"
    assert len([s for s in fake.sent if "APPROVAL REQUIRED" in s["text"]]) == 2


def test_silence_times_out_as_a_no_and_says_so(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    result = run(monkeypatch, fake, path, timeout=60)
    assert result["outcome"] == "timeout" and result["approved"] == []
    assert result["timed_out"] == [1] and result["pending"] == []
    assert "treated as denied" in texts(fake) and "Nothing was submitted" in texts(fake)
    assert fake.clock >= 1_000_060.0


def test_approve_without_number_or_unknown_number_waits_on(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("/approve", update_id=41)],
                  [fake.message("/approve 7", update_id=42)],
                  [fake.message("/pending", update_id=43)],
                  [fake.message("/approve 1", update_id=44)]]
    result = run(monkeypatch, fake, path)
    assert result["approved"] == [1]
    assert "Usage: /approve N" in texts(fake) and "No pending proposal #7" in texts(fake)


def test_second_run_resumes_same_window_without_resending(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("why this stop?")]]
    first = run(monkeypatch, fake, path)
    assert first["outcome"] == "reply"
    previews = len([s for s in fake.sent if "APPROVAL REQUIRED" in s["text"]])
    fake.pages = [[fake.message("/approve 1", update_id=42)]]
    fake.clock += 120
    second = run(monkeypatch, fake, path)
    assert second["outcome"] == "decided" and second["approved"] == [1]
    assert second["deadline"] == first["deadline"]
    assert len([s for s in fake.sent if "APPROVAL REQUIRED" in s["text"]]) == previews
    assert not any(c.get("offset") == -1 for c in fake.calls[len(fake.calls) - 3:])


def test_rebuilt_proposal_starts_fresh_and_old_approval_does_not_carry(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("/approve 1")]]
    assert run(monkeypatch, fake, path)["approved"] == [1]
    path.write_text(json.dumps({"proposals": [proposal(2, stop="667.00")]}), encoding="utf-8")
    fake.pages = []
    result = run(monkeypatch, fake, path, timeout=30)
    assert result["approved"] == [] and result["timed_out"] == [2]
    assert len([s for s in fake.sent if "APPROVAL REQUIRED" in s["text"]]) == 2


def test_expired_window_on_resume_is_a_timeout(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("question?")]]
    run(monkeypatch, fake, path, timeout=60)
    fake.clock += 3600
    fake.pages = [[fake.message("/approve 1", update_id=42)]]
    result = run(monkeypatch, fake, path, timeout=60)
    assert result["outcome"] == "timeout" and result["approved"] == []


def test_second_consumer_conflict_decides_nothing(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([], conflict_after=2)
    result = run(monkeypatch, fake, path)
    assert result["outcome"] == "conflict" and result["approved"] == [] and result["pending"] == [1]


def test_timeout_bounds_are_enforced(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    with pytest.raises(ValueError, match="timeout"):
        run(monkeypatch, fake, path, timeout=bridge.WAIT_MAX + 1)
    with pytest.raises(ValueError, match="timeout"):
        run(monkeypatch, fake, path, timeout=10)
    assert not fake.sent


def test_invalid_file_sends_nothing(monkeypatch, tmp_path) -> None:
    row = proposal()
    del row["stop"]
    path = write(tmp_path, row)
    fake = FakeTelegram([])
    with pytest.raises(ValueError):
        run(monkeypatch, fake, path)
    assert not fake.calls


def test_cli_prints_json_and_exits_2_on_conflict(monkeypatch, tmp_path, capsys) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([], conflict_after=2)
    monkeypatch.setattr(bridge, "api", fake)
    monkeypatch.setattr(bridge, "_now", fake.now)
    monkeypatch.setattr(bridge, "env", lambda: {"TELEGRAM_CHAT_ID": CHAT, "TELEGRAM_BOT_TOKEN": "t"})
    monkeypatch.setattr(sys, "argv", ["telegram.py", "wait-for-reply", str(path), "--timeout", "120"])
    with pytest.raises(SystemExit) as exc:
        bridge.main()
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):])["outcome"] == "conflict"  # the JSON object comes last


def test_source_never_approves_outside_the_approve_command() -> None:
    """Grep-level guard: a decision is written in exactly two places - the numbered /approve or /deny
    branch and the deadline timeout - and the timeout can only write "timeout"."""
    source = (ROOT / "scripts/telegram.py").read_text(encoding="utf-8")
    writes = [line.strip() for line in source.splitlines()
              if "_decide(" in line and not line.strip().startswith("def ")]
    assert writes == ['_decide(state, n, result, reason)', '_decide(state, n, "timeout", None)']
    assert source.count('result = "approved" if command == "/approve" else "denied"') == 1


# ------------------------------------------------------------------- Ask me: the order block


ORDER = {"symbol": "US.SPY", "side": "buy", "qty": 10, "limit": 672.40, "exit_floor": 665.50}


def test_order_block_is_validated_as_numbers_and_shown_in_the_preview() -> None:
    clean = bridge.load_proposals([proposal(order=ORDER)])[0]["order"]
    assert clean == {**ORDER, "multiplier": 1}
    text = bridge.render_proposal(bridge.load_proposals([proposal(order=ORDER)])[0])
    assert "Your approve authorizes</b>: BUY 10 US.SPY limit &lt;= 672.4, protective sell down to 665.5" in text
    for bad in ({**ORDER, "side": "short"}, {**ORDER, "qty": "10"}, {**ORDER, "qty": 0}, {**ORDER, "limit": 0},
                {**ORDER, "exit_floor": 700.0}, {**ORDER, "side": "sell", "exit_floor": 600.0},
                {**ORDER, "multiplier": 10}, {**ORDER, "account": "123"}, {"symbol": "US.SPY"}):
        with pytest.raises((ValueError, TypeError)):
            bridge.load_proposals([proposal(order=bad)])
    # The ref binds the approve to the order numbers, not only to the prose.
    a = bridge.proposal_ref(bridge.load_proposals([proposal(order=ORDER)]))
    b = bridge.proposal_ref(bridge.load_proposals([proposal(order={**ORDER, "qty": 11})]))
    assert a != b != bridge.proposal_ref(bridge.load_proposals([proposal()]))


def test_approve_writes_the_hand_off_file_and_nothing_else_does(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal(order=ORDER), proposal(2, symbol="US.QQQ", order={**ORDER, "symbol": "US.QQQ"}))
    fake = FakeTelegram([])
    fake.pages = [[fake.message("/approve 1"), fake.message("/deny 2 too wide", update_id=42)]]
    result = run(monkeypatch, fake, path)
    assert result["approved"] == [1] and result["denied"] == [2]
    assert result["approved_orders"] == [{"n": 1, "order": {**ORDER, "multiplier": 1}}]
    handoff = json.loads(bridge.approved_path(path).read_text())
    assert handoff["ref"] == result["ref"]
    assert [row["n"] for row in handoff["approved"]] == [1]
    assert handoff["approved"][0]["order"] == {**ORDER, "multiplier": 1}
    assert handoff["approved"][0]["decided_at"] == result["decisions"]["1"]["at"]
    # Silence, a deny and free text leave no hand-off file behind.
    for answer in ([], [fake.message("/deny 1")], [fake.message("looks rich, hold")]):
        sub = tmp_path / f"case-{len(answer)}-{(answer or [{}])[0].get('update_id', 0)}-{len(str(answer))}"
        sub.mkdir()
        other = write(sub, proposal(order=ORDER))
        quiet = FakeTelegram([])
        quiet.pages = [answer]
        out = run(monkeypatch, quiet, other, timeout=30)
        assert out["approved"] == [] and not bridge.approved_path(other).exists(), out


def test_approved_proposal_without_order_block_is_handed_off_as_such(monkeypatch, tmp_path) -> None:
    path = write(tmp_path, proposal())
    fake = FakeTelegram([])
    fake.pages = [[fake.message("/approve 1")]]
    result = run(monkeypatch, fake, path)
    assert result["approved"] == [1] and result["approved_orders"] == [{"n": 1, "order": None}]
    assert json.loads(bridge.approved_path(path).read_text())["approved"][0]["order"] is None
