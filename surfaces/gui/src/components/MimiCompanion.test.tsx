/** The floating companion: busy → sleeping, done → wake, click → restore. */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let activityHandler: ((msg: { type: string; data?: Record<string, unknown> }) => void) | null =
  null;
const getActivity = vi.fn();

vi.mock("../api", () => ({
  getActivity: (...args: unknown[]) => getActivity(...args),
  connectEvents: (h: (msg: { type: string; data?: Record<string, unknown> }) => void) => {
    activityHandler = h;
    return () => {
      activityHandler = null;
    };
  },
}));

import { MimiCompanion } from "./MimiCompanion";

describe("MimiCompanion", () => {
  beforeEach(() => {
    activityHandler = null;
    getActivity.mockReset();
  });
  afterEach(() => {
    cleanup();
    delete (globalThis as any).__TAURI__;
  });

  it("sleeps while the coworker is busy, with the zzz bubble", async () => {
    getActivity.mockResolvedValue({ busy: true, running_sessions: 1, running_automations: 0 });
    render(<MimiCompanion />);
    await waitFor(() =>
      expect(screen.getByTestId("companion-sprite").dataset.phase).toBe("sleep"),
    );
    expect(screen.getByTestId("companion-zzz")).toBeTruthy();
    expect(screen.getByTestId("companion-label").textContent).toContain("napping");
  });

  it("wakes up when the work finishes", async () => {
    getActivity.mockResolvedValue({ busy: true, running_sessions: 1, running_automations: 0 });
    render(<MimiCompanion />);
    await waitFor(() =>
      expect(screen.getByTestId("companion-sprite").dataset.phase).toBe("sleep"),
    );
    act(() => {
      activityHandler?.({ type: "activity", data: { busy: false } });
    });
    expect(screen.getByTestId("companion-sprite").dataset.phase).toBe("wake");
    expect(screen.getByTestId("companion-label").textContent).toBe("All done!");
    expect(screen.queryByTestId("companion-zzz")).toBeNull();
  });

  it("idles when nothing was ever running", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    render(<MimiCompanion />);
    await waitFor(() =>
      expect(screen.getByTestId("companion-sprite").dataset.phase).toBe("idle"),
    );
    expect(screen.queryByTestId("companion-zzz")).toBeNull();
  });

  it("clicking Mimi restores the main window via the shell", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    (globalThis as any).__TAURI__ = { core: { invoke } };
    render(<MimiCompanion />);
    fireEvent.click(screen.getByTestId("mimi-companion"));
    expect(invoke).toHaveBeenCalledWith("companion_restore");
  });
});
