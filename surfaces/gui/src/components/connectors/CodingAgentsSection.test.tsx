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
  model: "",
  effort: "",
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
    expect(claude.getByPlaceholderText("Default: opus")).toBeTruthy();
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

  it("choosing an effort and a model saves them for that agent", async () => {
    const calls = stubFetch([
      { match: "/settings", method: "POST", json: { ok: true, model: "haiku", effort: "low" } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    const claude = await waitFor(() => card("claude_code"));
    fireEvent.change(claude.getByTestId("coding-agent-effort"), { target: { value: "low" } });
    const model = claude.getByTestId("coding-agent-model");
    fireEvent.change(model, { target: { value: "haiku" } });
    fireEvent.blur(model);

    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/claude_code/settings")).length).toBe(2));
    const saved = calls.filter((c) => c.url.endsWith("/claude_code/settings")).map((c) => c.body);
    expect(saved[0]).toEqual({ model: "", effort: "low" });
    expect(saved[1].model).toBe("haiku");
  });

  it("the Test button reports how long the real call took, or the error in plain words", async () => {
    stubFetch([
      { match: "/claude_code/test", method: "POST", json: { ok: true, reply: "OK", seconds: 6.2 } },
      { match: "/v1/coding-agents", json: { agents: [CLAUDE] } },
    ]);
    render(<CodingAgentsSection />);

    fireEvent.click(await waitFor(() => card("claude_code").getByTestId("coding-agent-test")));

    await waitFor(() =>
      expect(card("claude_code").getByTestId("coding-agent-test-result").textContent).toBe("It answered in 6.2 seconds."),
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
});
