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
    expect(agentCol[1].sub).toBe("sales"); // workspace basename, not the path
    expect(actions.map((a) => a.title)).toEqual(["send_message", "run_shell"]);
    expect(actions[0].sub).toBe("→ slack:C9");
    expect(output.sub).toContain("completion note");
  });

  it("no grants → a single approval-gated node, never an empty column", () => {
    const { actions } = flowNodes({ ...TASK, always_allowed: [] });
    expect(actions).toHaveLength(1);
    expect(actions[0].title).toBe("Approval-gated");
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
