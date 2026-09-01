/** The automation flow: an n8n-shaped diagram of THIS automation — the chain of what
 *  happens, and, hanging below it, what the agent is made of. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(cleanup);
import { AutomationFlow, flowNodes } from "./AutomationFlow";
import type { Automation } from "../api";

const TASK: Automation = {
  id: "task-1",
  title: "Pipeline digest",
  instructions: "summarize the pipeline",
  schedule: "Mondays at 09:00",
  workspace: "/u/projects/sales",
  agent: "cowork",
  enabled: true,
  next_run: null,
  last_run: null,
  last_status: null,
  run_count: 0,
  notify_on_completion: true,
  always_allowed: [
    { entry: "e1", tool: "send_message", target: "slack:C9" },
    { entry: "e2", tool: "run_shell", target: null },
  ],
};

describe("flowNodes — the diagram describes THIS automation", () => {
  it("splits the main chain from what the agent is made of", () => {
    const { trigger, agent, subs, success, failure } = flowNodes(TASK);

    // The chain: when it runs, who runs it, and the two ways it ends.
    expect(trigger.sub).toBe("Mondays at 09:00");
    expect(agent.title).toBe("MimiWork");
    expect(success.title).toBe("Delivered");
    expect(failure.title).toBe("If it fails");

    // The sub-nodes are what it is BUILT from, not steps that follow — n8n draws these
    // below on dashed wires, and conflating the two is what made every automation's
    // diagram look the same.
    const ids = subs.map((s) => s.id);
    expect(ids.slice(0, 2)).toEqual(["model", "folder"]);
    expect(subs.map((s) => s.title)).toContain("send_message");
    expect(subs.map((s) => s.title)).toContain("run_shell");
  });

  it("the agent node says what it may do without asking", () => {
    // It used to say "Approval-gated" whatever the mode was — the diagram stating the
    // opposite of the truth for an automation set to Full access (owner-hit 2026-08-31).
    expect(flowNodes({ ...TASK, mode: "auto" }).agent.sub).toBe("runs unattended");
    expect(flowNodes({ ...TASK, mode: "plan" }).agent.sub).toBe("proposes only");
    expect(flowNodes({ ...TASK, mode: "interactive" }).agent.sub).toBe("asks before acting");
  });

  it("a send grant means the result is DELIVERED, and says where", () => {
    const { success } = flowNodes(TASK);
    expect(success.sub).toContain("slack:C9");
  });

  it("with no delivery it says where the result is kept instead", () => {
    const { success } = flowNodes({ ...TASK, always_allowed: [], notify_on_completion: false });
    expect(success.title).toBe("Saved");
    expect(success.sub).toBe("kept in Automations");
  });

  it("names the model that answers the run, without its routing prefix", () => {
    const { subs } = flowNodes({ ...TASK, model: "qualitati:mimi-wolf" });
    const model = subs.find((s) => s.id === "model")!;
    expect(model.title).toBe("mimi-wolf");
    expect(model.title).not.toContain("qualitati:");
  });

  it("falls back to the app default rather than an empty circle", () => {
    const { subs } = flowNodes({ ...TASK, model: null });
    expect(subs.find((s) => s.id === "model")!.title).toBe("App default");
  });

  it("a task's internal __task__ folder shows its parent workspace instead", () => {
    const { subs } = flowNodes({ ...TASK, workspace: "/u/MimiWork/__task__task-abc123" });
    expect(subs.find((s) => s.id === "folder")!.title).toBe("MimiWork");
  });

  it("a paused schedule is visibly muted", () => {
    const { trigger } = flowNodes({ ...TASK, enabled: false });
    expect(trigger.title).toContain("paused");
    expect(trigger.tone).toBe("muted");
  });

  it("a failed last run tints the failure branch", () => {
    expect(flowNodes({ ...TASK, last_status: "error" }).failure.tone).toBe("danger");
    expect(flowNodes({ ...TASK, last_status: "ok" }).failure.tone).toBe("muted");
  });

  it("an automation with no grants still draws both outcomes", () => {
    // Every generic flow diagram leaves the failure half out; a run that can only be
    // shown succeeding has never met a real automation.
    const { subs, success, failure } = flowNodes({ ...TASK, always_allowed: [] });
    expect(subs).toHaveLength(2); // model + folder, nothing else claimed
    expect(success).toBeTruthy();
    expect(failure).toBeTruthy();
  });
});

describe("AutomationFlow — rendering", () => {
  it("draws the chain, both outcomes and every capability", () => {
    render(<AutomationFlow task={TASK} />);
    expect(screen.getByTestId("automation-flow")).toBeTruthy();
    for (const id of ["trigger", "agent", "output", "failure"]) {
      expect(screen.getByTestId(`flow-node-${id}`)).toBeTruthy();
    }
    for (const id of ["model", "folder", "grant-0", "grant-1"]) {
      expect(screen.getByTestId(`flow-sub-${id}`)).toBeTruthy();
    }
  });

  it("two different automations do not draw the same picture", () => {
    // The complaint that started this: the diagram looked identical whatever the
    // automation did.
    const { container: a } = render(<AutomationFlow task={TASK} />);
    const first = a.querySelector("svg")!.textContent;
    cleanup();
    const { container: b } = render(
      <AutomationFlow
        task={{ ...TASK, always_allowed: [], mode: "auto", model: "qualitati:mimi-wolf", enabled: false }}
      />,
    );
    expect(b.querySelector("svg")!.textContent).not.toBe(first);
  });

  it("nodes are clickable when the caller wants them to be", () => {
    const onNodeClick = vi.fn();
    render(<AutomationFlow task={TASK} onNodeClick={onNodeClick} />);
    fireEvent.click(screen.getByTestId("flow-node-agent"));
    expect(onNodeClick).toHaveBeenCalledWith("agent");
    fireEvent.click(screen.getByTestId("flow-sub-model"));
    expect(onNodeClick).toHaveBeenCalledWith("model");
  });
});
