import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Keys for a person's own scripts (owner ask 2026-11-12): saved by name, never shown back.

const getScriptKeys = vi.fn();
const setScriptKey = vi.fn();
const removeScriptKey = vi.fn();
vi.mock("../api", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("../api")),
  getScriptKeys: () => getScriptKeys(),
  setScriptKey: (n: string, v: string) => setScriptKey(n, v),
  removeScriptKey: (n: string) => removeScriptKey(n),
}));
import { ScriptKeysCard } from "./SettingsView";

afterEach(cleanup);

describe("ScriptKeysCard", () => {
  it("saves a key under a capitalised name and then shows only the name", async () => {
    getScriptKeys.mockResolvedValue({ names: [] });
    setScriptKey.mockResolvedValue({ ok: true, names: ["OPENROUTER_API_KEY"] });
    render(<ScriptKeysCard />);
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "openrouter api_key" } });
    fireEvent.change(screen.getByLabelText("Key"), { target: { value: "secret-value" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(setScriptKey).toHaveBeenCalledWith("OPENROUTER_API_KEY", "secret-value"));
    expect(await screen.findByText("OPENROUTER_API_KEY")).toBeTruthy();
    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("");
    expect(screen.queryByText(/secret-value/)).toBeNull();
  });

  it("says why a name was refused and keeps what was typed", async () => {
    getScriptKeys.mockResolvedValue({ names: [] });
    setScriptKey.mockResolvedValue({ ok: false, error: "That name is used by the computer itself.", names: [] });
    render(<ScriptKeysCard />);
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "PATH" } });
    fireEvent.change(screen.getByLabelText("Key"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("That name is used by the computer itself.")).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("PATH");
  });

  it("removes a saved key", async () => {
    getScriptKeys.mockResolvedValue({ names: ["HF_TOKEN"] });
    removeScriptKey.mockResolvedValue({ ok: true, names: [] });
    render(<ScriptKeysCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove HF_TOKEN" }));
    await waitFor(() => expect(removeScriptKey).toHaveBeenCalledWith("HF_TOKEN"));
    await waitFor(() => expect(screen.queryByText("HF_TOKEN")).toBeNull());
  });

  it("stays hidden when the sidecar did not answer", async () => {
    getScriptKeys.mockRejectedValue(new Error("offline"));
    render(<ScriptKeysCard />);
    await waitFor(() => expect(getScriptKeys).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("Keys for your own scripts")).toBeNull();
  });
});
