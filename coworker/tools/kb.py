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
    return [kb_search]
