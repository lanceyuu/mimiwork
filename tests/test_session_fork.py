"""Session forking: transcript + scope copied under a fresh id; original untouched."""

from __future__ import annotations

from coworker.conversations import ConversationStore
from coworker.sessions import SessionRecord


def _seed(store, sid="orig", title=None):
    store.save(
        SessionRecord(
            session_id=sid,
            workspace="/tmp/ws",
            model="qualitati:mimi-hound",
            mode="interactive",
            messages=[
                {"role": "user", "content": "draft the report"},
                {"role": "assistant", "content": "done"},
            ],
            title=title,
            extra_roots=[{"path": "/tmp/extra", "writable": True, "label": "extra"}],
            grants={"tools": ["write_file"]},
        )
    )


def test_fork_copies_transcript_and_scope(tmp_path):
    store = ConversationStore(tmp_path)
    _seed(store)
    new_id = store.fork("orig")
    assert new_id and new_id != "orig"
    fork = store.load(new_id)
    orig = store.load("orig")
    assert fork.messages == orig.messages
    assert fork.workspace == orig.workspace
    assert fork.model == orig.model
    assert fork.extra_roots == orig.extra_roots
    assert fork.grants == orig.grants
    assert fork.title.startswith("Fork of ")
    assert fork.origin == "fork"
    # The fork has its own transcript file — appending there must not touch the original.
    fork.messages.append({"role": "user", "content": "try another angle"})
    store.save(fork)
    assert len(store.load("orig").messages) == 2


def test_fork_title_names_the_source(tmp_path):
    store = ConversationStore(tmp_path)
    _seed(store)
    store.rename("orig", "Budget plan")
    new_id = store.fork("orig")
    assert store.load(new_id).title == "Fork of Budget plan"


def test_fork_missing_session_returns_none(tmp_path):
    store = ConversationStore(tmp_path)
    assert store.fork("ghost") is None


def test_display_title_cheap_read(tmp_path):
    store = ConversationStore(tmp_path)
    _seed(store)
    assert store.display_title("orig") == "draft the report"
    store.rename("orig", "Renamed")
    assert store.display_title("orig") == "Renamed"
    assert store.display_title("ghost") is None
