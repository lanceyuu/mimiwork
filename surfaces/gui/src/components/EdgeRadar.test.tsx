import { describe, it, expect, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { EdgeRadar } from "./EdgeRadar";
import { FiveABars } from "./FiveABars";
import type { EdgeProfile, FiveAProfile } from "../timesaved";

afterEach(cleanup);

const edge = (percents: number[], enablingPercent = 12): EdgeProfile => ({
  pillars: ["Efficiency", "Decisions", "Growth"].map((label, i) => ({
    key: label,
    label,
    blurb: `${label} blurb`,
    minutes: percents[i] * 2,
    percent: percents[i],
  })),
  enabling: {
    key: "Empowerment",
    label: "Empowerment",
    blurb: "The enabling pillar",
    minutes: 30,
    percent: enablingPercent,
  },
  outcome_minutes: 200,
  total_minutes: 230,
  leading: "Efficiency",
  ready: true,
});

describe("EdgeRadar — three outcome pillars on one enabling pillar (ch. 9)", () => {
  it("draws a triangle, not a four-axis radar", () => {
    // Empowerment is "the enabling pillar", not a fourth slice; drawing four equal
    // axes summing to 100 contradicted the framework the chart claims to show.
    const { container } = render(<EdgeRadar edge={edge([50, 30, 20])} />);
    expect(container.querySelectorAll("circle")).toHaveLength(3);
    for (const label of ["Efficiency", "Decisions", "Growth"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("shows the enabler as a foundation, separate from the shares", () => {
    render(<EdgeRadar edge={edge([50, 30, 20])} />);
    expect(screen.getByText("Where the value lands")).toBeTruthy();
    expect(screen.getByText("What makes them possible")).toBeTruthy();
    expect(screen.getAllByText("Empowerment").length).toBeGreaterThan(0);
  });

  it("scales to the largest share so an even split still fills the chart", () => {
    const { container } = render(<EdgeRadar edge={edge([34, 33, 33])} />);
    const polys = container.querySelectorAll("polygon");
    const drawn = polys[polys.length - 1].getAttribute("points") || "";
    const ys = drawn.split(" ").map((p) => Number(p.split(",")[1]));
    expect(Math.min(...ys)).toBeCloseTo(84 - 58, 0); // CY − R at the top vertex
  });

  it("renders nothing rather than a broken shape if a pillar is missing", () => {
    const partial = { ...edge([50, 50, 0]), pillars: [] } as EdgeProfile;
    const { container } = render(<EdgeRadar edge={partial} />);
    expect(container.querySelector("[data-testid='edge-radar']")).toBeNull();
  });
});

const five = (percents: number[]): FiveAProfile => ({
  levels: ["Access", "Assistants", "Applications", "Automation", "Agents"].map((label, i) => ({
    key: label,
    label,
    blurb: `${label} blurb`,
    turns: percents[i],
    percent: percents[i],
  })),
  total_turns: percents.reduce((a, b) => a + b, 0),
  leading: "Applications",
  ready: true,
});

describe("FiveABars — the continuum (ch. 7)", () => {
  it("keeps the rungs in continuum order, never sorted by size", () => {
    // The finding IS the shape of the ladder: bars piling on the left means heavy
    // human involvement, on the right means light supervision. Sorting destroys it.
    render(<FiveABars five={five([10, 5, 50, 15, 20])} />);
    const row = screen.getByTestId("fivea-labels");
    const labels = [...row.children].map((c) => c.textContent);
    expect(labels).toEqual([
      "Access",
      "Assistants",
      "Applications",
      "Automation",
      "Agents",
    ]);
  });

  it("names the axis so the ladder is stated, not implied", () => {
    render(<FiveABars five={five([10, 5, 50, 15, 20])} />);
    expect(screen.getByText("more human involvement")).toBeTruthy();
    expect(screen.getByText("more autonomy")).toBeTruthy();
  });

  it("keeps an empty rung visible", () => {
    const { container } = render(<FiveABars five={five([100, 0, 0, 0, 0])} />);
    expect(container.querySelectorAll("[title$='turns'], [title$='turn']")).toHaveLength(5);
  });
});
