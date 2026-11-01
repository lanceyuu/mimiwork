/** One agent's settings: model, effort, tools, and the coding-agent fields. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AgentEdge, AgentNode, CodingAgent } from "../../api";
import { NodeInspector } from "./NodeInspector";

afterEach(cleanup);

const node = (over: Partial<AgentNode> = {}): AgentNode => ({
  id: "a", kind: "agent", name: "Drafter", instructions: "Draft it.", model: "", effort: "", tools: [],
  agent: "", folder: "", position: { x: 0, y: 0 }, ...over,
});

const CODEX = {
  key: "codex", label: "Codex", models: [{ id: "gpt-6-codex", label: "GPT-6 Codex" }],
} as unknown as CodingAgent;

function setup(n: AgentNode, edges: AgentEdge[] = []) {
  const props = {
    node: n,
    nodes: [n, node({ id: "b", name: "Checker" })],
    edges,
    isEntry: true,
    problems: [],
    models: ["qualitati:mimi-hound", "anthropic:claude-sonnet-5-5"],
    modelLabels: { "qualitati:mimi-hound": "Mimi Hound · QualiTaTi" },
    defaultModel: "qualitati:mimi-hound",
    codingAgents: [CODEX],
    onChange: vi.fn(),
    onEdgeChange: vi.fn(),
    onConnect: vi.fn(),
    onRemoveEdge: vi.fn(),
    onMakeEntry: vi.fn(),
    onDelete: vi.fn(),
    onClose: vi.fn(),
  };
  render(<NodeInspector {...props} />);
  return props;
}

describe("NodeInspector", () => {
  it("a Mimi agent offers the app's models, with the chat's model as the empty choice", () => {
    const p = setup(node());
    const options = within(screen.getByTestId("node-model")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["The model this chat uses (now Mimi Hound)", "Mimi Hound", "claude-sonnet-5-5"]);
    fireEvent.change(screen.getByTestId("node-model"), { target: { value: "anthropic:claude-sonnet-5-5" } });
    expect(p.onChange).toHaveBeenCalledWith({ model: "anthropic:claude-sonnet-5-5" });
  });

  it("thinking effort and tools change in place", () => {
    const p = setup(node({ tools: ["files"] }));
    fireEvent.change(screen.getByTestId("node-effort"), { target: { value: "high" } });
    expect(p.onChange).toHaveBeenCalledWith({ effort: "high" });
    fireEvent.click(screen.getByLabelText("Search"));
    expect(p.onChange).toHaveBeenCalledWith({ tools: ["files", "search"] });
    fireEvent.click(screen.getByLabelText("Files"));
    expect(p.onChange).toHaveBeenCalledWith({ tools: [] });
  });

  it("a coding agent shows its tool, that tool's models and the folder instead of Mimi's tools", () => {
    const p = setup(node({ kind: "coding", agent: "codex", model: "" }));
    expect(screen.queryByTestId("node-tools")).toBeNull();
    expect(screen.queryByTestId("node-model")).toBeNull();
    const models = within(screen.getByTestId("node-coding-model")).getAllByRole("option").map((o) => o.textContent);
    expect(models).toEqual(["Codex's own setting", "GPT-6 Codex"]);
    fireEvent.change(screen.getByTestId("node-folder"), { target: { value: "~/site" } });
    expect(p.onChange).toHaveBeenCalledWith({ folder: "~/site" });
  });

  it("changing the coding agent clears a model that belonged to the old one", () => {
    const p = setup(node({ kind: "coding", agent: "codex", model: "gpt-6-codex" }), []);
    fireEvent.change(screen.getByTestId("node-agent"), { target: { value: "codex" } });
    expect(p.onChange).toHaveBeenCalledWith({ agent: "codex", model: "" });
  });

  it("a human review has no model or tools to set", () => {
    setup(node({ kind: "review" }));
    expect(screen.queryByTestId("node-model")).toBeNull();
    expect(screen.queryByTestId("node-tools")).toBeNull();
    expect(screen.getByText("What should the person check?")).toBeTruthy();
  });

  it("a connection can be made to loop back with a round limit, or removed", () => {
    const edge: AgentEdge = { from: "a", to: "b", kind: "flow", label: "", max_rounds: null };
    const p = setup(node(), [edge]);
    fireEvent.change(screen.getByLabelText("Loop limit for the connection to Checker"), { target: { value: "2" } });
    expect(p.onEdgeChange).toHaveBeenCalledWith(edge, { max_rounds: 2 });
    fireEvent.click(screen.getByLabelText("Remove the connection to Checker"));
    expect(p.onRemoveEdge).toHaveBeenCalledWith(edge);
  });
});
