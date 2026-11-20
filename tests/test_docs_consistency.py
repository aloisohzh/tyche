from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tyche.config import rules_path_for
from tyche.pipeline import rules_hash

RULES_HASH_LINE = re.compile(r"\*\*Rules hash:\*\*\s*`([0-9a-f]{12})`")
PLAYBOOK_ID = re.compile(r"^(PB-\d{3})-")


def _risk() -> dict:
    return yaml.safe_load((ROOT / "config" / "risk.yaml").read_text(encoding="utf-8"))


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_published_order_and_turnover_match_config() -> None:
    risk = _risk()
    orders = risk["max_orders_per_day"]
    turnover = risk["max_daily_turnover_pct"]
    readme = _doc("README.md")
    assert f"Internal order budget is {orders}/day" in readme
    assert f"competition ceiling {risk['competition_order_cap']}" in readme
    assert f"daily turnover {turnover:.0%} of NAV" in readme
    card = _doc("docs/risk-card.md")
    assert f"| Executed orders/day | ≤ {risk['competition_order_cap']} | ≤ {orders} |" in card
    assert "`max_daily_turnover_pct`" in card


def test_published_price_floor_matches_config() -> None:
    price = _risk()["min_price"]
    assert f"${price:.2f} minimum price" in _doc("README.md")
    assert f"| Min price | ${price:.2f} | ${price:.2f} |" in _doc("docs/risk-card.md")


def _playbook_dir() -> Path:
    return ROOT / "playbook"


def _front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    return yaml.safe_load(text.split("---\n", 2)[1]) or {}


def _roster() -> list[dict]:
    return yaml.safe_load(_doc("playbook/INDEX.yaml"))["playbooks"]


def _playbook_hashes() -> list[tuple[str, str]]:
    found = []
    for path in sorted(_playbook_dir().glob("PB-*.md")):
        matched = PLAYBOOK_ID.match(path.name)
        declared = RULES_HASH_LINE.search(path.read_text(encoding="utf-8"))
        if matched and declared:
            found.append((matched.group(1), declared.group(1)))
    return found


def test_declared_playbook_rules_hash_matches_the_kernel() -> None:
    """A freeze hash that never matched its bytes silently launders a rules change (L-030)."""
    pairs = _playbook_hashes()
    assert pairs, "no playbook declares a rules hash; the guard would pass vacuously"
    for strategy_id, declared in pairs:
        try:
            frozen = rules_path_for(ROOT, strategy_id)
        except ValueError:
            continue  # planned playbook with no lane mapped yet
        assert frozen.is_file(), f"{strategy_id}: {frozen} is the freeze source but does not exist"
        assert declared == rules_hash(ROOT, strategy_id), (
            f"{strategy_id}: playbook says {declared} but the kernel computes "
            f"{rules_hash(ROOT, strategy_id)}; re-register the rules, do not just edit the doc"
        )


def test_playbook_ids_are_claimed_once() -> None:
    """PB-004 named two setups at once and attribution became unreliable (L-029)."""
    table = _doc("playbook/README.md")
    ids = re.findall(r"^\| (PB-\d{3}) \|", table, flags=re.MULTILINE)
    assert ids, "playbook index table is missing"
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"playbook id claimed by more than one setup: {sorted(duplicates)}"


def test_playbook_roster_files_and_ids_agree() -> None:
    """The roster, the table and the files must name the same set of ids (L-029)."""
    roster = _roster()
    assert roster, "playbook/INDEX.yaml is empty"
    roster_ids = [entry["id"] for entry in roster]
    assert len(roster_ids) == len(set(roster_ids)), "INDEX.yaml lists an id twice"
    table_ids = re.findall(r"^\| (PB-\d{3}) \|", _doc("playbook/README.md"), flags=re.MULTILINE)
    assert sorted(roster_ids) == sorted(table_ids), (
        f"roster {sorted(roster_ids)} and README table {sorted(table_ids)} disagree"
    )
    for entry in roster:
        path = _playbook_dir() / f"{entry['id']}-*.md"
        on_disk = sorted(path.parent.glob(path.name))
        if entry["status"] == "live":
            assert on_disk, f"{entry['id']} is live but has no playbook file"
        if entry.get("file") is not None:
            assert (ROOT / entry["file"]).is_file(), f"{entry['file']} is listed but missing"
        if on_disk:
            assert _front_matter(on_disk[0])["id"] == entry["id"], f"{entry['id']}: file id mismatch"


