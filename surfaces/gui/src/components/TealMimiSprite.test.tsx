import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TealMimiSprite } from "./TealMimiSprite";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("Teal Mimi animation", () => {
  it("plays the completion jump once and never enters the removed wave row", () => {
    vi.useFakeTimers();
    const onDone = vi.fn();
    render(<TealMimiSprite phase="wake" onDone={onDone} />);
    expect(screen.getByTestId("companion-sprite").dataset.row).toBe("4");
    act(() => vi.advanceTimersByTime(560));
    expect(screen.getByTestId("companion-sprite").dataset.frame).toBe("4");
    expect(onDone).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(280));
    expect(onDone).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(2000));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("keeps a still pose with reduced motion but still completes the transition", () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const onDone = vi.fn();
    render(<TealMimiSprite phase="wake" onDone={onDone} />);
    act(() => vi.advanceTimersByTime(840));
    expect(screen.getByTestId("companion-sprite").dataset.frame).toBe("0");
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("cancels a pending completion when the sprite is unmounted", () => {
    vi.useFakeTimers();
    const onDone = vi.fn();
    const view = render(<TealMimiSprite phase="wake" onDone={onDone} />);
    view.unmount();
    act(() => vi.advanceTimersByTime(2000));
    expect(onDone).not.toHaveBeenCalled();
  });
});
