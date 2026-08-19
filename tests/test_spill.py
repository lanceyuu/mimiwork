"""Spill: oversized tool results go to a file, keeping head and tail in the conversation."""

from coworker.engine import _tool_result_message
from coworker.providers import ToolCall
from coworker.spill import DEFAULT_LIMIT, SpillStore


def _call(name="read_workbook"):
    return ToolCall(id="call_1", name=name, arguments={})


def test_small_content_passes_through_untouched(tmp_path):
    store = SpillStore(tmp_path)
    assert store.maybe_spill("small") == "small"
    assert store.spilled == 0
    assert not list(tmp_path.glob("*.txt"))


def test_content_at_the_limit_is_not_spilled(tmp_path):
    store = SpillStore(tmp_path, limit=1000)
    assert store.maybe_spill("x" * 1000) == "x" * 1000


def test_oversized_content_is_written_to_a_file(tmp_path):
    store = SpillStore(tmp_path, limit=5000)
    store.maybe_spill("y" * 20_000, label="read_workbook")

    files = list(tmp_path.glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text() == "y" * 20_000
    assert "read_workbook" in files[0].name


def test_both_head_and_tail_survive(tmp_path):
    """Errors and totals live at the end — a head-only cut hides what mattered."""
    store = SpillStore(tmp_path, limit=5000)
    content = "HEAD-MARKER" + ("x" * 30_000) + "TAIL-MARKER"

    result = store.maybe_spill(content)
    assert "HEAD-MARKER" in result
    assert "TAIL-MARKER" in result
    assert len(result) < len(content)


def test_the_summary_tells_the_model_where_the_rest_went(tmp_path):
    store = SpillStore(tmp_path, limit=5000)
    result = store.maybe_spill("z" * 40_000, label="run_python")

    assert "characters omitted" in result
    assert str(tmp_path) in result
    assert "narrower query" in result


def test_identical_content_reuses_one_file(tmp_path):
    store = SpillStore(tmp_path, limit=5000)
    store.maybe_spill("q" * 20_000)
    store.maybe_spill("q" * 20_000)
    assert len(list(tmp_path.glob("*.txt"))) == 1


def test_an_unwritable_directory_still_returns_a_summary(tmp_path):
    """A spill that can't be saved must degrade, not fail the turn."""
    blocker = tmp_path / "blocked"
    blocker.write_text("I am a file, not a directory")
    store = SpillStore(blocker / "sub", limit=5000)

    result = store.maybe_spill("w" * 20_000)
    assert "characters omitted" in result
    assert "could not be saved" in result


def test_a_label_with_path_characters_cannot_escape_the_spill_dir(tmp_path):
    store = SpillStore(tmp_path, limit=5000)
    store.maybe_spill("v" * 20_000, label="../../etc/passwd")

    files = list(tmp_path.glob("*.txt"))
    assert len(files) == 1
    assert files[0].parent == tmp_path


def test_non_string_content_passes_through(tmp_path):
    store = SpillStore(tmp_path)
    assert store.maybe_spill(None) is None


# -- engine integration ---------------------------------------------------------


def test_engine_message_is_unchanged_when_no_spill_store_is_attached():
    """Default None must keep the pre-existing behaviour byte-for-byte."""
    message = _tool_result_message(_call(), {"rows": [1, 2, 3]})
    assert message["content"] == '{"rows": [1, 2, 3]}'


def test_engine_message_spills_an_oversized_result(tmp_path):
    store = SpillStore(tmp_path, limit=5000)
    message = _tool_result_message(_call(), {"rows": ["x" * 40_000]}, store)

    assert len(message["content"]) < 20_000
    assert "characters omitted" in message["content"]
    assert store.spilled == 1


def test_engine_message_keeps_a_normal_result_verbatim(tmp_path):
    store = SpillStore(tmp_path, limit=DEFAULT_LIMIT)
    message = _tool_result_message(_call(), {"ok": True}, store)

    assert message["content"] == '{"ok": true}'
    assert store.spilled == 0


def test_spilled_message_keeps_its_tool_call_id(tmp_path):
    """The provider rejects a tool result that can't be paired with its call."""
    store = SpillStore(tmp_path, limit=1000)
    message = _tool_result_message(_call(), {"data": "x" * 40_000}, store)

    assert message["tool_call_id"] == "call_1"
    assert message["role"] == "tool"
