"""The Forward fence: templates are no longer an authoring surface, and nothing may make them one.

Read-only scripts may still talk to the Forward base (the archived writers explain why it exists), but a
*write* to `/forward/templates` recompiles the Managed agent it was built from, and that recompile can
materialise a `managed_tool_config` grant the running pin never had (L-046). So the whole Forward authoring
path was moved to `archive/` on 2026-11-21 instead of being deleted, and this test is what keeps it moved.

Scope is authoring, plus one narrow read: `scripts/forward.py` is the client itself, so it may name its own
base. The desk's automation panel used to be the other exception - `dashboard/server.py` read
`/forward/schedules` and `/forward/sessions` - and it was repointed at the Managed cards on 21 Nov, so the
running code no longer reads that base at all and `test_the_desk_itself_does_not_read_the_forward_base`
keeps it that way. The hosted `desk-site` Function held out until 22 Nov, when its `/automation` overlay
moved to `/api/v1/cloud` too: nothing the desk publishes reads Forward any more, and this fence now covers
the hosted handler along with the local panel.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ARCHIVE = ROOT / "archive"

# The client is allowed to name its own base; nothing else in scripts/ may.
FORWARD_CLIENT = "forward.py"
TEMPLATE_ROUTE = re.compile(r"/templates")
FORWARD_BASE = re.compile(r"api/v1/forward")
IMPORT_FORWARD = re.compile(r"^\s*(?:from|import)\s+forward\b", re.MULTILINE)

# Forward-era writers parked on 2026-11-21, each with a row in archive/MANIFEST.md.
FENCED_WRITERS = (
    "deploy_calendar_check.py",
    "deploy_event_discovery.py",
    "deploy_role_skills.py",
    "deploy_scout_data_suite.py",
    "deploy_token_policy.py",
    "deploy_youtube_clause.py",
    "repin_stale_caps.py",
    "verify_envelope_deploy.py",
)


# The desk's own running code, local and hosted, which PRD §7 item 14 took off the Forward base.
DESK_READERS = ("dashboard/server.py", "scripts/export_dashboard.py", "desk-site/functions/handler.ts")

# Everything the hosted desk is built from: the Function, its build stamp, and the exported web bundle's
# source. The Sites platform binds a Secret to a release for as long as a published Function names it, so
# the Forward-era credential and the Forward label must stay out of all of it (PRD §7 item 14).
HOSTED_SOURCES = ("desk-site/functions", "dashboard/static")
FORWARD_SECRET = re.compile(r"TYCHE_FORWARD_PAT")
FORWARD_LABEL = re.compile(r"Forward API")


def _script_sources() -> list[Path]:
    return sorted(p for p in SCRIPTS.glob("*.py") if p.name != FORWARD_CLIENT)


def test_no_live_script_authors_a_forward_template() -> None:
    """`/templates` on the Forward base is not an authoring surface any more."""
    offenders = []
    for path in _script_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if TEMPLATE_ROUTE.search(text):
            offenders.append(f"{path.name}: names a /templates route")
        if IMPORT_FORWARD.search(text):
            offenders.append(f"{path.name}: imports the Forward client")
        if FORWARD_BASE.search(text):
            offenders.append(f"{path.name}: names the Forward base directly")
    assert not offenders, (
        "a script under scripts/ is back on the Forward plane; author the Managed object instead "
        "(see scripts/deploy_managed_agents.py) and park this one in archive/ with a MANIFEST row:\n"
        + "\n".join(offenders)
    )


def test_the_desk_itself_does_not_read_the_forward_base() -> None:
    """Reading is not authoring, but a panel that reads a retired base drifts from what the desk runs on.

    The automation panel used to enumerate `/forward/schedules` and `/forward/sessions`; PRD §7 item 14
    repointed it at `cloud_api.cards()` and the Managed sessions, and one day later repointed the hosted
    Function's same overlay at `/deployments` and `/sessions`. Nothing in the desk's own code may go back
    to the archived objects, or the panel starts showing a cadence that no longer fires.
    """
    offenders = []
    for rel in DESK_READERS:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if IMPORT_FORWARD.search(text):
            offenders.append(f"{rel}: imports the Forward client")
        if FORWARD_BASE.search(text):
            offenders.append(f"{rel}: names the Forward base directly")
    assert not offenders, (
        "the desk is back on the Forward plane; the cadence lives on the Managed cards "
        "(see scripts/deploy_managed_agents.py) and the runs on /sessions:\n" + "\n".join(offenders)
    )


def test_nothing_the_desk_publishes_names_the_forward_secret() -> None:
    """The hosted Secret can only be deleted once no live release references it.

    `delete_secret` refused `TYCHE_FORWARD_PAT` with `sites_secret_in_use` after the 22 Nov republish, so the
    name must not come back in anything the Sites publish ships: the Function sources, the build stamp, or
    the desk script and styles that `scripts/export_dashboard.py` copies into `desk-site/web/`. The visible
    "Forward API" label is fenced with it, because a desk that says it reads Forward invites someone to
    mount the credential again.
    """
    offenders = []
    for rel in HOSTED_SOURCES:
        for path in sorted((ROOT / rel).rglob("*")):
            if not path.is_file() or path.suffix not in {".ts", ".js", ".mjs", ".html", ".css", ".json"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            short = path.relative_to(ROOT).as_posix()
            if FORWARD_SECRET.search(text):
                offenders.append(f"{short}: names TYCHE_FORWARD_PAT")
            if FORWARD_LABEL.search(text):
                offenders.append(f"{short}: labels its source as the Forward API")
            if FORWARD_BASE.search(text):
                offenders.append(f"{short}: names the Forward base")
    assert not offenders, (
        "the hosted desk names the retired Forward plane again; it reads the Managed base under "
        "TYCHE_CLOUD_PAT and nothing else:\n" + "\n".join(offenders)
    )


def test_fenced_writers_are_parked_not_deleted() -> None:
    """The fence is only honest if the history it forbids is still somewhere readable."""
    missing = [name for name in FENCED_WRITERS if not (ARCHIVE / name).is_file()]
    assert not missing, f"archive/ is missing {missing}"
    still_live = [name for name in FENCED_WRITERS if (SCRIPTS / name).exists()]
    assert not still_live, f"Forward writers are back in scripts/: {still_live}"


def test_manifest_records_every_parked_writer() -> None:
    """An unexplained archive file is a file nobody can revive correctly."""
    manifest = (ARCHIVE / "MANIFEST.md").read_text(encoding="utf-8")
    unrowed = [name for name in FENCED_WRITERS if name not in manifest]
    assert not unrowed, f"archive/MANIFEST.md has no row for {unrowed}"
