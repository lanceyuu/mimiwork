"""Friendly translation of model access + quota failures.

The picker now defaults to brand-new flagships (GPT-5.6 Sol, Claude Fable 5), and not every
account can use them: OpenAI is still rolling GPT-5.6 out per-organization, and both vendors
reject calls once quota/credits run out. Those failures arrive as terse SDK exceptions
wrapping JSON error bodies; this maps the well-known shapes to one actionable sentence.
Anything unrecognized returns None and the caller surfaces the raw error unchanged.

Matching is on the error BODY text (error codes/types), not just HTTP status — a 404 also
means "wrong base_url" and a 429 also means "slow down", and neither of those should be
dressed up as an access problem.
"""

from __future__ import annotations

import re
from typing import Optional

# Error-body markers, verbatim from the vendors' error codes/messages:
# OpenAI: {"error": {"code": "model_not_found", "message": "The model `X` does not exist or
#   you do not have access to it."}} (404/403) and {"code": "insufficient_quota"} (429).
# Anthropic: {"type": "not_found_error", "message": "model: X"} (404),
#   {"type": "permission_error"} (403), and "credit balance is too low" (400).
_NO_ACCESS = (
    "model_not_found",
    "does not exist or you do not have access",
    "does not have access to model",
    "permission_error",
    "permission denied",
)
_NO_QUOTA = (
    "insufficient_quota",
    "exceeded your current quota",
    "credit balance is too low",
    "billing hard limit",
)


def friendly_model_error(model: str, exc: Exception) -> Optional[str]:
    """One actionable sentence for "your account can't use this model" failures, or None."""
    text = str(exc).lower()
    no_access = (
        f"Your account doesn't have access to {model} — new models can roll out "
        "gradually or require a plan upgrade. Pick a different model, or check "
        "the provider's console for availability."
    )
    if any(marker in text for marker in _NO_QUOTA):
        return (
            f"Your account is out of quota for {model} — add credits or raise the limit "
            "in the provider's billing console, or pick a different model."
        )
    if any(marker in text for marker in _NO_ACCESS):
        return no_access
    # Anthropic's 404 body is just "model: <id>" under type not_found_error; require both
    # halves so unrelated 404s (bad base_url, deleted resource) keep their raw message.
    if "not_found_error" in text and f"model: {model.split(':')[-1].lower()}" in text:
        return no_access
    return None


# -- transient failures (retry-worthy) ---------------------------------------------------
# Rate limits, upstream overloads and network blips: the call can succeed a moment later,
# so the engine retries with backoff instead of ending the turn. Quota exhaustion wears a
# 429 too but is NOT transient — it stays an error the user must act on.
_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
_TRANSIENT_MARKERS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "overloaded",
    "overloaded_error",
    "server_error",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway time",
    "timed out",
    "timeout",
    "connection reset",
    "connection error",
    "remote protocol error",
    "incomplete chunked read",
    "try again",
)
_STATUS_IN_TEXT = re.compile(
    r"(?:error\s+code\s*:\s*|status(?:_code)?[=:\s]+|via_upstream\s*\()(\d{3})",
    re.IGNORECASE,
)


def is_transient(exc: Exception) -> bool:
    """True when a provider failure looks momentary (429/5xx/timeouts/network)."""
    text = str(exc).lower()
    if any(marker in text for marker in _NO_QUOTA):
        return False
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS:
        return True
    embedded_status = _STATUS_IN_TEXT.search(text)
    if embedded_status and int(embedded_status.group(1)) in _TRANSIENT_STATUS:
        return True
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return True
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "connecterror", "connectionerror", "ratelimit", "apiconnection"))


def friendly_transient_error(exc: Exception) -> Optional[str]:
    """Plain-language terminal message for a temporary failure after retries are spent."""
    if not is_transient(exc):
        return None
    return (
        "The model service is temporarily unavailable. MimiWork retried automatically, "
        "but the service is still not responding. Your work is safe — try again in a moment."
    )


def retry_after_seconds(exc: Exception, cap: float = 30.0) -> Optional[float]:
    """The server's own Retry-After hint (seconds), when the exception carries a response."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return min(float(raw), cap)
    except (TypeError, ValueError):
        return None


# -- a credential the gateway no longer accepts ------------------------------------------
# QualiTaTi's gateway answers a key it cannot resolve with 401 {"detail": "Invalid or
# revoked API key"}. It reaches the user as that bare sentence, which says nothing about
# what to do — and the thing to do is not obvious, because the key on disk may well be
# fine: signing in mints a NEW key, and a client cached with the old one keeps presenting
# it (owner-hit 2026-08-31, "all models are not working now").
_STALE_CREDENTIAL = (
    "invalid or revoked api key",
    "invalid api key",
    "incorrect api key provided",
    "no api key provided",
    "authentication_error",
    "invalid_api_key",
)


def is_stale_credential(exc: Exception) -> bool:
    """True when the provider rejected the key itself, not the request."""
    text = str(exc).lower()
    if not any(marker in text for marker in _STALE_CREDENTIAL):
        return False
    # Guard against a 403 that means "this model is not yours" — that is _NO_ACCESS.
    return not any(marker in text for marker in _NO_ACCESS)


def friendly_credential_error(exc: Exception) -> Optional[str]:
    """One actionable sentence for a rejected key, or None."""
    if not is_stale_credential(exc):
        return None
    return (
        "Your QualiTaTi key is no longer accepted. Open Settings → Account and press "
        "Reconnect (or sign in again) — that mints a fresh key and MimiWork picks it up "
        "straight away. A key can stop working because it was revoked on qualitati.com "
        "or replaced by signing in on another computer."
    )
