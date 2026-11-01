"""Walk an agent system's graph: run each agent when its inputs are in, follow its edges.

The runner owns the coordination, never the agents: no agent talks to another directly,
every hand-off goes through here (the lesson from DeepSeek's superagent prototype). That
keeps the hard limits enforceable in one place:

    * at most MAX_STEPS agent runs per system run, so a mis-drawn graph cannot spin;
    * a loop edge fires at most its own max_rounds;
    * a person's review blocks the run until they answer, from the chat or the Inbox.

How an agent's result picks the next edges:

    router        its first line names a label; only that edge fires, carrying the
                  ORIGINAL request (the router sorts, it does not rewrite).
    has a loop    a checker. First line PASS: what it checked moves on. Otherwise the
                  loop edge carries the feedback back, while rounds remain.
    review        Approve: the draft moves on. Send back: the "revise" edge carries the
                  comment back; with no rounds left (or no such edge) the run stops.
    otherwise     every outgoing flow edge fires: one is a sequence, several are parallel.

A node with several incoming edges waits until no upstream agent that could still
deliver to it is pending, which is a join that also works behind a router.

The model-facing callables (`call_agent`, `call_coding`, `ask_person`) are injected, so
this file is plain graph logic and the tests drive it with fakes.
"""

from __future__ import annotations

import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .models import REVISE, AgentSystem

MAX_STEPS = 40
_PARALLEL = 4

# A lead agent's helper: its node, and the function that runs it on one task.
Worker = tuple[dict[str, Any], Callable[[str], str]]
# (node, prompt, workers) -> reply text. `workers` is non-empty only for a lead agent.
CallAgent = Callable[[dict[str, Any], str, list[Worker]], str]
CallCoding = Callable[[dict[str, Any], str], str]
# (node, draft) -> ("approve" | "revise" | "stop", comment)
AskPerson = Callable[[dict[str, Any], str], tuple[str, str]]


class RunStopped(Exception):
    pass


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        clean = re.sub(r"[*_`#>\s]+", " ", line).strip()
        if clean:
            return clean
    return ""


def role_note(system: AgentSystem, node: dict[str, Any]) -> str:
    """What the runner needs from this agent's reply, appended to its instructions."""
    out = [e for e in system.edges if e["from"] == node["id"] and e["kind"] == "flow"]
    if node["kind"] == "router":
        labels = ", ".join(e["label"] for e in out)
        return f"\n\nStart your reply with exactly one of these choices on its own line: {labels}. Then say why in one sentence."
    if any(e["max_rounds"] for e in out) and node["kind"] != "review":
        return ("\n\nStart your reply with PASS on its own line if the work needs no changes. "
                "Otherwise start with REVISE on its own line, then list exactly what to change.")
    return ""


