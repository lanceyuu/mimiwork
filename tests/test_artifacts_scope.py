"""Artifacts = what the conversation produced, not what happens to sit in the folder it
was given (owner report 2026-08-24: a granted course folder listed every document in it).

The signal is the transcript itself — the tool calls that wrote files — so it is right for
conversations that predate this rule, and a folder full of the user's own work stays out.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from coworker.conversations import SessionRecord
from coworker.providers import ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app


class _StubProvider(ProviderClient):
    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()


def _fixture(tmp_path):
    manager = SessionManager(workspace=tmp_path, provider=_StubProvider())
    return TestClient(create_app(manager)), manager


def _turn(tool: str, args: dict, result: dict, call_id: str = "c1") -> list[dict]:
    """One assistant tool call plus its result, exactly as the engine records them."""
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps(args)},
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)},
    ]


def _session(manager, sid: str, workspace: Path, messages: list[dict], extra=None) -> None:
    manager.session_store.save(
        SessionRecord(
            session_id=sid,
            workspace=str(workspace.resolve()),
            model="m",
            mode="interactive",
            messages=messages,
            title="t",
            extra_roots=extra or [],
        )
    )


def test_only_the_files_the_conversation_wrote_are_listed(tmp_path):
    folder = tmp_path / "Online marketing course"
    folder.mkdir()
    for name in ("week1.docx", "week2.docx", "syllabus.pdf"):
        (folder / name).write_bytes(b"the user's own work")
    (folder / "summary.docx").write_bytes(b"what Mimi wrote")

    client, manager = _fixture(tmp_path)
    _session(
        manager,
        "s-1",
        folder,
        _turn(
            "write_document",
            {"path": "summary.docx", "blocks": []},
            {"path": "summary.docx", "bytes": 18},
        ),
    )

    rows = client.get("/v1/sessions/s-1/artifacts").json()["artifacts"]
    assert [r["path"] for r in rows] == ["summary.docx"]
    assert rows[0]["kind"] == "office" and rows[0]["abs_path"].endswith("summary.docx")


def test_reading_a_folder_produces_nothing(tmp_path):
    """The distinction that matters: opening files is not making them."""
    folder = tmp_path / "reading-room"
    folder.mkdir()
    (folder / "paper.pdf").write_bytes(b"%PDF-")
    client, manager = _fixture(tmp_path)
    _session(
        manager,
        "s-2",
        folder,
        _turn("read_document", {"path": "paper.pdf"}, {"path": "paper.pdf", "text": "…"}),
    )
    assert client.get("/v1/sessions/s-2/artifacts").json()["artifacts"] == []


def test_charts_and_files_written_into_a_second_granted_folder_both_count(tmp_path):
    workspace = tmp_path / "ws"
    shared = tmp_path / "shared"
    workspace.mkdir()
    (workspace / "figures").mkdir()
    shared.mkdir()
    (workspace / "figures" / "trend.png").write_bytes(b"\x89PNG")
    (shared / "report.xlsx").write_bytes(b"xl")

    client, manager = _fixture(tmp_path)
    messages = _turn(
        "run_python",
        {"code": "plot()"},
        {"stdout": "", "figures": ["figures/trend.png"]},
        call_id="c1",
    ) + _turn(
        "write_workbook",
        {"path": str(shared / "report.xlsx")},
        {"path": str(shared / "report.xlsx")},
        call_id="c2",
    )
    _session(
        manager,
        "s-3",
        workspace,
        messages,
        extra=[{"path": str(shared), "writable": True, "label": "shared"}],
    )

    rows = {r["name"] for r in client.get("/v1/sessions/s-3/artifacts").json()["artifacts"]}
    assert rows == {"trend.png", "report.xlsx"}


def test_a_path_outside_the_granted_folders_is_never_listed(tmp_path):
    """A tool result is data. A path in one that points outside what the user granted
    doesn't become previewable just because it was echoed back."""
    workspace = tmp_path / "ws2"
    workspace.mkdir()
    outsider = tmp_path / "elsewhere.docx"
    outsider.write_bytes(b"not yours to show")
    client, manager = _fixture(tmp_path)
    _session(
        manager,
        "s-4",
        workspace,
        _turn("write_document", {"path": str(outsider)}, {"path": str(outsider)}),
    )
    assert client.get("/v1/sessions/s-4/artifacts").json()["artifacts"] == []


def test_a_conversation_that_wrote_nothing_shows_nothing_in_a_real_folder(tmp_path):
    folder = tmp_path / "untouched"
    folder.mkdir()
    (folder / "notes.md").write_text("mine", encoding="utf-8")
    client, manager = _fixture(tmp_path)
    _session(manager, "s-5", folder, [{"role": "user", "content": "hello"}])
    assert client.get("/v1/sessions/s-5/artifacts").json()["artifacts"] == []


def test_the_per_conversation_scratch_folder_is_all_its_own_work(tmp_path):
    """Cowork's temporary space holds nothing but this conversation's output, so an
    untracked file there (a shell redirect, say) is still its artifact."""
    client, manager = _fixture(tmp_path)
    scratch = manager.scratch_base() / "abc123-test"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "draft.md").write_text("# Draft", encoding="utf-8")
    try:
        _session(manager, "s-6", scratch, [{"role": "user", "content": "hi"}])
        names = [r["name"] for r in client.get("/v1/sessions/s-6/artifacts").json()["artifacts"]]
        assert "draft.md" in names
    finally:
        (scratch / "draft.md").unlink(missing_ok=True)
        scratch.rmdir()
