"""QualiTaTi account client: sign-in outcomes, key minting, and what gets stored.

The invariant that matters most: after a successful sign-in the `provider:qualitati`
profile holds a durable API key + the gateway base URL — that is what makes the
"Mimi Hound · QualiTaTi credits" model actually work — and after sign-out neither secret
profile survives.
"""

from types import SimpleNamespace

import pytest

from coworker.qualitati import (
    AUTH_PROFILE,
    PROVIDER_PROFILE,
    QualitatiClient,
)


class FakeSecrets:
    def __init__(self):
        self.store = {}

    def get(self, profile):
        return self.store.get(profile)

    def put(self, profile, data):
        self.store[profile] = dict(data)

    def delete(self, profile):
        return self.store.pop(profile, None) is not None


class FakeHTTP:
    """Route-table fake for httpx.post/get/delete."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _respond(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for (m, suffix), reply in self.routes.items():
            if m == method and url.endswith(suffix):
                status, body = reply(kwargs) if callable(reply) else reply
                return SimpleNamespace(status_code=status, json=lambda b=body: b)
        raise AssertionError(f"unexpected {method} {url}")

    def post(self, url, **kw):
        return self._respond("POST", url, **kw)

    def get(self, url, **kw):
        return self._respond("GET", url, **kw)

    def delete(self, url, **kw):
        return self._respond("DELETE", url, **kw)


PROFILE_BODY = {
    "id": 1,
    "username": "shubin",
    "email": "s@example.com",
    "credits": 420,
    "plan": "scholar",
}


def wire(monkeypatch, routes):
    fake = FakeHTTP(routes)
    import coworker.qualitati as mod

    monkeypatch.setattr(mod, "httpx", SimpleNamespace(
        post=fake.post, get=fake.get, delete=fake.delete,
        HTTPError=Exception, Response=SimpleNamespace,
    ))
    return fake


@pytest.fixture
def secrets():
    return FakeSecrets()


def test_successful_login_stores_jwt_key_and_provider(monkeypatch, secrets):
    wire(monkeypatch, {
        ("POST", "/api/login"): (200, {"access_token": "jwt-abc", "token_type": "bearer"}),
        ("POST", "/api/keys"): (200, {"id": 7, "key": "qt_secretkey", "warning": "…"}),
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    result = QualitatiClient(secrets).login("shubin", "pw")

    assert result["ok"] and result["signed_in"] and result["provider_configured"]
    assert result["profile"]["credits"] == 420
    assert secrets.store[AUTH_PROFILE]["access_token"] == "jwt-abc"
    provider = secrets.store[PROVIDER_PROFILE]
    assert provider["api_key"] == "qt_secretkey"
    assert provider["base_url"].endswith("/api/llm/v1")
    assert provider["qualitati_key_id"] == 7


def test_wrong_password_is_a_clean_error(monkeypatch, secrets):
    wire(monkeypatch, {
        ("POST", "/api/login"): (401, {"detail": "Incorrect username or password"}),
    })
    result = QualitatiClient(secrets).login("shubin", "nope")
    assert result["ok"] is False
    assert "Incorrect" in result["error"]
    assert AUTH_PROFILE not in secrets.store


def test_password_is_never_persisted(monkeypatch, secrets):
    wire(monkeypatch, {
        ("POST", "/api/login"): (200, {"access_token": "jwt", "token_type": "bearer"}),
        ("POST", "/api/keys"): (200, {"id": 1, "key": "qt_k"}),
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    QualitatiClient(secrets).login("shubin", "hunter2")
    import json

    assert "hunter2" not in json.dumps(secrets.store)


def test_mfa_flow_completes_in_two_steps(monkeypatch, secrets):
    wire(monkeypatch, {
        ("POST", "/api/login"): (200, {"mfa_required": True, "username": "shubin"}),
        ("POST", "/api/login/verify-mfa"): (200, {"access_token": "jwt-mfa"}),
        ("POST", "/api/keys"): (200, {"id": 2, "key": "qt_mfa"}),
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    client = QualitatiClient(secrets)
    first = client.login("shubin", "pw")
    assert first == {"ok": True, "mfa_required": True}
    assert secrets.store[AUTH_PROFILE]["pending_mfa_username"] == "shubin"

    second = client.verify_mfa("123456")
    assert second["ok"] and second["provider_configured"]
    assert secrets.store[PROVIDER_PROFILE]["api_key"] == "qt_mfa"


def test_mfa_without_pending_login_is_an_error(monkeypatch, secrets):
    wire(monkeypatch, {})
    result = QualitatiClient(secrets).verify_mfa("000000")
    assert result["ok"] is False


def test_key_mint_failure_still_signs_in(monkeypatch, secrets):
    """The account card should work even when /api/keys hiccups."""
    wire(monkeypatch, {
        ("POST", "/api/login"): (200, {"access_token": "jwt", "token_type": "bearer"}),
        ("POST", "/api/keys"): (500, {"detail": "boom"}),
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    result = QualitatiClient(secrets).login("shubin", "pw")
    assert result["ok"] and result["signed_in"]
    assert result["provider_configured"] is False
    assert PROVIDER_PROFILE not in secrets.store


def test_status_signed_out(monkeypatch, secrets):
    wire(monkeypatch, {})
    assert QualitatiClient(secrets).status() == {"ok": True, "signed_in": False}


def test_status_prefers_the_durable_api_key(monkeypatch, secrets):
    secrets.put(AUTH_PROFILE, {"username": "shubin", "access_token": "jwt"})
    secrets.put(PROVIDER_PROFILE, {"api_key": "qt_k", "base_url": "x"})
    fake = wire(monkeypatch, {("GET", "/api/user/profile"): (200, PROFILE_BODY)})

    result = QualitatiClient(secrets).status()
    assert result["signed_in"] and result["profile"]["credits"] == 420
    _, _, kwargs = fake.calls[0]
    assert kwargs["headers"] == {"X-API-Key": "qt_k"}  # JWT left unused


def test_status_offline_keeps_the_session(monkeypatch, secrets):
    secrets.put(AUTH_PROFILE, {"username": "shubin", "access_token": "jwt"})
    secrets.put(PROVIDER_PROFILE, {"api_key": "qt_k"})

    def down(kwargs):
        raise Exception("network down")

    import coworker.qualitati as mod

    class NetErr(Exception):
        pass

    monkeypatch.setattr(mod, "httpx", SimpleNamespace(
        get=lambda *a, **k: (_ for _ in ()).throw(NetErr()),
        post=None, delete=None, HTTPError=NetErr,
    ))
    result = QualitatiClient(secrets).status()
    assert result["signed_in"] is True
    assert "error" in result
    assert secrets.store  # nothing was wiped because of a network blip


def test_logout_revokes_the_key_and_wipes_both_profiles(monkeypatch, secrets):
    secrets.put(AUTH_PROFILE, {"username": "shubin", "access_token": "jwt"})
    secrets.put(PROVIDER_PROFILE, {"api_key": "qt_k", "qualitati_key_id": 7})
    fake = wire(monkeypatch, {("DELETE", "/api/keys/7"): (200, {"status": "revoked"})})

    result = QualitatiClient(secrets).logout()
    assert result == {"ok": True, "signed_in": False}
    assert secrets.store == {}
    assert fake.calls[0][0] == "DELETE"


def test_logout_works_offline(monkeypatch, secrets):
    secrets.put(AUTH_PROFILE, {"access_token": "jwt"})
    secrets.put(PROVIDER_PROFILE, {"api_key": "qt_k", "qualitati_key_id": 7})
    import coworker.qualitati as mod

    class NetErr(Exception):
        pass

    monkeypatch.setattr(mod, "httpx", SimpleNamespace(
        delete=lambda *a, **k: (_ for _ in ()).throw(NetErr()),
        post=None, get=None, HTTPError=NetErr,
    ))
    assert QualitatiClient(secrets).logout()["ok"] is True
    assert secrets.store == {}


def test_provider_descriptor_points_at_the_gateway():
    from coworker.providers.registry import get_descriptor

    d = get_descriptor("qualitati")
    assert d is not None
    base = next(f for f in d.fields if f.key == "base_url")
    assert base.default.endswith("/api/llm/v1")


def test_mimi_is_a_curated_model():
    from coworker.providers.matrix import MATRIX

    entry = MATRIX["qualitati:mimi-hound"]
    assert entry.caps.tools  # agent work needs tool calling
