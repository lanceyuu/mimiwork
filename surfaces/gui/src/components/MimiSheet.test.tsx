import { StrictMode } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SHEETS } from "../mimiSheets";
import { headMotion, MimiSheet, sheetPlayback } from "./MimiSheet";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("Mimi's expressions", () => {
  it("finishes waking once, even in Strict Mode", () => {
    vi.useFakeTimers();
    const done = vi.fn();
    render(<StrictMode><MimiSheet name="wake" onDone={done} /></StrictMode>);
    const duration = sheetPlayback("wake").reduce((sum, step) => sum + step.duration, 0);
    act(() => vi.advanceTimersByTime(duration - 1));
    expect(done).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(done).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(duration));
    expect(done).toHaveBeenCalledTimes(1);
  });

  it("cancels waking when new work interrupts it", () => {
    vi.useFakeTimers();
    const done = vi.fn();
    const view = render(<MimiSheet name="wake" onDone={done} />);
    act(() => vi.advanceTimersByTime(500));
    view.rerender(<MimiSheet name="thinking" onDone={done} />);
    act(() => vi.advanceTimersByTime(10000));
    expect(done).not.toHaveBeenCalled();
  });

  it("makes two distinct sniffing dips and returns the head to rest", () => {
    expect(headMotion("sniff", 12).y).toBeGreaterThan(headMotion("sniff", 16).y + 1);
    expect(headMotion("sniff", 20).y).toBeGreaterThan(headMotion("sniff", 16).y + 1);
    for (const name of ["thinking", "sniff"] as const) {
      for (const frame of [0, SHEETS[name].frames - 1]) {
        const motion = headMotion(name, frame);
        for (const value of [motion.x, motion.y, motion.angle]) expect(value).toBeCloseTo(0);
        expect(motion.scale).toBe(1);
      }
    }
  });

  it("keeps the head still under reduced motion while allowing completion", () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const done = vi.fn();
    render(<MimiSheet name="sniff" onDone={done} />);
    const head = screen.getByTestId("mimi-head");
    const resting = head.style.transform;
    act(() => vi.advanceTimersByTime(4000));
    expect(head.style.transform).toBe(resting);
    expect(done).toHaveBeenCalledTimes(1);
  });
});
