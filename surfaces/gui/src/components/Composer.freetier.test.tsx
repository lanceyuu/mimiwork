// Mimi Puppy's daily allowance, warned about before the gateway refuses (owner report
// 2026-09-04: "mimi puppy does not work" was a spent allowance shown as an outage).
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Composer } from "./Composer";

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive",
  model: "qualitati:mimi-puppy",
  running: false,
  connected: true,
  sessionId: "s1",
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

afterEach(cleanup);

describe("Composer / Mimi Puppy allowance banner", () => {
  it("shows the daily balance even when plenty remains and hides it for other models", () => {
    const { rerender } = render(<Composer {...props({ freeTier: { cap: 500, remaining: 300, resets_at: "2026-09-05T00:00:00+00:00" } })} />);
    expect(screen.getByTestId("free-tier-banner").textContent).toContain("300 free requests left today (daily limit: 500)");
    // Hound shares the allowance (free since 2026-09-08) and shows it too; Wolf is paid and never does.
    rerender(<Composer {...props({ model: "qualitati:mimi-hound", freeTier: { cap: 500, remaining: 300, resets_at: "2026-09-05T00:00:00+00:00" } })} />);
    expect(screen.getByTestId("free-tier-banner").textContent).toContain("Mimi Hound: 300 free requests left today");
    expect(screen.getByTestId("free-tier-banner").textContent).toContain("shared with Mimi Puppy");
    rerender(<Composer {...props({ model: "qualitati:mimi-wolf", freeTier: { cap: 500, remaining: 0, resets_at: "2026-09-05T00:00:00+00:00" } })} />);
    expect(screen.queryByTestId("free-tier-banner")).toBeNull();
  });

  it("warns at the last 10 percent with the count and the reset time", () => {
    render(<Composer {...props({ freeTier: { cap: 500, remaining: 37, resets_at: "2026-09-05T00:00:00+00:00" } })} />);
    const banner = screen.getByTestId("free-tier-banner");
    expect(banner.textContent).toContain("Mimi Puppy: 37 free requests left today");
    expect(banner.textContent).toContain("resets at");
    expect(screen.queryByTestId("free-tier-switch")).toBeNull();
  });

  it("when spent, says so and switches to Mimi Wolf in one click", () => {
    const onModelChange = vi.fn();
    render(<Composer {...props({ onModelChange, freeTier: { cap: 500, remaining: 0, resets_at: "2026-09-05T00:00:00+00:00" } })} />);
    expect(screen.getByRole("alert").textContent).toContain("Today's free allowance for Mimi Puppy and Mimi Hound is used up");
    expect(screen.getByRole("alert").textContent).toContain("Mimi Wolf uses account credits.");
    fireEvent.click(screen.getByTestId("free-tier-switch"));
    expect(onModelChange).toHaveBeenCalledWith("qualitati:mimi-wolf");
  });

  it("distinguishes the account balance from free requests and explains multi-step usage", () => {
    render(<Composer {...props({ accountCredits: 420, freeTier: { cap: 500, remaining: 300, resets_at: "2026-09-06T00:00:00Z" } })} />);
    const banner = screen.getByTestId("free-tier-banner");
    expect(banner.textContent).toContain("300 free requests left today");
    expect(banner.textContent).toContain("Account credits: 420");
    expect(banner.textContent).toContain("One task can use several requests.");
  });

});
