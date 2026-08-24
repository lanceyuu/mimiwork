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
    fireEvent.click(screen.getByTestId("companion-pet-zone"));
    expect(invoke).toHaveBeenCalledWith("companion_restore");
  });

  /** jsdom has no PointerEvent, so fireEvent.pointerDown drops init props (button/clientX);
   *  dispatch a hand-built bubbling event so React's synthetic handler sees real values. */
  function pointerDownAt(el: Element, x: number, y: number, screen?: { x: number; y: number }) {
    const ev = new Event("pointerdown", { bubbles: true });
    Object.assign(ev, {
      button: 0,
      clientX: x,
      clientY: y,
      screenX: screen?.x ?? x,
      screenY: screen?.y ?? y,
    });
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
    const pet = screen.getByTestId("companion-pet-zone");
    pointerDownAt(pet, 10, 10);
    expect(startDragging).toHaveBeenCalledOnce();
    // Drop far from where the press started: a drag, not a click.
    fireEvent.click(pet, { clientX: 120, clientY: 90, screenX: 120, screenY: 90 });
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");
  });

  it("dropping an OS window drag does not open the app, even though the pointer never moved inside the window", async () => {
    // The window travels WITH the cursor during startDragging(), so the drop
    // lands on the same client coordinates as the press — only the SCREEN
    // position moved. Measuring client-only used to open the app on every drop.
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    (globalThis as any).__TAURI__ = {
      core: { invoke },
      window: { getCurrentWindow: () => ({ startDragging: vi.fn() }) },
    };
    render(<MimiCompanion />);
    const pet = screen.getByTestId("companion-pet-zone");
    pointerDownAt(pet, 55, 60, { x: 400, y: 300 });
    fireEvent.click(pet, { clientX: 55, clientY: 60, screenX: 760, screenY: 520 });
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");
  });

  it("tells the shell a drag has begun, so where she lands is remembered", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    const startDragging = vi.fn();
    (globalThis as any).__TAURI__ = {
      core: { invoke },
      window: { getCurrentWindow: () => ({ startDragging }) },
    };
    render(<MimiCompanion />);
    pointerDownAt(screen.getByTestId("companion-pet-zone"), 10, 10);
    expect(invoke).toHaveBeenCalledWith("companion_drag_begin");
    expect(startDragging).toHaveBeenCalledOnce();
  });

  it("a window-moved event from the shell also marks the gesture a drag", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    let onMovedCb: (() => void) | null = null;
    const unlisten = vi.fn();
    (globalThis as any).__TAURI__ = {
      core: { invoke },
      window: {
        getCurrentWindow: () => ({
          startDragging: vi.fn(),
          onMoved: (cb: () => void) => {
            onMovedCb = cb;
            return Promise.resolve(unlisten);
          },
        }),
      },
    };
    render(<MimiCompanion />);
    await waitFor(() => expect(onMovedCb).toBeTruthy());
    const pet = screen.getByTestId("companion-pet-zone");
    pointerDownAt(pet, 55, 60, { x: 400, y: 300 });
    act(() => onMovedCb?.()); // the shell moved the window under the cursor
    fireEvent.click(pet, { clientX: 55, clientY: 60, screenX: 400, screenY: 300 });
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");

    // …and the next real click, with no move in between, still opens the app.
    pointerDownAt(pet, 55, 60, { x: 400, y: 300 });
    fireEvent.click(pet, { clientX: 55, clientY: 60, screenX: 400, screenY: 300 });
    expect(invoke).toHaveBeenCalledWith("companion_restore");
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
    const pet = screen.getByTestId("companion-pet-zone");
    pointerDownAt(pet, 10, 10);
    fireEvent.click(pet, { clientX: 12, clientY: 11, screenX: 12, screenY: 11 });
    expect(invoke).toHaveBeenCalledWith("companion_restore");
  });

  it("hides the \u2715 until the mouse is on Mimi", async () => {
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    render(<MimiCompanion />);
    const x = screen.getByTestId("companion-dismiss");
    expect(x.dataset.visible).toBe("false");
    fireEvent.pointerEnter(screen.getByTestId("companion-pet-zone"));
    expect(x.dataset.visible).toBe("true");
    fireEvent.pointerLeave(screen.getByTestId("companion-pet-zone"));
    expect(x.dataset.visible).toBe("false");
    // Keyboard users still reach it: focus reveals it too.
    fireEvent.focus(x);
    expect(x.dataset.visible).toBe("true");
  });

  it("clicking what Mimi said dismisses that message without opening the app", async () => {
    getActivity.mockResolvedValue({ busy: true, running_sessions: 1, running_automations: 0 });
    const invoke = vi.fn();
    (globalThis as any).__TAURI__ = { core: { invoke } };
    render(<MimiCompanion />);
    await waitFor(() => expect(screen.getByTestId("companion-bubble")).toBeTruthy());
    fireEvent.click(screen.getByTestId("companion-bubble"));
    expect(screen.queryByTestId("companion-bubble")).toBeNull();
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");
    // The pet is still there, and the next thing she says shows up again.
    expect(screen.getByTestId("companion-sprite")).toBeTruthy();
    act(() => {
      activityHandler?.({ type: "activity", data: { busy: false } });
    });
    expect(screen.getByTestId("companion-bubble").textContent).toContain("All done");
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

  it("ignores the empty air around her", async () => {
    // The window is a transparent box; only the dog is a control (owner ask 2026-08-24).
    getActivity.mockResolvedValue({ busy: false, running_sessions: 0, running_automations: 0 });
    const invoke = vi.fn();
    const startDragging = vi.fn();
    (globalThis as any).__TAURI__ = {
      core: { invoke },
      window: { getCurrentWindow: () => ({ startDragging }) },
    };
    render(<MimiCompanion />);
    const window_ = await screen.findByTestId("mimi-companion");
    pointerDownAt(window_, 10, 10);
    fireEvent.click(window_, { clientX: 10, clientY: 10, screenX: 10, screenY: 10 });
    expect(startDragging).not.toHaveBeenCalled();
    expect(invoke).not.toHaveBeenCalledWith("companion_restore");

    // …while the dog herself still opens the app.
    fireEvent.click(screen.getByTestId("companion-pet-zone"));
    expect(invoke).toHaveBeenCalledWith("companion_restore");
  });

  it("tells the shell where she actually is, so the rest of the window lets clicks through", async () => {
    getActivity.mockResolvedValue({ busy: true, running_sessions: 1, running_automations: 0 });
    const invoke = vi.fn();
    (globalThis as any).__TAURI__ = { core: { invoke } };
    // jsdom gives every element a zero rect; stand in for a real layout so the union means
    // something: the pet near the bottom, her bubble above it.
    const rects: Record<string, DOMRect> = {
      "companion-pet-zone": { left: 65, top: 140, right: 175, bottom: 250 } as DOMRect,
      "companion-bubble": { left: 20, top: 40, right: 220, bottom: 100 } as DOMRect,
    };
    const original = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function (this: Element) {
      const id = this.getAttribute("data-testid") || "";
      return rects[id] ?? (original.call(this) as DOMRect);
    };
    try {
      render(<MimiCompanion />);
      await waitFor(() =>
        expect(invoke).toHaveBeenCalledWith(
          "companion_hot_rect",
          // The union of what is alive: bubble on top, pet at the bottom.
          { x: 20, y: 40, width: 200, height: 210 },
        ),
      );
    } finally {
      Element.prototype.getBoundingClientRect = original;
    }
  });
});
