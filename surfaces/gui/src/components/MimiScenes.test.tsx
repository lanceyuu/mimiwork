/** The playful scenes' clock: what the sprite and the visitor do at a given second. */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MimiScene, SCENES, sampleScene, type SceneName } from "./MimiScenes";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("sampleScene", () => {
  it("butterfly: notice, investigate, delight — the visitor arrives, perches and leaves", () => {
    expect(sampleScene("butterfly", 0).visitor.opacity).toBe(0);
    expect(sampleScene("butterfly", 1).sheet).toBe("thinking");
    expect(sampleScene("butterfly", 3).sheet).toBe("sniff");
    expect(sampleScene("butterfly", 5).sheet).toBe("happy");
    const perched = sampleScene("butterfly", 2.5).visitor;
    expect(Math.round(perched.x)).toBe(49);
    expect(Math.round(perched.y)).toBe(40);
    expect(sampleScene("butterfly", SCENES.butterfly.duration).visitor.opacity).toBe(0);
    // Neutral cell 0 outside the expression window: no drift when a sheet takes over.
    expect(sampleScene("butterfly", 2.25).frame).toBe(0);
    expect(sampleScene("butterfly", 4.3).frame).toBe(0);
  });

  it("bubble: drifts in, pops at 2.35 s, a wink follows", () => {
    expect(sampleScene("bubble", 1).visitor.opacity).toBe(1);
    expect(sampleScene("bubble", 2.3).visitor.pop).toBe(0);
    expect(sampleScene("bubble", 2.9).visitor.pop).toBe(1);
    expect(sampleScene("bubble", 3).visitor.opacity).toBe(0);
    expect(sampleScene("bubble", 2.5).sheet).toBe("wink");
    expect(sampleScene("bubble", 2.5).frame).toBeGreaterThan(0);
    expect(sampleScene("bubble", 99).time).toBe(SCENES.bubble.duration);
  });

  it("the ball settles at her paw before her nudge sends it away", () => {
    const resting = sampleScene("ball", 3.2);
    expect(resting.visitor.x).toBe(25);
    expect(resting.visitor.y).toBe(89);
    expect(sampleScene("ball", 3.8).lean).toBeLessThan(0);
    expect(sampleScene("ball", 4.4).lift).toBeGreaterThan(0);
    expect(sampleScene("ball", 5.5).visitor.x).toBeGreaterThan(75);
  });

  it("the airplane completes its loop before flying away", () => {
    const start = sampleScene("paperPlane", 2.3).visitor;
    const opposite = sampleScene("paperPlane", 3.5).visitor;
    const end = sampleScene("paperPlane", 4.7).visitor;
    expect(start.x).toBeCloseTo(end.x);
    expect(start.y).toBeCloseTo(end.y);
    expect(opposite.x).toBeLessThan(start.x - 30);
    expect(sampleScene("paperPlane", 5).sheet).toBe("happy");
  });

  it.each(["ball", "paperPlane"] as SceneName[])("%s stays in the pet window and returns to a neutral pose", (name) => {
    for (let t = 0; t < SCENES[name].duration; t += 0.025) {
      const { visitor } = sampleScene(name, t);
      expect(visitor.x).toBeGreaterThanOrEqual(8);
      expect(visitor.x).toBeLessThanOrEqual(92);
      expect(visitor.y).toBeGreaterThanOrEqual(8);
      expect(visitor.y).toBeLessThanOrEqual(90);
      expect(Object.values(visitor).every(Number.isFinite)).toBe(true);
    }
    const end = sampleScene(name, SCENES[name].duration);
    expect(end.visitor.opacity).toBe(0);
    expect(end.frame).toBe(0);
    expect(end.lean).toBe(0);
    expect(end.lift).toBe(0);
  });

  it("stays still when reduced motion is enabled during a scene and still finishes", () => {
    vi.useFakeTimers();
    let change = () => {};
    const media = {
      matches: false,
      addEventListener: vi.fn((_event, callback) => { change = callback; }),
      removeEventListener: vi.fn(),
    };
    vi.stubGlobal("matchMedia", () => media);
    const onDone = vi.fn();
    render(<MimiScene name="ball" onDone={onDone} />);
    act(() => vi.advanceTimersByTime(1200));
    media.matches = true;
    act(() => change());
    expect(screen.getByTestId("companion-sprite").querySelector("svg > g")?.getAttribute("opacity")).toBe("0");
    act(() => vi.advanceTimersByTime(6600));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
