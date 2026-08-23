/** Project page: identity edits, instructions round-trip, project memory, sessions. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProjectView } from "./ProjectView";

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn() }));
vi.mock("../tauri", () => ({ openExternal }));

type Call = { url: string; method: string; body?: any };
function stubFetch(detail: any) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method || "GET").toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ url, method, body });
    if (url.includes("/v1/projects/detail")) return { ok: true, json: async () => detail } as Response;
    if (url.includes("/v1/projects/instructions")) return { ok: true, json: async () => ({ ok: true }) } as Response;
    if (url.includes("/v1/projects") && method === "DELETE")
      return { ok: true, json: async () => ({ ok: true, deleted_sessions: 1 }) } as Response;
    if (url.includes("/v1/projects") && method === "PATCH")
      return { ok: true, json: async () => ({ ok: true, project: { ...detail.project, ...body } }) } as Response;
    if (url.includes("/v1/memory") && method === "POST") return { ok: true, json: async () => ({ id: 9 }) } as Response;
    return { ok: true, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const DETAIL = {
  ok: true,
  project: {
    path: "/p/thesis", name: "Thesis", emoji: "🎓", pinned: false, archived: false,
    exists: true, sessions: 1, last_activity: "", has_instructions: true,
  },
  instructions: "Cite in APA 7.",
  instructions_file: "/p/thesis/AGENTS.md",
  memory: [{ id: 1, scope: "workspace", workspace: "/p/thesis", content: "Uses Stata 18", summary: "", created_at: "" }],
  sessions: [{ session_id: "s1", title: "Lit review", workspace: "/p/thesis", agent: "cowork", updated_at: "" }],
};

describe("ProjectView", () => {
  it("renders identity, instructions, memory and sessions from the detail endpoint", async () => {
    stubFetch(DETAIL);
    const onSelectSession = vi.fn();
    const onNewSession = vi.fn();
    render(<ProjectView path="/p/thesis" onNewSession={onNewSession} onSelectSession={onSelectSession} />);
    expect(((await screen.findByTestId("project-name")) as HTMLInputElement).value).toBe("Thesis");
    expect((screen.getByTestId("project-instructions-text") as HTMLTextAreaElement).value).toBe("Cite in APA 7.");
    expect(screen.getByTestId("project-memory").textContent).toContain("Uses Stata 18");
    fireEvent.click(screen.getByTestId("project-session-row"));
    expect(onSelectSession).toHaveBeenCalledWith("s1", "/p/thesis", "cowork");
    fireEvent.click(screen.getByTestId("project-new-session"));
    expect(onNewSession).toHaveBeenCalledWith("/p/thesis");
  });

  it("saves edited instructions to the folder's AGENTS.md and renames via PATCH", async () => {
    const calls = stubFetch(DETAIL);
    const onChanged = vi.fn();
    render(<ProjectView path="/p/thesis" onNewSession={vi.fn()} onSelectSession={vi.fn()} onChanged={onChanged} />);
    const ta = (await screen.findByTestId("project-instructions-text")) as HTMLTextAreaElement;
    expect((screen.getByTestId("project-instructions-save") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(ta, { target: { value: "Cite in APA 7.\nNever touch data/raw." } });
    expect((screen.getByTestId("project-instructions-save") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByTestId("project-instructions-save"));
    await waitFor(() =>
      expect(calls.find((c) => c.url.includes("/v1/projects/instructions"))?.body).toEqual({
        path: "/p/thesis",
        text: "Cite in APA 7.\nNever touch data/raw.",
      }),
    );
    const name = screen.getByTestId("project-name") as HTMLInputElement;
    fireEvent.change(name, { target: { value: "PhD thesis" } });
    fireEvent.blur(name);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ path: "/p/thesis", name: "PhD thesis" }),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  it("adds a project-scoped memory fact", async () => {
    const calls = stubFetch(DETAIL);
    render(<ProjectView path="/p/thesis" onNewSession={vi.fn()} onSelectSession={vi.fn()} />);
    const input = await screen.findByTestId("project-memory-add");
    fireEvent.change(input, { target: { value: "Advisor prefers British spelling" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() =>
      expect(calls.find((c) => c.url.includes("/v1/memory") && c.method === "POST")?.body).toEqual({
        content: "Advisor prefers British spelling",
        scope: "workspace",
        workspace: "/p/thesis",
      }),
    );
  });

  it("deleting asks first, says the folder is safe, and reports the page is done", async () => {
    const calls = stubFetch(DETAIL);
    const onDeleted = vi.fn();
    const onChanged = vi.fn();
    render(
      <ProjectView
        path="/p/thesis"
        onNewSession={() => {}}
        onSelectSession={() => {}}
        onChanged={onChanged}
        onDeleted={onDeleted}
      />,
    );
    await screen.findByTestId("project-instructions");
    // Nothing happens on the first click — it only arms the confirm panel.
    fireEvent.click(screen.getByTestId("project-delete"));
    const panel = screen.getByTestId("project-delete-confirm");
    expect(panel.textContent).toContain("stay exactly where they are");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    fireEvent.click(screen.getByTestId("project-delete-confirm-btn"));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("/p/thesis"));
    const del = calls.find((c) => c.method === "DELETE")!;
    expect(del.url).toContain("delete_sessions=true");
    expect(decodeURIComponent(del.url)).toContain("/p/thesis");
    expect(onChanged).toHaveBeenCalled(); // the sidebar band re-reads
  });

  it("keeps the conversations when the box is unticked", async () => {
    const calls = stubFetch(DETAIL);
    render(
      <ProjectView path="/p/thesis" onNewSession={() => {}} onSelectSession={() => {}} />,
    );
    await screen.findByTestId("project-instructions");
    fireEvent.click(screen.getByTestId("project-delete"));
    fireEvent.click(screen.getByTestId("project-delete-sessions")); // untick
    fireEvent.click(screen.getByTestId("project-delete-confirm-btn"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(calls.find((c) => c.method === "DELETE")!.url).toContain("delete_sessions=false");
  });

  it("keeps the page open and shows why when the server refuses", async () => {
    stubFetch(DETAIL);
    const fn = vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method || "GET").toUpperCase();
      if (url.includes("/v1/projects/detail"))
        return { ok: true, json: async () => DETAIL } as Response;
      if (method === "DELETE")
        return {
          ok: true,
          json: async () => ({ ok: false, error: "a conversation in this project is still running" }),
        } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fn);
    const onDeleted = vi.fn();
    render(
      <ProjectView
        path="/p/thesis"
        onNewSession={() => {}}
        onSelectSession={() => {}}
        onDeleted={onDeleted}
      />,
    );
    await screen.findByTestId("project-instructions");
    fireEvent.click(screen.getByTestId("project-delete"));
    fireEvent.click(screen.getByTestId("project-delete-confirm-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("project-delete-confirm").textContent).toContain("still running"),
    );
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
