"""Fetch the scoped YouTube research inbox (ADR 0015 perimeter, scout lane).

Scope: @moomoomalaysia "US Options Trading" and "Macro Insights" playlists only.
Playlist RSS needs no API key; transcripts come from youtube-transcript-api and
stay in the private raw dir (copyright: never republished verbatim). Git gets
the metadata index only; scout summaries are written by the cloud perimeter.
Transcripts are hypothesis fuel, never kernel inputs.
"""
from __future__ import annotations

import argparse
import json
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
    args = parser.parse_args()

    raw_dir = args.out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    known = {entry["video_id"] for entry in index}

    added = failed = 0
    for name, playlist_id in PLAYLISTS.items():
        added_here = 0
        for entry in playlist_entries(playlist_id):
            if entry["video_id"] in known:
                continue
            if added_here >= args.limit:
                break
            record = {**entry, "playlist": name, "fetched_at": datetime.now(UTC).isoformat()}
            try:
                language, text = fetch_transcript(entry["video_id"])
            except Exception as error:  # noqa: BLE001 - one bad video must not stop the inbox
                record.update(status="no_transcript", detail=type(error).__name__)
                failed += 1
            else:
                (raw_dir / f"{entry['video_id']}.txt").write_text(
                    f"# {entry['title']}\n# {entry['url']}\n# language: {language}\n\n{text}\n",
                    encoding="utf-8",
                )
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