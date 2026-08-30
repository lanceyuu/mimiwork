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

const ago = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();
const about = {
  version: "0.4.13",
  models: 59,
  providers: 16,
  releases: [
    { tag: "v0.4.13", name: "", published_at: ago(0) },
    { tag: "v0.4.12", name: "", published_at: ago(1) },
    { tag: "v0.4.11", name: "", published_at: ago(4) },
  ],
  maintainer: "Shubin Yu, HEC Paris",
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
    // someone real is behind it
    expect(screen.getByText("Shubin Yu, HEC Paris")).toBeTruthy();
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
});
