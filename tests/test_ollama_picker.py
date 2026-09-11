"""A local Ollama's models show up in the picker by themselves (owner-hit 2026-09-11:
Ollama running with gemma4 pulled, nothing visible — the app only listed models once the
Ollama card had been saved AND each model typed into the add-model form)."""

from __future__ import annotations

from types import SimpleNamespace

from coworker.server.manager import SessionManager


def _manager(tmp_path, monkeypatch, *, alive=True, models=("ollama:gemma4:26b",)):
    mgr = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    monkeypatch.setattr(SessionManager, "_ollama_alive", lambda self: alive)
    monkeypatch.setattr(SessionManager, "_ollama_models", lambda self: list(models))
    return mgr


def test_a_pulled_model_is_offered_without_any_setup(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch)
    assert mgr.secrets.get("provider:ollama") is None  # never saved in Settings
    assert "ollama:gemma4:26b" in mgr.get_settings()["models"]


def test_no_ollama_means_no_phantom_models(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch, alive=False)
    assert not [m for m in mgr.get_settings()["models"] if m.startswith("ollama:")]


def test_a_removed_ollama_model_stays_removed_until_added_back(tmp_path, monkeypatch):
    mgr = _manager(tmp_path, monkeypatch)
    assert "ollama:gemma4:26b" not in mgr.remove_model("ollama:gemma4:26b")["models"]
    assert "ollama:gemma4:26b" not in mgr.get_settings()["models"]
    assert "ollama:gemma4:26b" in mgr.add_model("ollama:gemma4:26b")["models"]


def test_the_live_list_defaults_to_localhost_when_the_card_was_never_saved(tmp_path, monkeypatch):
    mgr = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    seen = []

    def fake_get(url, timeout):
        seen.append(url)
        return SimpleNamespace(json=lambda: {"models": [{"name": "gemma4:26b"}]})

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    assert mgr._ollama_models() == ["ollama:gemma4:26b"]
    assert seen == ["http://localhost:11434/api/tags"]
    assert mgr._ollama_models() == ["ollama:gemma4:26b"] and len(seen) == 1  # cached
