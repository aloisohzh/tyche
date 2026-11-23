"""Sync cloud runs, refresh the hosted live desk's data feed, and push it to origin.

The live Sites Function (desk-site/functions) reads desk-site/web/data/{state,automation,schedule}.json
from the public repo. This script first fast-forward pulls origin/main so the cloud desk's
sanitized run bundles (docs/performance/<run>/) are current, then rebuilds the feed files
through the secret-guarded export (--data-only, so the live HTML/CSS/JS are never touched),
then restores the journal from the newest verified Drive run bundle when the checkout has none (the
sandbox starts empty; the feed and the pack are built from that journal), copies every Drive run bundle
that git does not hold yet into docs/performance/<run>/ through the sanitize gate (account ids and
tokens redacted, a bundle that still leaks a secret is withheld), then regenerates the day's fee-net performance pack (`tyche performance report`, docs/performance/
<date>-metrics.md, from the restored ledger journal and whatever price CSVs the run left behind),
then commits and pushes ONLY the data files, the new sanitized bundles and that pack. A pack that cannot be built is reported
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
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
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
# The desk's private system of record (ADR 0009): one directory per run, raw. Absent on a laptop.
DRIVE_RAW = Path("/data/drive/tyche-raw")
PERF_DIR = ROOT / "docs" / "performance"
JOURNAL = ROOT / "journal" / "events.jsonl"
# Directories under the Drive root that are state, not runs: never published.
NOT_A_RUN = {"lifecycle"}
# Secret values that must never reach a sanitized bundle (the env names the desk card and the laptop use).
GUARD_KEYS = ("QODER_PAT", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TYCHE_GITHUB_PAT", "TYCHE_GIT_PAT", "TYCHE_CLOUD_PAT")
# Either name works: TYCHE_GITHUB_PAT is the name Alois already uses for the Sites Function's repo token.
TOKEN_ENVS = ("TYCHE_GITHUB_PAT", "TYCHE_GIT_PAT")


GITHUB_API = "https://api.github.com"
# Prefixes GitHub issues today; anything else is reported as "unrecognised" so a pasted label or a quoted
# value shows up in the log without the value itself ever doing so.
TOKEN_PREFIXES = ("github_pat_", "ghp_", "ghs_", "gho_", "ghu_", "ghr_")


def token_env() -> str | None:
    return next((k for k in TOKEN_ENVS if clean_token(os.environ.get(k))), None)


def clean_token(raw: str | None) -> str:
    """The token exactly as GitHub must receive it: surrounding whitespace and one pair of matching
    quotes removed. `.env` lines are often written KEY="value", and a copied value can carry a trailing
    newline or a stray space; either turns a valid token into "Bad credentials" at the far end."""
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def token_value() -> str:
    key = token_env()
    return clean_token(os.environ.get(key)) if key else ""


def token_shape(token: str) -> str:
    """A description safe to print: the token's kind and length, never its characters."""
    kind = next((prefix + "..." for prefix in TOKEN_PREFIXES if token.startswith(prefix)), "unrecognised prefix")
    return f"{kind}, {len(token)} chars"


def repo_slug(url: str) -> str | None:
    """owner/repo from any GitHub remote spelling (https with or without userinfo, ssh, with or without .git)."""
    text = url.strip()
    if text.startswith("git@github.com:"):
        path = text.split(":", 1)[1]
    else:
        parsed = urllib.parse.urlparse(text)
        if parsed.hostname != "github.com":
            return None
        path = parsed.path
    path = path.strip("/")
    path = path.removesuffix(".git")
    return path if path.count("/") == 1 and all(path.split("/")) else None


