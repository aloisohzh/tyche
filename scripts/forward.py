"""Minimal Qoder Forward API client. PAT from gitignored .env, server-side only."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.qoder.com/api/v1/forward"
TERMINAL = {"confirmed", "expired", "denied", "error"}


def pat() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("QODER_PAT="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
    raise SystemExit("QODER_PAT missing from .env")


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        request = urllib.request.Request(
            BASE + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {pat()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2**attempt)
                continue
            raise SystemExit(f"HTTP {error.code}: {error.read().decode()[:500]}")
    raise SystemExit("retries exhausted")


def main() -> None:
    command = sys.argv[1]
    if command == "get":
        print(json.dumps(req("GET", sys.argv[2]), indent=2))
    elif command == "post":
        body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        print(json.dumps(req("POST", sys.argv[2], body), indent=2))
    elif command == "delete":
        print(json.dumps(req("DELETE", sys.argv[2]), indent=2))
    elif command == "env-set":
        path = sys.argv[2]
        merged = dict(req("GET", path).get("environment_variables") or {})
        values = {}
        for line in (ROOT / ".env").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        for key in sys.argv[3:]:
            if not values.get(key):
                raise SystemExit(f"{key} missing from .env")
            merged[key] = values[key]
        result = req("POST", path, {"environment_variables": merged})
        print("env keys:", sorted((result.get("environment_variables") or {}).keys()))
        print("updated_at:", result.get("updated_at"))
    elif command == "qr":
        session = req("POST", f"/channels/{sys.argv[2]}/qr_sessions", {})
        image = session.get("qr_code_image_base64") or ""
        if image.startswith("data:"):
            image = image.split(",", 1)[1]
        out = ROOT / "plans" / (sys.argv[3] if len(sys.argv) > 3 else "channel-qr.png")
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(base64.b64decode(image))
        print(json.dumps({k: session.get(k) for k in
                          ("session_key", "channel_id", "status", "expires_at")}, indent=2))
        print(f"QR image saved: {out}")
        print("image_sha256:", hashlib.sha256(out.read_bytes()).hexdigest()[:16])
        content = session.get("qr_code_content") or ""
        parsed = urllib.parse.urlparse(content)
        print("content_url:", parsed.scheme + "://" + parsed.netloc + parsed.path,
              "| query_keys:", sorted(urllib.parse.parse_qs(parsed.query)),
              "| embeds_session_key:", bool(session.get("session_key")) and session["session_key"] in content)
    elif command == "poll":
        key = sys.argv[2]
        deadline = time.time() + float(sys.argv[3] if len(sys.argv) > 3 else 240)
        last = None
        while time.time() < deadline:
            session = req("GET", f"/qr_sessions/{key}")
            status = session.get("status")
            if status != last:
                stamp = time.strftime("%H:%M:%S", time.gmtime())
                print(f"{stamp}Z qr status={status} err={session.get('err_code')} {session.get('err_msg') or ''}", flush=True)
                last = status
            if status in TERMINAL:
                raise SystemExit(0 if status == "confirmed" else 1)
            time.sleep(3)
        print("poll timeout", flush=True)
        raise SystemExit(2)
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()