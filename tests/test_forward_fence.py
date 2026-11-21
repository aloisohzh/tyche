"""The Forward fence: templates are no longer an authoring surface, and nothing may make them one.

Read-only scripts may still talk to the Forward base (the archived writers explain why it exists), but a
*write* to `/forward/templates` recompiles the Managed agent it was built from, and that recompile can
materialise a `managed_tool_config` grant the running pin never had (L-046). So the whole Forward authoring
path was moved to `archive/` on 2026-11-21 instead of being deleted, and this test is what keeps it moved.

Scope is `scripts/` deliberately: `dashboard/server.py` still *reads* `/forward/schedules` for its automation
panel (documented in the sentinel runbook as the remaining Forward-plane consumer), and `scripts/forward.py`
is the client itself. This fence is about authoring, not about the existence of the base.
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