def github_token_probe(token: str, slug: str, timeout: int = 20) -> dict:
    """Ask GitHub what this token may do on `slug`, before git tries to push with it.

    Returns {"ok", "status", "push", "detail"}; `ok` means the token is accepted AND may push. The value
    is sent only in the Authorization header and never appears in the result. A network failure is
    reported as status 0 so the caller can tell "GitHub said no" from "GitHub was not reached"."""
    request = urllib.request.Request(
        f"{GITHUB_API}/repos/{slug}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "tyche-publish", "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read() or b"{}").get("message", "")
        except (ValueError, AttributeError):
            message = ""
        detail = f"GitHub rejected the token: HTTP {error.code} {message}".strip()
        if error.code == 404:
            detail += f" (a fine-grained token that does not cover {slug} also reads as 404)"
        return {"ok": False, "status": error.code, "push": None, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {"ok": False, "status": 0, "push": None, "detail": f"GitHub not reached: {error}"}
    push = (payload.get("permissions") or {}).get("push")
    if push is True:
        return {"ok": True, "status": 200, "push": True, "detail": f"token accepted, may push to {slug}"}
    return {"ok": False, "status": 200, "push": bool(push),
            "detail": f"token accepted but may NOT push to {slug} (needs Contents: read and write)"}
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
            "def clean(raw):\n"
            "    v = (raw or '').strip()\n"
            "    quoted = len(v) >= 2 and v[0] == v[-1] and v[0] in ('\"', \"'\")\n"
            "    return v[1:-1].strip() if quoted else v\n"
            f"print('x-access-token' if 'username' in prompt else clean(os.environ.get({key!r})))\n",
            encoding="utf-8",
        )
        _ASKPASS.chmod(_ASKPASS.stat().st_mode | stat.S_IXUSR)
    return {"GIT_ASKPASS": str(_ASKPASS), "GIT_TERMINAL_PROMPT": "0"}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, **_askpass())
    # With a token, the askpass helper must be the only credential git consults: a stored helper or the
    # platform's own read-only mount credential would otherwise be sent first and the token never asked for.
    prefix = ["-c", "credential.helper="] if token_env() else []
    return subprocess.run(["git", *prefix, *args], cwd=ROOT, check=check, capture_output=True, text=True, env=env)


def identity_args() -> list[str]:
    """`-c user.name/email` for the commit when the checkout has no identity (the cloud desk's mount)."""
    if git("config", "user.email", check=False).returncode == 0:
        return []
    return ["-c", f"user.name={BOT_IDENTITY[0]}", "-c", f"user.email={BOT_IDENTITY[1]}"]


def https_remote() -> str:
    """The push target. With a token, an SSH remote is turned into its HTTPS twin and any credential
    embedded in the URL (user:token@github.com, as a platform mount may configure) is dropped, so the
    token from the environment is the one GitHub sees; otherwise the configured remote is used as is."""
    url = git("remote", "get-url", "origin").stdout.strip()
    if not token_env():
        return url
    slug = repo_slug(url)
    return f"https://github.com/{slug}.git" if slug else url


def _tyche():
    """The kernel's journal and persistence helpers, from the installed package or the checkout."""
    try:
        from tyche import journal, persist  # type: ignore
    except ImportError:
        sys.path.insert(0, str(ROOT / "src"))
        from tyche import journal, persist  # type: ignore
    return journal, persist


def ledger_candidates(drive_root: Path) -> list[tuple[int, str, Path]]:
    """Every verified journal under the Drive root as (events, run name, path), longest chain first.
    An unverifiable copy is left out: a broken chain is not a ledger, however many rows it has."""
    journal, _ = _tyche()
    found = []
    for path in sorted(drive_root.glob("*/journal/events.jsonl")):
        ok, count, _ = journal.verify_chain(path)
        if ok and count:
            found.append((count, path.parent.parent.name, path))
    found.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return found


def restore_journal(drive_root: Path = DRIVE_RAW, target: Path = JOURNAL) -> str:
    """Put the ledger where the feed builder and the pack read it (journal/events.jsonl, gitignored).

    The desk card is asked to restore the Drive lineage at bootstrap, and the 2026-11-23 fires showed
    what happens when that is skipped: the feed published with 0 journal events. So the publish step
    restores it itself, from the longest verified chain on Drive, and only when the checkout's own
    journal is shorter (a longer local chain is newer work, never overwritten)."""
    if not drive_root.is_dir():
        return "journal: no Drive mount, using the checkout's journal as is"
    candidates = ledger_candidates(drive_root)
    if not candidates:
        return "journal: Drive holds no verifiable journal; using the checkout's journal as is"
    count, run, path = candidates[0]
    journal, _ = _tyche()
    local_ok, local_count, _ = journal.verify_chain(target) if target.is_file() else (True, 0, None)
    if local_ok and local_count >= count:
        return f"journal: checkout has {local_count} verified events, Drive ledger {run} has {count}; kept the checkout's"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return f"journal: restored {count} verified events from Drive run {run}"


def is_run_bundle(path: Path) -> bool:
    """A run leaves a kernel snapshot or broker reads; a journal-only directory (an operator freeze, a
    lifecycle store) is not a run and has nothing the desk page can show."""
    return path.is_dir() and path.name not in NOT_A_RUN and (
        (path / "snapshot.json").is_file() or (path / "mcp").is_dir() or (path / "positions.json").is_file()
    )


