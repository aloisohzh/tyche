"""Pre-publish guard and build stamp for the hosted desk Function.

The Sites Function is published from whatever working tree the operator has open, not from
`origin/main`, which is how two commits on an already-merged branch reached production on
22 Nov while `main` still served the old handler. This script closes both halves:

  check    refuse unless HEAD is exactly origin/main (after a fetch) and the tree is clean
  write    run `check`, then fill desk-site/functions/build.ts with sha / branch / dirty / time
  restore  blank build.ts again (git checkout) once the publish has gone out

`write --allow-off-main` stamps anyway for a deliberate preview publish; the stamp then says
so, because the health route reports it and the acceptance read will show the branch name.

Run: .venv/Scripts/python.exe scripts/stamp_desk_build.py write
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_TS = ROOT / "desk-site" / "functions" / "build.ts"
BUILD_REL = BUILD_TS.relative_to(ROOT).as_posix()
TEMPLATE = """\
// Build stamp for the hosted desk Function. The committed copy is deliberately blank:
// `scripts/stamp_desk_build.py write` fills it from git immediately before a publish, after
// refusing any tree that is not a clean checkout of origin/main, and `--restore` blanks it
// again afterwards. The health route (`/app`, `/health`) reports it, so the signed-in
// acceptance read also answers "does the live site run main, and which commit?".
export const BUILD = {
  sha: @SHA@,
  branch: @BRANCH@,
  dirty: @DIRTY@ as boolean | null,
  stamped_at: @STAMPED_AT@ as string | null,
};
"""


class Refused(Exception):
    """The working tree is not a publishable checkout; the message says why."""


def git(root: Path, *args: str, strip: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return out.stdout.strip() if strip else out.stdout


def inspect(root: Path, fetch: bool = True) -> dict:
    """Describe HEAD against origin/main. Pure read; never raises on a dirty or off-main tree."""
    if fetch:
        subprocess.run(
            ["git", "fetch", "--quiet", "origin", "+refs/heads/main:refs/remotes/origin/main"],
            cwd=root,
            check=False,
        )
    head = git(root, "rev-parse", "HEAD")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    try:
        main = git(root, "rev-parse", "origin/main")
    except subprocess.CalledProcessError:
        main = None
    # Not stripped: porcelain lines start with the two status columns, which can be a space.
    status = git(root, "status", "--porcelain", "--untracked-files=no", strip=False)
    # The stamp file is the one thing this tool itself dirties; a stale stamp is not a reason
    # to refuse, because `write` overwrites it and `restore` blanks it.
    dirty_paths = [line[3:] for line in status.splitlines() if line[3:] != BUILD_REL]
    return {
        "sha": head,
        "branch": branch,
        "origin_main": main,
        "on_main": main is not None and head == main,
        "dirty": bool(dirty_paths),
        "dirty_paths": dirty_paths,
    }


def check(root: Path, fetch: bool = True, allow_off_main: bool = False) -> dict:
    info = inspect(root, fetch=fetch)
    problems = []
    if info["dirty"]:
        problems.append("uncommitted changes: " + ", ".join(info["dirty_paths"]))
    if not info["on_main"] and not allow_off_main:
        if info["origin_main"] is None:
            problems.append("origin/main is unknown here (fetch failed or no remote)")
        else:
            problems.append(
                f"HEAD {info['sha'][:7]} on '{info['branch']}' is not origin/main "
                f"{info['origin_main'][:7]}; merge first, then publish from main"
            )
    if problems:
        raise Refused("REFUSING TO STAMP - " + "; ".join(problems))
    return info


def render(info: dict, stamped_at: str) -> str:
    return (
        TEMPLATE.replace("@SHA@", json.dumps(info["sha"]))
        .replace("@BRANCH@", json.dumps(info["branch"]))
        .replace("@DIRTY@", json.dumps(info["dirty"]))
        .replace("@STAMPED_AT@", json.dumps(stamped_at))
    )


def write(root: Path, fetch: bool = True, allow_off_main: bool = False) -> dict:
    info = check(root, fetch=fetch, allow_off_main=allow_off_main)
    stamped_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    (root / BUILD_REL).write_text(render(info, stamped_at), encoding="utf-8")
    return {**info, "stamped_at": stamped_at}


def restore(root: Path) -> None:
    git(root, "checkout", "--", BUILD_REL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("check", "write", "restore"))
    parser.add_argument("--allow-off-main", action="store_true", help="stamp a non-main tree (preview publish)")
    parser.add_argument("--no-fetch", action="store_true", help="trust the local origin/main ref")
    args = parser.parse_args(argv)
    try:
        if args.command == "restore":
            restore(ROOT)
            print(f"restored {BUILD_REL} to the committed blank stamp")
            return 0
        if args.command == "check":
            info = check(ROOT, fetch=not args.no_fetch, allow_off_main=args.allow_off_main)
            print(f"OK - {info['sha'][:7]} on {info['branch']} is a clean checkout of origin/main")
            return 0
        info = write(ROOT, fetch=not args.no_fetch, allow_off_main=args.allow_off_main)
        where = "origin/main" if info["on_main"] else f"'{info['branch']}' (NOT main - preview only)"
        print(f"stamped {BUILD_REL}: {info['sha'][:7]} from {where} at {info['stamped_at']}")
        print("publish now, then run: scripts/stamp_desk_build.py restore")
        return 0
    except Refused as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
