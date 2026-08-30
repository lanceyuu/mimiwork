import { describe, it, expect, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { EdgeRadar } from "./EdgeRadar";
import type { EdgeProfile } from "../timesaved";

afterEach(cleanup);

const profile = (percents: number[]): EdgeProfile => ({
  pillars: ["Efficiency", "Decisions", "Growth", "Empowerment"].map((label, i) => ({
    key: label,
    label,
    blurb: `${label} blurb`,
    minutes: percents[i] * 2,
    percent: percents[i],
  })),
  total_minutes: 200,
  leading: "Efficiency",
  ready: true,
});

describe("EdgeRadar", () => {
  it("draws one point per pillar and labels every axis", () => {
    const { container } = render(<EdgeRadar edge={profile([50, 25, 17, 8])} />);
    expect(container.querySelectorAll("circle")).toHaveLength(4);
    for (const label of ["Efficiency", "Decisions", "Growth", "Empowerment"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("50%")).toBeTruthy();
  });

  it("scales the shape to the largest share, so a balanced profile isn't a dot", () => {
    // 25/25/25/25 must reach the outer ring, not draw a tiny diamond that reads
    // as "you barely use it".
    const { container } = render(<EdgeRadar edge={profile([25, 25, 25, 25])} />);
    const shape = container.querySelectorAll("polygon");
    const drawn = shape[shape.length - 1].getAttribute("points") || "";
    const ys = drawn.split(" ").map((p) => Number(p.split(",")[1]));
    expect(Math.min(...ys)).toBeCloseTo(95 - 66, 0); // CY − R: top vertex at full radius
  });

  it("keeps a zero pillar on the chart at the centre", () => {
    const { container } = render(<EdgeRadar edge={profile([100, 0, 0, 0])} />);
    const pts = (container.querySelectorAll("polygon")[4]?.getAttribute("points") || "").split(" ");
    expect(pts).toHaveLength(4); // an empty axis is information, not a hidden axis
  });
});