class Runner:
    def __init__(
        self,
        system: AgentSystem,
        *,
        call_agent: CallAgent,
        call_coding: CallCoding,
        ask_person: AskPerson,
        report: Callable[[str], None] = lambda _line: None,
        save: Callable[[dict[str, Any]], None] = lambda _run: None,
    ) -> None:
        self.system = system
        self.by_id = {n["id"]: n for n in system.nodes}
        self.flow = [e for e in system.edges if e["kind"] == "flow"]
        self.workers = {e["from"]: [] for e in system.edges if e["kind"] == "assign"}
        for e in system.edges:
            if e["kind"] == "assign" and e["to"] in self.by_id:
                self.workers[e["from"]].append(self.by_id[e["to"]])
        self.call_agent, self.call_coding, self.ask_person = call_agent, call_coding, ask_person
        self.report, self._save = report, save

    # -- graph helpers --------------------------------------------------------------
    def _out(self, node_id: str) -> list[dict[str, Any]]:
        return [e for e in self.flow if e["from"] == node_id]

    def _forward(self, node_id: str) -> list[dict[str, Any]]:
        return [e for e in self._out(node_id) if not e["max_rounds"]]

    def _loops(self, node_id: str) -> list[dict[str, Any]]:
        return [e for e in self._out(node_id) if e["max_rounds"]]

    def _upstream_of_pending(self, pending: set[str]) -> set[str]:
        seen, todo = set(pending), list(pending)
        while todo:
            for e in self._forward(todo.pop()):
                if e["to"] not in seen:
                    seen.add(e["to"])
                    todo.append(e["to"])
        return seen

    def _waits(self, node_id: str, busy: set[str]) -> bool:
        """True while an agent that could still deliver to this one is pending."""
        reach = self._upstream_of_pending(busy)
        return any(e["from"] in reach for e in self.flow if e["to"] == node_id and not e["max_rounds"])

    # -- run --------------------------------------------------------------------------
    def run(self, task: str) -> dict[str, Any]:
        # What each agent last received from upstream. A loop sends back only feedback;
        # without this, a drafter re-run by its checker loses the facts it was drafting
        # from and fills the reply with placeholders (live run, 2026-11-01).
        self._kept: dict[str, list[tuple[str, str]]] = {}
        run: dict[str, Any] = {
            "run_id": f"run-{secrets.token_hex(4)}",
            "system_id": self.system.id,
            "title": self.system.title,
            "input": task,
            "status": "working",
            "node_states": {n["id"]: "queued" for n in self.system.nodes},
            "outputs": {},
            "rounds": {},
            "steps": 0,
            "notes": [],
            "started_at": time.time(),
        }
        inbox: dict[str, list[tuple[str, str]]] = {self.system.entry: [("", task)]}
        try:
            self._loop(run, inbox)
        except RunStopped as stop:
            run["status"] = "stopped"
            run["notes"].append(str(stop))
        except Exception as e:  # an agent or CLI failure must still leave a readable run
            run["status"] = "failed"
            run["notes"].append(f"{type(e).__name__}: {e}")
        else:
            run["status"] = "done"
        for nid, state in run["node_states"].items():
            if run["status"] == "done" and state in ("queued", "working"):
                run["node_states"][nid] = "skipped"
            elif run["status"] == "failed" and state == "working":
                run["node_states"][nid] = "failed"
        run["result"] = self._result(run)
        run["finished_at"] = time.time()
        self._save(run)
        return run

    def _is_worker(self, node_id: str) -> bool:
        return any(node_id in [w["id"] for w in ws] for ws in self.workers.values())

    def _loop(self, run: dict[str, Any], inbox: dict[str, list[tuple[str, str]]]) -> None:
        with ThreadPoolExecutor(max_workers=_PARALLEL) as pool:
            while inbox:
                busy = set(inbox)
                ready = [n for n in inbox if not self._waits(n, busy - {n})]
                if not ready:  # only possible with a malformed graph validate() rejects
                    raise RunStopped("The agents are waiting on each other.")
                if run["steps"] + len(ready) > MAX_STEPS:
                    raise RunStopped(f"Stopped after {MAX_STEPS} agent runs, the limit for one run.")
                batch = {nid: inbox.pop(nid) for nid in ready}
                for nid in batch:
                    run["node_states"][nid] = "working"
                    self.report(f"{self.by_id[nid]['name']}: working")
                self._save(run)
                results = dict(zip(batch, pool.map(lambda nid: self._execute(run, nid, batch[nid]), batch)))
                run["steps"] += len(batch)
                for nid, (output, sends) in results.items():
                    run["outputs"][nid] = output
                    if run["node_states"][nid] == "working":
                        run["node_states"][nid] = "done"
                    self.report(f"{self.by_id[nid]['name']}: done")
                    for to, text in sends:
                        inbox.setdefault(to, []).append((nid, text))
                        if to in run["outputs"]:
                            run["node_states"][to] = "queued"  # a loop sends work back
                self._save(run)

    def _input(self, run: dict[str, Any], parts: list[tuple[str, str]]) -> str:
        if len(parts) == 1 and parts[0][0] == "":
            return parts[0][1]
        # The run's own input is already in the header; only agents' work goes below it.
        body = "\n\n".join(f"From {self.by_id[src]['name']}:\n{text}" for src, text in parts if src)
        return f"The task:\n{run['input']}\n\nWork handed to you:\n{body}"

    def _execute(self, run: dict[str, Any], nid: str, parts: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]]]:
        """Run one agent; return (its output, [(next node, what to send)]). `work` is what
        was handed over without the task header: what a checker or reviewer passes on."""
        node = self.by_id[nid]
        kind = node["kind"]
        looped_in = {e["from"] for e in self.flow if e["to"] == nid and e["max_rounds"]}
        fresh = [p for p in parts if p[0] not in looped_in]
        if fresh:
            self._kept[nid] = fresh
        else:
            parts = self._kept.get(nid, []) + parts
        prompt = self._input(run, parts)
        work = "\n\n".join(text for src, text in parts if src not in looped_in) if fresh else parts[-1][1]
        if kind == "review":
            return self._review(run, node, work)
        if kind == "coding":
            reply = self.call_coding(node, prompt + role_note(self.system, node))
        else:
            workers = [(w, self._worker_fn(run, w)) for w in self.workers.get(nid, [])]
            reply = self.call_agent(node, prompt + role_note(self.system, node), workers)
        if kind == "router":
            choice = _first_line(reply).lower()
            for e in self._out(nid):
                if e["label"].lower() in choice:
                    return reply, [(e["to"], work)]
            raise RunStopped(f"{node['name']} did not pick one of its choices.")
        loops = self._loops(nid)
        if loops:
            if _first_line(reply).upper().startswith("PASS"):
                return work, [(e["to"], work) for e in self._forward(nid)]
            feedback = f"Revise your work. Feedback from {node['name']}:\n{reply}\n\nThe work it checked:\n{work}"
            sends = self._send_back(run, node, loops[0], feedback)
            if sends:
                return reply, sends
            run["notes"].append(f"{node['name']} still asked for changes after the last allowed round.")
            return work, [(e["to"], work) for e in self._forward(nid)]
        return reply, [(e["to"], reply) for e in self._forward(nid)]

    def _worker_fn(self, run: dict[str, Any], worker: dict[str, Any]) -> Callable[[str], str]:
        def call(task: str) -> str:
            if run["steps"] >= MAX_STEPS:
                return f"Not run: the limit of {MAX_STEPS} agent runs for this run is reached."
            run["steps"] += 1
            run["node_states"][worker["id"]] = "working"
            self.report(f"{worker['name']}: working")
            try:
                if worker["kind"] == "coding":
                    out = self.call_coding(worker, task)
                else:
                    out = self.call_agent(worker, task, [])
            except Exception:
                run["node_states"][worker["id"]] = "failed"
                raise
            run["node_states"][worker["id"]] = "done"
            run["outputs"][worker["id"]] = out
            return out

        return call

    def _send_back(self, run: dict[str, Any], node: dict[str, Any], edge: dict[str, Any], text: str) -> list[tuple[str, str]]:
        key = f"{edge['from']}->{edge['to']}"
        used = run["rounds"].get(key, 0)
        if used >= edge["max_rounds"]:
            return []
        run["rounds"][key] = used + 1
        self.report(f"{node['name']}: sent back for round {used + 1} of {edge['max_rounds']}")
        return [(edge["to"], text)]

    def _review(self, run: dict[str, Any], node: dict[str, Any], draft: str) -> tuple[str, list[tuple[str, str]]]:
        run["node_states"][node["id"]] = "waiting_for_person"
        self._save(run)
        decision, comment = self.ask_person(node, draft)
        run["node_states"][node["id"]] = "working"
        if decision == "approve":
            return draft, [(e["to"], draft) for e in self._forward(node["id"]) if e["label"].lower() != REVISE]
        back = [e for e in self._out(node["id"]) if e["label"].lower() == REVISE and e["max_rounds"]]
        if decision == "revise" and back:
            sends = self._send_back(run, node, back[0], f"The reviewer sent this back:\n{comment}\n\nThe draft:\n{draft}")
            if sends:
                return draft, sends
        raise RunStopped(f"{node['name']} stopped the run" + (f": {comment}" if comment else "."))

    def _result(self, run: dict[str, Any]) -> str:
        """The output of every agent that ran and has nowhere further to send work."""
        ends = [n["id"] for n in self.system.nodes
                if n["id"] in run["outputs"] and not self._forward(n["id"]) and not self._is_worker(n["id"])]
        if not ends:
            return ""
        if len(ends) == 1:
            return run["outputs"][ends[0]]
        return "\n\n".join(f"## {self.by_id[n]['name']}\n{run['outputs'][n]}" for n in ends)


def worker_prompt_note(workers: list[dict[str, Any]]) -> str:
    names = "; ".join(f"{w['name']} ({w['kind']})" for w in workers)
    return f"\n\nYou lead this work. Your helpers, each callable as a tool: {names}. Give each a clear, self-contained task, then check and combine what they return."


def answer_to_decision(answer: Any) -> tuple[str, str]:
    """The person's answer to the review question as (decision, comment)."""
    text = answer if isinstance(answer, str) else str((answer or {}).get("answer", ""))
    low = text.strip().lower()
    if low.startswith("approve"):
        return "approve", ""
    if low.startswith("stop"):
        return "stop", ""
    comment = re.sub(r"^send (it )?back( with (a )?comment)?[:\s-]*", "", text.strip(), flags=re.I)
    return "revise", comment


def run_summary(run: dict[str, Any], *, limit: int = 12000) -> dict[str, Any]:
    out = {k: run[k] for k in ("run_id", "system_id", "status", "node_states", "steps") if k in run}
    out["result"] = (run.get("result") or "")[:limit]
    if run.get("notes"):
        out["notes"] = run["notes"]
    return out

