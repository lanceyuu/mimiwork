"""Report this problem → the QualiTaTi contact form, with the log tail (owner ask 2026-09-21)."""
from types import SimpleNamespace

import httpx

from coworker import qualitati as mod


class _Secrets:
    def __init__(self, d):
        self.d = d

    def get(self, k):
        return self.d.get(k)


def _fake_post(calls, status=200):
    def post(url, json=None, timeout=None, **_):
        calls.append((url, json))
        return httpx.Response(status, json={"status": "sent"}, request=httpx.Request("POST", url))
    return post


def test_report_posts_error_version_and_log(monkeypatch, tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "openworker-server.log").write_text("boot\nTraceback: engine exploded\n")
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=_fake_post(calls), HTTPError=httpx.HTTPError))
    secrets = _Secrets({"qualitati:auth": {"username": "shubin", "access_token": "jwt", "base_url": "https://qualitati.com"}})
    monkeypatch.setattr(mod.QualitatiClient, "_profile", lambda self, h: {"email": "s@x.org"})

    res = mod.report_problem(secrets, "could not open the conversation: boom", "connection")

    assert res == {"ok": True}
    url, body = calls[0]
    assert url == "https://qualitati.com/api/contact"
    assert body["name"] == "shubin" and body["email"] == "s@x.org"
    assert body["subject"].startswith("[MimiWork bug] could not open")
    assert "engine exploded" in body["message"]
    assert "MimiWork " in body["message"] and "connection" in body["message"]


def test_report_without_sign_in_still_sends(monkeypatch, tmp_path):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=_fake_post(calls), HTTPError=httpx.HTTPError))
    res = mod.report_problem(_Secrets({}), "x")
    assert res["ok"] and calls[0][1]["name"] == "MimiWork user" and "(no log)" in calls[0][1]["message"]


def test_report_failure_is_friendly(monkeypatch, tmp_path):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=_fake_post([], status=500), HTTPError=httpx.HTTPError))
    assert mod.report_problem(_Secrets({}), "x")["ok"] is False
