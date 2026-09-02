import { describe, it, expect, vi, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const getAbout = vi.fn();
vi.mock("../api", () => ({ getAbout: () => getAbout() }));
vi.mock("../tauri", () => ({ openExternal: vi.fn() }));

import { AliveCard } from "./AliveCard";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Anchored to local midnight so the fixture means "N calendar days ago" regardless of
// what time the suite runs — the bug this guards against was exactly a time-of-day one.
const ago = (days: number) => {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - days);
  return d.toISOString();
};
const about = {
  version: "0.4.13",
  models: 59,
  providers: 16,
  releases: [
    { tag: "v0.4.13", name: "", published_at: ago(0) },
    { tag: "v0.4.12", name: "", published_at: ago(1) },
    { tag: "v0.4.11", name: "", published_at: ago(4) },
  ],
  maintainer: "QualiTaTi",
  contact: { address: "47 rue Vivienne, 75002 Paris, France", phone: "+1 619 356 2184", email: "contact@qualitati.com" },
  repo_url: "https://github.com/lanceyuu/mimiwork",
  tutorial_url: "https://github.com/lanceyuu/mimiwork#the-ten-minute-tutorial",
};

const props = { card: "card", label: "label", help: "help" };

describe("AliveCard", () => {
  it("answers the three doubts with checkable evidence", async () => {
    getAbout.mockResolvedValue(about);
    render(<AliveCard {...props} />);
    // still being worked on — real versions, real recency
    await screen.findByText("v0.4.13");
    expect(screen.getByTestId("alive-card").textContent).toContain("today");
    expect(screen.getByTestId("release-history").textContent).toContain("v0.4.12");
    // models won't fall behind
    expect(screen.getByText(/59/)).toBeTruthy();
    expect(screen.getByText(/16/)).toBeTruthy();
    // someone real is behind it, with a way to reach them
    expect(screen.getByText("QualiTaTi")).toBeTruthy();
    expect(screen.getByTestId("about-contact").textContent).toContain("47 rue Vivienne");
    expect(screen.getByText("contact@qualitati.com")).toBeTruthy();
  });

  it("renders nothing rather than an error when offline", async () => {
    getAbout.mockRejectedValue(new Error("offline"));
    const { container } = render(<AliveCard {...props} />);
    await waitFor(() => expect(container.querySelector("[data-testid='alive-card']")).toBeNull());
  });

  it("survives an empty release list (a fresh fork, or GitHub down)", async () => {
    getAbout.mockResolvedValue({ ...about, releases: [] });
    render(<AliveCard {...props} />);
    await screen.findByTestId("alive-card");
    expect(screen.queryByTestId("release-history")).toBeNull();
    expect(screen.getByText(/59/)).toBeTruthy(); // local facts still shown
  });

  it("survives a payload from an older sidecar without taking the page down", async () => {
    // A GUI newer than its server gets a 404 body here. Reading .releases off it threw
    // during render and blanked the whole General page — caught by the e2e suite, not
    // by any unit test, which is why this one exists.
    getAbout.mockResolvedValue({} as any);
    const { container } = render(<AliveCard {...props} />);
    await waitFor(() => expect(container.querySelector("[data-testid='alive-card']")).toBeNull());
  });

  it("counts calendar days, so two releases from different days read differently", async () => {
    // v0.4.11 (1.4 days back) and v0.4.10 (1.99 days back) both floored to "yesterday",
    // which told the reader two versions shipped the same day.
    getAbout.mockResolvedValue({
      ...about,
      releases: [
        { tag: "v0.4.13", name: "", published_at: ago(0) },
        { tag: "v0.4.11", name: "", published_at: ago(1) },
        { tag: "v0.4.10", name: "", published_at: ago(2) },
      ],
    });
    render(<AliveCard {...props} />);
    await screen.findByTestId("alive-card");
    const history = screen.getByTestId("release-history").textContent || "";
    expect(history).toContain("yesterday");
    expect(history).toContain("2 days ago");
  });

  it("still renders when only the local facts arrive", async () => {
    getAbout.mockResolvedValue({ models: 59, providers: 16, maintainer: "Shubin Yu" } as any);
    render(<AliveCard {...props} />);
    await screen.findByTestId("alive-card");
    expect(screen.queryByTestId("release-history")).toBeNull();
  });
});
