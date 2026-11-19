"""The `kb_search` tool — Mimi's offline research-methods knowledge base.

Same corpus the QualiTaTi products ship (4,000 entries: qualitative-methodology
Q&A + exemplar interview questions), searched with BM25 fully offline. The
coworker consults it before reaching for the web on methodology questions —
exactly the contract Mimi follows in QualiTaTi.
"""

from __future__ import annotations

from typing import Any, Optional

import aisuite as ai

from .. import kb

_MAX_CONTENT_CHARS = 700

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "kb_search",
        "description": (
            "Search Mimi's built-in research-methods knowledge base (works offline): "
            "qualitative methodology Q&A (design, sampling, interviews, focus groups, "
            "coding, thematic analysis, rigor, ethics) and a bank of exemplar interview "
            "questions by domain. ALWAYS try this before web search for methodology "
            "questions. Returns the top matches with their content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up."},
                "collection": {
                    "type": "string",
                    "enum": list(kb.COLLECTIONS),
                    "description": (
                        "Optional filter: 'methodology_qa' for how-to-do-research "
                        "questions, 'interview_questions' for ready-made interview "
                        "question examples."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


def kb_tools() -> list:
    def kb_search(query: str, collection: Optional[str] = None) -> dict[str, Any]:
        if collection and collection not in kb.COLLECTIONS:
            return {"error": f"unknown collection {collection!r}; use one of {list(kb.COLLECTIONS)}"}
        hits = kb.search(str(query or ""), k=5, collection=collection)
        if not hits:
            return {
                "count": 0,
                "results": [],
                "note": "No knowledge-base match — rephrase, or fall back to web search.",
            }
        results = []
        for h in hits:
            content = (h.get("content") or "").strip()
            entry: dict[str, Any] = {
                "id": h.get("id"),
                "collection": h.get("collection"),
                "title": h.get("title"),
                "content": content[:_MAX_CONTENT_CHARS]
                + ("…" if len(content) > _MAX_CONTENT_CHARS else ""),
            }
            if (h.get("metadata") or {}).get("requires_citation_review"):
                entry["caveat"] = (
                    "educational summary — verify citations before quoting in a manuscript"
                )
            results.append(entry)
        return {"count": len(results), "results": results}

    kb_search.__name__ = "kb_search"
    kb_search.__doc__ = _SCHEMA["function"]["description"]
    kb_search.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="kb_search",
        category="knowledge",
        risk_level="low",
        capabilities=["read"],
        requires_approval=False,
    )
    kb_search.__coworker_schema__ = _SCHEMA
    return [kb_search, _mimiwork_help()]


_HELP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "mimiwork_help",
        "description": (
            "Look up how MimiWork itself works: where a setting, page or button is, how a "
            "feature works (Agents, coding agents, Mail, Automations, Apps, Skills, Memory, "
            "folders, models and tiers, keys, permission modes, slides), and what an app "
            "message means and how to fix it. Use it before naming any MimiWork menu, page "
            "or setting, and when a tool error mentions one. Works offline."
        ),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "What you want to know, in plain words."}},
            "required": ["question"],
        },
    },
}


def _mimiwork_help():
    def mimiwork_help(question: str) -> dict[str, Any]:
        hits = kb.search_help(str(question or ""), k=3)
        if not hits:
            return {
                "count": 0,
                "results": [],
                "note": (
                    "MimiWork's help has nothing on this. Tell the person you are not sure "
                    "where or how it works in MimiWork, rather than naming a place that may "
                    "not exist."
                ),
            }
        return {
            "count": len(hits),
            "results": [{"title": h["title"], "content": h["content"]} for h in hits],
            "note": "Name only the places and labels written here, exactly as written.",
        }

    mimiwork_help.__name__ = "mimiwork_help"
    mimiwork_help.__doc__ = _HELP_SCHEMA["function"]["description"]
    mimiwork_help.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="mimiwork_help",
        category="knowledge",
        risk_level="low",
        capabilities=["read"],
        requires_approval=False,
    )
    mimiwork_help.__coworker_schema__ = _HELP_SCHEMA
    return mimiwork_help