def redact_ids() -> list[str]:
    """Account ids the sanitize gate must strip: the config allowlist plus the desk's env allowlist."""
    ids = [x.strip() for x in os.environ.get("TYCHE_ALLOWED_ACCOUNT_IDS", "").split(",") if x.strip()]
    try:
        from tyche.config import load_config  # type: ignore
        ids += list(load_config(ROOT).risk.account_allowlist)
    except Exception as error:  # noqa: BLE001 - a config that will not load must not stop the feed
        print(f"bundles: config allowlist unavailable ({error}); redacting env ids only")
    return sorted(set(ids))


def guard_values() -> dict[str, str]:
    """Secret values that must not appear in anything staged for git: env first, then .env lines."""
    out = {key: value for key, value in os.environ.items() if key in GUARD_KEYS and value.strip()}
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in GUARD_KEYS and value.strip():
                    out.setdefault(key.strip(), value.strip().strip("\"'"))
    return out


def leaks_in(git_dir: Path, secrets: dict[str, str], ids: list[str]) -> list[str]:
    """Names (never values) of anything secret still present in a sanitized bundle."""
    leaks: set[str] = set()
    for path in git_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key, value in secrets.items():
            if len(value) >= 6 and value in text:
                leaks.add(key)
        for account_id in ids:
            if len(account_id) >= 4 and account_id in text:
                leaks.add("account_id:***" + account_id[-3:])
    return sorted(leaks)


def publish_run_bundles(drive_root: Path = DRIVE_RAW, perf_dir: Path = PERF_DIR) -> list[Path]:
    """Copy every Drive run bundle git does not hold yet into docs/performance/<run>/ through the sanitize
    gate, and return the directories to stage. The 2026-11-23 fires wrote their bundles to Drive and
    nothing carried them to git, so the hosted page kept showing the 2026-11-18 account snapshot.

    A bundle already in git is never rewritten (history stays history). A sanitized bundle in which a
    secret value or a full account id survives is deleted again and reported by name, never staged."""
    if not drive_root.is_dir():
        print("bundles: no Drive mount, nothing to copy")
        return []
    _, persist = _tyche()
    ids = redact_ids()
    secrets = guard_values()
    staged: list[Path] = []
    for raw in sorted(drive_root.iterdir()):
        if not is_run_bundle(raw):
            continue
        git_dir = perf_dir / raw.name
        if git_dir.exists():
            continue
        manifest = persist.persist_run(raw, git_dir, ids, bucket_dir=None)
        leaks = leaks_in(git_dir, secrets, ids)
        if leaks:
            shutil.rmtree(git_dir, ignore_errors=True)
            print(f"bundles: WITHHELD {raw.name} - sanitized copy still carries {', '.join(leaks)}")
            continue
        if not manifest["sanitized"]:
            shutil.rmtree(git_dir, ignore_errors=True)
            print(f"bundles: {raw.name} has no text files to publish")
            continue
        has_snapshot = (git_dir / "snapshot.json").is_file()
        print(f"bundles: copied {raw.name} ({len(manifest['sanitized'])} sanitized files"
              + (")" if has_snapshot else "; no snapshot.json, so the desk page cannot read its NAV)"))
        staged.append(git_dir)
    if not staged:
        print("bundles: git already holds every Drive run bundle")
    return staged


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
    print(restore_journal())
    bundles = publish_run_bundles()
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_dashboard.py"), "--data-only"],
        cwd=ROOT,
        check=True,
    )
    feed = (json.loads((DATA / "state.json").read_text(encoding="utf-8")).get("feed") or {})
    print(f"primary: {feed.get('primary_account')} | source: {feed.get('source')} | run: {feed.get('run')} | cloud runs: {feed.get('cloud_runs')}")
    paths = [str(DATA / name) for name in FEED] + [str(path) for path in bundles]
    pack = performance_pack()
    if pack is not None:
        paths.append(str(pack))
    git("add", *paths)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("desk data unchanged - nothing to push")
        return
    git(*identity_args(), "commit", "-m", "Refresh hosted desk data feed, run bundles and performance pack (sanitized, secret-guarded)", "--", *paths)
    remote = https_remote()
    if token_env():
        # Ask GitHub about the token before git does, so a bad value is named plainly (kind and length,
        # never the value) instead of surfacing as a bare "Invalid username or token" from the push.
        token = token_value()
        slug = repo_slug(remote) or "aloisohzh/tyche"
        probe = github_token_probe(token, slug)
        print(f"credential {token_env()} ({token_shape(token)}): {probe['detail']}")
        if not probe["ok"] and probe["status"] != 0:
            print("PUBLISH TOKEN REJECTED - data committed locally but not pushed. "
                  f"Fix from the laptop: deploy_two_fire_automation.py --card <desk card id> --set-env {token_env()} "
                  "(it now checks the token against GitHub before writing it).")
            raise SystemExit(1)
    push = git("push", remote, "HEAD:main", check=False)
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
