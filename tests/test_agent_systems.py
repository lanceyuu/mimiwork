"""Agent systems: a graph of agents the user designs once and runs again (Agents section).

The saved file is the whole design; validation explains, node by node, what stops a
design from running, without refusing to save a half-drawn one.
"""

from __future__ import annotations

import asyncio
import threading

import aisuite as ai
from helpers import CapturingProvider

from coworker.agent_systems import AgentSystemStore, from_dict, patterns, to_mermaid, validate
from coworker.agent_systems.tools import _agent_caller, agent_system_tools
from coworker.engine import ApprovalOutcome
from coworker.providers.base import AssistantTurn, ToolCall
from coworker.server.manager import SessionManager


def _system(**over):
    base = {
        "title": "Desk",
        "nodes": [
            {"id": "a", "name": "Draft", "instructions": "Draft it."},
            {"id": "b", "name": "Check", "instructions": "Check it."},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    return from_dict({**base, **over})


def _messages(system):
    return [p["message"] for p in validate(system)]


def test_every_one_of_the_nine_patterns_is_ready_to_run():
    found = patterns()
    assert [p["pattern"] for p in found] == [
        "sequence", "routing", "parallel", "reflection", "react",
        "planning", "tool_use", "multi_agent", "human_review",
    ]
    for p in found:
        assert validate(from_dict(p["system"])) == [], p["pattern"]


def test_a_system_round_trips_through_its_folder_with_an_a2a_style_card(tmp_path):
    store = AgentSystemStore(tmp_path)
    made = store.create(_system().public())
    assert made.id.startswith("sys-")
    again = AgentSystemStore(tmp_path).get(made.id)
    assert again is not None and [n["name"] for n in again.nodes] == ["Draft", "Check"]
    card = again.public()["card"]
    assert card["name"] == "Desk" and [s["name"] for s in card["skills"]] == ["Draft", "Check"]
    assert again.public()["mimiwork_agent_system"] == 1


def test_ids_that_are_not_ours_never_become_paths(tmp_path):
    store = AgentSystemStore(tmp_path)
    assert store.get("../../etc") is None
    assert store.delete("sys-zzzz") is False
    assert store.get_run("sys-00000000", "../x") is None


def test_unknown_keys_in_a_saved_node_are_dropped():
    system = from_dict({"nodes": [{"id": "a", "instructions": "x", "approver": "none", "mode": "auto"}]})
    assert "approver" not in system.nodes[0] and "mode" not in system.nodes[0]


def test_a_circle_without_a_round_limit_is_refused_but_a_limited_loop_is_fine():
    circle = _system(edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a"}])
    assert any("circle" in m for m in _messages(circle))
    loop = _system(edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a", "max_rounds": 3}])
    assert validate(loop) == []
    too_many = _system(edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a", "max_rounds": 9}])
    assert any("1 to 5" in m for m in _messages(too_many))


def test_a_router_must_offer_distinctly_labelled_choices():
    nodes = [{"id": "r", "kind": "router", "instructions": "Sort."},
             {"id": "x", "instructions": "X."}, {"id": "y", "instructions": "Y."}]
    unlabelled = from_dict({"nodes": nodes, "edges": [{"from": "r", "to": "x"}, {"from": "r", "to": "y"}]})
    assert validate(unlabelled)[0]["node"] == "r"
    labelled = from_dict({"nodes": nodes, "edges": [{"from": "r", "to": "x", "label": "x"},
                                                    {"from": "r", "to": "y", "label": "y"}]})
    assert validate(labelled) == []


def test_only_a_lead_agent_assigns_work_and_its_workers_stay_off_the_main_flow():
    nodes = [{"id": "lead", "kind": "orchestrator", "instructions": "Lead."},
             {"id": "w", "instructions": "Work."}, {"id": "z", "instructions": "Then."}]
    ok = from_dict({"nodes": nodes, "edges": [{"from": "lead", "to": "w", "kind": "assign"},
                                              {"from": "lead", "to": "z"}]})
    assert validate(ok) == []
    tangled = from_dict({"nodes": nodes, "edges": [{"from": "lead", "to": "w", "kind": "assign"},
                                                   {"from": "w", "to": "z"}]})
    assert any(p["node"] == "w" for p in validate(tangled))
    wrong_lead = from_dict({"nodes": nodes[1:], "edges": [{"from": "w", "to": "z", "kind": "assign"}]})
    assert any("lead agent" in m for m in _messages(wrong_lead))


def test_a_coding_agent_needs_a_known_cli_and_a_folder_and_tools_must_exist():
    system = from_dict({"nodes": [
        {"id": "c", "kind": "coding", "agent": "copilot"},
        {"id": "m", "instructions": "x", "tools": ["files", "teleport"], "effort": "extreme"},
    ]})
    by_node = {}
    for p in validate(system):
        by_node.setdefault(p["node"], []).append(p["message"])
    assert any("coding agent" in m for m in by_node["c"]) and any("folder" in m for m in by_node["c"])
    assert any("teleport" in m for m in by_node["m"]) and any("effort" in m for m in by_node["m"])


def test_the_mermaid_diagram_shows_loops_and_assignments_differently():
    text = to_mermaid(from_dict(patterns()[3]["system"]))
    assert 'check -->|"revise (up to 3x)"| draft' in text
    lead = to_mermaid(from_dict(patterns()[7]["system"]))
    assert "lead -.-> booking" in lead and 'lead[["Lead agent"]]' in lead


def test_the_manager_saves_a_half_drawn_design_and_reports_what_blocks_it(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    m = SessionManager(data_dir=tmp_path / "data", provider=CapturingProvider())
    made = m.create_agent_system({"title": "Draft", "nodes": [{"id": "a"}]})
    assert made["ok"] and made["problems"] == [{"node": "a", "message": "Tell this agent what to do."}]
    sid = made["system"]["id"]
    fixed = m.update_agent_system(sid, {"nodes": [{"id": "a", "instructions": "Do it."}]})
    assert fixed["problems"] == [] and fixed["system"]["title"] == "Draft"
    assert [s["id"] for s in m.list_agent_systems()["systems"]] == [sid]
    assert m.delete_agent_system(sid)["ok"] and m.get_agent_system(sid)["ok"] is False


# -- the tools Mimi uses -------------------------------------------------------------


class SettingsProvider(CapturingProvider):
    def __init__(self, turns=()):
        super().__init__(turns)
        self.seen: list[tuple[str, dict]] = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.seen.append((model, settings))
        return super().complete(model=model, messages=messages, tools=tools, **settings)


def _tools(tmp_path, provider, **kw):
    store = AgentSystemStore(tmp_path / "systems")
    tools = {t.__name__: t for t in agent_system_tools(
        store, session_id="s1", workspace=tmp_path, provider=provider, default_model="openai:gpt-5.5", **kw)}
    return store, tools


def test_only_running_a_system_asks_first(tmp_path):
    _, tools = _tools(tmp_path, CapturingProvider())
    gated = {n for n, t in tools.items() if t.__aisuite_tool_metadata__.requires_approval}
    assert gated == {"run_agent_system"}
    assert set(tools) == {"create_agent_system", "update_agent_system", "list_agent_systems", "run_agent_system"}


def test_mimi_saves_a_design_and_gets_back_a_diagram_and_its_problems(tmp_path):
    store, tools = _tools(tmp_path, CapturingProvider())
    out = tools["create_agent_system"]({"title": "Desk", "nodes": [{"id": "a"}]})
    assert out["ok"] and out["mermaid"].startswith("flowchart LR") and out["problems"]
    assert store.get(out["id"]).builder_session == "s1"
    refused = tools["run_agent_system"](out["id"], "x")
    assert refused["error"] == "This system cannot run yet."


def test_each_agent_runs_on_its_own_model_and_effort(tmp_path):
    provider = SettingsProvider([AssistantTurn(text="facts", finish_reason="stop"),
                                 AssistantTurn(text="the reply", finish_reason="stop")])
    store, tools = _tools(tmp_path, provider)
    made = tools["create_agent_system"]({"title": "Two", "nodes": [
        {"id": "a", "instructions": "Find facts.", "model": "anthropic:claude-opus-5-5", "effort": "high"},
        {"id": "b", "instructions": "Write.", "effort": "low"},
    ], "edges": [{"from": "a", "to": "b"}]})
    out = tools["run_agent_system"]("Two", "Breakfast?")
    assert out["status"] == "done" and out["result"] == "the reply"
    assert provider.seen[0] == ("anthropic:claude-opus-5-5", {"output_config": {"effort": "high"}})
    assert provider.seen[1] == ("openai:gpt-5.5", {"reasoning_effort": "low"})
    assert store.get_run(made["id"], out["run_id"])["status"] == "done"


def test_a_gated_tool_inside_a_subagent_still_asks_the_person(tmp_path, monkeypatch):
    sent: list[str] = []

    def send_note(text: str) -> str:
        """Send a note outside the machine.

        Args:
            text (str): The note.
        """
        sent.append(text)
        return "sent"

    gated = ai.tool(send_note, metadata=ai.ToolMetadata(
        category="messaging", risk_level="high", capabilities=["send"], requires_approval=True))
    monkeypatch.setattr("coworker.catalog.expand", lambda ids, ctx: [gated] if ids else [])
    asked: list[str] = []

    async def approver(request):
        asked.append(request.tool_name)
        return ApprovalOutcome.DENY

    # The turn's own loop, running elsewhere, as it does in the app.
    main = asyncio.new_event_loop()
    threading.Thread(target=main.run_forever, daemon=True).start()
    provider = CapturingProvider([
        AssistantTurn(tool_calls=[ToolCall(id="c1", name="send_note", arguments={"text": "hi"})],
                      finish_reason="tool_calls"),
        AssistantTurn(text="could not send", finish_reason="stop"),
    ])
    try:
        call = _agent_caller("Sender", provider, "openai:gpt-5.5", tmp_path, None, approver, main)
        reply = call({"id": "a", "name": "Sender", "instructions": "Send it.", "tools": ["x"],
                      "model": "", "effort": ""}, "go", [])
    finally:
        main.call_soon_threadsafe(main.stop)
    assert asked == ["send_note"] and sent == [] and reply == "could not send"


def test_a_systems_runs_list_newest_first_so_the_canvas_can_find_one_started_from_chat(tmp_path):
    import os

    store = AgentSystemStore(tmp_path)
    sid = store.create(_system().public()).id
    for i, rid in enumerate(("run-00000001", "run-00000002")):
        store.save_run({"run_id": rid, "system_id": sid, "status": "done"})
        path = tmp_path / sid / "runs" / f"{rid}.json"
        os.utime(path, (1000 + i, 1000 + i))
    assert [r["run_id"] for r in store.list_runs(sid)] == ["run-00000002", "run-00000001"]
    assert store.list_runs("sys-00000000") == [] and store.list_runs("../x") == []
