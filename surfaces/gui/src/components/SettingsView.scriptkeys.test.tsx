import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Keys for a person's own scripts (owner ask 2026-11-12): saved by name, never shown back.

const getScriptKeys = vi.fn();
const setScriptKey = vi.fn();
const removeScriptKey = vi.fn();
const setScriptKeysFromEnv = vi.fn();
vi.mock("../api", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("../api")),
  getScriptKeys: () => getScriptKeys(),
  setScriptKey: (n: string, v: string) => setScriptKey(n, v),
  removeScriptKey: (n: string) => removeScriptKey(n),
  setScriptKeysFromEnv: (text: string) => setScriptKeysFromEnv(text),
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
  // Owner, 2026-11-19: "it is always so difficult to put the API key to the .env".
  it("saves every key of a pasted .env file at once", async () => {
    getScriptKeys.mockResolvedValue({ names: [] });
    setScriptKeysFromEnv.mockResolvedValue({ ok: true, names: ["OPENAI_API_KEY", "TAVILY_API_KEY"] });
    render(<ScriptKeysCard />);
    const pasted = "OPENAI_API_KEY=sk-one\nTAVILY_API_KEY=tvly-two\n";
    fireEvent.paste(await screen.findByLabelText("Key"), { clipboardData: { getData: () => pasted } });
    await waitFor(() => expect(setScriptKeysFromEnv).toHaveBeenCalledWith(pasted));
    expect(await screen.findByText("TAVILY_API_KEY")).toBeTruthy();
    expect(screen.queryByText(/sk-one/)).toBeNull();
    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("");
  });

  it("leaves an ordinary pasted key in the box", async () => {
    getScriptKeys.mockResolvedValue({ names: [] });
    setScriptKeysFromEnv.mockClear();
    render(<ScriptKeysCard />);
    fireEvent.paste(await screen.findByLabelText("Key"), { clipboardData: { getData: () => "sk-or-v1-abc=" } });
    expect(setScriptKeysFromEnv).not.toHaveBeenCalled();
  });

  // The example name was OPENROUTER_API_KEY, and the card was read as "the OpenRouter key field".
  it("does not look like a field for one provider's key", async () => {
    getScriptKeys.mockResolvedValue({ names: [] });
    render(<ScriptKeysCard />);
    const name = (await screen.findByLabelText("Name")) as HTMLInputElement;
    expect(name.placeholder).not.toMatch(/OPENROUTER/);
    expect(screen.getByText(/OpenAI, Anthropic, Gemini/)).toBeTruthy();
    expect(document.querySelectorAll("#script-key-names option").length).toBeGreaterThan(4);
  });
});
