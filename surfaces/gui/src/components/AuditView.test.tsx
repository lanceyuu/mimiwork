import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const getAudit = vi.fn();
const qualitatiCredits = vi.fn();
const getSettings = vi.fn(async () => ({}) as any);
vi.mock("../api", () => ({
  getAudit: (...a: any[]) => getAudit(...a),
  qualitatiCredits: (...a: any[]) => qualitatiCredits(...a),
  // The EDGE panel reads the same settings payload as the hours badge; the default
  // here is "no profile yet", so these tests keep asserting the page without it.
  getSettings: () => getSettings(),
}));

import { AuditView } from "./AuditView";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const LEDGER = {
  ok: true,
  spent: 7,
  calls: 3,
  free_calls: 1,
  balance: { available: 530, team_points: 500, monthly_points: 30, lifelong_credits: 0 },
  entries: [
    {
      id: 1,
      at: "2026-08-25T09:00:00",
      credits: 6,
      free: false,
      model: "mimi-wolf",
      route: "advanced",
      tokens_in: 200000,
      tokens_out: 50000,
      team_points: 6,
      monthly_points: 0,
      lifelong_credits: 0,
    },
    {
      id: 2,
      at: "2026-08-25T08:00:00",
      credits: 0,
      free: true,
      model: "mimi-puppy",
      route: "",
      tokens_in: 900,
      tokens_out: 100,
      team_points: 0,
      monthly_points: 0,
      lifelong_credits: 0,
    },
  ],
};

describe("Activity — credits", () => {
  it("reports what was spent and what is left, by pool", async () => {
    getAudit.mockResolvedValue([]);
    qualitatiCredits.mockResolvedValue(LEDGER);
    render(<AuditView />);

    const panel = await screen.findByTestId("activity-credits");
    expect(panel.textContent).toContain("7");
    expect(panel.textContent).toContain("3 calls");
    expect(panel.textContent).toContain("1 free");
    const balance = screen.getByTestId("activity-credits-balance");
    // The whole point of the fix: a team member's pool is real balance.
    expect(balance.textContent).toContain("530");
    expect(balance.textContent).toContain("team 500");
    expect(balance.textContent).toContain("monthly 30");
  });

  it("names the pool each call was billed to, once expanded", async () => {
    getAudit.mockResolvedValue([]);
    qualitatiCredits.mockResolvedValue(LEDGER);
    render(<AuditView />);

    fireEvent.click(await screen.findByTestId("activity-credits-toggle"));
    const panel = screen.getByTestId("activity-credits");
    expect(panel.textContent).toContain("mimi-wolf");
    expect(panel.textContent).toContain("6 team");
    expect(panel.textContent).toContain("200,000 in");
    expect(panel.textContent).toContain("free"); // the puppy row cost nothing
  });

  it("says nothing is billed yet rather than showing an empty table", async () => {
    getAudit.mockResolvedValue([]);
    qualitatiCredits.mockResolvedValue({ ok: true, spent: 0, calls: 0, entries: [] });
    render(<AuditView />);
    const panel = await screen.findByTestId("activity-credits");
    expect(panel.textContent).toContain("Nothing billed yet");
  });

  it("shows no credits panel at all when the account isn't signed in", async () => {
    getAudit.mockResolvedValue([]);
    qualitatiCredits.mockResolvedValue({ ok: false, error: "not signed in" });
    render(<AuditView />);
    await waitFor(() => expect(getAudit).toHaveBeenCalled());
    expect(screen.queryByTestId("activity-credits")).toBeNull();
  });

  it("survives the credits call failing outright", async () => {
    getAudit.mockResolvedValue([]);
    qualitatiCredits.mockRejectedValue(new Error("offline"));
    render(<AuditView />);
    await waitFor(() => expect(getAudit).toHaveBeenCalled());
    expect(screen.queryByTestId("activity-credits")).toBeNull();
    expect(screen.getByText("No audit events yet.")).toBeTruthy();
  });
});
