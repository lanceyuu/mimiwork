/** Memory graph: data states — the canvas simulation itself is visual. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryGraph } from "./MemoryGraph";

function stubGraph(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => body }) as Response),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MemoryGraph", () => {
  it("shows the teach-the-syntax empty state when there are no memories", async () => {
    stubGraph({ nodes: [], edges: [] });
    render(<MemoryGraph />);
    const empty = await screen.findByTestId("memory-graph-empty");
    expect(empty.textContent).toContain("[[links]]");
    expect(empty.textContent).toContain("#tags");
  });

  it("renders the canvas and legend when the graph has nodes", async () => {
    stubGraph({
      nodes: [
        { id: "m:1", kind: "memory", label: "teal branding", scope: "global", memory_id: 1, degree: 1 },
        { id: "t:branding", kind: "tag", label: "#branding", degree: 1 },
      ],
      edges: [{ source: "m:1", target: "t:branding", kind: "tag" }],
    });
    render(<MemoryGraph />);
    expect(await screen.findByTestId("memory-graph-canvas")).toBeTruthy();
    const legend = screen.getByTestId("memory-graph-legend");
    expect(legend.textContent).toContain("Global");
    expect(legend.textContent).toContain("#tag");
  });

  it("a failed fetch degrades to the empty state, not a crash", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("down"); }));
    render(<MemoryGraph />);
    expect(await screen.findByTestId("memory-graph-empty")).toBeTruthy();
  });
});
