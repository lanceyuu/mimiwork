"""QualiTaTi account client: sign in once, spend your credits from MimiWork.

Flow (all local; the only network peer is the QualiTaTi API):

1. `login(username, password)` → `POST /api/login` (form-encoded). Two outcomes:
   a normal `access_token`, or `mfa_required` — then `verify_mfa(code)` finishes.
2. On success the JWT is stored under `qualitati:auth`, and a **personal API key**
   is minted via `POST /api/keys` and written into `provider:qualitati` together
   with the gateway base URL. The provider needs the API key, not the JWT: JWTs
   expire in days, personal keys don't — sign in once, keep working.
3. `status()` → `GET /api/user/profile` with the stored credential: username,
   plan, and the live credit balance for the Settings card.
4. `logout()` deletes both secret profiles. The remote API key is revoked too
   (best effort — local sign-out must succeed even when offline).

Passwords are used for the login call and never stored. Everything rides the
SecretStore, next to every other provider credential.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://starfish-app-73rfk.ondigitalocean.app"
AUTH_PROFILE = "qualitati:auth"
PROVIDER_PROFILE = "provider:qualitati"
KEY_NAME = "MimiWork desktop"
_TIMEOUT = 20.0


class QualitatiClient:
    def __init__(self, secrets: Any, base_url: str = DEFAULT_BASE) -> None:
        self.secrets = secrets
        self.base = base_url.rstrip("/")

    # ── auth ────────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Password sign-in. Returns {ok, mfa_required?} — never the token itself."""
        username = (username or "").strip()
        if not username or not password:
            return {"ok": False, "error": "username and password are required"}
        try:
            r = httpx.post(
                f"{self.base}/api/login",
                data={"username": username, "password": password},
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"could not reach QualiTaTi: {e}"}
        if r.status_code != 200:
            detail = _detail(r)
            return {"ok": False, "error": detail or f"login failed (HTTP {r.status_code})"}
        body = _json_object(r)
        if body is None:
            return {"ok": False, "error": "unexpected response from QualiTaTi"}
        if body.get("mfa_required"):
            # No token yet; remember who is mid-MFA so verify_mfa needs only the code.
            self.secrets.put(AUTH_PROFILE, {"pending_mfa_username": username, "base_url": self.base})
            return {"ok": True, "mfa_required": True}
        token = body.get("access_token")
        if not token:
            return {"ok": False, "error": "unexpected login response (no token)"}
        return self._finish_login(username, token)

    def verify_mfa(self, code: str) -> dict[str, Any]:
        pending = (self.secrets.get(AUTH_PROFILE) or {}).get("pending_mfa_username")
        if not pending:
            return {"ok": False, "error": "no sign-in awaiting an MFA code — start again"}
        try:
            r = httpx.post(
                f"{self.base}/api/login/verify-mfa",
                json={"username": pending, "code": (code or "").strip()},
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"could not reach QualiTaTi: {e}"}
        body = _json_object(r)
        if r.status_code != 200 or not body or not body.get("access_token"):
            return {"ok": False, "error": _detail(r) or "invalid MFA code"}
        return self._finish_login(pending, body["access_token"])

    def register(
        self,
        username: str,
        email: str,
        password: str,
        referrer_code: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a QualiTaTi account from inside the app (mirrors qualitati.com/register).

        Same loopback contract as login: the password travels to QualiTaTi and is
        never stored. QualiTaTi emails a verification link; the user signs in
        after clicking it, so this returns {ok, message, email_sent} — never a
        token. Server-side validation (username/email taken, password policy)
        comes back verbatim as `error` so the form can show the real reason.
        """
        username = (username or "").strip()
        email = (email or "").strip()
        if not username or not email or not password:
            return {"ok": False, "error": "username, email and password are required"}
        payload: dict[str, Any] = {"username": username, "email": email, "password": password}
        code = (referrer_code or "").strip().upper()
        if code:
            payload["referrer_code"] = code
        try:
            r = httpx.post(f"{self.base}/api/register", json=payload, timeout=_TIMEOUT)
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"could not reach QualiTaTi: {e}"}
        if r.status_code != 200:
            return {"ok": False, "error": _detail(r) or f"registration failed (HTTP {r.status_code})"}
        body = _json_object(r)
        if body is None:
            return {"ok": False, "error": "unexpected response from QualiTaTi"}
        return {
            "ok": True,
            "username": username,
            "email_sent": bool(body.get("email_sent", True)),
            "message": body.get("message")
            or "Account created — check your email to verify it, then sign in.",
        }

    def _finish_login(self, username: str, token: str) -> dict[str, Any]:
        """Store the JWT, mint the durable API key, configure the provider."""
        self.secrets.put(
            AUTH_PROFILE, {"username": username, "access_token": token, "base_url": self.base}
        )
        headers = {"Authorization": f"Bearer {token}"}
        api_key: Optional[str] = None
        key_id: Optional[int] = None
        try:
            r = httpx.post(
                f"{self.base}/api/keys", json={"name": KEY_NAME}, headers=headers, timeout=_TIMEOUT
            )
            if r.status_code == 200:
                body = _json_object(r) or {}
                # The raw key is shown exactly once, under `key`.
                api_key = body.get("key") or body.get("api_key")
                key_id = body.get("id")
        except httpx.HTTPError as e:
            logger.warning("qualitati: API key mint failed: %s", e)

        if api_key:
            self.secrets.put(
                PROVIDER_PROFILE,
                {
                    "api_key": api_key,
                    "base_url": f"{self.base}/api/llm/v1",
                    "key_set_at": __import__("datetime").date.today().isoformat(),
                    "qualitati_key_id": key_id,
                },
            )
        else:
            # Signed in but keyless (endpoint down?): the account card still works;
            # the provider will be configured on the next successful sign-in.
            logger.warning("qualitati: signed in without a provider key")

        profile = self._profile(headers)
        return {
            "ok": True,
            "signed_in": True,
            "provider_configured": bool(api_key),
            **({"profile": profile} if profile else {}),
        }

    def logout(self) -> dict[str, Any]:
        auth = self.secrets.get(AUTH_PROFILE) or {}
        provider = self.secrets.get(PROVIDER_PROFILE) or {}
        key_id = provider.get("qualitati_key_id")
        token = auth.get("access_token")
        if key_id and token:
            try:  # best effort — sign-out must work offline
                httpx.delete(
                    f"{self.base}/api/keys/{key_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=_TIMEOUT,
                )
            except httpx.HTTPError:
                pass
        self.secrets.delete(AUTH_PROFILE)
        self.secrets.delete(PROVIDER_PROFILE)
        return {"ok": True, "signed_in": False}

    # ── status ──────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Signed-in state + live profile (credits) for the Settings card."""
        auth = self.secrets.get(AUTH_PROFILE) or {}
        provider = self.secrets.get(PROVIDER_PROFILE) or {}
        if not auth.get("access_token") and not provider.get("api_key"):
            return {"ok": True, "signed_in": False}

        # Prefer the durable API key; fall back to the JWT while it lives.
        headers: dict[str, str] = {}
        if provider.get("api_key"):
            headers["X-API-Key"] = provider["api_key"]
        elif auth.get("access_token"):
            headers["Authorization"] = f"Bearer {auth['access_token']}"

        profile = self._profile(headers)
        if profile is None:
            return {
                "ok": True,
                "signed_in": True,
                "username": auth.get("username"),
                "provider_configured": bool(provider.get("api_key")),
                "error": "could not refresh the balance — check your connection",
            }
        return {
            "ok": True,
            "signed_in": True,
            "provider_configured": bool(provider.get("api_key")),
            "profile": profile,
        }

    def _profile(self, headers: dict[str, str]) -> Optional[dict[str, Any]]:
        try:
            r = httpx.get(f"{self.base}/api/user/profile", headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        body = _json_object(r)
        if body is None:
            return None
        return {
            "username": body.get("username"),
            "email": body.get("email"),
            "credits": body.get("credits"),
            "plan": body.get("plan"),
        }


def _json_object(r: httpx.Response) -> Optional[dict[str, Any]]:
    """Decode an API response without letting an HTML/proxy body crash the app."""
    try:
        body = r.json()
    except (TypeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _detail(r: httpx.Response) -> Optional[str]:
    try:
        detail = r.json().get("detail")
    except Exception:
        return None
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail) if detail else None
