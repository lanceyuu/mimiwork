/** The playful scenes' clock: what the sprite and the visitor do at a given second. */
import { describe, expect, it } from "vitest";
import { SCENES, sampleScene } from "./MimiScenes";

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
});
