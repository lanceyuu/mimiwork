"""Thinking effort (low / medium / high) as the provider-specific setting it becomes.

The Agents section lets a user give each agent its own effort. Providers spell it three
different ways, and a wrong spelling is a 400, not a no-op — so a model whose effort
control we have not verified gets nothing, and the GUI greys the control out for it.
"""

from __future__ import annotations

from typing import Any

LEVELS = ("low", "medium", "high")

# Claude models that predate the effort parameter (it errors on Sonnet/Haiku 4.5).
_CLAUDE_WITHOUT_EFFORT = (
    "claude-haiku-4-5", "claude-sonnet-4-5", "claude-sonnet-4-0",
    "claude-opus-4-0", "claude-opus-4-1", "claude-3", "claude-2",
)


def effort_settings(model: str, effort: str) -> dict[str, Any]:
    """`model_settings` for a TurnEngine; {} when the level is unset or unsupported."""
    if effort not in LEVELS:
        return {}
    prefix, _, bare = (model or "").partition(":")
    if not bare:
        prefix, bare = "openai", prefix
    if prefix == "anthropic" and bare.startswith("claude-") and not bare.startswith(_CLAUDE_WITHOUT_EFFORT):
        return {"output_config": {"effort": effort}}
    # GPT-5 and the o-series. openai_provider already retries at "none" when a tools
    # call rejects reasoning effort, so a tool-using agent still gets a working turn.
    if prefix == "openai" and bare.startswith(("gpt-5", "o3", "o4")):
        return {"reasoning_effort": effort}
    # ponytail: Mimi gateway tiers, Gemini and resellers get nothing until a live probe
    # shows the setting is accepted end to end; add their spelling here when it does.
    return {}


def supports_effort(model: str) -> bool:
    return bool(effort_settings(model, "medium"))
