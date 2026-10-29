// Models tab: a failed settings request is named and retriable — never an endless
// "Loading…" (Windows field report 2026-09-07: /v1/settings answered 500 and the page
// sat on the spinner text for good).
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { McpTab, ModelsTab } from "./ManageTabs";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MCP browser connections", () => {
  it("offers Connect for a configured OAuth server with saved credentials", async () => {
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      requests.push(String(url));
      return { ok: true, json: async () => String(url).endsWith("/connect") ? { ok: true, started: true } : {
        servers: [{ name: "notion", auth: "oauth", status: "configured", enabled: true,
          transport: "http", requires_approval: true, tool_count: null, config: {} }],
      } } as Response;
    }));
    render(<McpTab />);
    const connect = await screen.findByTestId("mcp-signin-notion");
    expect(connect.textContent).toBe("Connect");
    fireEvent.click(connect);
    await waitFor(() => expect(requests.some((url) => url.endsWith("/v1/mcp/notion/connect"))).toBe(true));
    expect(screen.getByText(/tools load with your next message/)).toBeTruthy();
  });
});

describe("ModelsTab load failure", () => {
  it("shows the server's answer and a Retry that asks again", async () => {
    let settingsCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/settings")) {
          settingsCalls += 1;
          return { ok: false, status: 500, text: async () => "Internal Server Error", json: async () => ({}) } as Response;
        }
        return { ok: true, status: 200, json: async () => [] } as Response;
      }),
    );
    render(<ModelsTab />);
    const err = await screen.findByTestId("models-load-error");
    expect(err.textContent).toContain("HTTP 500 Internal Server Error");
    fireEvent.click(screen.getByText("Retry"));
    await waitFor(() => expect(settingsCalls).toBe(2));
  });
});

// The QualiTaTi card is the app's only sign-in form, so it must survive a dead sidecar:
// hiding it behind the settings fetch left a signed-out user with no way to sign in at
// all (user report 2026-10-16 - "I don't see anywhere to log in").
describe("ModelsTab with the sidecar unreachable", () => {
  it("still shows the QualiTaTi sign-in form", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    render(<ModelsTab />);
    expect(await screen.findByTestId("qualitati-card")).toBeTruthy();
    expect(await screen.findByTestId("qualitati-username")).toBeTruthy();
    expect(screen.getByTestId("qualitati-password")).toBeTruthy();
  });
});
