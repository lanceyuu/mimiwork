"""Agent systems: a graph of agents the user designs once and runs again (Agents section).

The saved file is the whole design; validation explains, node by node, what stops a
design from running, without refusing to save a half-drawn one.
"""

from __future__ import annotations

from helpers import CapturingProvider

from coworker.agent_systems import AgentSystemStore, from_dict, patterns, to_mermaid, validate
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
