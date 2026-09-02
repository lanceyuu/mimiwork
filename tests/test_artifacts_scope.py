"""Artifacts = what the conversation produced, not what happens to sit in the folder it
was given (owner report 2026-08-24: a granted course folder listed every document in it).

The signal is the transcript itself — the tool calls that wrote files — so it is right for
conversations that predate this rule, and a folder full of the user's own work stays out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_an_artifact_link_opens_a_file_in_a_granted_folder_by_absolute_path(tmp_path, monkeypatch):
    """The agent ends a turn with [Open it](artifact:/abs/path.docx). When the deliverable
    was written into a folder the user ADDED, resolution used to look only in the workspace
    and the link went nowhere (owner report 2026-08-24)."""
    opened: list = []
    monkeypatch.setattr(
        "coworker.server.manager._os_reveal",
        lambda target, mode="reveal": opened.append((str(target), mode)) or {"ok": True},
    )
    workspace = tmp_path / "scratch"
    course = tmp_path / "Online marketing course"
    workspace.mkdir()
    course.mkdir()
    deliverable = course / "Debrief Module 2.docx"
    deliverable.write_bytes(b"docx")

    client, manager = _fixture(tmp_path)
    _session(
        manager,
        "s-link",
        workspace,
        _turn(
            "write_document",
            {"path": str(deliverable)},
            {"path": str(deliverable)},
        ),
        extra=[{"path": str(course), "writable": True, "label": "Online marketing course"}],
    )

    # It is listed as this conversation's artifact…
    rows = client.get("/v1/sessions/s-link/artifacts").json()["artifacts"]
    assert [r["name"] for r in rows] == ["Debrief Module 2.docx"]

    # …and the link's absolute path opens it.
    out = client.post(
        "/v1/sessions/s-link/artifacts/reveal",
        json={"path": str(deliverable), "mode": "open"},
    ).json()
    assert out["ok"] and opened == [(str(deliverable.resolve()), "open")]

    # A path outside every granted folder still goes nowhere.
    stranger = tmp_path / "elsewhere.docx"
    stranger.write_bytes(b"x")
    refused = client.post(
        "/v1/sessions/s-link/artifacts/reveal",
        json={"path": str(stranger), "mode": "open"},
    ).json()
    assert not refused["ok"] and len(opened) == 1


def test_the_deliverable_outranks_the_scratch_file_that_made_it(tmp_path):
    """A turn that writes a report also writes the script, the intermediate CSV and a
    note. Sorted by time alone the .docx someone actually wants lands under three files
    they never asked about (owner ask 2026-08-30), so type ranks above recency —
    recency still orders within a tier."""
    import os

    from coworker.server import SessionManager

    for index, name in enumerate(
        ["analysis.py", "notes.md", "chart.png", "rows.csv", "deck.pptx"]
    ):
        (tmp_path / name).write_text("x")
        os.utime(tmp_path / name, (2_000 + index, 2_000 + index))
    # The deliverable is the OLDEST file in the folder — the worst case for time sorting.
    (tmp_path / "Report.docx").write_text("x")
    os.utime(tmp_path / "Report.docx", (900, 900))

    rows = SessionManager(workspace=tmp_path).list_artifacts("no-session")
    order = [r["name"] for r in rows]
    assert order[:2] == ["deck.pptx", "Report.docx"]  # tier 0, newest first
    assert order.index("chart.png") < order.index("rows.csv")  # figure over data
    assert order[-1] == "notes.md"  # working files last
    assert "analysis.py" not in order  # machinery is not a deliverable (2026-09-02)
    assert [r["tier"] for r in rows] == sorted(r["tier"] for r in rows)


def test_a_full_folder_never_drops_a_deliverable_to_stay_under_the_cap(tmp_path):
    """The list is capped at 80. Ranking happens BEFORE the cut, so a folder full of
    fresh scratch files cannot push the one report off the end."""
    import os

    from coworker.server import SessionManager

    for i in range(120):
        p = tmp_path / f"step_{i:03d}.txt"  # working material, but not machinery
        p.write_text("x")
        os.utime(p, (9_000 + i, 9_000 + i))  # all newer than the report
    (tmp_path / "Final report.pdf").write_text("x")
    os.utime(tmp_path / "Final report.pdf", (100, 100))

    rows = SessionManager(workspace=tmp_path).list_artifacts("no-session")
    assert rows[0]["name"] == "Final report.pdf"
    assert len(rows) == 80


def test_a_file_written_by_running_code_still_shows_up(tmp_path, monkeypatch):
    """The deliverable a script PRODUCES is the point; the script is the leftover.

    Artifacts are harvested from the paths named in tool calls, so `write_file` put
    `extract_roster.py` on the list while the workbook that script went on to create was
    named by nobody and vanished from the rail (owner report 2026-09-02: "i only see all
    those python file in the artifact, but not the generated valuable new file").

    Inside a per-conversation scratch folder every file belongs to this conversation by
    construction — the same reasoning that already lets the empty case walk it.
    """
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-run"))

    script = workspace / "extract_roster.py"
    script.write_text("# writes the workbook", encoding="utf-8")
    produced = workspace / "GE_MM_2026_student_emails.xlsx"
    produced.write_bytes(b"the 496 students")

    _session(
        manager,
        "s-run",
        workspace,
        _turn("write_file", {"path": "extract_roster.py"}, {"path": "extract_roster.py"}),
    )

    names = [row["name"] for row in manager.list_artifacts("s-run")]
    assert "GE_MM_2026_student_emails.xlsx" in names, "the workbook is what the user wanted"
    assert "extract_roster.py" not in names, "the script that made it is machinery"


def test_walking_scratch_never_reaches_a_granted_folder(tmp_path, monkeypatch):
    """The union is scoped to scratch. A granted folder full of the user's own work
    must stay out — that is the 2026-08-24 report this module exists for."""
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-mix"))
    (workspace / "made-here.csv").write_bytes(b"produced")

    granted = tmp_path / "Course"
    granted.mkdir()
    (granted / "the-users-own-thesis.docx").write_bytes(b"not Mimi's")

    _session(
        manager,
        "s-mix",
        workspace,
        _turn("write_file", {"path": "made-here.csv"}, {"path": "made-here.csv"}),
        extra=[{"path": str(granted), "writable": False, "label": "Course"}],
    )

    names = [row["name"] for row in manager.list_artifacts("s-mix")]
    assert "made-here.csv" in names
    assert "the-users-own-thesis.docx" not in names


def test_the_script_that_made_the_deliverable_is_not_a_deliverable(tmp_path, monkeypatch):
    """Machinery is means, not end (owner ask 2026-09-02: "we would not put all those
    medium python file artifact, instead only meaningful output as artifacts")."""
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-quiet"))
    for name in ("extract_roster.py", "clean.sh", "notes.log", "report.md"):
        (workspace / name).write_text("x", encoding="utf-8")
    (workspace / "students.xlsx").write_bytes(b"the point")

    _session(
        manager,
        "s-quiet",
        workspace,
        _turn("write_file", {"path": "extract_roster.py"}, {"path": "extract_roster.py"}),
    )

    names = [row["name"] for row in manager.list_artifacts("s-quiet")]
    assert "students.xlsx" in names
    assert "report.md" in names, "prose the user reads is output, not machinery"
    assert "extract_roster.py" not in names
    assert "clean.sh" not in names
    assert "notes.log" not in names


def test_a_coding_session_still_shows_its_code(tmp_path, monkeypatch):
    """When the script IS the deliverable, hiding machinery would empty the panel."""
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-code"))
    (workspace / "solver.py").write_text("print(1)", encoding="utf-8")
    (workspace / "helper.py").write_text("pass", encoding="utf-8")

    _session(
        manager,
        "s-code",
        workspace,
        _turn("write_file", {"path": "solver.py"}, {"path": "solver.py"}),
    )

    names = [row["name"] for row in manager.list_artifacts("s-code")]
    assert "solver.py" in names, "nothing else was produced — the code is the output"


def test_an_automations_uploaded_reference_files_are_inputs_not_outputs(tmp_path, monkeypatch):
    """create_automation drops the creator's uploads in <workspace>/attachments. The scratch
    walk must not present them as something the run produced (review catch 2026-09-02)."""
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-auto"))
    (workspace / "attachments").mkdir()
    (workspace / "attachments" / "brief.pdf").write_bytes(b"the user's upload")
    (workspace / "digest.docx").write_bytes(b"what the run wrote")

    _session(
        manager,
        "s-auto",
        workspace,
        _turn("write_document", {"path": "digest.docx"}, {"path": "digest.docx"}),
    )

    names = [row["name"] for row in manager.list_artifacts("s-auto")]
    assert names == ["digest.docx"]


def test_r_markdown_is_a_document_not_machinery(tmp_path, monkeypatch):
    """An academic's standard deliverable — a report with R chunks — must not vanish
    beside its plain-markdown sibling (review catch 2026-09-02)."""
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-rmd"))
    (workspace / "analysis.Rmd").write_text("---\ntitle: x\n---", encoding="utf-8")
    (workspace / "helper.R").write_text("x <- 1", encoding="utf-8")
    (workspace / "figure.png").write_bytes(b"png")

    _session(
        manager,
        "s-rmd",
        workspace,
        _turn("write_file", {"path": "analysis.Rmd"}, {"path": "analysis.Rmd"}),
    )

    names = [row["name"] for row in manager.list_artifacts("s-rmd")]
    assert "analysis.Rmd" in names
    assert "helper.R" not in names


def test_a_differently_cased_tool_argument_does_not_list_one_file_twice(tmp_path, monkeypatch):
    """The transcript may name `Students.xlsx` while disk holds `students.xlsx`; on a
    case-insensitive volume those are one file and must be one row."""
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-case"))
    (workspace / "students.xlsx").write_bytes(b"rows")
    if not (workspace / "STUDENTS.XLSX").exists():
        pytest.skip("case-sensitive filesystem: the alias cannot exist here")

    _session(
        manager,
        "s-case",
        workspace,
        _turn("write_workbook", {"path": "STUDENTS.XLSX"}, {"path": "STUDENTS.XLSX"}),
    )

    rows = manager.list_artifacts("s-case")
    assert len(rows) == 1, [r["name"] for r in rows]
    assert rows[0]["name"].lower() == "students.xlsx"
