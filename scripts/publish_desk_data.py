"""Sync cloud runs, refresh the hosted live desk's data feed, and push it to origin.

The live Sites Function (desk-site/functions) reads desk-site/web/data/{state,automation}.json
from the public repo. This script first fast-forward pulls origin/main so the cloud desk's
sanitized run bundles (docs/performance/<run>/) are current, then rebuilds the two feed files
through the secret-guarded export (--data-only, so the live HTML/CSS/JS are never touched),
then commits and pushes ONLY the data files. The state builder is challenge-account-first:
the newest challenge cloud snapshot leads; the local drill snapshot is only a fallback.

No credentials are handled here: git uses the ambient mount/remote credential; the export's
secret guard refuses to write if any PAT / Telegram / signing secret / full account id leaks.

Run: .venv/Scripts/python.exe scripts/publish_desk_data.py [--offline]
  --offline  skip the pull (rebuild + push from the local checkout only)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "desk-site" / "web" / "data"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)


def main() -> None:
    if "--offline" not in sys.argv:
        pull = git("pull", "--ff-only", "origin", "main", check=False)
        if pull.returncode != 0:
            print("CLOUD SYNC FAILED — pull --ff-only rejected (diverged history or dirty overlap):\n" + (pull.stderr or pull.stdout))
            raise SystemExit(1)
        print("cloud sync: origin/main fast-forwarded")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_dashboard.py"), "--data-only"],
        cwd=ROOT,
        check=True,
    )
    feed = (json.loads((DATA / "state.json").read_text(encoding="utf-8")).get("feed") or {})
    print(f"primary: {feed.get('primary_account')} | source: {feed.get('source')} | run: {feed.get('run')} | cloud runs: {feed.get('cloud_runs')}")
    git("add", str(DATA / "state.json"), str(DATA / "automation.json"))
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("desk data unchanged — nothing to push")
        return
    git("commit", "-m", "Refresh hosted desk data feed (sanitized, secret-guarded)", "--", str(DATA / "state.json"), str(DATA / "automation.json"))
    push = git("push", "origin", "main", check=False)
    if push.returncode != 0:
        print("PUSH FAILED — data committed locally but not synced:\n" + (push.stderr or push.stdout))
        raise SystemExit(1)
    print("pushed refreshed desk data feed to origin/main")


if __name__ == "__main__":
    main()