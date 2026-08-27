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

  // ── editor (manuscript workbench lite) ──

  it("Edit switches to the editor with the file's raw text", async () => {
    mockFetch({ "/v1/workspace/tree": treeFixture, "/v1/workspace/read": readFixture });
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => screen.getByTestId("workspace-entry-notes.md"));
    screen.getByTestId("workspace-entry-notes.md").click();
    await waitFor(() => screen.getByTestId("workspace-file-title"));
    screen.getByTestId("workspace-edit-btn").click();
    const editor = await waitFor(() => screen.getByTestId("workspace-editor") as HTMLTextAreaElement);
    // numbered lines are stripped back to raw text
    expect(editor.value).toContain("first");
    expect(editor.value).not.toMatch(/^\d+\t/);
  });

  it("Save posts to /v1/manuscript/save and marks saved state", async () => {
    const calls: Array<{ url: string; body?: unknown }> = [];
    const fn = vi.fn((input: RequestInfo, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.includes("/v1/workspace/tree")) {
        return Promise.resolve(new Response(JSON.stringify(treeFixture), { status: 200 }));
      }
      if (url.includes("/v1/workspace/read")) {
        return Promise.resolve(new Response(JSON.stringify(readFixture), { status: 200 }));
      }
      if (url.includes("/v1/manuscript/save")) {
        return Promise.resolve(new Response(JSON.stringify({ ok: true, saved: true, versions: 1 }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    });
    vi.stubGlobal("fetch", fn);
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => screen.getByTestId("workspace-entry-notes.md"));
    screen.getByTestId("workspace-entry-notes.md").click();
    await waitFor(() => screen.getByTestId("workspace-file-title"));
    screen.getByTestId("workspace-edit-btn").click();
    await waitFor(() => screen.getByTestId("workspace-editor"));
    const save = screen.getByTestId("workspace-save-btn") as HTMLButtonElement;
    // unchanged draft → disabled
    expect(save.disabled).toBe(true);
    // type something → enabled
    const editor = screen.getByTestId("workspace-editor") as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")!.set!;
    setter.call(editor, "first\nsecond\nedited");
    editor.dispatchEvent(new Event("input", { bubbles: true }));
    await waitFor(() => expect((screen.getByTestId("workspace-save-btn") as HTMLButtonElement).disabled).toBe(false));
    screen.getByTestId("workspace-save-btn").click();
    await waitFor(() => {
      const call = calls.find((c) => c.url.includes("/v1/manuscript/save"));
      expect(call).toBeTruthy();
      expect((call!.body as { content: string }).content).toContain("edited");
    });
  });

  it("Proofread renders notes and can load the revision", async () => {
    const fn = vi.fn((input: RequestInfo) => {
      const url = String(input);
      if (url.includes("/v1/workspace/tree")) {
        return Promise.resolve(new Response(JSON.stringify(treeFixture), { status: 200 }));
      }
      if (url.includes("/v1/workspace/read")) {
        return Promise.resolve(new Response(JSON.stringify(readFixture), { status: 200 }));
      }
      if (url.includes("/v1/manuscript/proofread")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              revised: "First revised\nSecond revised",
              notes: [{ kind: "grammar", issue: "capitalization", suggestion: "capitalize" }],
              model: "test-model",
            }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    });
    vi.stubGlobal("fetch", fn);
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => screen.getByTestId("workspace-entry-notes.md"));
    screen.getByTestId("workspace-entry-notes.md").click();
    await waitFor(() => screen.getByTestId("workspace-file-title"));
    screen.getByTestId("workspace-edit-btn").click();
    await waitFor(() => screen.getByTestId("workspace-editor"));
    screen.getByTestId("workspace-proofread-btn").click();
    const card = await waitFor(() => screen.getByTestId("workspace-proofread"));
    expect(card.textContent).toContain("grammar");
    expect(card.textContent).toContain("test-model");
    screen.getByTestId("workspace-apply-btn").click();
    await waitFor(() => {
      const editor = screen.getByTestId("workspace-editor") as HTMLTextAreaElement;
      expect(editor.value).toContain("First revised");
    });
  });

  it("Versions drawer lists and loads snapshots", async () => {
    const fn = vi.fn((input: RequestInfo, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/v1/workspace/tree")) {
        return Promise.resolve(new Response(JSON.stringify(treeFixture), { status: 200 }));
      }
      if (url.includes("/v1/workspace/read")) {
        return Promise.resolve(new Response(JSON.stringify(readFixture), { status: 200 }));
      }
      if (url.includes("/v1/manuscript/versions")) {
        return Promise.resolve(
          new Response(JSON.stringify({ versions: [{ ts: "2026-08-25T10:00:00Z", label: "manual" }] }), { status: 200 }),
        );
      }
      if (url.includes("/v1/manuscript/restore")) {
        return Promise.resolve(new Response(JSON.stringify({ content: "old content" }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    });
    vi.stubGlobal("fetch", fn);
    render(<WorkspaceView workspace={null} sessionId={null} />);
    await waitFor(() => screen.getByTestId("workspace-entry-notes.md"));
    screen.getByTestId("workspace-entry-notes.md").click();
    await waitFor(() => screen.getByTestId("workspace-file-title"));
    screen.getByTestId("workspace-edit-btn").click();
    await waitFor(() => screen.getByTestId("workspace-editor"));
    screen.getByTestId("workspace-versions-btn").click();
    const drawer = await waitFor(() => screen.getByTestId("workspace-versions"));
    expect(drawer.textContent).toContain("manual");
    screen.getByTestId("workspace-restore").click();
    await waitFor(() => {
      const editor = screen.getByTestId("workspace-editor") as HTMLTextAreaElement;
      expect(editor.value).toContain("old content");
    });
  });
});
