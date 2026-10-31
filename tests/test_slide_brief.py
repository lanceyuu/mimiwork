import asyncio
from pathlib import Path

import pytest
from helpers import ScriptedProvider

from coworker.engine import TurnEngine
from coworker.permissions import PermissionEngine
from coworker.providers import AssistantTurn, ToolCall
from coworker.skills.base import SkillLoader, skill_tools
from coworker.tools.ask import ask_user_tool
from coworker.tools.registry import ToolRegistry


@pytest.mark.parametrize(
    ("user", "context", "expected"),
    [
        ("Make a short deck about heat pumps", "", 1),
        ("Make a short deck about heat pumps", "homeowners", 1),
        ("Teach homeowners how heat pumps work", "homeowners", 0),
        ("Use your judgment on this slide deck", "Use your judgment", 0),
    ],
)
def test_interactive_slides_ask_once_unless_the_user_supplied_the_brief(
    tmp_path, user, context, expected
):
    registry = ToolRegistry()
    registry.register_all(skill_tools(SkillLoader([Path("coworker/skills/builtin")])))
    registry.register(ask_user_tool())
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "load", "load_skill", {"name": "qualitati-style", "slide_brief": context}
                    )
                ]
            ),
            AssistantTurn(text="Done."),
        ]
    )
    asked = []

    async def answer(args, call_id):
        asked.append(args["question"])
        return {"answer": "Five slides to teach homeowners how the heating cycle works."}

    engine = TurnEngine(
        provider=provider,
        registry=registry,
        model="test",
        permissions=PermissionEngine(tmp_path),
        question_asker=answer,
    )

    async def run():
        return [event async for event in engine.run(user)]

    asyncio.run(run())
    assert len(asked) == expected
    if expected:
        assert any("Five slides" in m["content"] for m in engine.messages if m["role"] == "tool")
