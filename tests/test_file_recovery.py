"""File recovery: every offered Undo has a complete pre-write copy."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coworker.recovery import RecoverySession
from coworker.server import SessionManager, create_app


def _session(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    recovery = RecoverySession(tmp_path / "state", "session-1", lambda: str(root))
    return root, recovery


def test_a_modified_file_returns_to_its_pre_turn_contents(tmp_path):
    root, recovery = _session(tmp_path)
    report = root / "report.docx"
    report.write_bytes(b"original office package")

    recovery.begin_turn()
    recovery.capture("edit_document", {"path": "report.docx"})
    report.write_bytes(b"changed")

    point = recovery.list()[0]
    assert point["files"] == [
        {"path": str(report), "name": "report.docx", "action": "modified"}
    ]
    result = recovery.restore(point["id"])

    assert result["ok"] is True
    assert report.read_bytes() == b"original office package"
    assert recovery.list()[0]["restored_at"] is not None


def test_a_file_created_during_the_turn_is_removed_by_undo(tmp_path):
    root, recovery = _session(tmp_path)
    created = root / "brief.txt"

    recovery.begin_turn()
    recovery.capture("write_file", {"path": "brief.txt", "content": "finished"})
    created.write_text("finished", encoding="utf-8")

    point = recovery.list()[0]
    result = recovery.restore(point["id"])

    assert result["ok"] is True
    assert not created.exists()
    assert result["removed"] == [str(created)]


def test_repeated_writes_in_one_turn_keep_the_first_version(tmp_path):
    root, recovery = _session(tmp_path)
    note = root / "note.md"
    note.write_text("before", encoding="utf-8")

    recovery.begin_turn()
    recovery.capture("write_file", {"path": "note.md"})
    note.write_text("middle", encoding="utf-8")
    recovery.capture("replace_in_file", {"path": "note.md"})
    note.write_text("after", encoding="utf-8")

    point = recovery.list()[0]
    assert len(point["files"]) == 1
    assert recovery.restore(point["id"])["ok"] is True
    assert note.read_text(encoding="utf-8") == "before"


def test_patch_targets_are_all_captured_before_the_patch_runs(tmp_path):
    root, recovery = _session(tmp_path)
    (root / "old.txt").write_text("old", encoding="utf-8")

    recovery.begin_turn()
    recovery.capture(
        "apply_patch",
        {
            "patch": "*** Begin Patch\n*** Update File: old.txt\n@@\n-old\n+new\n*** Add File: new.txt\n+new\n*** End Patch"
        },
    )

    files = {row["name"]: row["action"] for row in recovery.list()[0]["files"]}
    assert files == {"old.txt": "modified", "new.txt": "created"}


def test_a_target_outside_the_granted_folder_never_gets_snapshotted(tmp_path):
    _root, recovery = _session(tmp_path)
    recovery.begin_turn()

    with pytest.raises(ValueError, match="escapes"):
        recovery.capture("write_file", {"path": "../outside.txt"})

    assert recovery.list() == []


def test_the_rest_api_lists_and_restores_a_session_recovery_point(tmp_path):
    manager = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    engine = manager.get_engine("session-api")
    assert engine is not None and engine.file_recovery is not None
    note = tmp_path / "note.txt"
    note.write_text("before", encoding="utf-8")
    engine.file_recovery.begin_turn()
    engine.file_recovery.capture("write_file", {"path": "note.txt"})
    note.write_text("after", encoding="utf-8")
    client = TestClient(create_app(manager))

    point = client.get("/v1/sessions/session-api/recovery").json()["recovery_points"][0]
    result = client.post(
        f"/v1/sessions/session-api/recovery/{point['id']}/restore"
    ).json()

    assert result["ok"] is True
    assert note.read_text(encoding="utf-8") == "before"
