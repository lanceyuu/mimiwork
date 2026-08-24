/** TRANSFER PACK (GUI) — the gestures a Claude Code / Cowork / Codex user already knows:
 *  one "/" palette (app commands + saved commands + skills), "@" file mentions, and ⇧⇥ to
 *  cycle permission modes. Owner ask 2026-08-23: what you learn here must work there.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Composer } from "./Composer";

const SKILLS = {
  skills: [{ name: "weekly-report", description: "Monday status", scope: "global", enabled: true }],
};
const COMMANDS = {
  commands: [
    { name: "digest", description: "Weekly research digest", scope: "project", path: "/w/digest.md" },
  ],
};
const FILES = {
  files: [
    { path: "chapters/intro.docx", full_path: "/w/chapters/intro.docx", root: "/w", root_label: "w" },
  ],
};

function stubFetch(expanded = "Write the digest for Q3.") {
  const calls: { url: string; body?: any }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.includes("/v1/commands/expand"))
        return { ok: true, json: async () => ({ ok: true, text: expanded }) } as Response;
      if (url.includes("/v1/commands")) return { ok: true, json: async () => COMMANDS } as Response;
      if (url.includes("/v1/files/search")) return { ok: true, json: async () => FILES } as Response;
      if (url.includes("/skills")) return { ok: true, json: async () => SKILLS } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
  return calls;
}

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive",
  model: "gpt-5.6-sol",
  running: false,
  connected: true,
  sessionId: "s1",
  workspace: "/w",
  onSend: vi.fn(),
  onAppCommand: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

const box = () => screen.getByPlaceholderText(/Ask the coworker/);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the / palette", () => {
  it("offers app commands, saved commands and skills together", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    await waitFor(() => expect(screen.getByText("/digest")).toBeTruthy());
    expect(screen.getByText("/help")).toBeTruthy(); // built-in, same name as Claude Code
    expect(screen.getByText("/weekly-report")).toBeTruthy(); // a skill
    const kinds = screen
      .getAllByRole("option")
      .map((el) => (el as HTMLElement).dataset.kind);
    expect(new Set(kinds)).toEqual(new Set(["app", "command", "skill"]));
  });

  it("filters as you type, across all three kinds", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/di" } });
    await waitFor(() => expect(screen.getByText("/digest")).toBeTruthy());
    expect(screen.queryByText("/help")).toBeNull();
  });

  it("runs a built-in command on pick instead of sending it as a message", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/hel" } });
    await waitFor(() => expect(screen.getByText("/help")).toBeTruthy());
    fireEvent.click(screen.getByText("/help"));
    expect(p.onAppCommand).toHaveBeenCalledWith("help");
    expect(p.onSend).not.toHaveBeenCalled();
    expect((box() as HTMLTextAreaElement).value).toBe("");
  });

  it("typing a built-in command by hand works too", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/clear " } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(p.onAppCommand).toHaveBeenCalledWith("clear");
    expect(p.onSend).not.toHaveBeenCalled();
  });

  it("plan and permissions are handled by the composer itself", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/plan " } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(p.onModeChange).toHaveBeenCalledWith("plan");
    expect(p.onAppCommand).not.toHaveBeenCalledWith("plan");
  });

  it("a saved command is expanded server-side and sent as the message", async () => {
    const calls = stubFetch("Write the digest for Q3.");
    const p = props();
    render(<Composer {...p} />);
    // Open the palette so the saved commands load, then type arguments after the name.
    fireEvent.change(box(), { target: { value: "/dig" } });
    await waitFor(() => expect(screen.getByText("/digest")).toBeTruthy());
    fireEvent.change(box(), { target: { value: "/digest Q3" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(p.onSend).toHaveBeenCalledWith("Write the digest for Q3.", []));
    const expand = calls.find((c) => c.url.includes("/v1/commands/expand"));
    expect(expand?.body).toMatchObject({ name: "digest", arguments: "Q3", workspace: "/w" });
  });

  it("a skill still rides as its own field, not as message text", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/weekly" } });
    await waitFor(() => expect(screen.getByText("/weekly-report")).toBeTruthy());
    fireEvent.click(screen.getByText("/weekly-report"));
    fireEvent.change(box(), { target: { value: "/weekly-report for June" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(p.onSend).toHaveBeenCalledWith("for June", [], "weekly-report");
  });
});

describe("@ file mentions", () => {
  it("suggests files from the granted folders and inserts the path", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "please read @intro" } });
    await waitFor(() => expect(screen.getByText("chapters/intro.docx")).toBeTruthy());
    fireEvent.click(screen.getByText("chapters/intro.docx"));
    expect((box() as HTMLTextAreaElement).value).toBe("please read @chapters/intro.docx ");
  });

  it("Enter picks the highlighted file rather than sending the draft", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "@intro" } });
    await waitFor(() => expect(screen.getByText("chapters/intro.docx")).toBeTruthy());
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(p.onSend).not.toHaveBeenCalled();
    expect((box() as HTMLTextAreaElement).value).toBe("@chapters/intro.docx ");
  });

  it("an email address is not a file mention", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "mail bob@example" } });
    await new Promise((r) => setTimeout(r, 180));
    expect(screen.queryByTestId("mention-popup")).toBeNull();
  });
});

describe("permission modes", () => {
  it("⇧⇥ cycles the modes, like Claude Code", () => {
    stubFetch();
    const p = props({ mode: "interactive" });
    render(<Composer {...p} />);
    fireEvent.keyDown(box(), { key: "Tab", shiftKey: true });
    expect(p.onModeChange).toHaveBeenCalledWith("auto"); // …→ Ask → Full access → wraps
  });

  it("offers exactly three modes: Plan, Ask for approval, Full access", () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.click(screen.getByLabelText("Mode"));
    const menu = screen.getByTestId("mode-menu");
    expect(menu.textContent).toContain("Plan");
    expect(menu.textContent).toContain("Ask for approval");
    expect(menu.textContent).toContain("Full access");
    expect(menu.textContent).not.toContain("Discuss"); // kept simple (owner ask)
  });

  // ── dropping a file: a reference, not an upload ───────────────────────────────────
  function drop(el: Element, files: { name: string; type?: string }[]) {
    const list = files.map((f) => new File(["x"], f.name, { type: f.type ?? "" }));
    fireEvent.drop(el, { dataTransfer: { files: list, items: [], types: ["Files"] } });
  }

  it("a file dragged in from a folder Mimi can read becomes an @mention, not an upload", async () => {
    // The complaint (owner, 2026-08-24): dropping a .docx said "file type not supported"
    // about a document the coworker reads perfectly well from disk.
    const calls = stubFetch();
    render(<Composer {...props()} />);
    drop(screen.getByPlaceholderText(/Ask the coworker/).closest("div")!, [
      { name: "intro.docx" },
    ]);
    await waitFor(() =>
      expect((box() as HTMLTextAreaElement).value).toBe("@chapters/intro.docx "),
    );
    // It was located by name in the granted folders — nothing was uploaded or refused.
    expect(calls.some((c) => c.url.includes("/v1/files/search"))).toBe(true);
    expect(screen.queryByTestId("attach-notice")).toBeNull();
    expect(screen.queryByText(/not supported/)).toBeNull();
  });

  it("keeps whatever is already typed and appends the mention at the caret", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "summarise" } });
    drop(box().closest("div")!, [{ name: "intro.docx" }]);
    await waitFor(() =>
      expect((box() as HTMLTextAreaElement).value).toBe("summarise @chapters/intro.docx "),
    );
  });

  it("still attaches a file that is not in any granted folder", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/v1/files/search"))
          return { ok: true, json: async () => ({ files: [] }) } as Response;
        if (url.includes("/skills")) return { ok: true, json: async () => SKILLS } as Response;
        return { ok: true, json: async () => ({}) } as Response;
      }),
    );
    render(<Composer {...props()} />);
    drop(box().closest("div")!, [{ name: "photo.png", type: "image/png" }]);
    // Nothing is mentioned — there is no path to point at — so the upload path runs.
    await waitFor(() => expect((box() as HTMLTextAreaElement).value).toBe(""));
  });
});
