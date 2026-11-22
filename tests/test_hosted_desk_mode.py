"""The hosted desk must be baked in live mode, or the published Function is never called."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTED_INDEX = ROOT / "desk-site" / "web" / "index.html"
LIVE_FLAG = re.compile(r"<script>window\.TYCHE_LIVE=(\{.*?\});</script>")


def test_hosted_index_is_baked_live_not_snapshot() -> None:
    """From 21 Nov (6fbef62) to 22 Nov the hosted index.html carried window.TYCHE_SNAPSHOT, so the
    page read data/automation.json and showed "Static snapshot · Nov 21" while the Function's live
    /automation read sat unused. desk-site/web/ is what Sites publishes: export it with --live."""
    html = HOSTED_INDEX.read_text(encoding="utf-8")
    assert "window.TYCHE_SNAPSHOT" not in html, (
        "desk-site/web/index.html is a baked snapshot; re-run "
        "scripts/export_dashboard.py desk-site/web --live before publishing"
    )
    match = LIVE_FLAG.search(html)
    assert match, "desk-site/web/index.html carries no window.TYCHE_LIVE config"
    cfg = match.group(1)
    for route in ("/functions/v1/app/state", "/functions/v1/app/automation", "/functions/v1/app/schedule"):
        assert route in cfg, f"live config does not point {route} at the Function"
    assert '"automation_fallback": "data/automation.json"' in cfg
