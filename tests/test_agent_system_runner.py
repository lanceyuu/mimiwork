"""The agent-system runner: graph logic only, with every agent replaced by a script."""

from __future__ import annotations

import copy
import threading
import time

from coworker.agent_systems import from_dict, patterns
from coworker.agent_systems.runner import MAX_STEPS, Runner, answer_to_decision
from coworker.providers.effort import effort_settings


def _pattern(name):
    return from_dict(next(p["system"] for p in patterns() if p["pattern"] == name))


class Script:
    """Replies per node id, in order; records who ran with what."""

    def __init__(self, replies=None, decisions=None):
        self.replies = {k: list(v) for k, v in (replies or {}).items()}
        self.decisions = list(decisions or [])
        self.calls: list[tuple[str, str]] = []
        self.lock = threading.Lock()

    def agent(self, node, prompt, workers):
        with self.lock:
            self.calls.append((node["id"], prompt))
            queue = self.replies.get(node["id"])
            reply = queue.pop(0) if queue else f"{node['id']} output"
        if callable(reply):
            return reply(workers)
        return reply

    def coding(self, node, prompt):
        return self.agent(node, prompt, [])

    def person(self, node, draft):
        self.calls.append((node["id"], draft))
        return self.decisions.pop(0)

    def runner(self, system, saves=None):
        return Runner(system, call_agent=self.agent, call_coding=self.coding, ask_person=self.person,
                      save=(lambda r: saves.append(copy.deepcopy(r))) if saves is not None else (lambda _r: None))

    def ran(self):
        return [nid for nid, _ in self.calls]


def test_a_sequence_hands_each_result_to_the_next_step():
    s = Script()
    run = s.runner(_pattern("sequence")).run("We arrive at 23:30.")
    assert s.ran() == ["extract", "policy", "draft"]
    assert "extract output" in s.calls[1][1] and "We arrive at 23:30." in s.calls[1][1]
    assert run["status"] == "done" and run["result"] == "draft output"


def test_a_router_fires_only_the_labelled_edge_and_passes_on_the_original_request():
    s = Script({"triage": ["**Late arrival**\nThey land at night."]})
    run = s.runner(_pattern("routing")).run("We arrive at 23:30.")
    assert s.ran() == ["triage", "late"]
    assert s.calls[1][1].endswith("We arrive at 23:30.")
    assert run["node_states"]["info"] == "skipped" and run["node_states"]["owner"] == "skipped"


def test_a_router_that_picks_nothing_stops_the_run_plainly():
    s = Script({"triage": ["I am not sure."]})
    run = s.runner(_pattern("routing")).run("Hello")
    assert run["status"] == "stopped" and "did not pick" in run["notes"][0]


def test_parallel_branches_run_together_and_join_before_the_next_agent():
    started, overlap = [], threading.Event()

    def slow(_workers):
        started.append(time.monotonic())
        time.sleep(0.2)
        if len(started) >= 2:
            overlap.set()
        return "finding"

    s = Script({"needs": [slow], "rules": [slow], "cost": [slow]})
    run = s.runner(_pattern("parallel")).run("Group of ten, one week.")
    assert overlap.is_set()
    assert s.ran()[-1] == "combine" and s.ran().count("combine") == 1
    combine_prompt = s.calls[-1][1]
    assert all(f"From Check {w}" in combine_prompt for w in ("needs", "policy", "cost"))
    assert run["status"] == "done"


def test_a_reflection_loop_revises_until_the_checker_passes_and_returns_the_draft():
    s = Script({"draft": ["first draft", "second draft"], "check": ["REVISE\nWrong breakfast time.", "PASS"]})
    run = s.runner(_pattern("reflection")).run("Breakfast times?")
    assert s.ran() == ["draft", "check", "draft", "check"]
    assert "Wrong breakfast time." in s.calls[2][1] and "first draft" in s.calls[2][1]
    assert run["result"] == "second draft" and run["rounds"] == {"check->draft": 1}


