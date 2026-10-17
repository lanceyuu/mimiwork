/** Coding agents page: Claude Code and Codex connected like any other tool. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { CodingAgentsSection } from "./CodingAgentsSection";

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn() }));
vi.mock("../../tauri", () => ({ openExternal }));

type Call = { url: string; method: string; body?: any };

function stubFetch(routes: { match: string; method?: string; json: any }[]) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method || "GET").toUpperCase();
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const r = routes.find((x) => url.includes(x.match) && (!x.method || x.method === method));
      return { ok: true, json: async () => r?.json ?? {} } as Response;
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const CLAUDE = {
  key: "claude_code",
  label: "Claude Code",
  billing: "your own Claude account",
  installed: true,
  path: "/Users/me/.local/bin/claude",
  version: "2.1.270 (Claude Code)",
  signed_in: true,
  account: "me@example.com",
  error: "",
  install_command: "curl -fsSL https://claude.ai/install.sh | bash",
  sign_in_command: "claude auth login",
  efforts: ["low", "medium", "high", "xhigh", "max"],
  defaults: { model: "opus", effort: "high" },
  models: [
    { id: "fable", label: "Latest Fable", resolved: "" },
    { id: "opus", label: "Latest Opus", resolved: "claude-opus-5" },
  ],
  models_listed: false,
  latest: "claude-opus-5-5",
  model: "",
  effort: "",
  keep_hooks: false,
};
const CODEX = {
  ...CLAUDE,
  key: "codex",
  label: "Codex",
  billing: "your own OpenAI account",
  path: "/opt/homebrew/bin/codex",
  version: "codex-cli 0.162.1",
  signed_in: false,
  account: "",
  install_command: "npm install -g @openai/codex",
  sign_in_command: "codex login",
  efforts: ["minimal", "low", "medium", "high", "xhigh"],
  defaults: { model: "gpt-6-astra", effort: "xhigh" },
  models: [
    { id: "gpt-6.1-sol", label: "GPT-6.1-Sol", description: "Latest workhorse model.", efforts: ["low", "high", "ultra"] },
    { id: "gpt-6-luna", label: "GPT-6-Luna", description: "Fast and affordable.", efforts: ["low", "medium"] },
  ],
  models_listed: true,
  latest: "gpt-6.1-sol",
};

const card = (key: string) => within(screen.getByTestId(`coding-agent-${key}`));

describe("Coding agents", () => {
  it("shows where each agent is installed, who it is signed in as, and the model it will use", async () => {
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [CLAUDE, CODEX] } }]);
    render(<CodingAgentsSection />);

    const claude = await waitFor(() => card("claude_code"));
    expect(claude.getByTestId("coding-agent-status").textContent).toBe("Connected");
    expect(claude.getByText("/Users/me/.local/bin/claude")).toBeTruthy();
    expect(claude.getByText("me@example.com")).toBeTruthy();
    expect((claude.getByTestId("coding-agent-model-select") as HTMLSelectElement).selectedOptions[0].textContent).toBe(
      "Latest (currently claude-opus-5-5)",
    );
    expect(card("codex").getByTestId("coding-agent-status").textContent).toBe("Not signed in");
    expect(card("codex").getByText("Runs on your own OpenAI account, not QualiTaTi credits.")).toBeTruthy();
  });

  it("an agent that is not installed shows the command to install it and cannot be tested", async () => {
    const missing = { ...CODEX, installed: false, path: "", version: "" };
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [missing] } }]);
    render(<CodingAgentsSection />);

    const codex = await waitFor(() => card("codex"));
    expect(codex.getByTestId("coding-agent-status").textContent).toBe("Not installed");
    expect(codex.getByText("npm install -g @openai/codex")).toBeTruthy();
    expect((codex.getByTestId("coding-agent-test") as HTMLButtonElement).disabled).toBe(true);
  });

  it("signing in starts the agent's own browser sign-in and still shows the terminal command", async () => {
    const calls = stubFetch([
      { match: "/sign-in", method: "POST", json: { started: true, url: "https://auth.openai.com/x" } },
      { match: "/v1/coding-agents", json: { agents: [CODEX] } },
    ]);
    render(<CodingAgentsSection />);

    const codex = await waitFor(() => card("codex"));
    expect(codex.getByText("codex login")).toBeTruthy();
    fireEvent.click(codex.getByTestId("coding-agent-sign-in"));

    await waitFor(() => expect(codex.getByTestId("coding-agent-sign-in-waiting")).toBeTruthy());
    expect(calls.some((c) => c.url.endsWith("/v1/coding-agents/codex/sign-in") && c.method === "POST")).toBe(true);
    fireEvent.click(codex.getByText("Open the sign-in page"));
    expect(openExternal).toHaveBeenCalledWith("https://auth.openai.com/x");
  });

  it("a sign-in that cannot start says why in plain words", async () => {
    stubFetch([
      { match: "/sign-in", method: "POST", json: { started: false, error: "Codex's sign-in did not start: port in use" } },
      { match: "/v1/coding-agents", json: { agents: [CODEX] } },
    ]);
    render(<CodingAgentsSection />);

    fireEvent.click(await waitFor(() => card("codex").getByTestId("coding-agent-sign-in")));

    await waitFor(() => expect(card("codex").getByText("Codex's sign-in did not start: port in use")).toBeTruthy());
  });

  it("the model list offers Latest first, then the agent's own models, then a custom name", async () => {
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [CLAUDE, CODEX] } }]);
    render(<CodingAgentsSection />);

    const options = (key: string) =>
      Array.from((card(key).getByTestId("coding-agent-model-select") as HTMLSelectElement).options).map((o) => o.textContent);
    await waitFor(() => card("codex"));
    expect(options("claude_code")).toEqual([
      "Latest (currently claude-opus-5-5)",
      "Latest Fable",
      "Latest Opus (claude-opus-5)",
      "Custom…",
    ]);
    expect(options("codex")).toEqual(["Latest (currently gpt-6.1-sol)", "GPT-6.1-Sol", "GPT-6-Luna", "Custom…"]);
    expect(card("claude_code").getByText(/Claude Code cannot list its models/)).toBeTruthy();
    expect(card("codex").getByText(/From Codex's own model list/)).toBeTruthy();
  });

  it("choosing a model, an effort, or a custom name saves it for that agent", async () => {
    const calls = stubFetch([
      { match: "/settings", method: "POST", json: { ok: true } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    const claude = await waitFor(() => card("claude_code"));
    fireEvent.change(claude.getByTestId("coding-agent-model-select"), { target: { value: "fable" } });
    fireEvent.change(claude.getByTestId("coding-agent-effort"), { target: { value: "low" } });
    fireEvent.change(claude.getByTestId("coding-agent-model-select"), { target: { value: "__custom" } });
    const typed = claude.getByTestId("coding-agent-model");
    fireEvent.change(typed, { target: { value: "claude-sonnet-5" } });
    fireEvent.blur(typed);

    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/claude_code/settings")).length).toBe(3));
    const saved = calls.filter((c) => c.url.endsWith("/claude_code/settings")).map((c) => c.body);
    expect(saved[0]).toEqual({ model: "fable", effort: "" });
    expect(saved[1].effort).toBe("low");
    expect(saved[2].model).toBe("claude-sonnet-5");
  });

  it("when Codex cannot list its models, a text box takes a model name and says why", async () => {
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [{ ...CODEX, models: [], models_listed: false, latest: "" }] } }]);
    render(<CodingAgentsSection />);

    const codex = await waitFor(() => card("codex"));
    expect(codex.queryByTestId("coding-agent-model-select")).toBeNull();
    expect(codex.getByTestId("coding-agent-model")).toBeTruthy();
    expect(codex.getByText(/Codex did not share its model list/)).toBeTruthy();
  });

  it("the effort list follows the levels the chosen Codex model takes", async () => {
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [{ ...CODEX, model: "gpt-6-luna" }] } }]);
    render(<CodingAgentsSection />);

    const effort = (await waitFor(() => card("codex").getByTestId("coding-agent-effort"))) as HTMLSelectElement;
    expect(Array.from(effort.options).map((o) => o.value)).toEqual(["", "low", "medium"]);
  });

  it("the page says Claude Code and Codex can work together on one job", async () => {
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [CLAUDE, CODEX] } }]);
    render(<CodingAgentsSection />);

    const note = await waitFor(() => screen.getByTestId("coding-agents-together"));
    expect(note.textContent).toContain("can have one review the other's branch");
  });

  it("the Test button reports how long the real call took, or the error in plain words", async () => {
    stubFetch([
      { match: "/claude_code/test", method: "POST", json: { ok: true, reply: "OK", seconds: 6.2, model: "claude-opus-5-5" } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    fireEvent.click(await waitFor(() => card("claude_code").getByTestId("coding-agent-test")));

    await waitFor(() =>
      expect(card("claude_code").getByTestId("coding-agent-test-result").textContent).toBe("It answered in 6.2 seconds, using claude-opus-5-5."),
    );
  });

  it("an agent that is installed but broken shows its error as an alert", async () => {
    const broken = { ...CLAUDE, error: "Claude Code is installed at /x but does not start: permission denied" };
    stubFetch([{ match: "/v1/coding-agents", json: { agents: [broken] } }]);
    render(<CodingAgentsSection />);

    const alert = await waitFor(() => card("claude_code").getByRole("alert"));
    expect(alert.textContent).toContain("does not start: permission denied");
    expect(card("claude_code").getByTestId("coding-agent-status").textContent).toBe("Needs attention");
  });

  it("when the page cannot reach the app it offers to try again", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response));
    render(<CodingAgentsSection />);

    await waitFor(() => expect(screen.getByTestId("coding-agents-error")).toBeTruthy());
    expect(screen.getByText("Try again")).toBeTruthy();
  });

  it("recent hand-offs list each run with its session and a command that reopens it in its own CLI", async () => {
    const run = {
      job: "csv-1", key: "codex", agent: "Codex", name: "csv export", status: "failed", branch: "mimi/codex-csv",
      workdir: "/p/.mimiwork/agents/codex-csv", session_id: "01a1-thread", at: 1_790_000_000,
      resume_command: "cd /p/.mimiwork/agents/codex-csv && codex resume 01a1-thread", folder_exists: true,
    };
    stubFetch([
      { match: "/v1/coding-agents/runs", json: { runs: [run] } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    const row = await waitFor(() => screen.getByTestId("coding-agent-run"));
    expect(row.textContent).toContain("csv export");
    expect(row.textContent).toContain("Did not finish");
    expect(row.textContent).toContain("01a1-thread");
    expect(within(row).getByText("cd /p/.mimiwork/agents/codex-csv && codex resume 01a1-thread")).toBeTruthy();
    expect(within(row).getByText("Copy")).toBeTruthy();
  });

  it("a hand-off whose folder has been removed says its conversation can still be read", async () => {
    stubFetch([
      { match: "/v1/coding-agents/runs", json: { runs: [{
        job: "a", key: "claude_code", agent: "Claude Code", name: "docs", status: "finished", branch: "", workdir: "/gone",
        session_id: "s9", at: 1_790_000_000, resume_command: "claude --resume s9", folder_exists: false,
      }] } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    const row = await waitFor(() => screen.getByTestId("coding-agent-run"));
    expect(row.textContent).toContain("Its folder has been removed");
    expect(within(row).getByText("claude --resume s9")).toBeTruthy();
  });

  it("before any hand-off the list says what will appear there", async () => {
    stubFetch([
      { match: "/v1/coding-agents/runs", json: { runs: [] } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    await waitFor(() => expect(screen.getByText(/No hand-offs yet/)).toBeTruthy());
  });

  it("Claude Code hand-offs run without your own hooks by default, and turning them on saves that choice", async () => {
    const calls = stubFetch([
      { match: "/settings", method: "POST", json: { ok: true } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE, CODEX] } },
    ]);
    render(<CodingAgentsSection />);

    const hooks = await waitFor(() => card("claude_code").getByTestId("coding-agent-hooks"));
    expect(hooks.textContent).toContain("Off for hand-offs (faster)");
    fireEvent.click(within(hooks).getByRole("switch"));

    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/claude_code/settings"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/claude_code/settings"))!.body).toEqual({ model: "", effort: "", keep_hooks: true });
    expect(card("codex").queryByTestId("coding-agent-hooks")).toBeNull();
  });
});
