import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { WorkspaceView } from "./WorkspaceView";

// Files surface — tree + viewer against a mocked /v1/workspace API.
const treeFixture = {
  root: "/ws/demo",
  root_label: "demo",
  roots: [{ index: 0, path: "/ws/demo", label: "demo" }],
  path: ".",
  entries: [
    { name: "analysis", type: "dir", size: 0, modified_at: 1, path: "analysis" },
    { name: "notes.md", type: "file", size: 1234, modified_at: 2, path: "notes.md" },
  ],
};
const readFixture = {
  path: "notes.md",
  full_path: "/ws/demo/notes.md",
  start_line: 1,
  end_line: 2,
  total_lines: 2,
  content: "1\tfirst\n2\tsecond",
};

function mockFetch(routes: Record<string, unknown>) {
  const calls: string[] = [];
  const fn = vi.fn((input: RequestInfo) => {
    const url = String(input);
    calls.push(url);
    for (const [prefix, body] of Object.entries(routes)) {
      if (url.includes(prefix)) {
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
      }
    }
    return Promise.resolve(new Response(JSON.stringify({ error: "not found" }), { status: 404 }));
  });
  vi.stubGlobal("fetch", fn);
  return { calls };
}

beforeEach(() => {
  // PanelHead lives in IntegrationsView, which imports api.ts → tauri-ish code;
  // keep the tree shallow by rendering WorkspaceView only (its own apiGet is local).
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("WorkspaceView", () => {
  it("loads the tree on mount and lists entries", async () => {
    const { calls } = mockFetch({ "/v1/workspace/tree": treeFixture });
    render(<WorkspaceView workspace="/ws/demo" sessionId="s1" />);
    await waitFor(() => {
      expect(screen.getByTestId("workspace-entry-analysis")).toBeTruthy();
    });
    expect(screen.getByTestId("workspace-entry-notes.md")).toBeTruthy();
    // containment params ride along
    expect(calls.some((c) => c.includes("workspace=%2Fws%2Fdemo") || c.includes("workspace=/ws/demo"))).toBe(true);
  });

  it("filters entries by the filter box", async () => {
    mockFetch({ "/v1/workspace/tree": treeFixture });
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => screen.getByTestId("workspace-entry-notes.md"));
    const box = screen.getByTestId("workspace-filter") as HTMLInputElement;
    // React 18 event: set value + dispatch
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
    setter.call(box, "notes");
    box.dispatchEvent(new Event("input", { bubbles: true }));
    await waitFor(() => {
      expect(screen.queryByTestId("workspace-entry-analysis")).toBeNull();
      expect(screen.getByTestId("workspace-entry-notes.md")).toBeTruthy();
    });
  });

  it("opens a file into the viewer with line numbers", async () => {
    mockFetch({
      "/v1/workspace/tree": treeFixture,
      "/v1/workspace/read": readFixture,
    });
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => screen.getByTestId("workspace-entry-notes.md"));
    screen.getByTestId("workspace-entry-notes.md").click();
    await waitFor(() => {
      expect(screen.getByTestId("workspace-file-title").textContent).toContain("notes.md");
    });
    expect(screen.getByTestId("workspace-file-content").textContent).toContain("first");
    expect(screen.getByTestId("workspace-file-content").textContent).toContain("second");
  });

  it("shows the error card when the server rejects the path", async () => {
    mockFetch({ "/v1/workspace/tree": { error: "no workspace folder is open" } });
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => {
      const el = screen.getByTestId("workspace-error");
      expect(el.textContent).toContain("no workspace folder");
    });
  });
});
