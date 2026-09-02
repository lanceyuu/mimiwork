import { describe, it, expect } from "vitest";
import { formatSaved, worthShowing, emptyTimeSaved } from "./timesaved";

describe("time saved", () => {
  it("reads in the unit a person would use", () => {
    expect(formatSaved(45)).toBe("≈45 min");
    expect(formatSaved(150)).toBe("≈2.5 h");
    expect(formatSaved(900)).toBe("≈15 h");
    expect(formatSaved(1800)).toBe("≈1.3 d"); // past a day, days of 24 h
    expect(formatSaved(4800)).toBe("≈3.3 d");
  });

  it("always marks itself as an estimate", () => {
    for (const m of [30, 90, 600, 5000]) expect(formatSaved(m).startsWith("≈")).toBe(true);
  });

  it("stays hidden until it is worth claiming", () => {
    // "≈4 min saved" starts an argument the feature cannot win.
    expect(worthShowing({ ...emptyTimeSaved(), saved_minutes: 4 })).toBe(false);
    expect(worthShowing({ ...emptyTimeSaved(), saved_minutes: 45 })).toBe(true);
    expect(worthShowing(null)).toBe(false);
  });
});
