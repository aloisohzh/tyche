from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import telegram as bridge


def make_state() -> dict:
    return {"offset": 0, "session_id": "sess_test", "cursors": {}, "threads": {},
            "pending": {}, "next_n": 1, "decisions": []}


def ask_event(event_id: str = "evt_1", permission: str = "ask") -> dict:
    return {
        "id": event_id,
        "type": "agent.mcp_tool_use",
        "mcp_server_name": "moomoo",
        "name": "sim_trade_input_order",
        "input": {"code": "US.SPY", "qty": 10, "account_id": "9000001"},
        "evaluated_permission": permission,
        "evaluation": {"type": "always_ask"},
        "session_thread_id": "sthr_exec",
    }


def test_ask_event_is_tracked() -> None:
    state = make_state()
    fresh = bridge.update_pending(state, [ask_event()])
    assert len(fresh) == 1
    assert state["pending"]["evt_1"]["n"] == 1
    assert state["next_n"] == 2


def test_allowed_tool_is_not_an_ask() -> None:
    state = make_state()
    assert bridge.update_pending(state, [ask_event(permission="allow")]) == []
    assert not state["pending"]


def test_builtin_tool_ask_is_tracked() -> None:
    state = make_state()
    event = {"id": "evt_b", "type": "agent.tool_use", "name": "Bash",
             "input": {"command": "ls"}, "evaluated_permission": "ask"}
    assert len(bridge.update_pending(state, [event])) == 1


def test_duplicate_event_does_not_double_count() -> None:
    state = make_state()
    bridge.update_pending(state, [ask_event()])
    assert bridge.update_pending(state, [ask_event()]) == []
    assert len(state["pending"]) == 1


def test_confirmation_resolves_pending() -> None:
    state = make_state()
    bridge.update_pending(state, [ask_event()])
    bridge.update_pending(state, [
        {"id": "evt_c", "type": "user.tool_confirmation", "tool_use_id": "evt_1", "result": "allow"},
    ])
    assert not state["pending"]


def test_tool_result_resolves_pending() -> None:
    state = make_state()
    bridge.update_pending(state, [ask_event()])
    bridge.update_pending(state, [
        {"id": "evt_r", "type": "agent.mcp_tool_result", "mcp_tool_use_id": "evt_1"},
    ])
    assert not state["pending"]


def test_numbering_survives_resolution() -> None:
    state = make_state()
    bridge.update_pending(state, [ask_event("evt_1")])
    bridge.update_pending(state, [
        {"id": "evt_c", "type": "user.tool_confirmation", "tool_use_id": "evt_1", "result": "deny"},
        ask_event("evt_2"),
    ])
    assert state["pending"]["evt_2"]["n"] == 2


def test_mask_ids_hides_account_ids_not_nav() -> None:
    assert bridge.mask_ids("account 9000001") == "account ...001"
    assert bridge.mask_ids("NAV 100000 cash 94000") == "NAV 100000 cash 94000"


def test_preview_masks_ids_and_offers_explicit_choice() -> None:
    state = make_state()
    bridge.update_pending(state, [ask_event()])
    preview = bridge.format_preview(state["pending"]["evt_1"])
    assert "/approve 1" in preview
    assert "/deny 1" in preview
    assert "9000001" not in preview
    assert "...001" in preview


def test_find_pending_by_number() -> None:
    state = make_state()
    bridge.update_pending(state, [ask_event()])
    found = bridge.find_pending(state, "1")
    assert found is not None and found[0] == "evt_1"
    assert bridge.find_pending(state, "9") is None
    assert bridge.find_pending(state, "abc") is None


def test_markdown_bold_becomes_html_bold() -> None:
    out = bridge.to_telegram_html("**Pre-market complete.** mood *cautious*")
    assert "<b>Pre-market complete.</b>" in out
    assert "<i>cautious</i>" in out
    assert "**" not in out


