"""New-flagship rollout (2026-07-14): GPT-5.6 Sol/Terra/Luna + Claude Fable 5 in the
matrix, both families' flagships as defaults, and friendly errors when an account can't
use them (GPT-5.6 rolls out per-organization; quota/credits can run out on any model).
"""

from coworker.config import Config
from coworker.providers.errors import friendly_model_error
from coworker.providers.matrix import MATRIX, models_for_provider
from coworker.providers.registry import get_descriptor


def test_new_flagships_in_matrix_with_labels():
    for mid, label in {
        "gpt-5.6-sol": "GPT-5.6 Sol · OpenAI",
        "gpt-5.6-terra": "GPT-5.6 Terra · OpenAI",
        "gpt-5.6-luna": "GPT-5.6 Luna · OpenAI",
        "anthropic:claude-fable-5": "Claude Fable 5 · Anthropic",
    }.items():
        assert MATRIX[mid].label == label
        assert MATRIX[mid].caps.tools and MATRIX[mid].caps.vision

    assert "gpt-5.6-sol" in models_for_provider("openai")
    assert "claude-fable-5" in models_for_provider("anthropic")


def test_flagships_are_the_defaults():
    assert Config().model == "gpt-5.6-sol"
    assert get_descriptor("openai").recommended_model == "gpt-5.6-sol"
    assert get_descriptor("anthropic").recommended_model == "claude-fable-5"


# -- friendly access/quota errors --------------------------------------------------------
def test_no_access_errors_are_translated():
    # OpenAI's 404/403 body for a model the org can't use yet
    exc = RuntimeError(
        "Error code: 404 - {'error': {'code': 'model_not_found', 'message': "
        "'The model `gpt-5.6-sol` does not exist or you do not have access to it.'}}"
    )
    msg = friendly_model_error("gpt-5.6-sol", exc)
    assert msg and "doesn't have access to gpt-5.6-sol" in msg

    # Anthropic's 404 body is type not_found_error + "model: <id>"
    exc = RuntimeError(
        "Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', "
        "'message': 'model: claude-fable-5'}}"
    )
    msg = friendly_model_error("anthropic:claude-fable-5", exc)
    assert msg and "doesn't have access to anthropic:claude-fable-5" in msg


def test_quota_errors_are_translated():
    exc = RuntimeError(
        "Error code: 429 - {'error': {'code': 'insufficient_quota', 'message': "
        "'You exceeded your current quota, please check your plan and billing details.'}}"
    )
    msg = friendly_model_error("gpt-5.6-sol", exc)
    assert msg and "out of quota for gpt-5.6-sol" in msg

    exc = RuntimeError(
        "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
        "'message': 'Your credit balance is too low to access the Anthropic API.'}}"
    )
    msg = friendly_model_error("anthropic:claude-fable-5", exc)
    assert msg and "out of quota" in msg


def test_unrelated_errors_pass_through_raw():
    # a plain rate-limit (429 without a quota code) must NOT be dressed up
    assert (
        friendly_model_error(
            "gpt-5.6-sol",
            RuntimeError("Error code: 429 - rate_limit_exceeded, retry after 2s"),
        )
        is None
    )
    # a 404 from a wrong base_url isn't an access problem
    assert (
        friendly_model_error(
            "gpt-5.6-sol", RuntimeError("Error code: 404 - no route /v2/chat")
        )
        is None
    )
    assert (
        friendly_model_error("gpt-5.6-sol", RuntimeError("connection reset by peer"))
        is None
    )


# -- the QualiTaTi gateway's own refusals (owner report 2026-09-04) --------------------
def test_a_spent_free_allowance_is_explained_not_retried():
    from coworker.providers.errors import friendly_gateway_error, is_transient

    exc = RuntimeError(
        "Error code: 429 - {'detail': {'code': 'FREE_TIER_EXHAUSTED', 'message': "
        "\"Mimi Puppy's free daily allowance is used up (200 requests today).\", "
        "'used': 214, 'cap': 200}}"
    )
    assert is_transient(exc) is False  # a 429, but not "slow down"
    msg = friendly_gateway_error(exc)
    assert msg and "used up (214 of 200 requests)" in msg
    assert "midnight UTC" in msg and "Mimi Hound" in msg


def test_an_empty_balance_points_at_the_top_up_page():
    from coworker.providers.errors import friendly_gateway_error, is_transient

    exc = RuntimeError('Error code: 402 - {"detail": {"code": "INSUFFICIENT_CREDITS", "message": "empty"}}')
    assert is_transient(exc) is False
    msg = friendly_gateway_error(exc)
    assert msg and "qualitati.com/recharge" in msg and "Mimi Puppy" in msg


def test_a_busy_gateway_is_still_a_retry():
    from coworker.providers.errors import friendly_gateway_error, is_transient

    exc = RuntimeError("Error code: 429 - {'detail': {'code': 'GATEWAY_BUSY', 'message': 'busy', 'retry_after': 2}}")
    assert is_transient(exc) is True
    assert friendly_gateway_error(exc) is None
