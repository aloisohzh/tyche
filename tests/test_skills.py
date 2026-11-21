"""Phase 1 guards for the role-scoped skills tree.

Four things must stay true as procedures move out of the prompts and into skills:

1. every skill packages (frontmatter present, name matches its directory, role matches its parent);
2. every skill stays inside the context budget;
3. every ``tyche`` command a skill tells an agent to run really exists in the CLI;
4. the hard rules that stay in the prompts are still in them, verbatim, and the skills do not
   restate the numeric caps that config/ owns (L-033: two copies of a number drift).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
LIVE_PROMPTS = ROOT / "templates" / "prompts" / "live"
CARD_SCRIPT = ROOT / "scripts" / "deploy_two_fire_automation.py"

BODY_CHAR_BUDGET = 2500
ROLES = {"coordinator", "researcher", "auditor", "executor"}

# Numbers that belong to config/ or docs/risk-card.md. A skill may name the key, never the value.
FORBIDDEN_NUMBERS = (
    "25%", "45%", "95%", ">=5%", "120s", "60s", "3500", "3,500", "0.3%", "5%", "OI >=100",
)


def _frontmatter_and_body(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    assert match, "SKILL.md must open with a --- frontmatter block"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields, match.group(2).strip()


def _skills() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/*/SKILL.md"))


SKILL_PATHS = _skills()


def test_skills_tree_exists():
    assert SKILL_PATHS, f"no skills found under {SKILLS_DIR}"


@pytest.mark.parametrize("path", SKILL_PATHS, ids=lambda p: f"{p.parts[-3]}/{p.parts[-2]}")
def test_skill_frontmatter_and_budget(path: Path):
    fields, body = _frontmatter_and_body(path.read_text(encoding="utf-8"))
    role, name = path.parts[-3], path.parts[-2]

    assert role in ROLES, f"{name}: skills live under skills/<role>/<name>/"
    assert fields.get("name") == name, f"{path}: frontmatter name must equal its directory name"
    assert fields.get("role") == role, f"{name}: frontmatter role must match its directory"
    assert fields.get("version", "").isdigit(), f"{name}: version must be an integer"
    description = fields.get("description", "")
    assert description, f"{name}: description drives triggering, it cannot be empty"
    # The description is what the agent reads when deciding to load the skill, so it has to
    # name the moment it fires. "Use when/before/whenever ..." are the accepted phrasings.
    assert re.search(r"\bUse (?:when|before|whenever|after|if)\b", description), (
        f"{name}: description must state its trigger"
    )
    assert len(description) <= 500, f"{name}: description is {len(description)} chars, keep it short"
    assert len(body) <= BODY_CHAR_BUDGET, (
        f"{name}: body is {len(body)} chars, over the {BODY_CHAR_BUDGET} budget; move detail into "
        "the CLI or docs instead of lengthening the skill"
    )


def _cli_commands() -> tuple[set[str], set[str], set[str]]:
    """Top-level commands, "<group> <sub>" pairs and group names, read from the CLI source.

    Each ``*_cli.py`` module builds its own ``app = typer.Typer()`` and ``cli.py`` mounts the
    aliases, so a Typer is identified by (module, variable) and import aliases are resolved.
    """
    defined: set[tuple[str, str]] = set()
    aliases: dict[tuple[str, str], tuple[str, str]] = {}
    commands: dict[tuple[str, str], set[str]] = {}
    mounted: dict[tuple[str, str], str] = {}

    def resolve(current: str, expr: ast.expr) -> tuple[str, str] | None:
        if isinstance(expr, ast.Name):
            return aliases.get((current, expr.id), (current, expr.id))
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            module = expr.value.id
            for (source, alias), target in aliases.items():
                if source == current and alias == module:
                    return (target[0], expr.attr)
            return (f"{module}.py", expr.attr)
        return None

    paths = sorted((ROOT / "src" / "tyche").rglob("*.py"))
    parsed = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parsed[path.name] = tree
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_file = f"{node.module.split('.')[-1]}.py" if node.module else ""
                for alias in node.names:
                    local = alias.asname or alias.name
                    aliases[(path.name, local)] = (module_file, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[-1]
                    aliases[(path.name, local)] = (f"{alias.name.split('.')[-1]}.py", "app")
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and getattr(node.value.func, "attr", "") == "Typer":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add((path.name, target.id))

    for module, tree in parsed.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attr = getattr(node.func, "attr", "")
            if attr == "add_typer" and node.args:
                target = resolve(module, node.args[0])
                group = next((str(kw.value.value) for kw in node.keywords
                              if kw.arg == "name" and isinstance(kw.value, ast.Constant)), None)
                if target and group:
                    mounted[target] = group
            elif attr == "command" and isinstance(node.func, ast.Attribute):
                owner = (module, getattr(node.func.value, "id", ""))
                name = None
                if node.args and isinstance(node.args[0], ast.Constant):
                    name = str(node.args[0].value)
                else:
                    name = next((str(kw.value.value) for kw in node.keywords if kw.arg == "name"
                                 and isinstance(kw.value, ast.Constant)), None)
                if name:
                    commands.setdefault(owner, set()).add(name)
            elif attr == "command" and isinstance(node.func, ast.Name):
                continue

    # Bare @app.command() and @app.command decorators take the name from the function they wrap.
    for path in paths:
        if "cli" not in path.name:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                func = dec.func if isinstance(dec, ast.Call) else dec
                if not (isinstance(func, ast.Attribute) and func.attr == "command"):
                    continue
                if isinstance(dec, ast.Call) and (dec.args or dec.keywords):
                    continue  # the explicit name was collected in the first pass
                commands.setdefault((path.name, getattr(func.value, "id", "")), set()).add(
                    node.name.replace("_", "-"))

    groups = set(mounted.values())
    top: set[str] = set(groups)
    pairs: set[str] = set()
    for owner, names in commands.items():
        group = mounted.get(owner)
        for name in names:
            (pairs.add(f"{group} {name}") if group else top.add(name))
    return top, pairs, groups


TOP_LEVEL, SUBCOMMANDS, SUBCOMMAND_GROUPS = _cli_commands()


def test_cli_command_map_is_populated():
    assert {"plan", "execute", "record-order", "strategies"} <= TOP_LEVEL, sorted(TOP_LEVEL)
    assert {"lifecycle reserve", "tactical capture", "events add"} <= SUBCOMMANDS, sorted(SUBCOMMANDS)


@pytest.mark.parametrize("path", SKILL_PATHS, ids=lambda p: f"{p.parts[-3]}/{p.parts[-2]}")
def test_skills_only_name_real_tyche_commands(path: Path):
    _fields, body = _frontmatter_and_body(path.read_text(encoding="utf-8"))
    prose = re.sub(r"`[^`]*`", " ", body)  # only prose outside code spans may be loose
    assert "tyche " not in prose, f"{path.name}: tyche commands belong inside code spans"

    unknown = []
    for span in re.findall(r"`([^`]+)`", body):
        match = re.match(r"tyche\s+([A-Za-z0-9_.-]+)(?:\s+([A-Za-z0-9_.-]+))?", span.strip())
        if not match:
            continue
        first, second = match.group(1), match.group(2)
        if first in SUBCOMMAND_GROUPS:
            command = f"{first} {second}" if second else first
        else:
            command = first
        if command not in TOP_LEVEL and command not in SUBCOMMANDS:
            unknown.append(span)
    assert not unknown, f"{path.name}: commands not in the tyche CLI: {unknown}"


@pytest.mark.parametrize("path", SKILL_PATHS, ids=lambda p: f"{p.parts[-3]}/{p.parts[-2]}")
def test_skills_do_not_restate_config_numbers(path: Path):
    _fields, body = _frontmatter_and_body(path.read_text(encoding="utf-8"))
    hits = [number for number in FORBIDDEN_NUMBERS if number in body]
    assert not hits, f"{path.name}: restates caps {hits}; point at config/ or docs/risk-card.md"


def _card_prompt() -> str:
    tree = ast.parse(CARD_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(target, "id", "") == "PROMPT" for target in node.targets):
            return str(ast.literal_eval(node.value))
    raise AssertionError(f"no PROMPT constant found in {CARD_SCRIPT}")


def _sources() -> dict[str, str]:
    texts = {"card": _card_prompt()}
    for path in sorted(LIVE_PROMPTS.glob("*.md")):
        texts[path.stem] = re.sub(r"^<!--.*?-->\s*", "", path.read_text(encoding="utf-8"),
                                  flags=re.DOTALL)
    return {key: re.sub(r"\s+", " ", value) for key, value in texts.items()}


SOURCES = _sources()

# The rules Phase 3 must never let a skill replace: they stay verbatim in the prompts that gate
# behaviour, because a skill is loaded on demand and may not load on a given turn.
HARD_RULES: dict[str, dict[str, str]] = {
    "paper only, live trading forbidden": {
        "card": "Paper only; live trading is forbidden",
        "desk": "Live/crypto remain unavailable/forbidden",
        "executor": "exact paper RTH limit order",
        "auditor": "no live/crypto/reset",
        "researcher": "paper-trading desk",
    },
    "the executor is the only broker writer": {
        "card": "the executor is the only writer",
        "desk": "executor only broker captures",
        "executor": "never independently submit",
    },
    "no submit without same-day envelope, fresh audit and persisted reserve": {
        "card": "persisted before ONE paper regular-session limit order",
        "desk": "same-ET-day exact setup/config/account-bound entry AND exit envelope",
        "executor": "same-ET-day exact setup/config/account-bound entry AND exit envelope",
    },
    "never retry a timed-out submit": {
        "card": "Timeouts, partial fills and uncertain statuses block retry",
        "desk": "unmatched requests block retry",
        "executor": "unmatched requests block retry",
    },
    "never invent operator or auditor references": {
        "card": "Never invent references and never claim a fill or approval that did not occur",
        "desk": "Never invent operator or auditor references",
        "executor": "Never invent operator or auditor references",
        "auditor": "invent operator/auditor references",
    },
    "redact account ids and tokens everywhere": {
        "card": "redact account ids and tokens",
        "auditor": "Do not expose full account IDs or credentials",
        "executor": "No credentials, tokens or full account IDs in reports",
        "researcher": "Keep credentials, tokens and full account IDs out of reports",
    },
    "the auditor judges from evidence, not from pressure": {
        "auditor": "the independent Risk Auditor",
        "auditor_standalone": "do not approve or plan",
        "card": "fresh independent exact-order audit",
    },
    "the 12:05 fire submits nothing": {
        "card": "12:05 is the midday protection fire and submits nothing",
        "card_may_not": "It may not open, change or close any position",
    },
}


@pytest.mark.parametrize("rule", sorted(HARD_RULES))
def test_hard_rules_stay_verbatim_in_the_live_prompts(rule: str):
    missing = []
    for source, phrase in HARD_RULES[rule].items():
        name = source.split("_")[0] if source.split("_")[0] in SOURCES else source
        carrier = SOURCES.get(name) or SOURCES.get("card", "")
        if phrase not in carrier:
            missing.append(f"{source}: {phrase!r}")
    assert not missing, f"hard rule lost from the live prompts - {rule} -> {missing}"


def _env_values() -> dict[str, str]:
    """Keys from the local gitignored .env, if it exists; empty in CI so nothing is required."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def test_live_prompt_snapshots_are_present_and_secret_free():
    assert set(SOURCES) >= {"card", "desk", "researcher", "auditor", "executor"}
    secret_patterns = {
        "telegram bot token": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{20,}\b"),
        "bearer token": re.compile(r"Bearer\s+[A-Za-z0-9_\-]{16,}"),
        "personal access token": re.compile(r"\b(pat|ghp|github_pat)_[A-Za-z0-9]{16,}"),
        # Account and chat ids are bare long numbers; ISO dates use separators, so this stays quiet
        # on prose and only fires on an id. Anything from .env is checked by value as well.
        "bare long number": re.compile(r"\b\d{7,}\b"),
    }
    for label, value in _env_values().items():
        if label.endswith("IDS"):
            for ident in (part.strip() for part in value.split(",")):
                if ident.isdigit() and len(ident) >= 6:
                    secret_patterns[f"{label} value"] = re.compile(rf"\b{ident}\b")
    leaks = []
    for path in sorted(LIVE_PROMPTS.glob("*.md")) + [CARD_SCRIPT]:
        text = path.read_text(encoding="utf-8")
        for label, pattern in secret_patterns.items():
            if pattern.search(text):
                leaks.append(f"{path.name}: {label}")
    assert not leaks, f"secret material committed into the prompt snapshots: {leaks}"