def test_markdown_pipe_table_becomes_pre() -> None:
    md = "| Order | Qty |\n| --- | --- |\n| BUY SPY | 28 |\n| BUY EFA | 142 |"
    out = bridge.to_telegram_html(md)
    assert out.startswith("<pre>") and out.endswith("</pre>")
    assert "|" not in out
    assert "BUY SPY" in out and "142" in out


def test_compliant_html_passes_through_unchanged() -> None:
    html_in = "<b>TYCHE</b>\n<pre>BUY SPY 28 &amp; hold\nrow2</pre>\nNAV &lt; 100k &amp; cash"
    assert bridge.to_telegram_html(html_in) == html_in


def test_free_text_specials_escaped_once() -> None:
    out = bridge.to_telegram_html("risk < cap & ok")
    assert "&lt;" in out and "&amp;" in out
    assert "&amp;amp;" not in out and "&amp;lt;" not in out


def test_mixed_html_header_and_markdown_table() -> None:
    md = "<b>Orders</b>\n| A | B |\n| - | - |\n| 1 | 2 |"
    out = bridge.to_telegram_html(md)
    assert "<b>Orders</b>" in out
    assert "<pre>" in out and "|" not in out


def test_digest_ref_stable_and_distinct() -> None:
    assert bridge.digest_ref("TYCHE SKIP") == bridge.digest_ref("TYCHE SKIP")
    assert bridge.digest_ref("TYCHE SKIP") != bridge.digest_ref("TYCHE SKIP 2")
    assert len(bridge.digest_ref("x")) == 8


def test_send_appends_ref_footer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_api(method: str, params: dict) -> dict:
        captured.update(method=method, params=params)
        return {"result": {"message_id": 42}}

    monkeypatch.setattr(bridge, "api", fake_api)
    bridge.send("hello **world**", "123")
    ref = bridge.digest_ref("hello **world**")
    assert captured["method"] == "sendMessage"
    assert captured["params"]["chat_id"] == "123"
    assert captured["params"]["parse_mode"] == "HTML"
    assert captured["params"]["text"].endswith(f"<i>ref: {ref}</i>")
    assert "<b>world</b>" in captured["params"]["text"]


def test_send_masks_account_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    monkeypatch.setattr(
        bridge, "api",
        lambda method, params: captured.update(params=params) or {"result": {"message_id": 1}},
    )
    bridge.send("account 1234567 nav 99914.93", "123")
    assert "1234567" not in captured["params"]["text"]
    assert "...567" in captured["params"]["text"]
    assert "99914.93" in captured["params"]["text"]


def test_send_timeout_exits_unconfirmed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    def timeout_api(method: str, params: dict) -> dict:
        raise OSError("read timed out")

    monkeypatch.setattr(bridge, "api", timeout_api)
    with pytest.raises(SystemExit) as exc:
        bridge.send("digest", "123")
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "UNCONFIRMED" in out
    assert bridge.digest_ref("digest") in out


def test_send_api_error_is_definitive_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def error_api(method: str, params: dict) -> dict:
        raise SystemExit("telegram error: Bad Request")

    monkeypatch.setattr(bridge, "api", error_api)
    with pytest.raises(SystemExit) as exc:
        bridge.send("digest", "123")
    # Definitive API errors propagate untouched (string code -> process exit 1),
    # never converted to the exit-2 unconfirmed path.
    assert exc.value.code == "telegram error: Bad Request"


def test_send_truncates_long_digest_but_keeps_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    monkeypatch.setattr(
        bridge, "api",
        lambda method, params: captured.update(params=params) or {"result": {"message_id": 1}},
    )
    bridge.send("x" * 5000, "123")
    text = captured["params"]["text"]
    assert len(text) <= bridge.MAX_MESSAGE + 40
    assert len(text) < 4096
    assert text.endswith(f"<i>ref: {bridge.digest_ref('x' * 5000)}</i>")