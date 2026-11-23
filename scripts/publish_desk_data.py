"""Sync cloud runs, refresh the hosted live desk's data feed, and push it to origin.

The live Sites Function (desk-site/functions) reads desk-site/web/data/{state,automation,schedule}.json
from the public repo. This script first fast-forward pulls origin/main so the cloud desk's
sanitized run bundles (docs/performance/<run>/) are current, then rebuilds the feed files
through the secret-guarded export (--data-only, so the live HTML/CSS/JS are never touched),
then regenerates the day's fee-net performance pack (`tyche performance report`, docs/performance/
<date>-metrics.md, from the restored ledger journal and whatever price CSVs the run left behind),
then commits and pushes ONLY the data files plus that pack. A pack that cannot be built is reported
and skipped; it never blocks the feed. The state builder is challenge-account-first:
the newest challenge cloud snapshot leads; the local drill snapshot is only a fallback.

Where it runs (23 Nov 2026): as the last step of every desk card run, from the desk's cloud
environment, so the hosted page is never older than the last run. It still works by hand from a laptop.

Credentials: git uses the ambient remote credential, unless TYCHE_GITHUB_PAT (or TYCHE_GIT_PAT) is set in the environment
(a fine-grained GitHub token for this one repo, Contents: read and write). That token is handed to git
through GIT_ASKPASS, so it never appears on a command line, in a remote URL or in this script's output.
The export's secret guard refuses to write if any PAT / Telegram / signing secret / full account id leaks.

Run: python scripts/publish_desk_data.py [--offline]
  --offline  skip the pull (rebuild + push from the local checkout only)
"""
from __future__ import annotations

import glob
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "desk-site" / "web" / "data"
# Every file the hosted Function reads. A feed file the exporter rebuilds but this script never stages is
# a route that serves the last publish forever - hence the tuple rather than a hand-maintained list.
FEED = ("state.json", "automation.json", "schedule.json")

# Price CSVs the performance pack may read for SPY closes, in the order the researcher leaves them:
# the run's own fetch, the Drive run bundles (present on the desk card only), the sanitized bundles
# in git, and the operator's hand-fetched closes. A pattern that matches nothing is simply skipped.
PRICE_PATTERNS = (
    "data/prices.csv",
    "/data/drive/tyche-raw/*/data/prices.csv",
    "docs/performance/*/data/prices.csv",
    "docs/performance/spy-closes.csv",
)
# Either name works: TYCHE_GITHUB_PAT is the name Alois already uses for the Sites Function's repo token.
TOKEN_ENVS = ("TYCHE_GITHUB_PAT", "TYCHE_GIT_PAT")


def token_env() -> str | None:
    return next((k for k in TOKEN_ENVS if os.environ.get(k, "").strip()), None)
# A commit needs an author; the desk's cloud environment has none configured. Only used when git has no identity.
BOT_IDENTITY = ("tyche-desk", "tyche-desk@users.noreply.github.com")

_ASKPASS: Path | None = None


def _askpass() -> dict[str, str]:
    """GIT_ASKPASS wiring for TYCHE_GIT_PAT: git asks the helper for the username and password, and the
    helper reads the token from the environment, so nothing secret is ever an argument or printed."""
    global _ASKPASS
    key = token_env()
    if not key:
        return {}
    if _ASKPASS is None:
        fd, name = tempfile.mkstemp(prefix="tyche-askpass-", suffix=".py")
        os.close(fd)
        _ASKPASS = Path(name)
        _ASKPASS.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "prompt = ' '.join(sys.argv[1:]).lower()\n"
            f"print('x-access-token' if 'username' in prompt else os.environ.get({key!r}, ''))\n",
            encoding="utf-8",
        )
        _ASKPASS.chmod(_ASKPASS.stat().st_mode | stat.S_IXUSR)
    return {"GIT_ASKPASS": str(_ASKPASS), "GIT_TERMINAL_PROMPT": "0"}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, **_askpass())
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True, env=env)


def identity_args() -> list[str]:
    """`-c user.name/email` for the commit when the checkout has no identity (the cloud desk's mount)."""
    if git("config", "user.email", check=False).returncode == 0:
        return []
    return ["-c", f"user.name={BOT_IDENTITY[0]}", "-c", f"user.email={BOT_IDENTITY[1]}"]


def https_remote() -> str:
    """The push target. With a token, an SSH remote is turned into its HTTPS twin so the token applies;
    otherwise the configured remote is used as is."""
    url = git("remote", "get-url", "origin").stdout.strip()
    if token_env() and url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    return url


def performance_args(root: Path, today: str) -> tuple[list[str], Path] | None:
    """The `tyche performance report` call for today, or None when there is no journal to read.

    Everything is a file under `root` (or the Drive mount); nothing is fetched. The output path is
    dated in ET so one file per trading day accumulates under docs/performance/.
    """
    journal = root / "journal" / "events.jsonl"
    if not journal.is_file():
        return None
    out = root / "docs" / "performance" / f"{today}-metrics.md"
    args = ["performance", "report", "--journal", str(journal),
            "--feed", str(root / "desk-site" / "web" / "data" / "state.json"), "--out", str(out)]
    for pattern in PRICE_PATTERNS:
        base = pattern if pattern.startswith("/") else str(root / pattern)
        if glob.glob(base):
            args += ["--prices", base]
    return args, out


def performance_pack() -> Path | None:
    """Regenerate today's pack; print and skip on any failure so the feed still publishes."""
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    plan = performance_args(ROOT, today)
    if plan is None:
        print("performance pack: no journal/events.jsonl here - skipped")
        return None
    args, out = plan
    run = subprocess.run([sys.executable, "-c", "from tyche.cli import main; main()", *args],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    if run.returncode != 0 or not out.is_file():
        print("PERFORMANCE PACK FAILED (feed still published):\n" + (run.stderr or run.stdout).strip()[-800:])
        return None
    print(f"performance pack: wrote {out.relative_to(ROOT)}")
    return out


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
    paths = [str(DATA / name) for name in FEED]
    pack = performance_pack()
    if pack is not None:
        paths.append(str(pack))
    git("add", *paths)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("desk data unchanged - nothing to push")
        return
    git(*identity_args(), "commit", "-m", "Refresh hosted desk data feed and performance pack (sanitized, secret-guarded)", "--", *paths)
    push = git("push", https_remote(), "HEAD:main", check=False)
    if push.returncode != 0:
        print("PUSH FAILED — data committed locally but not synced:\n" + (push.stderr or push.stdout))
        raise SystemExit(1)
    print("pushed refreshed desk data feed to origin/main" + (f" (credential: {token_env()})" if token_env() else ""))


if __name__ == "__main__":
    try:
        main()
    finally:
        if _ASKPASS is not None:
            _ASKPASS.unlink(missing_ok=True)
