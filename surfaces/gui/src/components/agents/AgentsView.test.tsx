/** The Agents section: describe a need, start from a pattern, open and run a system. */
import "./flowTestEnv";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

afterEach(cleanup);

const NODE = {
  id: "draft", kind: "agent", name: "Draft the reply", instructions: "Write.", model: "", effort: "", tools: [],
  agent: "", folder: "", position: { x: 0, y: 0 },
};
const SYSTEM = {
  id: "as-1", title: "Reply desk", description: "Drafts replies.", pattern: "sequence", nodes: [NODE], edges: [],
  entry: "draft", builder_session: "", created_at: 1, updated_at: 1,
};
const PATTERN = (pattern: string, group: string, title: string) => ({
  pattern, group, title, summary: `${title} summary`, when: "Always.",
  system: { title, description: "", pattern, nodes: [{ ...NODE, id: pattern }], edges: [], entry: pattern },
});

const api = vi.hoisted(() => ({
  systems: [] as unknown[],
  createAgentSystem: vi.fn(),
  updateAgentSystem: vi.fn(),
  getAgentSystemRuns: vi.fn(async () => [] as unknown[]),
}));

vi.mock("../../api", () => ({
  AGENT_TOOLS: [{ id: "files", label: "Files" }],
  getAgentSystems: async () => api.systems,
  getAgentSystemPatterns: async () => [
    PATTERN("sequence", "Flow", "Sequence"),
    PATTERN("reflection", "Loops", "Reflection"),
    PATTERN("human_review", "Collaboration", "Human review"),
  ],
  getAgentSystem: async () => ({ ok: true, system: SYSTEM, problems: [] }),
  createAgentSystem: api.createAgentSystem,
  updateAgentSystem: api.updateAgentSystem,
  deleteAgentSystem: vi.fn(async () => ({ ok: true })),
  exportAgentSystem: vi.fn(async () => ({ ok: true, path: "/Users/x/Downloads/system.json" })),
  getAgentSystemRuns: api.getAgentSystemRuns,
  announceAgentSystemsChanged: vi.fn(),
  getSettings: async () => ({ models: ["qualitati:mimi-hound"], model: "qualitati:mimi-hound", model_labels: {} }),
  getCodingAgents: async () => [],
}));

import { AgentsView } from "./AgentsView";

describe("AgentsView", () => {
  it("describing a need becomes a design request for Mimi", async () => {
    const onBuild = vi.fn();
    render(<AgentsView onBuild={onBuild} />);
    fireEvent.change(screen.getByTestId("agents-wish"), { target: { value: "answer guest emails" } });
    fireEvent.click(screen.getByTestId("agents-describe-go"));
    expect(onBuild).toHaveBeenCalledWith("Design an agent system for me: answer guest emails");
  });

  it("the pattern gallery is grouped the way the deck groups them, each with a picture", async () => {
    render(<AgentsView onBuild={vi.fn()} />);
    const gallery = await screen.findByTestId("agents-gallery");
    const groups = [...gallery.querySelectorAll(".apps-gallery-cat")].map((g) => g.textContent);
    expect(groups).toEqual(["Flow", "Loops", "Collaboration"]);
    expect(screen.getByTestId("agent-pattern-reflection").querySelector(".ag-mini")).toBeTruthy();
  });

  it("picking a pattern saves it as a new system and opens it", async () => {
    api.createAgentSystem.mockResolvedValueOnce({ ok: true, system: SYSTEM, problems: [] });
    render(<AgentsView onBuild={vi.fn()} />);
    fireEvent.click(await screen.findByTestId("agent-pattern-sequence"));
    await waitFor(() => expect(api.createAgentSystem).toHaveBeenCalledWith(expect.objectContaining({ pattern: "sequence" })));
    expect(await screen.findByTestId("agent-system-page")).toBeTruthy();
    expect(await screen.findByTestId("agent-canvas")).toBeTruthy();
  });

  it("running a system opens a chat that asks Mimi to run it on the input", async () => {
    const onBuild = vi.fn();
    render(<AgentsView onBuild={onBuild} initialOpenId="as-1" />);
    fireEvent.click(await screen.findByTestId("agent-system-run"));
    fireEvent.change(screen.getByTestId("agent-run-input"), { target: { value: "Can I check in late?" } });
    fireEvent.click(screen.getByTestId("agent-run-go"));
    expect(onBuild.mock.calls[0][0]).toContain('Run the agent system "Reply desk" (id as-1) with run_agent_system');
    expect(onBuild.mock.calls[0][0]).toContain("Can I check in late?");
  });

  it("the newest run's status and agent states show on the page", async () => {
    api.getAgentSystemRuns.mockResolvedValue([
      { run_id: "run-0000abcd", system_id: "as-1", status: "working", node_states: { draft: "working" } },
      { run_id: "run-0000aaaa", system_id: "as-1", status: "done", node_states: { draft: "done" } },
    ]);
    render(<AgentsView onBuild={vi.fn()} initialOpenId="as-1" />);
    expect((await screen.findByTestId("agent-run-status")).textContent).toContain("Running");
    await waitFor(() => expect(screen.getByTestId("agent-node-draft").getAttribute("data-state")).toBe("working"));
    api.getAgentSystemRuns.mockResolvedValue([]);
  });

  it("export says where the file went", async () => {
    render(<AgentsView onBuild={vi.fn()} initialOpenId="as-1" />);
    fireEvent.click(await screen.findByTestId("agent-system-export"));
    expect(await screen.findByText("Saved to /Users/x/Downloads/system.json.")).toBeTruthy();
  });
});