def test_live_playbooks_have_a_freezable_rule_source() -> None:
    """A live strategy whose rules cannot be hashed is not pre-registered (L-036).

    The roster's `config:` and the kernel's PLAYBOOK_LANES must name the same bytes, or the
    dashboard reports a strategy as live while approvals freeze a different file.
    """
    for entry in _roster():
        if entry["status"] != "live":
            continue
        strategy_id = entry["id"]
        assert rules_hash(ROOT, strategy_id), f"{strategy_id}: no rules hash"
        assert rules_path_for(ROOT, strategy_id) == ROOT / entry["config"], (
            f"{strategy_id}: playbook/INDEX.yaml says {entry['config']} but the kernel freezes "
            f"{rules_path_for(ROOT, strategy_id).relative_to(ROOT)}"
        )


LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _markdown_files() -> list[Path]:
    """Tracked markdown only: a link out of an untracked directory goes nowhere real."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8").split("\0")
    return [ROOT / rel for rel in sorted(tracked) if rel.endswith(".md")]


FENCE = re.compile(r"```.*?```", re.DOTALL)


def _prose(path: Path) -> str:
    """Fenced blocks hold templates, not links: `[evidence](relative/link)` must not count."""
    return FENCE.sub("", path.read_text(encoding="utf-8"))


def test_markdown_links_resolve() -> None:
    """Docs rotted twice because nothing checked a link survived a move (audit section 3.1)."""
    dangling = []
    for path in _markdown_files():
        for _, target in LINK.findall(_prose(path)):
            if target.startswith(("#", "http://", "https://", "mailto:", "{")):
                continue
            relative = target.split("#")[0]
            if relative and not (path.parent / relative).resolve().exists():
                dangling.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not dangling, "dangling markdown links:\n" + "\n".join(sorted(dangling))


ARCHIVE_REF = re.compile(r"""(?:from|import)\s+[\w.]*archive|["'/]archive/|bridge-site|cloud_bridge""")
LIVE_CODE_DIRS = ("src", "dashboard", "scripts", "dev", "config")
LIVE_CODE_SUFFIXES = {".py", ".mjs", ".js", ".ts", ".yaml", ".json"}


def test_no_live_code_reaches_into_the_archive() -> None:
    """archive/ is dead by contract, so a revival must be a move, not a silent import.

    This file is not scanned: it names the patterns it forbids.
    """
    offenders = []
    for rel in LIVE_CODE_DIRS:
        root = ROOT / rel
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in LIVE_CODE_SUFFIXES or not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped.startswith(("#", "//", "*")) or not ARCHIVE_REF.search(line):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}: {stripped[:90]}")
    assert not offenders, "live code references the archive:\n" + "\n".join(offenders)


@pytest.mark.parametrize("dimension,vocabulary", [
    ("holding_period", {"Scalping", "Intraday", "Swing", "Position", "Long-term"}),
    ("strategy_type", {"Trend following", "Mean reversion", "Momentum", "Breakout", "Arbitrage",
                       "Market making", "Event-driven", "Statistical/quantitative"}),
    ("execution_style", {"Manual", "Semi-automated", "Fully automated"}),
])
def test_playbook_classification_uses_the_frozen_vocabulary(
    dimension: str, vocabulary: set[str]
) -> None:
    """Four independent dimensions, fixed words: Scout and the dashboard filter on these."""
    offenders = []
    for path in sorted(_playbook_dir().glob("PB-*.md")):
        matter = _front_matter(path)
        assert matter, f"{path.name} has no YAML front matter"
        value = (matter.get("classification") or {}).get(dimension)
        if value is None or (dimension != "instruments" and value not in vocabulary):
            offenders.append(f"{path.name}: {dimension}={value!r}")
    assert not offenders, f"unknown {dimension} value(s): {offenders}"


