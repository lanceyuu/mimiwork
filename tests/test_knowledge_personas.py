"""The knowledge-work personas resolve, and compose the Office/analysis capabilities."""

from __future__ import annotations

import pytest

from coworker.agents.base import AgentContext
from coworker.catalog import CATALOG, risk_summary
from coworker.personas.registry import PersonaRegistry
from coworker.risk import RiskClass
from coworker.roots import RootDir
from coworker.tools.todo import TodoList

KNOWLEDGE_PERSONAS = ["analyst", "documents", "slides"]


def _ctx(tmp_path) -> AgentContext:
    return AgentContext(
        workspace=tmp_path,
        executor=object(),
        todo=TodoList(),
        roots=[RootDir(path=tmp_path, writable=True)],
    )


def _names(agent, ctx) -> set:
    return {getattr(t, "__name__", "") for t in agent.build_tools(ctx)}


@pytest.mark.parametrize("persona_id", KNOWLEDGE_PERSONAS)
def test_persona_is_registered_and_resolves(persona_id, tmp_path):
    agent = PersonaRegistry().agent(persona_id)
    assert agent.name == persona_id
    assert agent.family == "knowledge"
    assert agent.needs_workspace
    assert agent.system_prompt.strip()


@pytest.mark.parametrize("persona_id", KNOWLEDGE_PERSONAS)
def test_persona_is_installed_and_offered_in_settings(persona_id):
    """A fresh install ships Coworker-only by deliberate policy (registry.is_enabled), so the
    contract for a new persona is that it is *installed and listed*, not enabled."""
    listed = {entry["id"] for entry in PersonaRegistry().list_all()}
    assert persona_id in listed


@pytest.mark.parametrize("persona_id", KNOWLEDGE_PERSONAS)
def test_persona_surfaces_in_the_picker_once_enabled(persona_id, tmp_path):
    registry = PersonaRegistry(state_path=tmp_path / "personas.json")
    registry.set_enabled(persona_id, True)
    # sidebar() carries the persona id under "name" and its display title under "title".
    assert persona_id in {entry["name"] for entry in registry.sidebar()}


def test_analyst_gets_the_full_analysis_toolset(tmp_path):
    names = _names(PersonaRegistry().agent("analyst"), _ctx(tmp_path))
    assert {"inspect_data", "run_python", "reset_python", "run_r"} <= names
    # It also has to be able to hand back a deliverable, not just compute.
    assert {"write_workbook", "write_document", "write_presentation"} <= names


def test_documents_persona_can_read_edit_and_write_word(tmp_path):
    names = _names(PersonaRegistry().agent("documents"), _ctx(tmp_path))
    assert {"read_document", "write_document", "edit_document"} <= names
    # No code execution: this persona has no reason to hold EXEC authority.
    assert "run_python" not in names
    assert "run_shell" not in names


def test_slides_persona_can_build_charts_and_decks(tmp_path):
    names = _names(PersonaRegistry().agent("slides"), _ctx(tmp_path))
    assert {"write_presentation", "read_presentation", "run_python"} <= names


@pytest.mark.parametrize("persona_id", KNOWLEDGE_PERSONAS)
def test_persona_always_has_a_task_list(persona_id, tmp_path):
    """Every prompt requires todo_write; the tool must actually be there to call."""
    assert "todo_write" in _names(PersonaRegistry().agent(persona_id), _ctx(tmp_path))


def test_office_capabilities_declare_local_write_risk():
    for cap_id in ("documents", "spreadsheets", "slides"):
        assert RiskClass.WRITE_LOCAL in CATALOG[cap_id].risk


def test_code_execution_capabilities_declare_exec_risk():
    """run_python is the same authority as run_shell and must be gated identically."""
    assert risk_summary(["python_analysis"]) == {RiskClass.EXEC}
    assert risk_summary(["r_analysis"]) == {RiskClass.EXEC}


def test_data_inspection_is_read_only():
    assert risk_summary(["data_inspect"]) == {RiskClass.READ}


def test_capabilities_are_skipped_without_a_workspace():
    """A workspace-less context must degrade, not raise."""
    from coworker.catalog import expand

    assert expand(["documents", "python_analysis", "data_inspect"], AgentContext()) == []


def test_analyst_prompt_requires_the_statistical_essentials():
    """These aren't stylistic: an effect-free, n-free p-value misleads whoever reads it."""
    prompt = PersonaRegistry().agent("analyst").system_prompt.lower()
    for essential in ("effect size", "sample size", "assumption", "inspect_data"):
        assert essential in prompt


def test_slides_prompt_requires_speaker_notes():
    assert "speaker notes" in PersonaRegistry().agent("slides").system_prompt.lower()


def test_documents_prompt_warns_against_regenerating_to_edit():
    prompt = PersonaRegistry().agent("documents").system_prompt.lower()
    assert "edit_document" in prompt
