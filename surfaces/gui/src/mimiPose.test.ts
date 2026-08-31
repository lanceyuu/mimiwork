import { afterEach, describe, expect, it, vi } from "vitest";
import { MIMI_POSES, nextPose } from "./mimiPose";

afterEach(() => {
  // Unstub FIRST: a test that replaced localStorage with a throwing stub has no
  // clear() to call.
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("Mimi's launch pose", () => {
  it("advances one pose per launch and wraps", () => {
    const seen = MIMI_POSES.map(() => nextPose());
    expect(new Set(seen).size).toBe(MIMI_POSES.length);
    // Round the loop: the eleventh launch is the first pose again.
    expect(nextPose()).toBe(seen[0]);
  });

  it("survives storage being unavailable — the splash must never be what fails", () => {
    vi.stubGlobal("localStorage", {
      getItem() { throw new Error("blocked"); },
      setItem() { throw new Error("blocked"); },
    });
    expect(MIMI_POSES).toContain(nextPose());
  });

  it("recovers from a junk or out-of-range stored value", () => {
    window.localStorage.setItem("mimi.pose.next", "not a number");
    expect(nextPose()).toBe(MIMI_POSES[0]);
    window.localStorage.setItem("mimi.pose.next", "-7");
    expect(MIMI_POSES).toContain(nextPose());
    window.localStorage.setItem("mimi.pose.next", "999");
    expect(MIMI_POSES).toContain(nextPose());
  });
});
