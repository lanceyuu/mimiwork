"""QualiTaTi account client: sign-in outcomes, key minting, and what gets stored.

The invariant that matters most: after a successful sign-in the `provider:qualitati`
profile holds a durable API key + the gateway base URL — that is what makes the
"Mimi Hound · QualiTaTi credits" model actually work — and after sign-out neither secret
profile survives.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from coworker.qualitati import (
    AUTH_PROFILE,
    PROVIDER_PROFILE,
    QualitatiClient,
)
from coworker.server import SessionManager, create_app


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


def test_legacy_qualitati_ids_keep_vision():
    """Sessions bound before the tier rename hold 'qualitati:mimi' — the gateway
    routes their images to a multimodal leg, so the engine must not strip them."""
    from coworker.providers.capabilities import capabilities_for

    for legacy in ("qualitati:mimi", "qualitati:hound", "qualitati:wolf"):
        assert capabilities_for(legacy).vision, legacy
    assert not capabilities_for("qualitati:puppy").vision
    assert not capabilities_for("qualitati:deepseek-v4-flash").vision


# -- in-app registration (mirrors qualitati.com/register) --------------------------


def test_register_posts_json_and_never_stores_anything(monkeypatch, secrets):
    fake = wire(monkeypatch, {
        ("POST", "/api/register"): (200, {
            "success": True,
            "message": "Registration successful! Please check your email to verify your account.",
            "email_sent": True,
        }),
    })
    result = QualitatiClient(secrets).register(" newbie ", "n@example.com", "Str0ng!pw", "abc12")

    assert result["ok"] and result["email_sent"] and result["username"] == "newbie"
    assert "verify" in result["message"].lower()
    method, url, kw = fake.calls[0]
    assert url.endswith("/api/register")
    assert kw["json"] == {
        "username": "newbie", "email": "n@example.com", "password": "Str0ng!pw",
        "referrer_code": "ABC12",  # invite codes are upper-case server-side
    }
    assert secrets.store == {}  # no token, no password, nothing persisted


def test_register_without_invite_code_omits_the_field(monkeypatch, secrets):
    fake = wire(monkeypatch, {("POST", "/api/register"): (200, {"success": True, "email_sent": True})})
    QualitatiClient(secrets).register("a", "a@b.co", "pw", "")
    assert "referrer_code" not in fake.calls[0][2]["json"]


def test_register_surfaces_the_servers_reason(monkeypatch, secrets):
    wire(monkeypatch, {
        ("POST", "/api/register"): (400, {"detail": "Password must contain at least one uppercase letter"}),
    })
    result = QualitatiClient(secrets).register("a", "a@b.co", "weak")
    assert not result["ok"]
    assert result["error"] == "Password must contain at least one uppercase letter"


def test_register_requires_all_three_fields(secrets):
    assert not QualitatiClient(secrets).register("a", "", "pw")["ok"]


def test_register_non_json_success_is_a_clean_error(monkeypatch, secrets):
    """A proxy/CDN HTML response must not turn the loopback endpoint into a 500."""
    import coworker.qualitati as mod

    def bad_json():
        raise ValueError("not JSON")

    monkeypatch.setattr(
        mod,
        "httpx",
        SimpleNamespace(
            post=lambda *_a, **_kw: SimpleNamespace(status_code=200, json=bad_json),
            HTTPError=Exception,
            Response=SimpleNamespace,
        ),
    )

    result = QualitatiClient(secrets).register("newbie", "n@example.com", "Str0ng!pw")

    assert result == {"ok": False, "error": "unexpected response from QualiTaTi"}


def test_non_json_profile_does_not_undo_a_successful_login(monkeypatch, secrets):
    """Profile refresh is optional after auth + durable provider-key creation succeed."""
    import coworker.qualitati as mod

    def post(url, **_kwargs):
        if url.endswith("/api/login"):
            return SimpleNamespace(status_code=200, json=lambda: {"access_token": "jwt"})
        if url.endswith("/api/keys"):
            return SimpleNamespace(status_code=200, json=lambda: {"id": 7, "key": "qt_key"})
        raise AssertionError(url)

    def bad_json():
        raise ValueError("not JSON")

    monkeypatch.setattr(
        mod,
        "httpx",
        SimpleNamespace(
            post=post,
            get=lambda *_a, **_kw: SimpleNamespace(status_code=200, json=bad_json),
            HTTPError=Exception,
            Response=SimpleNamespace,
        ),
    )

    result = QualitatiClient(secrets).login("newbie", "Str0ng!pw")

    assert result == {"ok": True, "signed_in": True, "provider_configured": True}
    assert secrets.store[AUTH_PROFILE]["access_token"] == "jwt"
    assert secrets.store[PROVIDER_PROFILE]["api_key"] == "qt_key"


def test_a_name_clash_on_the_key_does_not_leave_the_user_without_models(monkeypatch, secrets):
    """The reported failure (2026-08-24): signed in, credits visible, and no Mimi models —
    because the account already had a key called "MimiWork desktop" (another computer, an
    earlier install) and the plain create was refused. The raw secret of that key can't be
    read back, so the mint retries under a name of its own instead of giving up."""
    attempts: list[str] = []

    def keys(kwargs):
        name = kwargs["json"]["name"]
        attempts.append(name)
        if name == "MimiWork desktop":
            return 400, {"detail": "An API key with this name already exists"}
        return 200, {"id": 11, "key": "qt_second"}

    wire(monkeypatch, {
        ("POST", "/api/login"): (200, {"access_token": "jwt-abc"}),
        ("POST", "/api/keys"): keys,
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    result = QualitatiClient(secrets).login("shubin", "pw")

    assert result["provider_configured"] is True
    assert secrets.store[PROVIDER_PROFILE]["api_key"] == "qt_second"
    assert len(attempts) >= 2 and attempts[0] == "MimiWork desktop"
    assert attempts[1] != attempts[0]  # a name of its own, not the same one again


def test_a_refusal_that_is_not_a_name_clash_is_not_retried(monkeypatch, secrets):
    """A 403 means the account may not mint keys at all; hammering it helps nobody."""
    attempts: list[str] = []

    def keys(kwargs):
        attempts.append(kwargs["json"]["name"])
        return 403, {"detail": "not allowed"}

    wire(monkeypatch, {
        ("POST", "/api/login"): (200, {"access_token": "jwt-abc"}),
        ("POST", "/api/keys"): keys,
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    result = QualitatiClient(secrets).login("shubin", "pw")
    assert result["provider_configured"] is False and len(attempts) == 1
    assert PROVIDER_PROFILE not in secrets.store


def test_reconnect_mints_the_key_without_asking_for_the_password_again(monkeypatch, secrets):
    """Signed in but keyless is repairable: the sign-in worked, only the key didn't."""
    secrets.put(AUTH_PROFILE, {"username": "shubin", "access_token": "jwt-abc"})
    wire(monkeypatch, {
        ("POST", "/api/keys"): (200, {"id": 12, "key": "qt_repaired"}),
        ("GET", "/api/user/profile"): (200, PROFILE_BODY),
    })
    client = QualitatiClient(secrets)
    assert client.status()["provider_configured"] is False

    assert client.ensure_provider_key() == {"ok": True, "provider_configured": True}
    assert secrets.store[PROVIDER_PROFILE]["api_key"] == "qt_repaired"
    assert client.status()["provider_configured"] is True
    # Already keyed: a second call is a no-op, not another key on the account.
    assert client.ensure_provider_key()["ok"] is True


