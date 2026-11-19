"""Redact local .env secrets from the gitignored plans/ snapshots.

The snapshots are local inspection/rollback records, not deploy inputs. Redacting
them keeps a shared copy of plans/ from leaking credentials. Run after any deploy
script writes a fresh snapshot.

Usage:
  .venv/Scripts/python.exe scripts/redact_plans.py          # rewrite in place
  .venv/Scripts/python.exe scripts/redact_plans.py --check  # exit 1 if secrets remain
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = (
    "QODER_PAT",
    "TYCHE_ALLOWED_ACCOUNT_IDS",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_WEBHOOK_SECRET",
    "FORWARD_SIGNING_SECRET",
    "FORWARD_WEBHOOK_ENDPOINT_ID",
)
EXTENSIONS = {".json", ".md", ".txt", ".py", ".yaml", ".yml", ".csv"}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() in KEYS and len(value) >= 6:
            values[key.strip()] = value
    return values


def redact(text: str, env: dict[str, str]) -> str:
    for key, value in env.items():
        token = "${" + key + "}"
        if key == "TYCHE_ALLOWED_ACCOUNT_IDS":
            for part in value.split(","):
                part = part.strip()
                if len(part) >= 4:
                    text = re.sub(rf"(?<!\d){re.escape(part)}(?!\d)", token, text)
        else:
            text = text.replace(value, token)
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report without rewriting.")
    args = parser.parse_args()
    env = load_env(ROOT / ".env")
    if not env:
        print("no secrets found in .env")
        return 0
    hits: list[Path] = []
    for path in sorted((ROOT / "plans").rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        cleaned = redact(text, env)
        if cleaned == text:
            continue
        hits.append(path.relative_to(ROOT))
        if not args.check:
            path.write_text(cleaned, encoding="utf-8")
    print(f"{'found' if args.check else 'redacted'}: {len(hits)} file(s)")
    for hit in hits:
        print(" ", hit)
    return 1 if (args.check and hits) else 0


if __name__ == "__main__":
    sys.exit(main())
