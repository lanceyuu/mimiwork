/** Memory graph: data states — the canvas simulation itself is visual. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("MemoryGraph — right-click a dot to forget it (owner ask 2026-08-31)", () => {
  const GRAPH = {
    nodes: [
      { id: "m:1", kind: "memory", label: "Participants are coded P01–P24", scope: "global", memory_id: 1, degree: 1 },
      { id: "t:method", kind: "tag", label: "#method", degree: 1 },
    ],
    edges: [],
  };

  function stubCalls(body: unknown) {
    const calls: { url: string; method: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, method: (init?.method || "GET").toUpperCase() });
        return { ok: true, json: async () => body } as Response;
      }),
    );
    return calls;
  }

  /** Drive the handler the way a browser does: a contextmenu event on the canvas at the
   *  node's position. The initial layout is a deterministic ring — node i sits at
   *  (W/2 + cos(θ)·r, H/2 + sin(θ)·r) with r = 90 + (i%5)·26 — and jsdom reports the
   *  parent as zero-width, so the first memory node lands at (90, 210). */
  const rightClickFirstNode = (canvas: HTMLElement) => {
    canvas.dispatchEvent(
      new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 90, clientY: 210 }),
    );
  };

  it("offers Forget, asks with the memory's own words, and deletes on confirm", async () => {
    const calls = stubCalls(GRAPH);
    const onForgotten = vi.fn();
    render(<MemoryGraph onForgotten={onForgotten} />);
    const canvas = await screen.findByTestId("memory-graph-canvas");

    rightClickFirstNode(canvas);
    const menu = await screen.findByTestId("memory-graph-menu");
    expect(menu.textContent).toContain("Forget this memory");

    fireEvent.click(screen.getByTestId("memory-graph-forget"));
    // The confirm names the fact — "delete this node" means nothing when the dot is
    // one of two hundred.
    const dialog = await screen.findByTestId("confirm-dialog");
    expect(dialog.textContent).toContain("Participants are coded P01–P24");

    fireEvent.click(screen.getByTestId("confirm-accept"));
    await waitFor(() => {
      expect(calls.find((c) => c.url.includes("/v1/memory/1") && c.method === "DELETE")).toBeTruthy();
    });
    await waitFor(() => expect(onForgotten).toHaveBeenCalled());
  });

  it("cancelling forgets nothing", async () => {
    const calls = stubCalls(GRAPH);
    render(<MemoryGraph />);
    const canvas = await screen.findByTestId("memory-graph-canvas");

    rightClickFirstNode(canvas);
    fireEvent.click(await screen.findByTestId("memory-graph-forget"));
    fireEvent.click(screen.getByTestId("confirm-cancel"));

    expect(screen.queryByTestId("confirm-dialog")).toBeNull();
    expect(calls.find((c) => c.method === "DELETE")).toBeUndefined();
  });

  it("Escape closes the menu without deleting", async () => {
    const calls = stubCalls(GRAPH);
    render(<MemoryGraph />);
    const canvas = await screen.findByTestId("memory-graph-canvas");

    rightClickFirstNode(canvas);
    await screen.findByTestId("memory-graph-menu");
    // The dismiss listeners are armed on the NEXT frame (so the contextmenu that opened
    // the menu does not immediately close it), so wait one out before pressing Escape.
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    });
    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() => expect(screen.queryByTestId("memory-graph-menu")).toBeNull());
    expect(calls.find((c) => c.method === "DELETE")).toBeUndefined();
  });
});
