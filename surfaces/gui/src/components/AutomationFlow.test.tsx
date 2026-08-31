/** The automation flow: pipeline structure derived from task data. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
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

describe("flowNodes", () => {
  it("builds trigger → agent → one action per grant → output", () => {
    const { agentCol, actions, output } = flowNodes(TASK);
    expect(agentCol[0].sub).toBe("Mondays at 09:00");
    expect(agentCol[1].sub).toContain("sales"); // workspace basename, not the path
    // Grants, then the permission level — a standing grant is an exception to the
    // mode, not a replacement for it.
    expect(actions.map((a) => a.title)).toEqual(["send_message", "run_shell", "Asks first"]);
    expect(actions[0].sub).toBe("→ slack:C9");
    // A send grant means the result is DELIVERED, and the diagram should say where.
    expect(output.title).toBe("Delivered");
    expect(output.sub).toContain("slack:C9");
  });

  it("no grants → a single permission node, never an empty column", () => {
    const { actions } = flowNodes({ ...TASK, always_allowed: [] });
    expect(actions).toHaveLength(1);
    expect(actions[0].title).toBe("Asks first");
  });

  it("the permission node says what the automation ACTUALLY does", () => {
    // It used to say "Approval-gated" whatever the mode was — so an automation set to
    // Full access was drawn as one that asks, which is the diagram stating the opposite
    // of the truth (owner-hit 2026-08-31).
    const bare = { ...TASK, always_allowed: [] };
    expect(flowNodes({ ...bare, mode: "auto" }).actions[0].title).toBe("Runs unattended");
    expect(flowNodes({ ...bare, mode: "auto" }).actions[0].sub).toBe("acts without asking");
    expect(flowNodes({ ...bare, mode: "plan" }).actions[0].title).toBe("Proposes only");
    expect(flowNodes({ ...bare, mode: "interactive" }).actions[0].title).toBe("Asks first");
  });

  it("an unattended run with grants does not also claim to ask", () => {
    const { actions } = flowNodes({ ...TASK, mode: "auto" });
    expect(actions.map((a) => a.title)).toEqual(["send_message", "run_shell"]);
  });

  it("names the model that answers the run, without its routing prefix", () => {
    const { agentCol } = flowNodes({ ...TASK, model: "qualitati:mimi-wolf" });
    expect(agentCol[1].sub).toContain("mimi-wolf");
    expect(agentCol[1].sub).not.toContain("qualitati:");
  });

  it("a task's internal __task__ folder shows its parent workspace instead", () => {
    const { agentCol } = flowNodes({ ...TASK, workspace: "/u/MimiWork/__task__task-abc123" });
    expect(agentCol[1].sub).toBe("MimiWork");
  });

  it("a paused schedule is visibly muted", () => {
    const { agentCol } = flowNodes({ ...TASK, enabled: false });
    expect(agentCol[0].title).toContain("paused");
    expect(agentCol[0].tone).toBe("muted");
  });
});

describe("AutomationFlow", () => {
  it("renders every node as SVG", () => {
    render(<AutomationFlow task={TASK} />);
    expect(screen.getByTestId("automation-flow")).toBeTruthy();
    for (const id of ["trigger", "agent", "grant-0", "grant-1", "output"]) {
      expect(screen.getByTestId(`flow-node-${id}`)).toBeTruthy();
    }
  });
});
