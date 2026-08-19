"""The single builtin persona resolves to exactly the Cowork builder's toolset.

Legacy surfaces (code/chat/ops) are gone; their ids resolve to Cowork — covered
in test_persona_registry. This keeps the builder↔registry equivalence net.
"""

from __future__ import annotations

from coworker.agents.base import AgentContext
from coworker.agents.cowork import cowork_agent
from coworker.personas.registry import PersonaRegistry
from coworker.tools.todo import TodoList


def _ctx(tmp_path) -> AgentContext:
    return AgentContext(workspace=tmp_path, executor=object(), todo=TodoList())


def _names(agent, ctx) -> set:
    return {getattr(t, "__name__", "") for t in agent.build_tools(ctx)}


def test_cowork_persona_matches_builder(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    assert _names(reg.agent("cowork"), ctx) == _names(cowork_agent(), ctx)
    a = reg.agent("cowork")
    assert a.messaging and a.connectors


def test_cowork_carries_the_full_knowledge_toolset(tmp_path):
    """The one Coworker owns documents, decks, spreadsheets, PDFs, images, and
    analysis — not separate personas (owner ask 2026-08-19)."""
    reg = PersonaRegistry()
    names = _names(reg.agent("cowork"), _ctx(tmp_path))
    for expected in (
        "read_file",
        "list_directory",
        "grep",
        "write_document",
        "write_workbook",
        "write_presentation",
        "read_pdf",
        "edit_image",
        "inspect_data",
        "run_python",
        "run_r",
    ):
        assert expected in names, expected
