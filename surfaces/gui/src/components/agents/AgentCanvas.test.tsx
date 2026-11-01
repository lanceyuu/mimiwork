/** The agent-system diagram: add, connect, remove, autosave, problems and run states. */
import "./flowTestEnv";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AgentEdge, AgentNode } from "../../api";
import { AgentCanvas, newEdge } from "./AgentCanvas";

afterEach(cleanup);

const node = (id: string, over: Partial<AgentNode> = {}): AgentNode => ({
  id, kind: "agent", name: id.toUpperCase(), instructions: "Do it.", model: "", effort: "", tools: [],
  agent: "", folder: "", position: { x: 0, y: 0 }, ...over,
});
const flow = (from: string, to: string, over: Partial<AgentEdge> = {}): AgentEdge => ({
  from, to, kind: "flow", label: "", max_rounds: null, ...over,
});

const lastSave = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0];

describe("AgentCanvas", () => {
  it("adding a Mimi agent from the palette puts it on the canvas, opens its settings and saves", async () => {
    const onSave = vi.fn();
    render(<AgentCanvas system={{ nodes: [node("a")], edges: [], entry: "a" }} onSave={onSave} saveDelayMs={5} />);
    fireEvent.click(screen.getByTestId("agent-add-agent"));
    expect((await screen.findByTestId("agent-node-n2")).textContent).toContain("Mimi agent");
    expect((screen.getByTestId("node-name") as HTMLInputElement).value).toBe("Mimi agent");
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(lastSave(onSave).nodes.map((n: AgentNode) => n.kind)).toEqual(["agent", "agent"]);
  });

  it("connecting two agents from the settings panel saves a flow connection", async () => {
    const onSave = vi.fn();
    render(<AgentCanvas system={{ nodes: [node("a"), node("b")], edges: [], entry: "a" }} onSave={onSave} saveDelayMs={5} />);
    fireEvent.click(screen.getByTestId("agent-node-a"));
    fireEvent.change(await screen.findByTestId("node-connect"), { target: { value: "b" } });
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(lastSave(onSave).edges).toEqual([flow("a", "b")]);
  });

  it("a connection from a lead agent assigns work instead of passing it on", async () => {
    const onSave = vi.fn();
    render(<AgentCanvas system={{ nodes: [node("a")], edges: [], entry: "a" }} onSave={onSave} saveDelayMs={5} />);
    fireEvent.click(screen.getByTestId("agent-add-orchestrator"));
    fireEvent.change(await screen.findByTestId("node-connect"), { target: { value: "a" } });
    await waitFor(() => expect(lastSave(onSave).edges).toHaveLength(1));
    expect(lastSave(onSave).edges[0]).toMatchObject({ to: "a", kind: "assign" });
  });

  it("removing an agent also removes its connections and saves", async () => {
    const onSave = vi.fn();
    render(
      <AgentCanvas system={{ nodes: [node("a"), node("b")], edges: [flow("a", "b")], entry: "a" }} onSave={onSave} saveDelayMs={5} />,
    );
    fireEvent.click(screen.getByTestId("agent-node-b"));
    fireEvent.click(await screen.findByTestId("node-delete"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const saved = lastSave(onSave);
    expect(saved.nodes.map((n: AgentNode) => n.id)).toEqual(["a"]);
    expect(saved.edges).toEqual([]);
    expect(screen.queryByTestId("agent-node-b")).toBeNull();
  });

  it("removing the starting agent hands the start to another agent", async () => {
    const onSave = vi.fn();
    render(<AgentCanvas system={{ nodes: [node("a"), node("b")], edges: [], entry: "a" }} onSave={onSave} saveDelayMs={5} />);
    fireEvent.click(screen.getByTestId("agent-node-a"));
    fireEvent.click(await screen.findByTestId("node-delete"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(lastSave(onSave).entry).toBe("b");
  });

  it("a burst of typing becomes one save with the final text", async () => {
    const onSave = vi.fn();
    render(<AgentCanvas system={{ nodes: [node("a")], edges: [], entry: "a" }} onSave={onSave} saveDelayMs={60} />);
    fireEvent.click(screen.getByTestId("agent-node-a"));
    const name = await screen.findByTestId("node-name");
    for (const v of ["D", "Dr", "Dra", "Draft"]) fireEvent.change(name, { target: { value: v } });
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(lastSave(onSave).nodes[0].name).toBe("Draft");
  });

  it("a change still pending when the page closes is saved right away", () => {
    const onSave = vi.fn();
    const { unmount } = render(
      <AgentCanvas system={{ nodes: [node("a")], edges: [], entry: "a" }} onSave={onSave} saveDelayMs={10_000} />,
    );
    fireEvent.click(screen.getByTestId("agent-add-review"));
    expect(onSave).not.toHaveBeenCalled();
    unmount();
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(lastSave(onSave).nodes).toHaveLength(2);
  });

  it("problems are pinned on their agent and whole-design problems show above the diagram", () => {
    render(
      <AgentCanvas
        system={{ nodes: [node("a")], edges: [], entry: "a" }}
        problems={[
          { node: "a", message: "Tell this agent what to do." },
          { node: "", message: "Choose which agent starts the work." },
        ]}
      />,
    );
    expect(screen.getByTestId("agent-node-a").textContent).toContain("Tell this agent what to do.");
    expect(screen.getByTestId("agent-problems").textContent).toContain("Choose which agent starts the work.");
  });

  it("a run's node states light up each agent", () => {
    render(
      <AgentCanvas
        system={{ nodes: [node("a"), node("b")], edges: [flow("a", "b")], entry: "a" }}
        nodeStates={{ a: "done", b: "working" }}
      />,
    );
    expect(screen.getByTestId("agent-node-a").getAttribute("data-state")).toBe("done");
    expect(screen.getByTestId("agent-node-b").getAttribute("data-state")).toBe("working");
    expect(screen.getByTestId("agent-node-b").textContent).toContain("Working");
  });

  it("the gallery picture has no palette and nothing to edit", () => {
    render(<AgentCanvas system={{ nodes: [node("a")], edges: [], entry: "a" }} readOnly />);
    expect(screen.queryByTestId("agent-palette")).toBeNull();
    expect(screen.getByText("A")).toBeTruthy();
  });
});

describe("newEdge", () => {
  const nodes = [node("draft"), node("check"), node("review", { kind: "review" }), node("pick", { kind: "router" })];

  it("a connection that closes a circle becomes a loop with a round limit", () => {
    expect(newEdge(nodes, [flow("draft", "check")], "check", "draft")).toEqual(flow("check", "draft", { max_rounds: 3 }));
  });

  it("a review's way back is labelled revise", () => {
    expect(newEdge(nodes, [flow("draft", "review")], "review", "draft")).toMatchObject({ label: "revise", max_rounds: 3 });
  });

  it("a router's choice is labelled with the agent it leads to", () => {
    expect(newEdge(nodes, [], "pick", "check")).toMatchObject({ label: "CHECK", max_rounds: null });
  });

  it("the same connection twice, or an agent to itself, is refused", () => {
    expect(newEdge(nodes, [flow("draft", "check")], "draft", "check")).toBeNull();
    expect(newEdge(nodes, [], "draft", "draft")).toBeNull();
  });
});
