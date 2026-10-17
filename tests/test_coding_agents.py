"""Connecting Claude Code and Codex like any other tool — driven by fake CLIs on a bare PATH."""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from coworker.tools import delegate

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake CLIs are POSIX scripts")

CLAUDE = """
import json, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("2.1.270 (Claude Code)")
elif args[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": SIGNED_IN, "authMethod": "claude.ai", "email": "me@example.com"}))
    sys.exit(0 if SIGNED_IN else 1)
elif args[:1] == ["-p"]:
    open(LOG, "w").write(json.dumps(args))
    sys.stdin.read()
    for e in [
        {"type": "system", "subtype": "init", "session_id": "s1", "model": globals().get("RESOLVED", "")},
        {"type": "result", "subtype": "success", "is_error": False, "result": "OK"},
    ]:
        print(json.dumps(e), flush=True)
"""

CODEX = """
import json, sys, time
args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli 0.162.1")
elif args == ["login", "status"]:
    print("Logged in using ChatGPT" if SIGNED_IN else "Not logged in")
    sys.exit(0 if SIGNED_IN else 1)
elif args == ["debug", "models"]:
    if not globals().get("CATALOG"):
        print("error: unknown subcommand", file=sys.stderr)
        sys.exit(2)
    print(json.dumps({"models": CATALOG}))
elif args[:1] == ["exec"]:
    open(LOG, "w").write(json.dumps(args))
    sys.stdin.read()
    for e in [{"type": "thread.started", "thread_id": "t1"},
              {"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}},
              {"type": "turn.completed"}]:
        print(json.dumps(e), flush=True)
elif args == ["login"]:
    if not LOGIN_WORKS:
        print("Error: port 1455 is already in use", flush=True)
        sys.exit(1)
    print("Starting local login server on http://localhost:1455.", flush=True)
    print("If your browser did not open, navigate to this URL to authenticate:", flush=True)
    print("https://auth.openai.com/oauth/authorize?client=mimi", flush=True)
    time.sleep(30)
"""


@pytest.fixture(autouse=True)
def _clean_state():
    delegate._settings.clear()
    delegate._settings_path = None
    delegate._runs_path = None
    delegate._catalog.update(at=0.0, models=[])
    yield
    delegate._runs_path = None
    delegate._catalog.update(at=0.0, models=[])
    for proc in delegate._LOGINS.values():
        delegate._kill(proc)
    delegate._LOGINS.clear()
    delegate._settings.clear()
    delegate._settings_path = None


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # what an app opened from Finder gets
    # Only the fake home's bin: the real machine's Homebrew copy must not be found.
    monkeypatch.setattr(delegate, "_EXTRA_DIRS", ["~/.local/bin"])
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    return tmp_path


def _install(home, name, body, **values):
    script = home / f"{name}_cli.py"
    head = "".join(f"{k} = {v!r}\n" for k, v in values.items())
    script.write_text(head + textwrap.dedent(body), encoding="utf-8")
    exe = home / ".local" / "bin" / name
    # A shell wrapper, not a shebang: the interpreter's path may hold spaces.
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    exe.chmod(0o755)
    return exe


def test_the_page_shows_where_each_agent_is_installed_and_which_account_it_is_signed_in_with(home):
    claude = _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG="")
    _install(home, "codex", CODEX, SIGNED_IN=True, LOGIN_WORKS=True)

    c, x = delegate.agent_status("claude_code"), delegate.agent_status("codex")

    assert (c["installed"], c["path"], c["version"]) == (True, str(claude), "2.1.270 (Claude Code)")
    assert (c["signed_in"], c["account"], c["error"]) == (True, "me@example.com", "")
    assert (x["signed_in"], x["account"]) == (True, "ChatGPT")
    assert delegate.connection_problem("claude_code") == delegate.connection_problem("codex") == ""


def test_the_page_shows_the_model_and_effort_each_agent_uses_when_none_is_chosen(home):
    _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG="")
    _install(home, "codex", CODEX, SIGNED_IN=True, LOGIN_WORKS=True)
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text(json.dumps({"model": "opus", "effortLevel": "high"}))
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text(
        'model = "gpt-6-astra"\nmodel_reasoning_effort = "xhigh"\n\n[profiles.fast]\nmodel = "gpt-mini"\n'
    )

    assert delegate.agent_status("claude_code")["defaults"] == {"model": "opus", "effort": "high"}
    assert delegate.agent_status("codex")["defaults"] == {"model": "gpt-6-astra", "effort": "xhigh"}