def test_an_agent_sent_back_by_a_loop_still_sees_what_it_was_working_from():
    system = from_dict({"nodes": [
        {"id": "facts", "instructions": "x"}, {"id": "draft", "instructions": "x"},
        {"id": "check", "instructions": "x"}],
        "edges": [{"from": "facts", "to": "draft"}, {"from": "draft", "to": "check"},
                  {"from": "check", "to": "draft", "max_rounds": 2}]})
    s = Script({"facts": ["Breakfast 07:00-10:00"], "check": ["REVISE\nToo long.", "PASS"]})
    s.runner(system).run("Breakfast?")
    redraft = [p for nid, p in s.calls if nid == "draft"][1]
    assert "Breakfast 07:00-10:00" in redraft and "Too long." in redraft


def test_a_reflection_loop_stops_at_its_round_limit_and_says_so():
    s = Script({"check": ["REVISE\nstill wrong"] * 10})
    run = s.runner(_pattern("reflection")).run("x")
    assert s.ran().count("draft") == 4  # the first draft plus three revisions
    assert run["status"] == "done" and "still asked for changes" in run["notes"][0]


def test_the_run_cap_stops_a_runaway_graph():
    nodes = [{"id": f"n{i}", "instructions": "x"} for i in range(2)]
    system = from_dict({"nodes": nodes, "edges": [{"from": "n0", "to": "n1"},
                                                  {"from": "n1", "to": "n0", "max_rounds": 5}]})
    s = Script({"n1": ["REVISE"] * 100})
    run = s.runner(system).run("x")
    assert len(s.calls) <= MAX_STEPS and run["status"] == "done"
    assert run["rounds"]["n1->n0"] == 5


def test_a_review_waits_for_the_person_then_revises_with_their_comment_and_finishes():
    s = Script({"draft": ["refund 50", "refund 80"]}, decisions=[("revise", "Offer 80."), ("approve", "")])
    saves = []
    run = s.runner(_pattern("human_review"), saves).run("Refund please.")
    assert s.ran() == ["draft", "review", "draft", "review", "final"]
    assert "Offer 80." in s.calls[2][1]
    assert any(r["node_states"].get("review") == "waiting_for_person" for r in saves)
    assert run["status"] == "done" and run["result"] == "final output"


def test_a_reviewer_can_stop_the_run():
    s = Script(decisions=[("stop", "")])
    run = s.runner(_pattern("human_review")).run("Refund please.")
    assert run["status"] == "stopped" and "final" not in s.ran()


def test_a_lead_agent_calls_its_helpers_as_tools_and_they_never_run_on_their_own():
    def lead(workers):
        names = [w["id"] for w, _ in workers]
        assert names == ["booking", "billing", "local"]
        return " + ".join(fn(f"task for {w['id']}") for w, fn in workers[:2])

    s = Script({"lead": [lead]})
    run = s.runner(_pattern("multi_agent")).run("Room and refund?")
    assert s.ran() == ["lead", "booking", "billing"]
    assert run["result"] == "booking output + billing output"
    assert run["node_states"]["local"] == "skipped" and run["node_states"]["booking"] == "done"


def test_a_failing_agent_leaves_a_readable_failed_run():
    def boom(_w):
        raise RuntimeError("model unavailable")

    s = Script({"policy": [boom]})
    run = s.runner(_pattern("sequence")).run("x")
    assert run["status"] == "failed" and "model unavailable" in run["notes"][0]
    assert run["node_states"]["policy"] == "failed" and run["node_states"]["draft"] == "queued"


def test_the_persons_answer_becomes_a_decision_and_a_comment():
    assert answer_to_decision("Approve") == ("approve", "")
    assert answer_to_decision({"answer": "Stop the run"}) == ("stop", "")
    assert answer_to_decision("Send back: offer 80 instead") == ("revise", "offer 80 instead")


def test_effort_becomes_each_providers_own_setting_and_nothing_where_unverified():
    assert effort_settings("anthropic:claude-opus-5-5", "high") == {"output_config": {"effort": "high"}}
    assert effort_settings("anthropic:claude-haiku-4-5", "high") == {}
    assert effort_settings("openai:gpt-5.6-sol", "low") == {"reasoning_effort": "low"}
    assert effort_settings("gpt-5.5", "medium") == {"reasoning_effort": "medium"}
    assert effort_settings("qualitati:mimi-wolf", "high") == {"reasoning_effort": "high"}
    assert effort_settings("qualitati_cn:mimi-wolf", "high") == {}
    assert effort_settings("gemini:gemini-3.1-pro", "high") == {}
    assert effort_settings("anthropic:claude-opus-5-5", "") == {}
