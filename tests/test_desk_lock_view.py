"""The hosted desk shows everything while locked; only the buttons that change state are held.

Until 22 Nov the whole admin zone was blurred to 34% opacity with pointer-events off until the
operator passphrase was entered, and the unlock redrew only three of the five control surfaces,
so the "Strategies in play" switches kept showing plain on/off text after an unlock. These tests
pin the replacement: no blur, lock-glyph buttons that route to the unlock card, and one redraw
helper that every lock transition calls.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "dashboard" / "static" / "app.js").read_text(encoding="utf-8")
STYLE = (ROOT / "dashboard" / "static" / "style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")


def test_locked_admin_zone_is_not_blurred_or_click_blocked() -> None:
    locked_rules = [line for line in STYLE.splitlines() if 'data-locked="true"' in line]
    assert not locked_rules, f"locked zone still styled as unreadable: {locked_rules}"
    assert "pointer-events: none" not in "".join(
        line for line in STYLE.splitlines() if ".admin" in line
    )


def test_locked_notice_is_a_banner_above_the_cards_not_an_overlay() -> None:
    assert INDEX.index('id="admin-locked"') < INDEX.index('id="admin-cards"')
    assert "position: absolute" not in next(
        line for line in STYLE.splitlines() if line.startswith(".admin-locked")
    )
    assert 'id="admin-jump"' in INDEX and 'id="admin-locked-text"' in INDEX


def test_every_lock_transition_redraws_all_control_surfaces() -> None:
    helper = re.search(r"function renderControlSurfaces\(\) \{(.*?)\n\}", APP_JS, re.DOTALL)
    assert helper, "renderControlSurfaces() missing"
    for fn in ("renderOperator", "renderApproval", "renderKillControl", "renderStrategies", "renderSchedule"):
        assert f"{fn}()" in helper.group(1), f"{fn} is not redrawn on lock/unlock"
    # the three places the lock state flips: unlock, lock again, passphrase rejected mid-session
    assert APP_JS.count("renderControlSurfaces();") >= 3
    assert "renderOperator(); renderApproval(); renderKillControl();" not in APP_JS, (
        "a partial redraw is back - the strategy switches would show on/off text after an unlock"
    )


def test_strategy_switch_keeps_a_lock_button_while_locked() -> None:
    row = re.search(r"function strategyRow\(row, canControl, view\) \{(.*?)\n\}", APP_JS, re.DOTALL).group(1)
    assert "adminLocked()" in row
    assert 'lockedButton(row.enabled ? "Turn off" : "Turn on")' in row
    # once unlocked the real toggle is wired
    assert 'data-strat="${esc(row.strategy_id)}"' in row
    assert "toggleStrategy(btn.dataset.strat" in APP_JS


def test_locked_buttons_route_to_the_unlock_card() -> None:
    assert "function jumpToUnlock()" in APP_JS
    assert 'data-locked-action' in APP_JS
    assert APP_JS.count('querySelectorAll("[data-locked-action]")') >= 2, "strategy and kill-switch lock buttons"
    assert "jumpToUnlock()" in re.search(r'querySelectorAll\("\.mode-opt"\).*', APP_JS).group(0)
    assert 'adminJump.addEventListener("click", jumpToUnlock)' in APP_JS


@pytest.mark.parametrize("name", ["app.js", "style.css"])
def test_hosted_copy_matches_source(name: str) -> None:
    src = (ROOT / "dashboard" / "static" / name).read_bytes().replace(b"\r\n", b"\n")
    hosted = (ROOT / "desk-site" / "web" / name).read_bytes().replace(b"\r\n", b"\n")
    assert src == hosted


def test_hosted_index_carries_the_same_lock_banner() -> None:
    hosted = (ROOT / "desk-site" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="admin-locked-text"' in hosted
    assert hosted.index('id="admin-locked"') < hosted.index('id="admin-cards"')
