"""One model call per version of a script, only when asked, cached by content."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app

GOOD = json.dumps({"steps": [{"start": 1, "end": 2, "note": "Loads the survey.", "choice": None}]})


class _ExplainProvider(ProviderClient):
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls.append(messages)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return AssistantTurn(text=item, finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


def _setup(tmp_path, replies):
    provider = _ExplainProvider(replies)
    manager = SessionManager(workspace=tmp_path, provider=provider)
    engine = manager.get_engine("s1", workspace=str(tmp_path))
    manager.save("s1", engine)
    (tmp_path / "clean.py").write_text("import pandas as pd\ndf = pd.read_csv('a.csv')\n", encoding="utf-8")
    return manager, provider


def test_explaining_a_script_returns_steps_that_cover_it(tmp_path):
    manager, _ = _setup(tmp_path, [GOOD])
    result = manager.explain_artifact("s1", "clean.py")
    assert result["ok"] is True
    assert result["steps"][0]["note"] == "Loads the survey."
    assert result["truncated"] is False


def test_an_unchanged_script_is_not_explained_twice(tmp_path):
    manager, provider = _setup(tmp_path, [GOOD])
    manager.explain_artifact("s1", "clean.py")
    again = manager.explain_artifact("s1", "clean.py")
    assert again["ok"] is True and len(provider.calls) == 1


def test_asking_only_for_saved_notes_never_calls_the_model(tmp_path):
    manager, provider = _setup(tmp_path, [])
    result = manager.explain_artifact("s1", "clean.py", cached_only=True)
    assert result == {"ok": False, "cached": False}
    assert provider.calls == []


def test_a_changed_script_is_explained_again(tmp_path):
    manager, provider = _setup(tmp_path, [GOOD, GOOD])
    manager.explain_artifact("s1", "clean.py")
    (tmp_path / "clean.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    manager.explain_artifact("s1", "clean.py")
    assert len(provider.calls) == 2


def test_a_reply_that_is_not_json_is_an_error_and_is_not_saved(tmp_path):
    manager, provider = _setup(tmp_path, ["no idea", GOOD])
    assert manager.explain_artifact("s1", "clean.py")["ok"] is False
    assert manager.explain_artifact("s1", "clean.py")["ok"] is True
    assert len(provider.calls) == 2


def test_a_provider_failure_is_an_error_not_a_crash(tmp_path):
    manager, _ = _setup(tmp_path, [RuntimeError("gateway down")])
    assert manager.explain_artifact("s1", "clean.py")["ok"] is False


def test_notes_are_asked_for_in_the_app_language(tmp_path):
    manager, provider = _setup(tmp_path, [GOOD])
    manager.set_language("zh")
    manager.explain_artifact("s1", "clean.py")
    assert "Simplified Chinese" in provider.calls[0][0]["content"]


def test_an_empty_script_is_refused_without_calling_the_model(tmp_path):
    manager, provider = _setup(tmp_path, [])
    (tmp_path / "empty.py").write_text("\n", encoding="utf-8")
    assert manager.explain_artifact("s1", "empty.py")["ok"] is False
    assert provider.calls == []


def test_a_file_outside_the_granted_folders_is_refused(tmp_path):
    manager, provider = _setup(tmp_path, [])
    assert manager.explain_artifact("s1", "/etc/hosts")["ok"] is False
    assert provider.calls == []


def test_the_route_passes_path_and_cached_only(tmp_path):
    manager, _ = _setup(tmp_path, [])
    client = TestClient(create_app(manager))
    body = client.post("/v1/sessions/s1/artifacts/explain", json={"path": "clean.py", "cached_only": True}).json()
    assert body == {"ok": False, "cached": False}
