/** Project page — a project groups conversations (2026-08-31). Identity edits,
 *  instructions round-trip, its conversations, and a delete that says what it takes. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProjectView } from "./ProjectView";

type Call = { url: string; method: string; body?: any };
function stubFetch(detail: any) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method || "GET").toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ url, method, body });
    if (url.includes("/v1/projects/detail")) return { ok: true, json: async () => detail } as Response;
    if (url.includes("/v1/projects/instructions"))
      return { ok: true, json: async () => ({ ok: true }) } as Response;
    if (url.includes("/v1/memory")) return { ok: true, json: async () => ({ id: 9 }) } as Response;
    if (url.includes("/v1/projects") && method === "DELETE")
      return { ok: true, json: async () => ({ ok: true, deleted_sessions: 0, ungrouped: 1 }) } as Response;
    if (url.includes("/v1/projects") && method === "PATCH")
      return { ok: true, json: async () => ({ ok: true, project: { ...detail.project, ...body } }) } as Response;
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
    id: "grp_1", name: "Thesis", emoji: "🎓", pinned: false, archived: false,
    sessions: 1, last_activity: "", has_instructions: true,
  },
  instructions: "Cite in APA 7.",
  memory: [
    { id: 7, scope: "project", content: "Participants are coded P01–P24", summary: "", created_at: "" },
  ],
  sessions: [
    { session_id: "s1", title: "Lit review", workspace: "/p/thesis", agent: "cowork", updated_at: "" },
  ],
};

describe("ProjectView — a group, not a folder", () => {
  it("shows the group's identity and its conversations, and never a folder path", async () => {
    stubFetch(DETAIL);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} />);

    expect(await screen.findByDisplayValue("Thesis")).toBeTruthy();
    expect(screen.getByTestId("project-emoji").textContent).toBe("🎓");
    expect(screen.getByTestId("project-session").textContent).toContain("Lit review");
    // The page must not offer a path anywhere — a group does not have one.
    expect(document.body.textContent).not.toContain("/p/thesis");
  });

  it("saves instructions to the group, not to a file", async () => {
    const calls = stubFetch(DETAIL);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} onChanged={vi.fn()} />);

    const box = (await screen.findByTestId("project-instructions")) as HTMLTextAreaElement;
    expect(box.value).toBe("Cite in APA 7.");
    fireEvent.change(box, { target: { value: "Cite in APA 7. Use British English." } });
    fireEvent.click(screen.getByTestId("project-instructions-save"));

    await waitFor(() => {
      const put = calls.find((c) => c.url.includes("/v1/projects/instructions") && c.method === "PUT");
      expect(put?.body).toEqual({ id: "grp_1", text: "Cite in APA 7. Use British English." });
    });
  });

  it("renames on blur", async () => {
    const calls = stubFetch(DETAIL);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} onChanged={vi.fn()} />);

    const input = (await screen.findByTestId("project-name")) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Thesis chapter 3" } });
    fireEvent.blur(input);

    await waitFor(() => {
      const patch = calls.find((c) => c.method === "PATCH");
      expect(patch?.body).toEqual({ id: "grp_1", name: "Thesis chapter 3" });
    });
  });

  it("deleting says the conversations come BACK, and takes them only when asked", async () => {
    const calls = stubFetch(DETAIL);
    const onDeleted = vi.fn();
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} onDeleted={onDeleted} />);

    fireEvent.click(await screen.findByTestId("project-delete"));
    const dialog = screen.getByTestId("confirm-dialog");
    // The default must reassure: nothing is destroyed.
    expect(dialog.textContent).toContain("returns");
    expect(dialog.textContent).toContain("nothing is deleted");

    fireEvent.click(screen.getByTestId("confirm-accept"));
    await waitFor(() => {
      const del = calls.find((c) => c.method === "DELETE");
      expect(del?.url).toContain("delete_sessions=false");
    });
    expect(onDeleted).toHaveBeenCalled();
  });

  it("ticking the box changes both the wording and what is sent", async () => {
    const calls = stubFetch(DETAIL);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} onDeleted={vi.fn()} />);

    fireEvent.click(await screen.findByTestId("project-delete"));
    fireEvent.click(screen.getByTestId("project-delete-sessions"));
    expect(screen.getByTestId("confirm-dialog").textContent).toContain("deleted too");

    fireEvent.click(screen.getByTestId("confirm-accept"));
    await waitFor(() => {
      const del = calls.find((c) => c.method === "DELETE");
      expect(del?.url).toContain("delete_sessions=true");
    });
  });

  it("cancelling deletes nothing", async () => {
    const calls = stubFetch(DETAIL);
    const onDeleted = vi.fn();
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} onDeleted={onDeleted} />);

    fireEvent.click(await screen.findByTestId("project-delete"));
    fireEvent.click(screen.getByTestId("confirm-cancel"));

    expect(screen.queryByTestId("confirm-dialog")).toBeNull();
    expect(calls.find((c) => c.method === "DELETE")).toBeUndefined();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("an empty group says so instead of offering a checkbox", async () => {
    stubFetch({ ...DETAIL, project: { ...DETAIL.project, sessions: 0 }, sessions: [] });
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} />);

    fireEvent.click(await screen.findByTestId("project-delete"));
    expect(screen.getByTestId("confirm-dialog").textContent).toContain("empty");
    expect(screen.queryByTestId("project-delete-sessions")).toBeNull();
  });
});

describe("ProjectView — what Mimi knows, scoped to the group", () => {
  it("lists the group's memory and adds a new fact against the group", async () => {
    const calls = stubFetch(DETAIL);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} />);

    expect((await screen.findByTestId("project-memory-row")).textContent).toContain(
      "Participants are coded P01–P24",
    );

    fireEvent.change(screen.getByTestId("project-memory-new"), {
      target: { value: "Interviews run 45 minutes" },
    });
    fireEvent.click(screen.getByTestId("project-memory-add"));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/v1/memory") && c.method === "POST");
      // The group, never a folder — the page has no folder to scope against.
      expect(post?.body).toEqual({
        content: "Interviews run 45 minutes",
        scope: "project",
        project_id: "grp_1",
      });
    });
  });

  it("forgetting a fact asks the server to delete it", async () => {
    const calls = stubFetch(DETAIL);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} />);
    fireEvent.click(await screen.findByTestId("project-memory-forget"));

    await waitFor(() => {
      expect(calls.find((c) => c.url.includes("/v1/memory/7") && c.method === "DELETE")).toBeTruthy();
    });
  });
});

describe("ProjectView — a partial payload must not take the page down", () => {
  it("renders without a memory list at all", async () => {
    // An older sidecar, or an error body missing a field. Reading `.length` off it
    // crashed the whole page over a section that is not even the point of it — the same
    // shape of bug that once white-screened the General tab.
    const { memory: _omitted, ...noMemory } = DETAIL;
    stubFetch(noMemory);
    render(<ProjectView projectId="grp_1" onSelectSession={vi.fn()} />);

    expect(await screen.findByDisplayValue("Thesis")).toBeTruthy();
    expect(screen.queryByTestId("project-memory-row")).toBeNull();
    // And you can still teach it something.
    expect(screen.getByTestId("project-memory-new")).toBeTruthy();
  });
});
