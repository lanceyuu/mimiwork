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

# The two QualiTaTi sites are isolated deployments — separate accounts, credits and
# model lineups (质见中国 runs DeepSeek/Qwen domestically). Each is its own model
# provider in the app, so a picked model says where a call goes and whose credits it
# spends: "qualitati:mimi-puppy" is the global account, "qualitati_cn:mimi-puppy" the
# China one. Both can be signed in at once; nothing is shared between them.
SITES: dict[str, dict[str, str]] = {
    "global": {
        "base": DEFAULT_BASE,
        "link": "https://qualitati.com",
        "provider": "qualitati",
        "auth": AUTH_PROFILE,
        "keys": PROVIDER_PROFILE,
        "title": "QualiTaTi",
    },
    "cn": {
        "base": "https://qualitati.cn",
        "link": "https://qualitati.cn",
        "provider": "qualitati_cn",
        "auth": "qualitati_cn:auth",
        "keys": "provider:qualitati_cn",
        "title": "质见中国",
    },
}
MIMI_TIERS = ("mimi-puppy", "mimi-hound", "mimi-wolf", "mimi-werewolf")


def site_for_model(model: Optional[str]) -> Optional[str]:
    """The site a model id belongs to, or None for a non-QualiTaTi model."""
    provider = str(model or "").split(":", 1)[0]
    return next((site for site, d in SITES.items() if d["provider"] == provider), None)


def site_credentials(secrets: Any, site: str) -> dict[str, Any]:
    """{site, base, jwt, api_key} for one site from the stored sign-in — keys may be None."""
    d = SITES.get(site) or SITES["global"]
    auth = secrets.get(d["auth"]) or {}
    keys = secrets.get(d["keys"]) or {}
    auth = auth if isinstance(auth, dict) else {}
    keys = keys if isinstance(keys, dict) else {}
    return {
        "site": site,
        "base": str(auth.get("base_url") or d["base"]).rstrip("/"),
        "jwt": auth.get("access_token"),
        "api_key": keys.get("api_key"),
    }


def signed_in_sites(secrets: Any) -> list[str]:
    return [
        site for site in SITES
        if (lambda c: c["jwt"] or c["api_key"])(site_credentials(secrets, site))
    ]


def tool_site(secrets: Any) -> str:
    """Which site the QualiTaTi data tools talk to: the site of the model answering the
    turn (owner rule 2026-09-11 — a conversation on 质见中国 reads 质见中国 projects, and
    is told to sign in there if it is not), else the one site that is signed in."""
    from .tools.context import tool_model

    wanted = site_for_model(tool_model.get())
    if wanted:
        return wanted
    signed = signed_in_sites(secrets)
    return signed[0] if signed else "global"


