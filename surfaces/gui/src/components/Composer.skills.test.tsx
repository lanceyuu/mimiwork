// SKILLS-SPEC §4.6 GUI — the composer's "/" force-run popup: opens only for a leading
// slash, lists only the session's effective (enabled) menu, filters while typing, and the
// picked skill rides onSend as its own field — never as message text.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Composer } from "./Composer";

const MENU = {
  skills: [
    { name: "weekly-report", description: "Monday status report", scope: "global", enabled: true },
    { name: "greet", description: "says hello", scope: "project", enabled: true },
    {
      name: "qualitati-projects",
      description: "List research projects",
      scope: "global",
      enabled: true,
    },
    { name: "muted-one", description: "muted here", scope: "global", enabled: false },
  ],
};

function stubFetch() {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: (init?.method || "GET").toUpperCase() });
      if (url.includes("/skills")) return { ok: true, json: async () => MENU } as Response;
      if (url.includes("/v1/commands"))
        return {
          ok: true,
          json: async () => ({
            commands: [
              {
                name: "qualitati-export",
                description: "Internal export command",
                scope: "global",
                path: "/commands/qualitati-export.md",
              },
            ],
          }),
        } as Response;
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
  onSend: vi.fn(),
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

describe("Composer / skills popup", () => {
  it("keeps a bare '/' to app commands and does not fetch broader menus", async () => {
    const calls = stubFetch();
    render(<Composer {...props({ onAppCommand: vi.fn() })} />);
    fireEvent.change(box(), { target: { value: "/" } });
    expect(await screen.findByRole("listbox", { name: "Commands and skills" })).toBeTruthy();
    expect(screen.getByText("/help")).toBeTruthy();
    expect(screen.queryByText("/weekly-report")).toBeNull();
    expect(calls.some((c) => c.url.includes("/skills"))).toBe(false);
    expect(calls.some((c) => c.url.includes("/v1/commands"))).toBe(false);
  });

  it("waits for two typed characters before fetching skills", async () => {
    const calls = stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/g" } });
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/v1/commands"))).toBe(true),
    );
    expect(calls.some((c) => c.url.includes("/skills"))).toBe(false);
    expect(screen.queryByText("/greet")).toBeNull();

    fireEvent.change(box(), { target: { value: "/gr" } });
    expect(await screen.findByText("/greet")).toBeTruthy();
    expect(calls.some((c) => c.url.includes("/skills"))).toBe(true);
  });

  it("searches skill names and descriptions but never exposes QualiTaTi tools", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/monday" } });
    expect(await screen.findByText("/weekly-report")).toBeTruthy();
    expect(screen.queryByText("/muted-one")).toBeNull();

    fireEvent.change(box(), { target: { value: "/qualitati" } });
    await screen.findByText(/No commands or skills match/);
    expect(screen.queryByText("/qualitati-projects")).toBeNull();
    expect(screen.queryByText("/qualitati-export")).toBeNull();
  });

  it("resets keyboard selection when the query changes", async () => {
    stubFetch();
    const onAppCommand = vi.fn();
    render(<Composer {...props({ onAppCommand })} />);
    fireEvent.change(box(), { target: { value: "/" } });
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    fireEvent.keyDown(box(), { key: "ArrowDown" });

    fireEvent.change(box(), { target: { value: "/mo" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(onAppCommand).toHaveBeenCalledWith("model");
  });

  it("does NOT open for a mid-text slash", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "rate 5/10 please" } });
    expect(screen.queryByTestId("skill-popup")).toBeNull();
  });

  it("selecting inserts /name inline; the send strips the prefix and carries the skill field", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/gr" } });
    fireEvent.click(await screen.findByRole("option", { name: /greet/ }));
    expect((box() as HTMLTextAreaElement).value).toBe("/greet "); // inline, no chip
    fireEvent.change(box(), { target: { value: "/greet say hi to the team" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(p.onSend).toHaveBeenCalled());
    expect(p.onSend).toHaveBeenCalledWith("say hi to the team", [], "greet");
  });

  it("a skill-only send works and Enter inside the popup never sends the query text", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/wee" } });
    await screen.findByText("/weekly-report");
    fireEvent.keyDown(box(), { key: "Enter" }); // selects, does not send
    expect(p.onSend).not.toHaveBeenCalled();
    expect((box() as HTMLTextAreaElement).value).toBe("/weekly-report ");
    fireEvent.keyDown(box(), { key: "Enter" }); // now sends, skill-only
    await waitFor(() => expect(p.onSend).toHaveBeenCalledWith("", [], "weekly-report"));
  });

  it("editing the /name prefix away un-picks the skill", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/gr" } });
    fireEvent.click(await screen.findByRole("option", { name: /greet/ }));
    fireEvent.change(box(), { target: { value: "hello plain" } }); // prefix gone
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(p.onSend).toHaveBeenCalledWith("hello plain", [], undefined));
  });

  it("Escape closes the popup and no popup ever opens without a sessionId", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/gr" } });
    await screen.findByTestId("skill-popup");
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(screen.queryByTestId("skill-popup")).toBeNull();
    cleanup();
    stubFetch();
    render(<Composer {...props({ sessionId: undefined })} />);
    fireEvent.change(box(), { target: { value: "/" } });
    expect(screen.queryByTestId("skill-popup")).toBeNull();
  });
});

describe("Composer — the doorway prefill (SKILLS-SPEC §5.2)", () => {
  it("a prefill arriving together with a session switch survives the draft clear", async () => {
    stubFetch();
    const { rerender } = render(<Composer {...props({ resetKey: "s1" })} />);
    // The doorway does both in one render: new session (resetKey) + prefill. The clear
    // effect must run BEFORE the prefill effect or the prefill is wiped (regression).
    rerender(
      <Composer
        {...props({
          resetKey: "s2",
          prefill: { text: "Build a new skill for me: release procedure", nonce: 1 },
        })}
      />,
    );
    await waitFor(() => {
      expect((box() as HTMLTextAreaElement).value).toBe(
        "Build a new skill for me: release procedure",
      );
    });
  });

  it("reports the prefill as consumed, so the host can stop handing it back", async () => {
    // Regression (owner report 2026-08-23): the starter-card sentence reappeared in every
    // new conversation, because the host kept the prefill in state and each remount of the
    // composer applied it again. The composer now says when it has landed.
    stubFetch();
    const onPrefillConsumed = vi.fn();
    const prefill = { text: "Analyze the files in this folder.", nonce: 7 };
    const { unmount } = render(
      <Composer {...props({ prefill, onPrefillConsumed })} />,
    );
    await waitFor(() => expect(onPrefillConsumed).toHaveBeenCalledTimes(1));
    expect((box() as HTMLTextAreaElement).value).toBe("Analyze the files in this folder.");
    unmount();

    // What the host does with that: drops it. A fresh composer then starts empty.
    render(<Composer {...props({ prefill: undefined })} />);
    expect((box() as HTMLTextAreaElement).value).toBe("");
  });
});
