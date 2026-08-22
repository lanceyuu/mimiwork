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
    expect(screen.getByTestId("companion-bubble").textContent).toContain("Working on");
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
    expect(screen.getByTestId("companion-bubble").textContent).toContain("All done");
    expect(screen.queryByTestId("companion-zzz")).toBeNull();
  });

  it("scratches for attention when MimiWork needs the user", async () => {
    getActivity.mockResolvedValue({
      busy: true, running_sessions: 1, running_automations: 0, pending_input: 1,
    });
    render(<MimiCompanion />);
    await waitFor(() =>
      expect(screen.getByTestId("companion-sprite").dataset.phase).toBe("alert"),
    );
    expect(screen.getByTestId("companion-bubble").textContent).toContain("need your OK");
    expect(screen.queryByTestId("companion-zzz")).toBeNull(); // not napping — asking
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

  /** jsdom has no PointerEvent, so fireEvent.pointerDown drops init props (button/clientX);
   *  dispatch a hand-built bubbling event so React's synthetic handler sees real values. */
  function pointerDownAt(el: Element, x: number, y: number) {
    const ev = new Event("pointerdown", { bubbles: true });
    Object.assign(ev, { button: 0, clientX: x, clientY: y });
    fireEvent(el, ev);
  }

  it("pressing her starts an OS window drag; dropping far away does not restore the app", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    const startDragging = vi.fn();
    (globalThis as any).__TAURI__ = {
      core: { invoke },
      window: { getCurrentWindow: () => ({ startDragging }) },
    };
    render(<MimiCompanion />);
    const pet = screen.getByTestId("mimi-companion");
    pointerDownAt(pet, 10, 10);
    expect(startDragging).toHaveBeenCalledOnce();
    // Drop far from where the press started: a drag, not a click.
    fireEvent.click(pet, { clientX: 120, clientY: 90 });
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");
  });

  it("a click that barely moves after the press still restores the app", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    const startDragging = vi.fn();
    (globalThis as any).__TAURI__ = {
      core: { invoke },
      window: { getCurrentWindow: () => ({ startDragging }) },
    };
    render(<MimiCompanion />);
    const pet = screen.getByTestId("mimi-companion");
    pointerDownAt(pet, 10, 10);
    fireEvent.click(pet, { clientX: 12, clientY: 11 });
    expect(invoke).toHaveBeenCalledWith("companion_restore");
  });

  it("the \u2715 dismisses without restoring the app", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    (globalThis as any).__TAURI__ = { core: { invoke } };
    render(<MimiCompanion />);
    fireEvent.click(screen.getByTestId("companion-dismiss"));
    expect(invoke).toHaveBeenCalledWith("companion_dismiss");
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");
  });
});
