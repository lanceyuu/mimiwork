"""A persona may BIND a model, not only recommend one (opencode's per-agent model idea)."""

import pytest

from coworker.personas.manifest import ManifestError, parse_manifest
from coworker.personas.registry import PersonaRegistry

_BODY = "You are a test persona."


def _manifest(extra: str = "") -> str:
    return f"---\nid: t\nname: Test\nfamily: knowledge\n{extra}---\n{_BODY}\n"


def test_model_defaults_to_empty_so_the_session_decides():
    assert parse_manifest(_manifest()).model == ""


def test_model_is_parsed_when_declared():
    assert parse_manifest(_manifest("model: anthropic:claude-opus-4-8\n")).model == (
        "anthropic:claude-opus-4-8"
    )


def test_model_is_stripped():
    assert parse_manifest(_manifest("model: '  openai:gpt-5.6-sol  '\n")).model == (
        "openai:gpt-5.6-sol"
    )


def test_a_non_string_model_is_rejected_loudly():
    """A third-party manifest must fail to parse rather than silently produce a broken persona."""
    with pytest.raises(ManifestError) as exc:
        parse_manifest(_manifest("model:\n  - a\n  - b\n"))
    assert "model" in str(exc.value)


def test_binding_is_distinct_from_recommending():
    manifest = parse_manifest(
        _manifest("model: anthropic:claude-opus-4-8\nrecommended_models: [openai:gpt-5.6-sol]\n")
    )
    assert manifest.model == "anthropic:claude-opus-4-8"
    assert manifest.recommended_models == ["openai:gpt-5.6-sol"]


def test_registry_reports_no_binding_for_builder_backed_personas():
    """Cowork/Code/Chat come from builders, not manifests, so they can't bind a model."""
    assert PersonaRegistry().bound_model("cowork") == ""


def test_registry_reports_the_binding_for_a_manifest_persona(tmp_path):
    (tmp_path / "bound.md").write_text(
        "---\nid: bound\nname: Bound\nfamily: knowledge\nmodel: anthropic:claude-opus-4-8\n"
        f"---\n{_BODY}\n",
        encoding="utf-8",
    )
    registry = PersonaRegistry(extra_dirs=[tmp_path], state_path=tmp_path / "state.json")
    assert registry.bound_model("bound") == "anthropic:claude-opus-4-8"


def test_unknown_persona_has_no_binding():
    assert PersonaRegistry().bound_model("does-not-exist") == ""


def test_list_all_exposes_the_binding_to_the_settings_panel():
    entries = {e["id"]: e for e in PersonaRegistry().list_all()}
    assert entries["ops"]["model"] == ""  # ops recommends, it does not bind
    assert "model" in entries["cowork"]
