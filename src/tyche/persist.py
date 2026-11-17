"""Persistence sink: raw artifacts to a bucket, sanitized artifacts to git.

The sandbox is ephemeral. Raw journal/plans/payloads go to an OSS bucket mount;
id-free, token-free copies go to git. ``sanitize`` is the hard gate: nothing reaches
git until full account ids and bearer tokens are stripped.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

REDACTED = "[REDACTED]"
_TOKEN_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
_ID_PATTERN = re.compile(r'"(?:account_id|acc_id)"\s*:\s*"([^"]+)"')


def sanitize(text: str, account_ids: list[str]) -> str:
    ids = set(account_ids) | set(_ID_PATTERN.findall(text))
    for account_id in ids:
        if account_id:
            text = text.replace(account_id, REDACTED)
    return _TOKEN_PATTERN.sub(rf"\1{REDACTED}", text)


def persist_run(
    raw_dir: Path,
    git_dir: Path,
    account_ids: list[str],
    bucket_dir: Path | None = None,
) -> dict:
    raw_dir = Path(raw_dir)
    git_dir = Path(git_dir)
    git_dir.mkdir(parents=True, exist_ok=True)
    if bucket_dir is not None:
        bucket_dir = Path(bucket_dir)
        bucket_dir.mkdir(parents=True, exist_ok=True)

    files = [path for path in sorted(raw_dir.rglob("*")) if path.is_file()]
    texts: dict[Path, str] = {}
    for path in files:
        try:
            texts[path] = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue

    discovered: set[str] = set()
    for text in texts.values():
        discovered.update(_ID_PATTERN.findall(text))
    redact_ids = list(set(account_ids) | discovered)

    raw_copied: list[str] = []
    sanitized_copied: list[str] = []
    for path in files:
        rel = path.relative_to(raw_dir)
        if bucket_dir is not None:
            dest = bucket_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            raw_copied.append(str(rel))
        if path not in texts:
            continue
        dest = git_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(sanitize(texts[path], redact_ids), encoding="utf-8")
        sanitized_copied.append(str(rel))

    return {
        "raw": raw_copied,
        "sanitized": sanitized_copied,
        "bucket": str(bucket_dir) if bucket_dir is not None else None,
    }