"""Keys a person saves in Settings for their own scripts: they reach the shell and the
Python kernel, the model never sees their values, and a name that would take over the
commands Mimi runs is refused."""

from __future__ import annotations

import sys

import pytest

from coworker import script_keys
from coworker.engine import _without_script_keys
from coworker.secrets import SecretStore
from coworker.tools.shell import LocalExecutor

VALUE = "sk-test-4f9a17c2e8b05d36"
SHOW = "echo got:$env:WORKSHOP_API_KEY" if sys.platform == "win32" else 'echo "got:$WORKSHOP_API_KEY"'


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    return SecretStore()


def test_a_saved_key_reaches_a_shell_that_was_already_open(store, tmp_path):
    shell = LocalExecutor(cwd=tmp_path)
    try:
        assert "got:" + VALUE not in shell.run(SHOW)["output"]
        assert script_keys.save(store, "WORKSHOP_API_KEY", VALUE) is None
        assert "got:" + VALUE in shell.run(SHOW)["output"]
        script_keys.remove(store, "WORKSHOP_API_KEY")
        assert VALUE not in shell.run(SHOW)["output"]
    finally:
        shell.close()


def test_a_saved_key_reaches_the_python_kernel(store, tmp_path):
    from coworker.tools.analysis.kernel import PythonKernel

    script_keys.save(store, "WORKSHOP_API_KEY", VALUE)
    kernel = PythonKernel(tmp_path)
    try:
        out = kernel.run("import os; print(len(os.environ['WORKSHOP_API_KEY']))")
        assert out["stdout"].strip() == str(len(VALUE))
    finally:
        kernel.close()


def test_a_key_a_script_prints_is_hidden_from_the_model(store):
    script_keys.save(store, "WORKSHOP_API_KEY", VALUE)
    shown = _without_script_keys({"exit_code": 0, "output": f"Authorization: Bearer {VALUE}\n"})
    assert shown == {"exit_code": 0, "output": "Authorization: Bearer [WORKSHOP_API_KEY hidden]\n"}
    assert _without_script_keys(f"key is {VALUE}") == "key is [WORKSHOP_API_KEY hidden]"


@pytest.mark.parametrize("name", ["PATH", "LD_PRELOAD", "PYTHONPATH", "DYLD_INSERT_LIBRARIES", "COWORKER_STATE_DIR"])
def test_a_name_that_would_change_what_commands_run_is_refused(store, name):
    assert script_keys.save(store, name, "/tmp/evil") is not None
    assert script_keys.load(store) == {}


@pytest.mark.parametrize("name", ["openrouter key", "1KEY", "KEY; rm -rf ~", "A", ""])
def test_a_name_that_is_not_a_plain_variable_name_is_refused(store, name):
    assert script_keys.save(store, name, VALUE) is not None


def test_a_key_with_a_line_break_is_refused(store):
    assert script_keys.save(store, "WORKSHOP_API_KEY", "abc\nexport PATH=/tmp") is not None


def test_a_key_with_quotes_arrives_unchanged(store, tmp_path):
    if sys.platform == "win32":
        pytest.skip("checked on the POSIX shell")
    tricky = "it's \"quoted\" $HOME `id`"
    script_keys.save(store, "WORKSHOP_API_KEY", tricky)
    shell = LocalExecutor(cwd=tmp_path)
    try:
        out = shell.run('printf "%s" "$WORKSHOP_API_KEY" | wc -c')["output"]
        assert int(out.strip()) == len(tricky)
    finally:
        shell.close()


def test_the_sidecar_lists_names_and_never_values(store):
    from coworker.server.manager import SessionManager

    manager = SessionManager.__new__(SessionManager)
    manager.secrets = store
    assert manager.set_script_key("WORKSHOP_API_KEY", VALUE) == {"ok": True, "names": ["WORKSHOP_API_KEY"]}
    refused = manager.set_script_key("PATH", "/tmp")
    assert refused["ok"] is False and refused["error"]
    assert VALUE not in str(manager.get_script_keys())
    assert manager.remove_script_key("WORKSHOP_API_KEY") == {"ok": True, "names": []}


def test_mimi_can_keep_a_key_the_person_pasted_and_asks_before_it_does(store, tmp_path):
    """Asked on four tiers to keep a pasted key for later chats (2026-11-19), every one
    answered that it could not and sent the person to Settings. The owner: "we always need
    to input API keys to the AI"."""
    from coworker.agents.base import AgentContext
    from coworker.catalog import expand

    shell = LocalExecutor(cwd=tmp_path)
    try:
        tools = {t.__name__: t for t in expand(["shell"], AgentContext(workspace=tmp_path, executor=shell))}
        keep = tools["save_script_key"]
        assert keep.__aisuite_tool_metadata__.requires_approval
        result = keep(name="WORKSHOP_API_KEY", value=VALUE)
        assert result["saved"] == "WORKSHOP_API_KEY" and VALUE not in str(result)
        assert script_keys.load(store) == {"WORKSHOP_API_KEY": VALUE}
        assert "got:" + VALUE in script_keys_shown(shell)
        assert "error" in keep(name="PATH", value="/tmp/evil")
        assert "error" in keep(name="lowercase", value=VALUE)
    finally:
        shell.close()


def script_keys_shown(shell):
    # The engine hides a saved value before the model sees it; the shell itself has it.
    return shell.run(SHOW)["output"]


def test_a_dotenv_file_is_read_into_names_and_keys():
    """The Settings card takes the lines of a .env file, so a person with a file of keys
    does not type each one."""
    text = '# keys\nOPENAI_API_KEY="sk-one"\nexport TAVILY_API_KEY=tvly-two\n\nBAD LINE\nempty=\nSPACED = three  \n'
    assert script_keys.parse_env(text) == [
        ("OPENAI_API_KEY", "sk-one"), ("TAVILY_API_KEY", "tvly-two"), ("SPACED", "three"),
    ]


def test_pasting_a_dotenv_file_saves_what_it_can_and_names_what_it_cannot(store):
    from coworker.server.manager import SessionManager

    manager = SessionManager.__new__(SessionManager)
    manager.secrets = store
    result = manager.set_script_keys_from_env(f"OPENAI_API_KEY={VALUE}\nPATH=/tmp/evil\nTAVILY_API_KEY='tvly-two'\n")
    assert result["ok"] and result["saved"] == ["OPENAI_API_KEY", "TAVILY_API_KEY"]
    assert result["names"] == ["OPENAI_API_KEY", "TAVILY_API_KEY"] and "PATH" in result["error"]
    assert VALUE not in str(result)
    assert not manager.set_script_keys_from_env("just some words")["ok"]
