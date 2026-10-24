/** The in-chat panel for the coding agents a conversation is coordinating. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AgentTeamPanel } from "./AgentTeamPanel";

const CURSOR = {
  key: "cursor",
  label: "Cursor",
  installed: true,
  signed_in: true,
  error: "",
  efforts: [],
  models: [
    { id: "auto", label: "Auto", efforts: [], default: true },
    { id: "gpt-6-luna", label: "GPT-6 Luna", efforts: [] },
  ],
  latest: "auto",
  model: "",
  effort: "",
};
const GEMINI = { ...CURSOR, key: "gemini", label: "Gemini CLI", signed_in: false, models: [], latest: "" };
const CODEX = {
  ...CURSOR,
  key: "codex",
  label: "Codex",
  efforts: ["low", "high"],
  models: [
    { id: "gpt-6.1-sol", label: "GPT-6.1-Sol", efforts: ["low", "high", "ultra"] },
    { id: "gpt-6-luna", label: "GPT-6-Luna", efforts: ["low"] },
  ],
  latest: "gpt-6.1-sol",
  model: "gpt-6.1-sol",
  effort: "ultra",
};

function stub(agents: unknown[]) {
  const posts: { url: string; body: any }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") posts.push({ url, body: JSON.parse(String(init.body)) });
      return { ok: true, json: async () => (init?.method === "POST" ? { ok: true } : { agents }) } as Response;
    }),
  );
  return posts;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Agent team panel", () => {
  it("lists only the agents that can take work, each with its model", async () => {
    stub([CURSOR, CODEX, GEMINI]); // Gemini is not signed in
    render(<AgentTeamPanel />);

    await waitFor(() => screen.getByTestId("agent-team-cursor"));
    expect(screen.getByTestId("agent-team-codex")).toBeTruthy();
    expect(screen.queryByTestId("agent-team-gemini")).toBeNull();
    const cursor = within(screen.getByTestId("agent-team-cursor"));
    expect((cursor.getByTestId("agent-team-model") as HTMLSelectElement).selectedOptions[0].textContent).toBe("Default: auto");
    expect(cursor.queryByTestId("agent-team-effort")).toBeNull(); // Cursor takes no effort level
  });

  it("picking a model saves it, and an effort the new model does not take falls back to the default", async () => {
    const posts = stub([CODEX]);
    render(<AgentTeamPanel />);

    const codex = within(await waitFor(() => screen.getByTestId("agent-team-codex")));
    fireEvent.change(codex.getByTestId("agent-team-model"), { target: { value: "gpt-6-luna" } });

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toContain("/v1/coding-agents/codex/settings");
    expect(posts[0].body).toEqual({ model: "gpt-6-luna", effort: "" });
    await waitFor(() => codex.getByText("Saved"));
    const effort = codex.getByTestId("agent-team-effort") as HTMLSelectElement;
    expect(Array.from(effort.options).map((o) => o.value)).toEqual(["", "low"]);
  });

  it("with no agent connected it says so and still links to the settings", async () => {
    stub([GEMINI]);
    const open = vi.fn();
    render(<AgentTeamPanel onOpenSettings={open} />);

    await waitFor(() => screen.getByText("No coding agent is connected yet."));
    fireEvent.click(screen.getByText("All agent settings"));
    expect(open).toHaveBeenCalled();
  });
});
