/** TRANSFER PACK (GUI) — the gestures a Claude Code / Cowork / Codex user already knows:
 *  one progressive "/" palette (app commands + saved commands + skills), "@" file mentions, and ⇧⇥ to
 *  cycle permission modes. Owner ask 2026-08-23: what you learn here must work there.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const box = () => screen.getByPlaceholderText(/Ask Mimi/);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the / palette", () => {
  it("starts with all three kinds, app commands first", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    expect(screen.getByText("/help")).toBeTruthy(); // built-in, same name as Claude Code
    await waitFor(() => expect(screen.getByText("/digest")).toBeTruthy());
    await waitFor(() => expect(screen.getByText("/weekly-report")).toBeTruthy());
    const kinds = screen
      .getAllByRole("option")
      .map((el) => (el as HTMLElement).dataset.kind);
    expect(kinds[0]).toBe("app");
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
    expect(p.onModeChange).toHaveBeenCalledWith("accept_edits"); // Default → Accept edits → Plan → wraps
    const q = props({ mode: "plan" });
    cleanup();
    stubFetch();
    render(<Composer {...q} />);
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Mimi/), { key: "Tab", shiftKey: true });
    expect(q.onModeChange).toHaveBeenCalledWith("interactive"); // Bypass is never a keystroke away
  });

  it("offers Claude Code's four modes, in its order", () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.click(screen.getByLabelText("Mode"));
    const menu = screen.getByTestId("mode-menu");
    const text = menu.textContent!;
    for (const label of ["Default", "Accept edits", "Plan", "Bypass permissions"]) expect(text).toContain(label);
    expect(text.indexOf("Default")).toBeLessThan(text.indexOf("Accept edits"));
    expect(text.indexOf("Accept edits")).toBeLessThan(text.indexOf("Plan"));
    expect(menu.textContent!.indexOf("Plan")).toBeLessThan(menu.textContent!.indexOf("Bypass permissions"));
    expect(menu.textContent).not.toContain("Discuss"); // kept simple (owner ask)
  });

  it("y / a / n answer a pending approval while the box is empty, and never while typing", () => {
    stubFetch();
    const onQuickApprove = vi.fn();
    const p = props({ onQuickApprove });
    render(<Composer {...p} />);
    fireEvent.keyDown(box(), { key: "y" });
    fireEvent.keyDown(box(), { key: "a" });
    fireEvent.keyDown(box(), { key: "n" });
    expect(onQuickApprove.mock.calls.map((c) => c[0])).toEqual(["yes", "always", "no"]);
    fireEvent.change(box(), { target: { value: "not yet" } });
    fireEvent.keyDown(box(), { key: "y" });
    expect(onQuickApprove).toHaveBeenCalledTimes(3);
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
    drop(screen.getByPlaceholderText(/Ask Mimi/).closest("div")!, [
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

describe("steering a running turn", () => {
  // Adopted from FrontierAgent's asynchronous intervention (owner ask 2026-08-28):
  // typing while Mimi works must reach it, not bounce off a locked composer.
  const runningBox = () => screen.getByPlaceholderText(/steer it mid-run/);

  it("a plain typed message sends while Mimi is running", () => {
    stubFetch();
    const p = props({ running: true });
    render(<Composer {...p} />);
    fireEvent.change(runningBox(), { target: { value: "focus on chapter two only" } });
    fireEvent.keyDown(runningBox(), { key: "Enter" });
    expect(p.onSend).toHaveBeenCalledWith("focus on chapter two only", [], undefined);
    expect((runningBox() as HTMLTextAreaElement).value).toBe("");
  });

  it("the placeholder says the message will steer, and Stop stays available", () => {
    stubFetch();
    render(<Composer {...props({ running: true })} />);
    expect(runningBox()).toBeTruthy();
    expect(screen.getByText(/Stop/)).toBeTruthy();
  });

  it("Steer submits the new direction without hiding Stop task", () => {
    stubFetch();
    const p = props({ running: true });
    render(<Composer {...p} />);
    fireEvent.change(runningBox(), { target: { value: "use the new numbers" } });
    expect(screen.getByRole("button", { name: "Stop task" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Steer" }));
    expect(p.onSend).toHaveBeenCalledWith("use the new numbers", [], undefined);
    expect(p.onInterrupt).not.toHaveBeenCalled();
  });

  it("Escape stops a task and, after a moment, a second Escape can force it to stop", () => {
    stubFetch();
    vi.useFakeTimers();
    try {
      const p = props({ running: true, onForceStop: vi.fn() });
      const { rerender } = render(<Composer {...p} />);
      fireEvent.keyDown(runningBox(), { key: "Escape" });
      expect(p.onInterrupt).toHaveBeenCalledOnce();
      rerender(<Composer {...p} stopping connected={false} />);
      // A double-Esc (or double-click) is not a force stop.
      fireEvent.keyDown(runningBox(), { key: "Escape" });
      expect(p.onForceStop).not.toHaveBeenCalled();
      expect((screen.getByRole("button", { name: "Stopping…" }) as HTMLButtonElement).disabled).toBe(true);
      act(() => { vi.advanceTimersByTime(1500); });
      fireEvent.keyDown(runningBox(), { key: "Escape" });
      expect(p.onForceStop).toHaveBeenCalledOnce();
      expect((screen.getByRole("button", { name: "Force stop" }) as HTMLButtonElement).disabled).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("a disconnected or stopping composer keeps the user's draft", () => {
    stubFetch();
    const p = props({ running: true });
    const { rerender } = render(<Composer {...p} connected={false} />);
    fireEvent.change(runningBox(), { target: { value: "do this next" } });
    fireEvent.keyDown(runningBox(), { key: "Enter" });
    expect(p.onSend).not.toHaveBeenCalled();
    rerender(<Composer {...p} stopping />);
    fireEvent.keyDown(runningBox(), { key: "Enter" });
    expect(p.onSend).not.toHaveBeenCalled();
    expect((runningBox() as HTMLTextAreaElement).value).toBe("do this next");
  });

  it("a picked /skill still waits for the turn to end", async () => {
    stubFetch();
    const p = props({ running: true });
    render(<Composer {...p} />);
    fireEvent.change(runningBox(), { target: { value: "/we" } });
    await waitFor(() => expect(screen.getByText("/weekly-report")).toBeTruthy());
    fireEvent.click(screen.getByText("/weekly-report"));
    fireEvent.keyDown(runningBox(), { key: "Enter" });
    // Steering is for plain text only: a skill run needs a fresh turn's framing.
    expect(p.onSend).not.toHaveBeenCalled();
  });
});