def test_a_missing_agent_shows_how_to_install_it_and_delegation_points_to_the_page(home):
    status = delegate.agent_status("codex")

    assert (status["installed"], status["path"]) == (False, "")
    assert status["install_command"] == "npm install -g @openai/codex"
    assert "Codex is not installed" in delegate.connection_problem("codex")
    assert "Connectors > Coding agents" in delegate.connection_problem("codex")


def test_a_signed_out_agent_is_refused_before_anything_runs_with_directions_to_sign_in(home, tmp_path):
    log = tmp_path / "ran.json"
    _install(home, "claude", CLAUDE, SIGNED_IN=False, LOG=str(log))
    tools = {t.__name__: t for t in delegate.agent_team_tools(workspace=tmp_path, session_id="s")}

    error = tools["start_agent"](agent="claude_code", task="fix it")["error"]

    assert "Claude Code is installed but not signed in" in error
    assert "Connectors > Coding agents" in error
    assert not log.exists()
    assert delegate.agent_status("claude_code")["sign_in_command"] == "claude auth login"


def test_with_neither_agent_installed_asking_for_one_says_where_to_connect_it_without_an_approval(home, tmp_path):
    tools = delegate.agent_team_tools(workspace=tmp_path, session_id="s")

    assert [t.__name__ for t in tools] == ["start_agent"]
    assert tools[0].__aisuite_tool_metadata__.requires_approval is False
    assert "Connectors > Coding agents" in tools[0](agent="codex", task="t")["error"]


def test_an_agent_installed_after_the_conversation_began_never_runs_through_the_unapproved_tool(home, tmp_path):
    log = tmp_path / "ran.json"
    tools = delegate.agent_team_tools(workspace=tmp_path, session_id="s")
    _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG=str(log))

    assert "Start a new conversation" in tools[0](agent="claude_code", task="t")["error"]
    assert not log.exists()


def test_the_chosen_model_and_effort_reach_both_command_lines_and_blank_leaves_the_agents_default():
    claude = delegate.agent_command("claude_code", "claude", model="opus", effort="max")
    codex = delegate.agent_command("codex", "codex", "t1", model="gpt-6-astra", effort="high")

    assert claude[claude.index("--model") + 1] == "opus" and claude[claude.index("--effort") + 1] == "max"
    assert codex[codex.index("-m") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="high"' in codex and codex[-2:] == ["t1", "-"]
    assert "--model" not in delegate.agent_command("claude_code", "claude")
    assert "-m" not in delegate.agent_command("codex", "codex")


def test_a_chosen_model_survives_a_restart_and_a_name_that_could_break_the_command_is_refused(tmp_path):
    path = tmp_path / "coding-agents.json"
    delegate.load_settings(path)
    assert delegate.save_settings("codex", " gpt-6-astra ", "high") == {
        "ok": True, "model": "gpt-6-astra", "effort": "high", "keep_hooks": False,
    }

    delegate._settings.clear()
    delegate.load_settings(path)

    assert delegate.agent_settings("codex") == {"model": "gpt-6-astra", "effort": "high"}
    assert not delegate.save_settings("codex", 'x" -c sandbox_mode="danger', "")["ok"]
    assert not delegate.save_settings("codex", "--yolo", "")["ok"]
    assert not delegate.save_settings("claude_code", "", "minimal")["ok"]  # a Codex-only level
    assert delegate.agent_settings("codex")["model"] == "gpt-6-astra"


def test_the_test_button_makes_one_real_call_with_the_chosen_model_and_reports_the_reply(home, tmp_path):
    log = tmp_path / "argv.json"
    _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG=str(log))
    delegate.save_settings("claude_code", "haiku", "low")

    result = delegate.try_agent("claude_code")

    assert result["ok"] and result["reply"] == "OK"
    argv = json.loads(log.read_text())
    assert argv[argv.index("--model") + 1] == "haiku" and argv[argv.index("--effort") + 1] == "low"


def test_the_test_button_on_a_signed_out_agent_says_so_instead_of_running(home):
    _install(home, "codex", CODEX, SIGNED_IN=False, LOGIN_WORKS=True)

    result = delegate.try_agent("codex")

    assert not result["ok"] and "not signed in" in result["error"]


