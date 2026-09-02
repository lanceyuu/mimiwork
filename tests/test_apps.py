"""Apps: one HTML file Mimi writes, the user runs inside MimiWork.

The store is a folder per app; the bridge's ask goes through the app's own model;
nothing with an external resource is accepted, because the sandbox would show a
blank page and nobody would know why.
"""

from __future__ import annotations

import json

import pytest
from helpers import CapturingProvider

from coworker.apps import AppStore, app_tools, validate_html
from coworker.apps.store import builtin_starters, pack, unpack
from coworker.providers.base import AssistantTurn
from coworker.server.manager import SessionManager

HTML = "<!doctype html><html><body><h1>Hi</h1><script>Mimi.ask('x')</script></body></html>"


def _manager(tmp_path, monkeypatch, provider=None) -> SessionManager:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    return SessionManager(data_dir=tmp_path / "data", provider=provider or CapturingProvider())


def test_an_app_round_trips_through_its_folder(tmp_path):
    store = AppStore(tmp_path / "apps")
    app = store.create(title="Translator", html=HTML, icon="🌐", description="Translates.")
    assert app.id.startswith("app-")
    assert (tmp_path / "apps" / app.id / "index.html").read_text() == HTML
    again = AppStore(tmp_path / "apps")
    assert [a.title for a in again.list()] == ["Translator"]
    assert again.html(app.id) == HTML
    assert again.delete(app.id) and again.list() == []


def test_nothing_from_the_web_is_accepted():
    assert validate_html('<script src="https://cdn.x/y.js"></script>') is not None
    assert validate_html('<link href="//fonts.googleapis.com/css">') is not None
    assert validate_html("") is not None
    assert validate_html(HTML) is None
    assert validate_html('<a href="#top">ok</a><img src="data:image/png;base64,AA">') is None


def test_ids_that_are_not_ours_never_become_paths(tmp_path):
    store = AppStore(tmp_path / "apps")
    assert store.get("../../etc") is None
    assert store.html("app-zzzzzzzz") == ""
    assert store.delete("nope") is False


def test_state_is_a_small_object_or_nothing(tmp_path):
    store = AppStore(tmp_path / "apps")
    app = store.create(title="T", html=HTML)
    assert store.state(app.id) == {}
    store.set_state(app.id, {"history": [1, 2]})
    assert store.state(app.id) == {"history": [1, 2]}
    with pytest.raises(ValueError):
        store.set_state(app.id, ["not", "an", "object"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        store.set_state(app.id, {"big": "x" * 300_000})


def test_the_tools_write_only_under_apps_and_remember_who_built_it(tmp_path):
    store = AppStore(tmp_path / "apps")
    create, update, listing = app_tools(store, session_id="sess-1")
    res = create(title="Cards", html=HTML, icon="🃏", description="Flashcards")
    assert res["ok"]
    app = store.get(res["id"])
    assert app.builder_session == "sess-1" and app.icon == "🃏"
    assert update(id=res["id"], html=HTML.replace("Hi", "Hello"), title="Cards 2")["ok"]
    assert "Hello" in store.html(res["id"]) and store.get(res["id"]).title == "Cards 2"
    assert "error" in update(id="app-00000000", html=HTML)
    assert "error" in create(title="Bad", html='<script src="https://x/y.js"></script>')
    assert listing()["apps"][0]["title"] == "Cards 2"
    assert {p.name for p in (tmp_path / "apps").iterdir()} == {res["id"]}


def test_ask_uses_the_apps_own_model_and_counts_the_call(tmp_path, monkeypatch):
    provider = CapturingProvider([AssistantTurn(text="Bonjour", finish_reason="stop")])
    m = _manager(tmp_path, monkeypatch, provider)
    app = m.app_store.create(title="T", html=HTML, model="qualitati:mimi-hound")
    res = m.app_ask(app.id, "Translate: hello", system="Reply with the translation only.")
    assert res == {"ok": True, "text": "Bonjour"}
    assert provider.calls[0][0] == {"role": "system", "content": "Reply with the translation only."}
    assert m.app_store.get(app.id).asks == 1
    assert not m.app_ask(app.id, "")["ok"]
    assert not m.app_ask("app-00000000", "x")["ok"]
    assert not m.app_ask(app.id, "x" * 40_000)["ok"]


def test_import_export_is_one_share_file(tmp_path, monkeypatch):
    m = _manager(tmp_path, monkeypatch)
    res = m.import_app({"title": "Shared", "icon": "🔁", "description": "d", "html": HTML})
    assert res["ok"]
    app = m.app_store.get(res["app"]["id"])
    text = pack(app, HTML)
    manifest, html = unpack(text)
    assert manifest["title"] == "Shared" and manifest["mimiwork_app"] == 1 and html == HTML
    assert unpack(HTML) == ({}, HTML)
    assert not m.import_app({"title": "x", "html": '<script src="https://a/b.js"></script>'})["ok"]


def test_the_starters_are_valid_apps():
    starters = builtin_starters()
    assert {s["title"] for s in starters} >= {"Translator", "Rewrite in my voice"}
    for s in starters:
        assert validate_html(s["html"]) is None
        assert "Mimi.ask(" in s["html"]


def test_rest_shapes(tmp_path, monkeypatch):
    m = _manager(tmp_path, monkeypatch)
    created = m.import_app({"title": "T", "html": HTML})["app"]
    assert m.list_apps()["apps"][0]["id"] == created["id"]
    got = m.get_app(created["id"])
    assert got["ok"] and got["html"] == HTML
    assert m.update_app(created["id"], {"title": "New", "model": "x:y"})["app"]["model"] == "x:y"
    assert m.update_app(created["id"], {"model": ""})["app"]["model"] is None
    assert m.set_app_state(created["id"], {"a": 1})["ok"]
    assert m.app_state(created["id"])["state"] == {"a": 1}
    assert not m.set_app_state(created["id"], "nope")["ok"]
    assert m.delete_app(created["id"])["ok"]
    assert m.get_app(created["id"]) == {"ok": False, "error": "not found"}
    assert json.dumps(m.list_apps()) == '{"apps": []}'
