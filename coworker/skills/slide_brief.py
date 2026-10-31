"""The first slide-skill load can ask a real briefing question before drafting."""

from __future__ import annotations

import json

from ..providers import ToolCall


def pending_slide_brief(messages):
    # Only the batch that just finished can start an intake. The normal ask_user
    # transcript both persists the answer across restarts and consumes this trigger.
    if not messages or messages[-1].get("role") != "tool":
        return None
    i = len(messages) - 1
    while i >= 0 and messages[i].get("role") == "tool":
        i -= 1
    if i < 0:
        return None
    calls = messages[i].get("tool_calls", [])
    for call in calls:
        fn = call.get("function", {})
        if fn.get("name") != "load_skill":
            continue
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(args, dict) or args.get("name") != "qualitati-style":
            continue
        result = next((m for m in messages[i + 1 :] if m.get("tool_call_id") == call["id"]), {})
        try:
            loaded = json.loads(result.get("content", ""))
        except (TypeError, ValueError):
            continue
        if not isinstance(loaded, dict) or loaded.get("name") != "qualitati-style":
            continue
        # Follow-ups already have an audience or a deck to revise. For the first
        # load, accept supplied context rather than a model-invented audience.
        history = messages[: i + 1]
        if any(
            tc.get("function", {}).get("name") in {"ask_user", "write_presentation"}
            for m in history
            for tc in m.get("tool_calls", [])
        ):
            return None
        quote = str(args.get("slide_brief") or "").strip().casefold()
        sources = {
            tc["id"]
            for m in history
            for tc in m.get("tool_calls", [])
            if tc.get("function", {}).get("name")
            in {"read_file", "read_presentation", "read_document"}
        }
        if quote and any(
            quote in str(m.get("content", "")).casefold()
            for m in messages
            if (m.get("role") == "user" and not m.get("steering"))
            or m.get("tool_call_id") in sources
        ):
            return None
        return ToolCall(
            id="brief_" + call["id"][-22:],
            name="ask_user",
            arguments={
                "header": "Slide brief",
                "question": args.get("slide_question")
                or (
                    "Who will see the slides, what should they take away, and what length, "
                    "materials or design requirements should I plan for?"
                ),
                "options": ["Use your judgment"],
                "allow_text": True,
            },
        )
    return None
