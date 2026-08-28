"""The Mimi model-region switch, in the app's own Settings (owner correction
2026-08-28: not on the qualitati.com Profile). The sidecar proxies the account
setting with the stored credential — key first, because the JWT expires."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from test_qualitati_credits import _manager, _urlopen

from coworker.server import create_app


def test_reading_the_region_carries_the_stored_key(tmp_path, monkeypatch):
    seen: list = []
    _urlopen(monkeypatch, {"region": "us", "configured": False}, seen=seen)
    got = _manager(tmp_path).qualitati_region()
    assert got["ok"] is True and got["region"] == "us"
    assert seen[0].full_url == "https://qt.example/api/user/mimiwork-region"
    assert seen[0].headers["X-api-key"] == "qt_key"


def test_setting_the_region_puts_json_and_validates_first(tmp_path, monkeypatch):
    seen: list = []
    _urlopen(monkeypatch, {"region": "eu", "configured": True}, seen=seen)
    manager = _manager(tmp_path)
    got = manager.qualitati_set_region("eu")
    assert got["ok"] is True and got["region"] == "eu"
    request = seen[0]
    assert request.get_method() == "PUT"
    assert json.loads(request.data.decode()) == {"region": "eu"}
    # Garbage never reaches the network.
    assert manager.qualitati_set_region("asia")["error"].startswith("region must")
    assert len(seen) == 1


def test_signed_out_says_so(tmp_path, monkeypatch):
    def boom(*a, **k):  # pragma: no cover
        raise AssertionError("signed out must not reach the network")

    import urllib.request as request_mod

    monkeypatch.setattr(request_mod, "urlopen", boom)
    assert _manager(tmp_path, signed_in=False).qualitati_region()["error"] == "not signed in"


def test_rest_round_trip(tmp_path, monkeypatch):
    _urlopen(monkeypatch, {"region": "eu", "configured": True})
    client = TestClient(create_app(_manager(tmp_path)))
    got = client.get("/v1/qualitati/region")
    assert got.status_code == 200 and got.json()["region"] == "eu"
    put = client.put("/v1/qualitati/region", json={"region": "eu"})
    assert put.status_code == 200 and put.json()["ok"] is True
