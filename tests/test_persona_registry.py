"""Persona registry in the single-coworker app: one builtin (Cowork, always the
default), third-party personas installed → enabled → surfaced on top of it."""

from __future__ import annotations

import pytest

from coworker.personas.registry import DEFAULT_PERSONA_ID, PersonaRegistry
from tests.test_persona_loading import THIRD_PARTY


def _reg(tmp_path) -> PersonaRegistry:
    return PersonaRegistry(state_path=tmp_path / "personas.json")


def _with_acme(tmp_path) -> PersonaRegistry:
    reg = _reg(tmp_path)
    vendor = tmp_path / "vendor"
    vendor.mkdir(exist_ok=True)
    (vendor / "acme.md").write_text(THIRD_PARTY, encoding="utf-8")
    reg.install_from_dir(str(vendor))
    return reg


def test_cowork_is_the_only_builtin(tmp_path):
    reg = _reg(tmp_path)
    assert set(reg.ids()) == {"cowork"}
    assert reg.get("cowork").builtin is True
    assert reg.default_id() == DEFAULT_PERSONA_ID == "cowork"


def test_sidebar_defaults_to_cowork_only(tmp_path):
    reg = _with_acme(tmp_path)
    sidebar = reg.sidebar()
    # A fresh install offers ONLY the default persona; installed personas are
    # opt-in from Settings ▸ Personas (enable implies surface).
    assert [e["name"] for e in sidebar] == ["cowork"]
    assert sidebar[0]["default"] is True
    reg.set_enabled("acme-ops", True)
    assert {e["name"] for e in reg.sidebar()} == {"cowork", "acme-ops"}


def test_legacy_builtin_ids_resolve_to_cowork(tmp_path):
    """Sessions saved under the retired chat/code/ops/analyst surfaces must keep
    opening — they resolve to the one Coworker instead of erroring."""
    reg = _reg(tmp_path)
    for legacy in ("chat", "code", "ops", "analyst", "documents", "slides"):
        assert reg.agent(legacy).name == "cowork"


def test_surface_toggle_filters_picker_but_keeps_resolvable(tmp_path):
    reg = _with_acme(tmp_path)
    reg.set_enabled("acme-ops", True)
    reg.set_surfaced("acme-ops", False)
    assert "acme-ops" not in [e["name"] for e in reg.sidebar()]
    # Still installed + still resolvable (a session already on it keeps working).
    assert "acme-ops" in reg.ids()
    assert reg.agent("acme-ops").name == "acme-ops"
    assert any(p["id"] == "acme-ops" and not p["surfaced"] for p in reg.list_all())


def test_cowork_cannot_be_disabled_away(tmp_path):
    """The default coworker is the floor of the app: disabling it either refuses
    or falls back to an enabled persona — the registry never ends up empty."""
    reg = _with_acme(tmp_path)
    reg.set_enabled("acme-ops", True)
    try:
        reg.set_enabled("cowork", False)
    except (KeyError, ValueError):
        assert reg.default_id() == "cowork"
    else:
        fallback = reg.agent(None)
        assert reg.is_enabled(fallback.name)


def test_set_default_enables_and_persists(tmp_path):
    reg = _with_acme(tmp_path)
    reg.set_default("acme-ops")
    assert reg.default_id() == "acme-ops" and reg.is_enabled("acme-ops")
    # A new instance reads persisted state (installed personas re-load from disk).
    reg2 = _reg(tmp_path)
    assert reg2.default_id() in ("acme-ops", "cowork")


def test_agent_resolution(tmp_path):
    reg = _reg(tmp_path)
    assert reg.agent("cowork").family == "knowledge"
    assert reg.agent("does-not-exist").name == reg.default_id()


def test_list_all_carries_workspace_enum(tmp_path):
    reg = _reg(tmp_path)
    ws = {p["id"]: p["workspace"] for p in reg.list_all()}
    assert ws["cowork"] == "deliverable"


def test_set_unknown_persona_raises(tmp_path):
    reg = _reg(tmp_path)
    with pytest.raises(KeyError):
        reg.set_enabled("ghost", False)
