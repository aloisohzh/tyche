"""Bake the tyche desk dashboard into a redacted static Qoder Site.

Reuses dashboard/server.py's builders (journal-derived state + live Forward
automation + market calendar), scrubs full account ids, and writes a
self-contained static site under desk-site/web/ that app.js renders in snapshot
mode (window.TYCHE_SNAPSHOT). A hard secret guard refuses to write if any PAT,
Telegram credential, signing secret or full account id appears in the output.

The local dashboard is untouched; only the baked copy carries the snapshot flag.

Run: .venv/Scripts/python.exe scripts/export_dashboard.py [output-dir]
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "dashboard" / "static"
SECRET_KEYS = (
    "QODER_PAT",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_WEBHOOK_SECRET",
    "FORWARD_SIGNING_SECRET",
)


def load_server():
    spec = importlib.util.spec_from_file_location("desk_server", ROOT / "dashboard" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env_values() -> dict[str, str]:
    out: dict[str, str] = {}
    env = ROOT / ".env"
    if not env.is_file():
        return out
    for line in env.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def assert_no_secrets(blob: str, srv, env: dict[str, str]) -> None:
    leaks = []
    for key in SECRET_KEYS:
        value = env.get(key, "")
        if len(value) >= 6 and value in blob:
            leaks.append(key)
    for sid in srv.SENSITIVE:
        if sid in blob:
            leaks.append("account_id:" + srv.mask_id(sid))
    if leaks:
        raise SystemExit("SECRET GUARD FAILED — refusing to write. Leaked: " + ", ".join(leaks))


def main() -> None:
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "desk-site"
    web = out_root / "web"
    srv = load_server()
    env = env_values()

    state = srv.build_state()
    automation = srv.scrub(srv.build_automation())
    built_at = datetime.now(UTC).isoformat()

    state_json = json.dumps(state, ensure_ascii=False, default=str)
    auto_json = json.dumps(automation, ensure_ascii=False, default=str)
    assert_no_secrets(state_json + auto_json, srv, env)

    if web.exists():
        shutil.rmtree(web)
    (web / "data").mkdir(parents=True)
    (web / "data" / "state.json").write_text(state_json, encoding="utf-8")
    (web / "data" / "automation.json").write_text(auto_json, encoding="utf-8")

    shutil.copy2(STATIC / "style.css", web / "style.css")
    shutil.copy2(STATIC / "app.js", web / "app.js")

    snapshot = {"built_at": built_at, "state_url": "data/state.json", "automation_url": "data/automation.json"}
    inject = "<script>window.TYCHE_SNAPSHOT=" + json.dumps(snapshot) + ";</script>\n"
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace('<script src="app.js"></script>', inject + '<script src="app.js"></script>')
    (web / "index.html").write_text(html, encoding="utf-8")

    # Guard the assembled HTML too (injected flag carries no secrets, but verify).
    assert_no_secrets(html, srv, env)

    cal = automation.get("calendar") or {}
    print("SECRET GUARD: PASS (no PAT / Telegram / signing secret / full account id)")
    print("output:", web)
    print("built_at:", built_at)
    print("automation ok:", automation.get("ok"), "| schedules:", len(automation.get("schedules") or []))
    print("calendar phase:", cal.get("phase"), "| run:", cal.get("run"), "| next:", (cal.get("next_run") or {}).get("name"))
    print("state bytes:", len(state_json), "| automation bytes:", len(auto_json))


if __name__ == "__main__":
    main()