def test_reconnect_without_a_sign_in_says_so(secrets):
    out = QualitatiClient(secrets).ensure_provider_key()
    assert not out["ok"] and out["error"] == "not signed in"


def test_reconnect_that_still_fails_explains_where_to_look(monkeypatch, secrets):
    secrets.put(AUTH_PROFILE, {"username": "shubin", "access_token": "jwt-abc"})
    wire(monkeypatch, {("POST", "/api/keys"): (403, {"detail": "nope"})})
    out = QualitatiClient(secrets).ensure_provider_key()
    assert not out["ok"] and "qualitati.com" in out["error"]


# -- the Mimi tiers, testable from the account card -----------------------------------


def test_testing_a_model_asks_it_to_answer_and_reports_what_came_back(tmp_path):
    """Listing a provider's catalog proves the key works; only a real completion proves the
    tier does. The card's Test button needs the second thing."""
    from types import SimpleNamespace

    calls: list[dict] = []

    class _Speaking:
        def complete(self, **kw):
            calls.append(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=" ready "))]
            )

        def capabilities(self, model):
            from coworker.providers import ModelCapabilities

            return ModelCapabilities()

    manager = SessionManager(workspace=tmp_path, provider=_Speaking())
    client = TestClient(create_app(manager))
    out = client.post("/v1/models/test", json={"model": "qualitati:mimi-puppy"}).json()
    assert out == {"ok": True, "model": "qualitati:mimi-puppy", "reply": "ready"}
    assert calls[0]["model"] == "qualitati:mimi-puppy" and calls[0]["max_tokens"] == 16


def test_a_tier_that_refuses_is_reported_in_words_the_user_can_act_on(tmp_path):
    class _Refusing:
        def complete(self, **kw):
            raise RuntimeError(
                "Error code: 404 - {'error': {'message': 'The model `mimi-wolf` does not "
                "exist or you do not have access to it.'}}"
            )

        def capabilities(self, model):
            from coworker.providers import ModelCapabilities

            return ModelCapabilities()

    client = TestClient(create_app(SessionManager(workspace=tmp_path, provider=_Refusing())))
    out = client.post("/v1/models/test", json={"model": "qualitati:mimi-wolf"}).json()
    assert not out["ok"]
    assert "access" in out["error"].lower() or "mimi-wolf" in out["error"]
