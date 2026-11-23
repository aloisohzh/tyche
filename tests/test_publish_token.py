"""The publish step's GitHub token must be cleaned, checked and the only credential git sees.

2026-11-23: the first unattended publish failed with "invalid token" although the same token answered
200 with permissions.push on the laptop. Nothing in the chain named the cause, so the chain now cleans
the value, asks GitHub about it before pushing, and keeps stored helpers out of the way.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def publish():
    return _load("publish_desk_data")


@pytest.fixture(scope="module")
def deploy():
    return _load("deploy_two_fire_automation")


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("github_pat_abc", "github_pat_abc"),
        ('"github_pat_abc"', "github_pat_abc"),
        ("'github_pat_abc'  \n", "github_pat_abc"),
        (" github_pat_abc\r\n", "github_pat_abc"),
        ('"github_pat_abc', '"github_pat_abc'),  # an unmatched quote is left alone: it is not a quoting habit
        (None, ""),
    ],
)
def test_clean_token_strips_whitespace_and_one_pair_of_quotes(publish, raw, clean):
    assert publish.clean_token(raw) == clean


def test_token_shape_names_kind_and_length_but_never_the_value(publish):
    token = "github_pat_11AAAA_secretsecretsecret"
    shape = publish.token_shape(token)
    assert shape == f"github_pat_..., {len(token)} chars"
    assert "secret" not in shape
    assert publish.token_shape('"oops"') == "unrecognised prefix, 6 chars"


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://github.com/aloisohzh/tyche.git", "aloisohzh/tyche"),
        ("https://github.com/aloisohzh/tyche", "aloisohzh/tyche"),
        ("https://x-access-token:ghp_mount@github.com/aloisohzh/tyche.git", "aloisohzh/tyche"),
        ("git@github.com:aloisohzh/tyche.git", "aloisohzh/tyche"),
        ("https://gitlab.com/aloisohzh/tyche.git", None),
        ("https://github.com/aloisohzh", None),
    ],
)
def test_repo_slug_reads_every_github_remote_spelling(publish, url, slug):
    assert publish.repo_slug(url) == slug


def test_https_remote_drops_an_embedded_credential_when_a_token_is_set(publish, monkeypatch):
    class Done:
        stdout = "https://x-access-token:ghp_mount@github.com/aloisohzh/tyche.git\n"

    monkeypatch.setattr(publish, "git", lambda *args, **kwargs: Done())
    monkeypatch.setenv("TYCHE_GITHUB_PAT", "github_pat_live")
    assert publish.https_remote() == "https://github.com/aloisohzh/tyche.git"
    monkeypatch.delenv("TYCHE_GITHUB_PAT")
    assert publish.https_remote() == Done.stdout.strip()  # without a token the remote is used as is


def test_git_disables_stored_credential_helpers_only_when_a_token_is_set(publish, monkeypatch):
    calls = []

    class Done:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr(publish.subprocess, "run", fake_run)
    monkeypatch.setattr(publish, "_askpass", dict)
    monkeypatch.delenv("TYCHE_GITHUB_PAT", raising=False)
    monkeypatch.delenv("TYCHE_GIT_PAT", raising=False)
    publish.git("status")
    assert calls[-1] == ["git", "status"]
    monkeypatch.setenv("TYCHE_GIT_PAT", "ghp_x")
    publish.git("status")
    assert calls[-1] == ["git", "-c", "credential.helper=", "status"]


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen_returning(payload: dict):
    def fake(request, timeout=0):
        fake.headers = dict(request.header_items())
        return _Response(json.dumps(payload).encode())
    return fake


def test_probe_reports_push_permission_and_sends_the_token_only_as_a_header(publish, monkeypatch):
    fake = _urlopen_returning({"permissions": {"push": True}})
    monkeypatch.setattr(publish.urllib.request, "urlopen", fake)
    verdict = publish.github_token_probe("github_pat_live", "aloisohzh/tyche")
    assert verdict == {"ok": True, "status": 200, "push": True, "detail": "token accepted, may push to aloisohzh/tyche"}
    assert fake.headers["Authorization"] == "Bearer github_pat_live"
    assert "github_pat_live" not in json.dumps(verdict)


def test_probe_says_when_a_token_is_accepted_but_read_only(publish, monkeypatch):
    monkeypatch.setattr(publish.urllib.request, "urlopen", _urlopen_returning({"permissions": {"push": False, "pull": True}}))
    verdict = publish.github_token_probe("github_pat_ro", "aloisohzh/tyche")
    assert verdict["ok"] is False and verdict["status"] == 200 and verdict["push"] is False
    assert "Contents: read and write" in verdict["detail"]


def test_probe_names_a_rejected_token_without_echoing_it(publish, monkeypatch):
    def refuse(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"message": "Bad credentials"}'))

    monkeypatch.setattr(publish.urllib.request, "urlopen", refuse)
    verdict = publish.github_token_probe("ghp_bad", "aloisohzh/tyche")
    assert verdict == {"ok": False, "status": 401, "push": None, "detail": "GitHub rejected the token: HTTP 401 Bad credentials"}


def test_probe_tells_a_network_failure_apart_from_a_refusal(publish, monkeypatch):
    def offline(request, timeout=0):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(publish.urllib.request, "urlopen", offline)
    verdict = publish.github_token_probe("ghp_x", "aloisohzh/tyche")
    assert verdict["ok"] is False and verdict["status"] == 0 and "not reached" in verdict["detail"]


def test_dotenv_parser_unquotes_values_and_warns_on_duplicate_keys(deploy):
    values, warnings = deploy.parse_dotenv(
        "# comment\nQODER_PAT=\"qp\"\nTYCHE_GITHUB_PAT=github_pat_old\nTYCHE_GITHUB_PAT='github_pat_new'\nEMPTY=\n"
    )
    assert values["QODER_PAT"] == "qp"
    assert values["TYCHE_GITHUB_PAT"] == "github_pat_new"
    assert values["EMPTY"] == ""
    assert warnings == ["WARNING: TYCHE_GITHUB_PAT appears 2 times in .env; the LAST line wins - delete the stale one"]
    assert deploy.parse_dotenv("A=1\nB=2\n")[1] == []


def test_publish_token_check_reuses_the_publish_probe_and_hides_the_value(deploy, publish, monkeypatch):
    seen = {}

    def fake_probe(token, slug, timeout=20):
        seen["token"], seen["slug"] = token, slug
        return {"ok": True, "status": 200, "push": True, "detail": "fine"}

    fake_module = type("M", (), {"clean_token": publish.clean_token, "token_shape": publish.token_shape,
                                 "github_token_probe": staticmethod(fake_probe)})
    monkeypatch.setattr(deploy, "_publish_module", lambda: fake_module)
    check = deploy.publish_token_check('"github_pat_quoted"')
    assert seen == {"token": "github_pat_quoted", "slug": deploy.GITHUB_REPO}
    assert check["ok"] is True and check["shape"] == "github_pat_..., 17 chars"
    assert "github_pat_quoted" not in json.dumps(check)
