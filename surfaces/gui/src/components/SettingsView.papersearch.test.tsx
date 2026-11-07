import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// The OpenAlex key (spec 2026-11-07): stored only on this computer, never shown back.

const getScholarly = vi.fn();
const setScholarly = vi.fn();
vi.mock("../api", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("../api")),
  getScholarly: () => getScholarly(),
  setScholarly: (k: string) => setScholarly(k),
}));
vi.mock("../tauri", async () => ({ ...(await vi.importActual<Record<string, unknown>>("../tauri")), openExternal: vi.fn() }));
import { PaperSearchCard } from "./SettingsView";

afterEach(cleanup);

describe("PaperSearchCard", () => {
  it("explains the shared limit when no key is saved, and saves a new key", async () => {
    getScholarly.mockResolvedValue({ has_key: false });
    setScholarly.mockResolvedValue({ ok: true, has_key: true });
    render(<PaperSearchCard />);
    expect(await screen.findByText(/a small free daily limit shared with your network/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("OpenAlex key"), { target: { value: "k-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(setScholarly).toHaveBeenCalledWith("k-1"));
    expect(await screen.findByText("Using your OpenAlex key.")).toBeTruthy();
    expect((screen.getByLabelText("OpenAlex key") as HTMLInputElement).value).toBe("");
  });

  it("never shows a saved key and can remove it", async () => {
    getScholarly.mockResolvedValue({ has_key: true });
    setScholarly.mockResolvedValue({ ok: true, has_key: false });
    render(<PaperSearchCard />);
    await screen.findByText("Using your OpenAlex key.");
    expect((screen.getByLabelText("OpenAlex key") as HTMLInputElement).value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(setScholarly).toHaveBeenCalledWith(""));
    expect(await screen.findByText(/a small free daily limit/)).toBeTruthy();
  });
});
