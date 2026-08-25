"""What MimiWork spent, on the Activity page.

The number shown has to be the number on the bill, so it comes from the
account's own credit ledger (`source=mimiwork*`) rather than a local estimate of
token cost. The manager's job is only to shape those rows for the page — and to
carry which pool paid, because a team pool and this month's points expire while
purchased credits don't.
"""

from __future__ import annotations

import io
import json
from urllib import error

import pytest
from fastapi.testclient import TestClient

from coworker.qualitati import AUTH_PROFILE, PROVIDER_PROFILE
from coworker.server import SessionManager, create_app

LEDGER = {
    "entries": [
        {
            "id": 9,
            "created_at": "2026-08-25T09:00:00",
            "source": "mimiwork_gateway",
            "delta_credits": -6,
            "metadata": {
                "model": "mimi-wolf",
                "route": "advanced",
                "tokens_in": 200000,
                "tokens_out": 50000,
                "credits_cost": 6,
                "team_points_used": 6,
                "monthly_points_used": 0,
                "lifelong_credits_used": 0,
                "usage_estimated": False,
            },
        },
        {
            "id": 8,
            "created_at": "2026-08-25T08:00:00",
            "source": "mimiwork_free",
            "delta_credits": 0,
            "metadata": {"model": "mimi-puppy", "tokens_in": 900, "tokens_out": 100},
        },
    ],
    "current_credits": 0,
    "monthly_points": 30,
    "team_points": 494,
    "available_balance": 524,
}


def _manager(tmp_path, *, signed_in=True, key=True):
    manager = SessionManager(workspace=tmp_path)
    if signed_in:
        manager.secrets.put(AUTH_PROFILE, {"access_token": "jwt-1", "base_url": "https://qt.example"})
        if key:
            manager.secrets.put(PROVIDER_PROFILE, {"api_key": "qt_key"})
    return manager


def _urlopen(monkeypatch, body, *, seen=None, status=200):
    def fake(req, timeout=None):
        if seen is not None:
            seen.append(req)
        if status >= 400:
            raise error.HTTPError(req.full_url, status, "nope", {}, None)
        return _Ctx(json.dumps(body).encode())

    class _Ctx(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    import urllib.request as request_mod

    monkeypatch.setattr(request_mod, "urlopen", fake)


def test_it_reads_only_this_apps_rows_and_carries_the_stored_key(tmp_path, monkeypatch):
    seen: list = []
    _urlopen(monkeypatch, LEDGER, seen=seen)
    got = _manager(tmp_path).qualitati_credits(limit=50)
    assert got["ok"] is True
    request = seen[0]
    assert request.full_url.startswith("https://qt.example/api/user/credit-ledger")
    assert "source=mimiwork*" in request.full_url
    # The API key outlives the JWT, so it is the credential of choice.
    assert request.headers["X-api-key"] == "qt_key"


def test_the_jwt_is_used_when_no_key_was_minted(tmp_path, monkeypatch):
    seen: list = []
    _urlopen(monkeypatch, LEDGER, seen=seen)
    _manager(tmp_path, key=False).qualitati_credits()
    assert seen[0].headers["Authorization"] == "Bearer jwt-1"


def test_the_totals_are_the_ledgers_own_numbers(tmp_path, monkeypatch):
    _urlopen(monkeypatch, LEDGER)
    got = _manager(tmp_path).qualitati_credits()
    assert got["spent"] == 6 and got["calls"] == 2 and got["free_calls"] == 1


def test_each_row_says_what_it_cost_and_which_pool_paid(tmp_path, monkeypatch):
    _urlopen(monkeypatch, LEDGER)
    rows = _manager(tmp_path).qualitati_credits()["entries"]
    paid, free = rows
    assert paid["credits"] == 6 and paid["team_points"] == 6 and paid["free"] is False
    assert paid["model"] == "mimi-wolf" and paid["tokens_in"] == 200000
    assert free["free"] is True and free["credits"] == 0


def test_the_balance_covers_every_pool_not_just_purchased_credits(tmp_path, monkeypatch):
    """A team member with 0 purchased credits is not out of balance — that was the
    bug this panel has to show honestly."""
    _urlopen(monkeypatch, LEDGER)
    balance = _manager(tmp_path).qualitati_credits()["balance"]
    assert balance == {
        "available": 524,
        "team_points": 494,
        "monthly_points": 30,
        "lifelong_credits": 0,
    }


def test_a_row_without_metadata_still_counts_its_movement(tmp_path, monkeypatch):
    _urlopen(monkeypatch, {"entries": [{"id": 1, "source": "mimiwork_gateway", "delta_credits": -3}]})
    got = _manager(tmp_path).qualitati_credits()
    assert got["spent"] == 3 and got["entries"][0]["credits"] == 3


def test_signed_out_says_so_without_calling_anything(tmp_path, monkeypatch):
    def boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("signed out must not reach the network")

    import urllib.request as request_mod

    monkeypatch.setattr(request_mod, "urlopen", boom)
    got = _manager(tmp_path, signed_in=False).qualitati_credits()
    assert got["ok"] is False and "not signed in" in got["error"]


def test_an_api_failure_is_reported_not_raised(tmp_path, monkeypatch):
    _urlopen(monkeypatch, {}, status=401)
    got = _manager(tmp_path).qualitati_credits()
    assert got["ok"] is False and "credit history unavailable (401)" in got["error"]


@pytest.mark.parametrize("asked,expected", [(0, 50), (5000, 200), (10, 10)])
def test_the_page_size_is_clamped(tmp_path, monkeypatch, asked, expected):
    seen: list = []
    _urlopen(monkeypatch, LEDGER, seen=seen)
    _manager(tmp_path).qualitati_credits(limit=asked)
    assert f"limit={expected}" in seen[0].full_url


def test_the_route_serves_the_shaped_payload(tmp_path, monkeypatch):
    _urlopen(monkeypatch, LEDGER)
    manager = _manager(tmp_path)
    client = TestClient(create_app(manager))
    body = client.get("/v1/qualitati/credits?limit=5").json()
    assert body["ok"] is True and body["spent"] == 6
    assert body["balance"]["available"] == 524
