"""Fetch the scoped YouTube research inbox (ADR 0015 perimeter, scout lane).

Scope: @moomoomalaysia "US Options Trading" and "Macro Insights" playlists, plus the links the
operator drops into research/youtube/inbox.txt (one URL or video id per line, # comments allowed)
or passes with --video. Playlist RSS needs no API key; transcripts come from youtube-transcript-api
and stay in the private raw dir (copyright: never republished verbatim). --raw-dir mirrors them to a
second private location (the Drive locker the cloud researcher can read). Git gets the metadata
index only; summaries are written by hand under docs/research/youtube/. Transcripts are hypothesis
fuel, never kernel inputs. Runs on the desk machine: YouTube blocks caption requests from most
cloud addresses, so do not schedule this inside a cloud fire.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYLISTS = {
    "us-options": "PLBRoeWovEAxM",
    "macro": "PLUGItBtS96vlxs4RAZ5JRwt07Sj3N19ZM",
}
ATOM = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
LANGUAGES = ["en", "en-US", "ms", "zh-Hans", "zh-Hant"]
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
INBOX_NAME = "inbox.txt"


def video_id_from(text: str) -> str | None:
    """A bare 11-char id, or the id inside a watch/shorts/live/embed/youtu.be URL; None otherwise."""
    value = text.strip()
    if not value or value.startswith("#"):
        return None
    if VIDEO_ID.match(value):
        return value
    if not re.match(r"^(?:https?://)?(?:[a-z0-9-]+\.)*(?:youtube\.com|youtu\.be)/", value, re.IGNORECASE):
        return None
    match = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})(?:[?&#/]|$)", value)
    return match.group(1) if match else None


def inbox_entries(lines: list[str]) -> list[dict]:
    """Operator-provided links as index-shaped records, deduplicated in order; junk lines are skipped."""
    seen: set[str] = set()
    out = []
    for line in lines:
        video_id = video_id_from(line)
        if video_id and video_id not in seen:
            seen.add(video_id)
            out.append({"video_id": video_id, "title": "", "published": "",
                        "url": f"https://www.youtube.com/watch?v={video_id}"})
    return out


def playlist_entries(playlist_id: str) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
    with urllib.request.urlopen(url, timeout=30) as response:
        root = ET.fromstring(response.read())
    entries = []
    for entry in root.findall("a:entry", ATOM):
        video_id = entry.findtext("yt:videoId", default="", namespaces=ATOM)
        if not video_id:
            continue
        entries.append(
            {
                "video_id": video_id,
                "title": entry.findtext("a:title", default="", namespaces=ATOM),
                "published": entry.findtext("a:published", default="", namespaces=ATOM),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    return entries


def fetch_transcript(video_id: str) -> tuple[str, str]:
    from youtube_transcript_api import YouTubeTranscriptApi

    fetched = YouTubeTranscriptApi().fetch(video_id, languages=LANGUAGES)
    return fetched.language_code, "\n".join(snippet.text for snippet in fetched)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5, help="max new videos per playlist per run")
    parser.add_argument("--out", type=Path, default=ROOT / "research" / "youtube")
    parser.add_argument("--video", action="append", default=[], metavar="URL_OR_ID",
                        help="one operator-provided video (repeatable); same as a line in inbox.txt")
    parser.add_argument("--raw-dir", type=Path, default=None,
                        help="also copy each new transcript here (private Drive locker); never git")
    parser.add_argument("--playlists", dest="playlists", action=argparse.BooleanOptionalAction,
                        default=True, help="--no-playlists fetches only the provided links")
    args = parser.parse_args()

    raw_dir = args.out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if args.raw_dir:
        args.raw_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    known = {entry["video_id"] for entry in index}

    inbox_path = args.out / INBOX_NAME
    inbox_lines = inbox_path.read_text(encoding="utf-8").splitlines() if inbox_path.exists() else []
    sources: list[tuple[str, list[dict], int | None]] = [
        ("inbox", inbox_entries(inbox_lines + args.video), None),
    ]
    if args.playlists:
        sources += [(name, playlist_entries(pid), args.limit) for name, pid in PLAYLISTS.items()]

    added = failed = 0
    for name, entries, limit in sources:
        added_here = 0
        for entry in entries:
            if entry["video_id"] in known:
                continue
            if limit is not None and added_here >= limit:
                break
            record = {**entry, "playlist": name, "fetched_at": datetime.now(UTC).isoformat()}
            try:
                language, text = fetch_transcript(entry["video_id"])
            except Exception as error:  # noqa: BLE001 - one bad video must not stop the inbox
                record.update(status="no_transcript", detail=type(error).__name__)
                failed += 1
            else:
                raw_path = raw_dir / f"{entry['video_id']}.txt"
                raw_path.write_text(
                    f"# {entry['title']}\n# {entry['url']}\n# language: {language}\n\n{text}\n",
                    encoding="utf-8",
                )
                if args.raw_dir:
                    shutil.copyfile(raw_path, args.raw_dir / raw_path.name)
                record.update(status="transcript", transcript_language=language)
                added += 1
                added_here += 1
                time.sleep(1.0)
            index.append(record)
            known.add(entry["video_id"])

    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"inbox: {added} transcripts, {failed} without, {len(index)} indexed total -> {index_path}")


if __name__ == "__main__":
    main()