class QualitatiClient:
    def __init__(self, secrets: Any, site: str = "global") -> None:
        if site not in SITES:
            raise ValueError(f"unknown QualiTaTi site {site!r}")
        self.secrets = secrets
        self.site = site
        self.base = SITES[site]["base"]
        self.auth_profile = SITES[site]["auth"]
        self.provider_profile = SITES[site]["keys"]

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
            self.secrets.put(self.auth_profile, {"pending_mfa_username": username, "base_url": self.base})
            return {"ok": True, "mfa_required": True}
        token = body.get("access_token")
        if not token:
            return {"ok": False, "error": "unexpected login response (no token)"}
        return self._finish_login(username, token)

    def verify_mfa(self, code: str) -> dict[str, Any]:
        pending = (self.secrets.get(self.auth_profile) or {}).get("pending_mfa_username")
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

    def _mint_key(self, headers: dict[str, str]) -> tuple[Optional[str], Optional[int]]:
        """Create the gateway API key the Mimi models are billed through.

        Retried under a machine-specific name: an account that already carries a key called
        "MimiWork desktop" (a second computer, an earlier install) can have the plain create
        refused, and the raw secret of the existing key is not retrievable — which left the
        user signed in with no key, and therefore no Mimi models in the picker, with nothing
        on screen saying why (user report 2026-08-24). A fresh name sidesteps the clash
        without revoking a key another machine may still be using.
        """
        import datetime
        import platform

        host = "".join(c for c in platform.node().split(".")[0] if c.isalnum() or c in "-_")[:24]
        names = [KEY_NAME]
        if host:
            names.append(f"{KEY_NAME} ({host})")
        names.append(f"{KEY_NAME} {datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}")
        for name in names:
            try:
                r = httpx.post(
                    f"{self.base}/api/keys",
                    json={"name": name},
                    headers=headers,
                    timeout=_TIMEOUT,
                )
            except httpx.HTTPError as e:
                logger.warning("qualitati: API key mint failed: %s", e)
                return None, None
            if r.status_code == 200:
                body = _json_object(r) or {}
                # The raw key is shown exactly once, under `key`.
                return body.get("key") or body.get("api_key"), body.get("id")
            if r.status_code not in (400, 409, 422):
                logger.warning("qualitati: API key mint refused (%s)", r.status_code)
                return None, None  # not a name clash — a retry would only repeat it
        logger.warning("qualitati: API key mint refused for every candidate name")
        return None, None

    def _store_provider_key(self, api_key: str, key_id: Optional[int]) -> None:
        import datetime

        self.secrets.put(
            self.provider_profile,
            {
                "api_key": api_key,
                "base_url": f"{self.base}/api/llm/v1",
                "key_set_at": datetime.date.today().isoformat(),
                "qualitati_key_id": key_id,
            },
        )

    def ensure_provider_key(self) -> dict[str, Any]:
        """Mint the gateway key for an account that is signed in without one.

        This is the repair for "I signed in and the Mimi models still aren't there": the
        sign-in itself succeeded, only the key did not, so there is no reason to make the
        user type their password again.
        """
        auth = self.secrets.get(self.auth_profile) or {}
        provider = self.secrets.get(self.provider_profile) or {}
        if provider.get("api_key"):
            return {"ok": True, "provider_configured": True}
        token = auth.get("access_token")
        if not token:
            return {"ok": False, "error": "not signed in", "provider_configured": False}
        api_key, key_id = self._mint_key({"Authorization": f"Bearer {token}"})
        if not api_key:
            return {
                "ok": False,
                "provider_configured": False,
                "error": (
                    "QualiTaTi would not issue a key for this app. Check qualitati.com → "
                    "API keys, then try again."
                ),
            }
        self._store_provider_key(api_key, key_id)
        return {"ok": True, "provider_configured": True}

    def _finish_login(self, username: str, token: str) -> dict[str, Any]:
        """Store the JWT, mint the durable API key, configure the provider."""
        self.secrets.put(
            self.auth_profile, {"username": username, "access_token": token, "base_url": self.base}
        )
        headers = {"Authorization": f"Bearer {token}"}
        api_key, key_id = self._mint_key(headers)
        if api_key:
            self._store_provider_key(api_key, key_id)
        else:
            # Signed in but keyless: the account card says so and offers Reconnect, which
            # retries this without a fresh password.
            logger.warning("qualitati: signed in without a provider key")

        profile = self._profile(headers)
        return {
            "ok": True,
            "signed_in": True,
            "provider_configured": bool(api_key),
            **({"profile": profile} if profile else {}),
        }

    def logout(self) -> dict[str, Any]:
        auth = self.secrets.get(self.auth_profile) or {}
        provider = self.secrets.get(self.provider_profile) or {}
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
        self.secrets.delete(self.auth_profile)
        self.secrets.delete(self.provider_profile)
        return {"ok": True, "signed_in": False}

    # ── status ──────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Signed-in state + live profile (credits) for the Settings card."""
        auth = self.secrets.get(self.auth_profile) or {}
        provider = self.secrets.get(self.provider_profile) or {}
        if not auth.get("access_token") and not provider.get("api_key"):
            return {"ok": True, "signed_in": False, "site": self.site}

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
                "site": self.site,
                "username": auth.get("username"),
                "provider_configured": bool(provider.get("api_key")),
                "error": "could not refresh the balance — check your connection",
            }
        return {
            "ok": True,
            "signed_in": True,
            "site": self.site,
            "provider_configured": bool(provider.get("api_key")),
            "profile": profile,
            # Mimi Puppy's remaining free requests today — so the app can warn before
            # the gateway refuses (owner ask 2026-09-04). None when unavailable.
            "free_tier": self._free_tier(headers),
        }

    def _free_tier(self, headers: dict[str, str]) -> Optional[dict[str, Any]]:
        """{cap, remaining, resets_at} from the gateway's model list, or None."""
        try:
            r = httpx.get(f"{self.base}/api/llm/v1/models", headers=headers, timeout=_TIMEOUT)
            if r.status_code != 200:
                return None
            for m in (r.json() or {}).get("data") or []:
                if (
                    isinstance(m, dict)
                    and str(m.get("id", "")).split(":")[-1] == "mimi-puppy"
                    and m.get("free_daily_cap") is not None
                    and m.get("free_daily_remaining") is not None
                ):
                    from datetime import datetime, timedelta, timezone

                    reset = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    return {
                        "model": m.get("id"),
                        "cap": int(m.get("free_daily_cap") or 0),
                        "remaining": int(m.get("free_daily_remaining") or 0),
                        "resets_at": reset.isoformat(),
                    }
        except Exception:
            return None
        return None

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


_LOG_TAIL_BYTES = 24_000


def _log_tail() -> str:
    """The end of the sidecar log (the desktop shell writes stdout/stderr there)."""
    from .secrets import state_dir

    path = state_dir() / "logs" / "openworker-server.log"
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-_LOG_TAIL_BYTES:].decode("utf-8", "replace")


def report_problem(secrets: Any, error: str, context: str = "", site: str = "global") -> dict[str, Any]:
    """Send an error the user hit to the QualiTaTi team through the site's public contact
    form (it lands in contact@qualitati.com). What goes: the error, where it happened, the
    app version and platform, the signed-in username if any, and the sidecar log tail.
    Nothing is sent without the user pressing the button that calls this."""
    import platform

    from . import __version__

    creds = site_credentials(secrets, site)
    auth = secrets.get((SITES.get(site) or SITES["global"])["auth"]) or {}
    username = str(auth.get("username") or "") if isinstance(auth, dict) else ""
    headers: dict[str, str] = {}
    if creds["jwt"]:
        headers["Authorization"] = f"Bearer {creds['jwt']}"
    profile = QualitatiClient(secrets, site)._profile(headers) if headers else None
    email = str((profile or {}).get("email") or "") or "mimiwork-report@qualitati.com"
    message = "\n".join(
        [
            f"Error: {error}",
            f"Where: {context or '-'}",
            f"MimiWork {__version__} on {platform.platform()}",
            f"User: {username or '(not signed in)'}",
            "",
            "--- sidecar log tail ---",
            _log_tail() or "(no log)",
        ]
    )
    try:
        r = httpx.post(
            f"{creds['base']}/api/contact",
            json={
                "name": username or "MimiWork user",
                "email": email,
                "subject": f"[MimiWork bug] {error[:80]}",
                "message": message,
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"could not reach {creds['base']}: {exc}"}
    if r.status_code != 200:
        return {"ok": False, "error": _detail(r) or f"HTTP {r.status_code}"}
    return {"ok": True}
