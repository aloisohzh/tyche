from __future__ import annotations

import io
import json
import sys
import xml.etree.ElementTree as ET
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


def sample_digest() -> dict:
    path = Path(__file__).resolve().parents[1] / "templates" / "sentinel-digest.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("urgent", [False, True])
def test_shared_digest_layout(urgent: bool) -> None:
    data = sample_digest()
    data["urgent"] = urgent
    rendered = bridge.render_digest(data)
    root = ET.fromstring("<message>" + rendered + "</message>")
    headings = [node.text for node in root.findall("b")]
    assert ("URGENT RISK ALERT" in headings[0]) is urgent
    assert headings.index("Orders") < headings.index("Account") < headings.index("Protection")
    assert "Problems" in headings
    table = root.find("pre").text
    assert table.splitlines()[0].split() == ["ACTION", "SYMBOL", "QTY"]
    assert table.splitlines()[1].split() == ["HOLD", "US.SPY", "28"]
    assert "Exit approval missing" not in table
    assert data["orders"][0]["reason"] in rendered
    assert "Cash: Not verified\nPositions:" in rendered
    assert "No orders submitted by this run." in rendered
    assert len(rendered) < bridge.MAX_DIGEST


def test_empty_orders_do_not_invent_trading_outcome() -> None:
    data = sample_digest()
    data["orders"] = []
    data["orders_summary"] = "Order history unavailable; submission count not verified."
    rendered = bridge.render_digest(data)
    assert "<pre>" not in rendered
    assert data["orders_summary"] in rendered
    assert "No orders submitted" not in rendered


def test_empty_risk_sections_do_not_claim_safety() -> None:
    data = sample_digest()
    data["protection"] = []
    data["problems"] = []
    rendered = bridge.render_digest(data)
    assert "<b>Protection</b>\n- Not reported." in rendered
    assert "<b>Problems</b>\n- Not reported." in rendered
    assert "None" not in rendered


def test_structured_send_escapes_without_reinterpreting_markdown(monkeypatch) -> None:
    data = sample_digest()
    data["stance"] = "A < B & C; **literal** plan_id_one - account 1234567"
    data["orders"][0]["reason"] = "Literal <b>input</b> is not markup."
    data["problems"] = ["Approval pending\u2014do not submit."]
    captured = {}
    monkeypatch.setattr(
        bridge, "api",
        lambda method, params: captured.update(params=params) or {"result": {"message_id": 1}},
    )
    bridge.send_digest(data, "test-chat")
    text = captured["params"]["text"]
    root = ET.fromstring("<message>" + text + "</message>")
    assert captured["params"]["parse_mode"] == "HTML"
    assert captured["params"]["chat_id"] == "test-chat"
    assert "A &lt; B &amp; C; **literal** plan_id_one" in text
    assert "&lt;b&gt;input&lt;/b&gt;" in text
    assert "1234567" not in text and "...567" in text
    assert "\u2014" not in text and "Approval pending-do not submit." in text
    assert root.findall("i")[-1].text == "ref: " + bridge.digest_ref(bridge.render_digest(data))


@pytest.mark.parametrize("change", [
    lambda d: d.pop("account"),
    lambda d: d.update(unknown_risk="must not silently disappear"),
    lambda d: d.update(urgent="false"),
    lambda d: d.update(orders="none"),
    lambda d: d.update(protection="No protection"),
    lambda d: d.update(phase="CLOSE\nInjected heading"),
    lambda d: d.update(stance=""),
    lambda d: d["orders"][0].update(qty=28),
    lambda d: d["orders"][0].pop("reason"),
    lambda d: d["account"].update(secret="ignored?"),
    lambda d: d.update(problems=["x"] * 13),
])
def test_invalid_digest_never_reaches_api(change, monkeypatch) -> None:
    data = sample_digest()
    change(data)
    monkeypatch.setattr(bridge, "api", lambda *args: pytest.fail("Must not send invalid input"))
    with pytest.raises((ValueError, TypeError)):
        bridge.send_digest(data, "test-chat")


def test_oversize_digest_keeps_risks_intact_and_does_not_send(monkeypatch) -> None:
    data = sample_digest()
    data["problems"] = ["Risk: " + "x" * 230] * 12
    monkeypatch.setattr(bridge, "api", lambda *args: pytest.fail("Must not truncate/send"))
    with pytest.raises(ValueError, match="shorten prose, retain all risk facts"):
        bridge.send_digest(data, "test-chat")


def test_digest_timeout_still_exits_unconfirmed_without_retry(monkeypatch) -> None:
    calls = []

    def timeout_api(*args):
        calls.append(args)
        raise OSError("read timed out")

    monkeypatch.setattr(bridge, "api", timeout_api)
    with pytest.raises(SystemExit) as exc:
        bridge.send_digest(sample_digest(), "test-chat")
    assert exc.value.code == 2
    assert len(calls) == 1


def test_render_digest_cli_is_offline(monkeypatch, capsys) -> None:
    data = sample_digest()
    monkeypatch.setattr(sys, "argv", ["telegram.py", "render-digest", "-"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    monkeypatch.setattr(bridge, "env", lambda: pytest.fail("Offline render must not read secrets"))
    monkeypatch.setattr(bridge, "api", lambda *args: pytest.fail("Offline render must not send"))
    bridge.main()
    assert capsys.readouterr().out.strip() == bridge.render_digest(data)


def test_send_digest_cli_uses_shared_transport(monkeypatch) -> None:
    data = sample_digest()
    captured = {}
    monkeypatch.setattr(sys, "argv", ["telegram.py", "send-digest", "-"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    monkeypatch.setattr(bridge, "env", lambda: {"TELEGRAM_CHAT_ID": "test-chat"})
    monkeypatch.setattr(
        bridge, "api",
        lambda method, params: captured.update(params=params) or {"result": {"message_id": 1}},
    )
    bridge.main()
    assert captured["params"]["text"].startswith(bridge.render_digest(data))
    assert captured["params"]["text"].endswith("</i>")


def test_render_cli_reports_invalid_json_without_env_access(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["telegram.py", "render-digest", "-"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    monkeypatch.setattr(bridge, "env", lambda: pytest.fail("Must validate before reading secrets"))
    with pytest.raises(SystemExit, match="Invalid digest .nothing sent."):
        bridge.main()
