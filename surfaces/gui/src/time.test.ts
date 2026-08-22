import { describe, expect, it } from "vitest";
import { clockTime, compactAge, relativeTime } from "./time";

describe("clockTime", () => {
  it("formats epoch seconds as a locale clock time", () => {
    const t = new Date(2026, 0, 15, 14, 5).getTime() / 1000;
    expect(clockTime(t)).toMatch(/2:05/);
  });
  it("is empty for falsy or non-finite input", () => {
    expect(clockTime(0)).toBe("");
    expect(clockTime(NaN)).toBe("");
  });
});

describe("relativeTime", () => {
  it("says just now for fresh timestamps and near-future ones", () => {
    expect(relativeTime(Date.now() / 1000)).toBe("just now");
    expect(relativeTime(Date.now() / 1000 + 60)).toBe("just now");
  });
  it("coarses up through minutes, hours, days, then a date", () => {
    expect(relativeTime(Date.now() / 1000 - 300)).toMatch(/^5m ago$/);
    expect(relativeTime(Date.now() / 1000 - 7200)).toMatch(/^2h ago$/);
    expect(relativeTime(Date.now() / 1000 - 3 * 86_400)).toMatch(/^3d ago$/);
    expect(relativeTime(Date.now() / 1000 - 30 * 86_400)).toBeTruthy();
  });
  it("is empty for falsy input", () => {
    expect(relativeTime(0)).toBe("");
  });
});

describe("compactAge", () => {
  const minsAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
  it("buckets minutes/hours/days", () => {
    expect(compactAge(minsAgo(0.1))).toBe("now");
    expect(compactAge(minsAgo(5))).toBe("5m");
    expect(compactAge(minsAgo(6 * 60))).toBe("6h");
    expect(compactAge(minsAgo(72 * 60))).toBe("3d");
  });
  it("weeks, months, years", () => {
    expect(compactAge(minsAgo(12 * 24 * 60))).toBe("1w");
    expect(compactAge(minsAgo(45 * 24 * 60))).toBe("1mo");
    expect(compactAge(minsAgo(500 * 24 * 60))).toBe("1y");
  });
  it("is empty for missing or unparseable input", () => {
    expect(compactAge(undefined)).toBe("");
    expect(compactAge(null)).toBe("");
    expect(compactAge("not a date")).toBe("");
  });
});
