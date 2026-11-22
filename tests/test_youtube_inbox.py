"""The operator link inbox for scripts/fetch_youtube_insights.py (ADR 0015 scout perimeter)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_youtube_insights",
                                              ROOT / "scripts" / "fetch_youtube_insights.py")
yt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = yt
spec.loader.exec_module(yt)


def test_video_id_from_accepts_the_shapes_people_paste():
    for text in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "  dQw4w9WgXcQ  ",
    ):
        assert yt.video_id_from(text) == "dQw4w9WgXcQ", text


def test_video_id_from_rejects_comments_blanks_and_other_sites():
    for text in ("", "   ", "# a note", "https://example.com/watch?v=dQw4w9WgXcQ",
                 "https://www.youtube.com/@moomoomalaysia", "not a link"):
        assert yt.video_id_from(text) is None, text


def test_inbox_entries_dedupe_in_order_and_shape_like_the_index():
    rows = yt.inbox_entries([
        "# links from the operator",
        "https://youtu.be/dQw4w9WgXcQ",
        "",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "dQw4w9WgXcQ",
    ])
    assert [r["video_id"] for r in rows] == ["dQw4w9WgXcQ", "9bZkp7q19f0"]
    assert rows[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert set(rows[0]) == {"video_id", "title", "published", "url"}
