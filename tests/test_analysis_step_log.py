"""The analysis written down as it runs, so a researcher has a script to read and re-run."""

from __future__ import annotations

from types import SimpleNamespace

from coworker.tools.analysis import python_tool
from coworker.tools.analysis.step_log import MARKER, append_restart, append_step


def test_a_successful_block_is_written_as_live_code_under_a_step_header(tmp_path):
    path = append_step(tmp_path, "df = pd.read_csv('a.csv')", failed=False, now=0)
    text = path.read_text(encoding="utf-8")
    assert path.name == "analysis_steps.py"
    assert text.startswith(MARKER + "\n")
    assert "# Step 1 · " in text
    assert "\ndf = pd.read_csv('a.csv')\n" in text


def test_a_failed_block_is_kept_commented_out_with_a_warning(tmp_path):
    path = append_step(tmp_path, "df = df.dropna()\nraise ValueError", failed=True, now=0)
    text = path.read_text(encoding="utf-8")
    assert "may have changed the data" in text
    assert "# df = df.dropna()" in text
    assert "\ndf = df.dropna()" not in text


def test_step_numbers_continue_from_the_headers_already_in_the_file(tmp_path):
    append_step(tmp_path, "a = 1", failed=False, now=0)
    append_step(tmp_path, "b = 2", failed=True, now=0)
    path = append_step(tmp_path, "c = 3", failed=False, now=0)
    text = path.read_text(encoding="utf-8")
    assert "# Step 3 · " in text and "# Step 4 · " not in text


def test_the_log_never_appends_to_a_file_it_did_not_start(tmp_path):
    theirs = tmp_path / "analysis_steps.py"
    theirs.write_text("print('my own script')\n", encoding="utf-8")
    path = append_step(tmp_path, "a = 1", failed=False, now=0)
    assert path.name == "analysis_steps-2.py"
    assert theirs.read_text(encoding="utf-8") == "print('my own script')\n"


def test_a_restart_note_is_written_only_into_an_existing_log(tmp_path):
    assert append_restart(tmp_path) is None
    assert not (tmp_path / "analysis_steps.py").exists()
    append_step(tmp_path, "a = 1", failed=False, now=0)
    append_restart(tmp_path)
    text = (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")
    assert "restarted" in text and "# Step 2" not in text


def test_a_folder_that_cannot_be_written_returns_none_instead_of_raising(tmp_path):
    missing = tmp_path / "gone"
    assert append_step(missing, "a = 1", failed=False, now=0) is None


def test_a_log_with_unreadable_bytes_is_left_alone_and_nothing_raises(tmp_path):
    bad = MARKER.encode() + b"\n\xff\xfe\n"
    (tmp_path / "analysis_steps.py").write_bytes(bad)
    append_step(tmp_path, "a = 1", failed=False, now=0)
    assert (tmp_path / "analysis_steps.py").read_bytes() == bad


class _FakeKernel:
    def __init__(self, reply):
        self.reply = reply

    def run(self, code, timeout):
        return self.reply

    def reset(self):
        pass


def _tools(tmp_path, monkeypatch, reply):
    monkeypatch.setattr(python_tool.KernelHandle, "kernel", lambda self: _FakeKernel(reply))
    run, reset = python_tool.python_tools(SimpleNamespace(workspace=tmp_path))
    return run, reset


def test_run_python_names_the_step_log_in_its_result(tmp_path, monkeypatch):
    run, _ = _tools(tmp_path, monkeypatch, {"ok": True, "stdout": "1"})
    result = run(code="print(1)")
    assert result["files"] == ["analysis_steps.py"]
    assert "print(1)" in (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")


def test_a_failed_run_is_logged_as_failed(tmp_path, monkeypatch):
    reply = {"ok": False, "error": {"message": "boom", "kind": "exception"}}
    run, _ = _tools(tmp_path, monkeypatch, reply)
    run(code="x = 1/0")
    assert "# x = 1/0" in (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")


def test_a_lost_kernel_writes_a_restart_note_after_the_step(tmp_path, monkeypatch):
    reply = {"ok": False, "error": {"message": "died", "kind": "crash", "state_lost": True}}
    run, _ = _tools(tmp_path, monkeypatch, reply)
    run(code="huge()")
    text = (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")
    assert text.index("# huge()") < text.index("restarted")


def test_reset_python_writes_a_restart_note(tmp_path, monkeypatch):
    run, reset = _tools(tmp_path, monkeypatch, {"ok": True})
    run(code="a = 1")
    reset()
    assert "restarted" in (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")


def test_the_schema_tells_the_model_where_the_steps_are_saved():
    assert "analysis_steps.py" in python_tool._RUN_SCHEMA["function"]["description"]