def test_playbook_instruments_are_stocks_and_options_only() -> None:
    """The window trades stocks and options; anything else is out of scope by construction."""
    for path in sorted(_playbook_dir().glob("PB-*.md")):
        instruments = (_front_matter(path).get("classification") or {}).get("instruments")
        assert isinstance(instruments, list) and instruments, f"{path.name}: instruments must be a list"
        assert set(instruments) <= {"Stocks", "Options"}, f"{path.name}: {instruments}"


_VOCAB_ROW = re.compile(r"^\|\s*\*\*(\w+)\*\*\s*\|", re.MULTILINE)
_LEADING_WORD = re.compile(r"[A-Za-z]+")


def _status_vocabulary() -> set[str]:
    """The vocabulary lives in documentation/README.md, not in this test, so it cannot fork."""
    section = _doc("documentation/README.md").split("## Status vocabulary (fixed)", 1)[1]
    words = set(_VOCAB_ROW.findall(section.split("\n## ", 1)[0]))
    assert words, "documentation/README.md lost its status vocabulary"
    return words


def _prd_status_cells(prd: str) -> list[tuple[str, str]]:
    """(capability, status) for every row of a PRD table whose second column is headed "Status"."""
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in prd.splitlines():
        if not line.lstrip().startswith("|"):
            in_table = False
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            in_table = False
            continue
        if cells[1] == "Status":
            in_table = True
        elif in_table and set(cells[1]) - set("-: "):
            rows.append((cells[0], cells[1]))
    return rows


def test_prd_capability_statuses_use_the_fixed_vocabulary() -> None:
    """A PRD may only describe state with the agreed words; prose tense is not a status."""
    vocabulary = _status_vocabulary()
    cells = _prd_status_cells(_doc("documentation/PRD.md"))
    assert cells, "documentation/PRD.md has no capability table with a Status column"
    offenders = []
    for capability, status in cells:
        match = _LEADING_WORD.search(status.lstrip("*` "))
        if match is None or match.group().lower() not in vocabulary:
            offenders.append(f"{capability[:52]!r} -> {status!r}")
    assert not offenders, (
        f"PRD status cell(s) outside {sorted(vocabulary)}:\n" + "\n".join(offenders)
    )


def test_hosted_desk_assets_have_sources_that_survive_a_full_export() -> None:
    """A full export deletes desk-site/web/ wholesale (L-039), so every hosted asset needs a source.

    The copies are byte-compared modulo line endings: CRLF drift is noise, a stale publish is not.
    """
    for name in ("app.js", "style.css"):
        source = (ROOT / "dashboard" / "static" / name).read_bytes().replace(b"\r\n", b"\n")
        hosted = (ROOT / "desk-site" / "web" / name).read_bytes().replace(b"\r\n", b"\n")
        assert source == hosted, (
            f"desk-site/web/{name} no longer matches dashboard/static/{name}; "
            "run scripts/export_dashboard.py before publishing"
        )
    vendor = ROOT / "dashboard" / "static" / "vendor"
    assert vendor.is_dir() and list(vendor.glob("*.js")), (
        "the vendored chart library needs a source under dashboard/static/vendor/, "
        "not a copy inside the directory the exporter deletes"
    )
    assert list((ROOT / "desk-site" / "web" / "vendor").glob("*.js")), "hosted desk is missing its chart library"
    assert (ROOT / "desk-site" / "web" / "charts.html").is_file(), (
        "desk-site/web/charts.html vanished: export_dashboard.py must carry it across the wipe"
    )