def test_sign_in_starts_the_agents_own_browser_login_and_hands_back_its_link(home):
    _install(home, "codex", CODEX, SIGNED_IN=False, LOGIN_WORKS=True)

    result = delegate.sign_in("codex")

    assert result == {"started": True, "url": "https://auth.openai.com/oauth/authorize?client=mimi"}
    assert delegate._LOGINS["codex"].poll() is None  # still waiting for the browser


def test_a_sign_in_that_cannot_start_says_why(home):
    _install(home, "codex", CODEX, SIGNED_IN=False, LOGIN_WORKS=False)

    result = delegate.sign_in("codex")

    assert not result["started"] and "port 1455 is already in use" in result["error"]


def test_the_coding_agents_routes_answer_for_both_agents_and_refuse_any_other_name(home, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from coworker.providers import ModelCapabilities, ProviderClient
    from coworker.server.app import create_app
    from coworker.server.manager import SessionManager

    class _Provider(ProviderClient):
        def complete(self, *, model, messages, tools=None, **settings):
            raise AssertionError("no turns expected")

        def capabilities(self, model):
            return ModelCapabilities()

    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    client = TestClient(create_app(SessionManager(workspace=tmp_path, provider=_Provider())))

    agents = client.get("/v1/coding-agents").json()["agents"]
    assert [a["key"] for a in agents] == ["claude_code", "codex"]
    assert client.post("/v1/coding-agents/codex/settings", json={"effort": "high"}).json()["ok"]
    assert client.get("/v1/coding-agents").json()["agents"][1]["effort"] == "high"
    assert client.post("/v1/coding-agents/rm -rf/test").status_code == 404
    assert client.post("/v1/coding-agents/gemini/sign-in").status_code == 404


CATALOG = [
    {"slug": "gpt-old", "display_name": "GPT-Old", "description": "Older model.", "priority": 5, "visibility": "list",
     "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]},
    {"slug": "gpt-internal", "display_name": "Internal", "priority": 0, "visibility": "hide",
     "supported_reasoning_levels": [{"effort": "low"}]},
    {"slug": "gpt-new", "display_name": "GPT-New", "description": "Latest model.", "priority": 1, "visibility": "list",
     "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}, {"effort": "ultra"}]},
]


def test_with_no_model_chosen_claude_code_runs_on_its_recommended_alias_and_the_page_learns_what_that_was(home, tmp_path):
    log = tmp_path / "argv.json"
    _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG=str(log), RESOLVED="claude-opus-5-5")
    assert delegate.agent_status("claude_code")["latest"] == ""  # not known until it has run

    result = delegate.try_agent("claude_code")

    argv = json.loads(log.read_text())
    assert argv[argv.index("--model") + 1] == "default"
    assert result["model"] == "claude-opus-5-5"
    assert delegate.agent_status("claude_code")["latest"] == "claude-opus-5-5"


def test_claude_code_offers_its_family_aliases_because_it_cannot_list_models(home):
    _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG="")
    delegate.note_resolved("claude_code", "opus", "claude-opus-5")

    status = delegate.agent_status("claude_code")

    assert status["models_listed"] is False
    assert [m["id"] for m in status["models"]] == ["fable", "opus", "sonnet", "haiku"]
    assert status["models"][1] == {"id": "opus", "label": "Latest Opus", "resolved": "claude-opus-5"}


def test_with_no_model_chosen_codex_runs_on_the_newest_model_in_its_own_catalog(home, tmp_path):
    log = tmp_path / "argv.json"
    _install(home, "codex", CODEX, SIGNED_IN=True, LOGIN_WORKS=True, LOG=str(log), CATALOG=CATALOG)

    status = delegate.agent_status("codex")
    result = delegate.try_agent("codex")

    assert status["models_listed"] and [m["id"] for m in status["models"]] == ["gpt-new", "gpt-old"]
    assert status["latest"] == "gpt-new" and status["efforts"] == ["low", "high", "ultra"]
    argv = json.loads(log.read_text())
    assert argv[argv.index("-m") + 1] == "gpt-new" and result["model"] == "gpt-new"
    assert delegate.save_settings("codex", "gpt-old", "ultra")["ok"]  # a level the catalog lists


def test_when_codex_cannot_list_its_models_the_page_falls_back_to_a_typed_name_and_codex_keeps_its_own_default(home, tmp_path):
    log = tmp_path / "argv.json"
    _install(home, "codex", CODEX, SIGNED_IN=True, LOGIN_WORKS=True, LOG=str(log), CATALOG=[])

    status = delegate.agent_status("codex")
    delegate.try_agent("codex")

    assert (status["models_listed"], status["models"], status["latest"]) == (False, [], "")
    assert "-m" not in json.loads(log.read_text())


def test_a_hand_off_is_listed_with_a_command_that_reopens_it_in_its_own_cli_from_its_folder(tmp_path):
    delegate.load_settings(tmp_path / "coding-agents.json")
    work = tmp_path / "my project" / ".mimiwork" / "agents" / "csv"
    work.mkdir(parents=True)
    job = delegate.Job("s", "claude_code", "claude", "csv export", work, "mimi/csv")
    job.resume_id, job.status = "sess-1", "finished"

    delegate.record_run(job)

    run = delegate.recent_runs()[0]
    assert (run["agent"], run["name"], run["branch"], run["session_id"]) == ("Claude Code", "csv export", "mimi/csv", "sess-1")
    assert run["resume_command"] == f"cd '{work}' && claude --resume sess-1"
    assert job.report()["resume_command"] == run["resume_command"]
    assert (tmp_path / "coding-agent-runs.json").exists()  # survives a restart


def test_codex_hand_offs_resume_with_codex_resume_and_a_removed_folder_still_gives_the_id(tmp_path):
    delegate.load_settings(tmp_path / "coding-agents.json")
    job = delegate.Job("s", "codex", "codex", "review", tmp_path / "gone", "mimi/review")
    job.resume_id, job.status = "thread-9", "failed"

    delegate.record_run(job)

    run = delegate.recent_runs()[0]
    assert run["resume_command"] == "codex resume thread-9"
    assert run["folder_exists"] is False and run["status"] == "failed"


def test_a_later_round_replaces_its_row_and_the_list_keeps_only_the_newest_fifty(tmp_path):
    delegate.load_settings(tmp_path / "coding-agents.json")
    jobs = [delegate.Job("s", "codex", "codex", f"task {n}", tmp_path, "") for n in range(52)]
    for job in jobs:
        job.resume_id, job.status = "t", "finished"
        delegate.record_run(job)
    jobs[-1].status = "failed"
    delegate.record_run(jobs[-1])

    runs = delegate.recent_runs()
    assert len(runs) == 50 and runs[0]["name"] == "task 51" and runs[0]["status"] == "failed"
    assert [r["name"] for r in runs].count("task 51") == 1


def test_a_job_that_never_started_a_session_is_not_listed(tmp_path):
    delegate.load_settings(tmp_path / "coding-agents.json")
    delegate.record_run(delegate.Job("s", "codex", "codex", "x", tmp_path, ""))
    assert delegate.recent_runs() == []


def test_claude_code_hand_offs_run_without_the_users_own_hooks_unless_the_page_keeps_them(home, tmp_path):
    log = tmp_path / "argv.json"
    _install(home, "claude", CLAUDE, SIGNED_IN=True, LOG=str(log))
    delegate.load_settings(tmp_path / "coding-agents.json")

    delegate.try_agent("claude_code")
    argv = json.loads(log.read_text())
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks": true}'
    assert delegate.agent_status("claude_code")["keep_hooks"] is False

    assert delegate.save_settings("claude_code", "", "", keep_hooks=True)["keep_hooks"] is True
    delegate.try_agent("claude_code")
    assert "--settings" not in json.loads(log.read_text())


def test_saving_a_model_leaves_the_hooks_choice_alone_and_codex_is_never_given_the_claude_setting(tmp_path):
    delegate.load_settings(tmp_path / "coding-agents.json")
    delegate.save_settings("claude_code", "", "", keep_hooks=True)

    delegate.save_settings("claude_code", "opus", "high")  # what the model and effort boxes send

    assert delegate.keeps_hooks("claude_code") is True
    assert delegate.run_settings("claude_code")["skip_hooks"] is False
    assert "--settings" not in delegate.agent_command("codex", "codex", skip_hooks=True)
