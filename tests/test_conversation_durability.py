"""Durability behavior at the JSONL and tool-journal persistence boundary."""

from __future__ import annotations

import pytest

import coworker.conversations as conversations
from coworker.conversations import ConversationStore
from coworker.sessions import SessionRecord


def test_torn_final_jsonl_record_preserves_valid_prefix(tmp_path):
    store = ConversationStore(tmp_path)
    store.save(
        SessionRecord(
            session_id="torn",
            workspace=str(tmp_path),
            model="test-model",
            mode="interactive",
            messages=[{"role": "user", "content": "safe"}],
        )
    )
    with open(store._file("torn"), "ab") as stream:
        stream.write(b'{"role":"assistant","content":"part')

    loaded = store.load("torn")

    assert loaded is not None
    assert loaded.messages == [{"role": "user", "content": "safe"}]

    loaded.messages.append({"role": "assistant", "content": "continued"})
    store.save(loaded)
    assert store.load("torn").messages == [
        {"role": "user", "content": "safe"},
        {"role": "assistant", "content": "continued"},
    ]


def test_corruption_before_final_jsonl_record_is_not_silenced(tmp_path):
    store = ConversationStore(tmp_path)
    store._file("broken").write_bytes(
        b'{"role":"user","content":"safe"}\nnot-json\n'
        b'{"role":"assistant","content":"later"}\n'
    )

    try:
        store._read_jsonl("broken")
    except ValueError:
        pass
    else:  # pragma: no cover - assertion spelling keeps the expected exception broad
        raise AssertionError("middle-of-file corruption must remain visible")


def test_complete_invalid_final_jsonl_record_is_not_silenced(tmp_path):
    store = ConversationStore(tmp_path)
    store._file("broken-tail").write_bytes(
        b'{"role":"user","content":"safe"}\nnot-json\n'
    )

    try:
        store._read_jsonl("broken-tail")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("only a truncated final record may be ignored")


def test_valid_final_record_without_newline_gets_a_separator_before_append(tmp_path):
    store = ConversationStore(tmp_path)
    record = SessionRecord(
        session_id="no-newline",
        workspace=str(tmp_path),
        model="test-model",
        mode="interactive",
        messages=[{"role": "user", "content": "one"}],
    )
    store.save(record)
    path = store._file("no-newline")
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))

    loaded = store.load("no-newline")
    loaded.messages.append({"role": "assistant", "content": "two"})
    store.save(loaded)

    assert store.load("no-newline").messages == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    ]


def test_atomic_rewrite_preserves_old_prefix_if_replace_fails(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path)
    record = SessionRecord(
        session_id="atomic",
        workspace=str(tmp_path),
        model="test-model",
        mode="interactive",
        messages=[{"role": "user", "content": "original"}],
    )
    store.save(record)
    path = store._file("atomic")
    original = path.read_bytes()

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(conversations.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        store._write_all("atomic", [{"role": "assistant", "content": "new"}])

    assert path.read_bytes() == original
    assert list(store.conv_dir.glob(".atomic.*.tmp")) == []
