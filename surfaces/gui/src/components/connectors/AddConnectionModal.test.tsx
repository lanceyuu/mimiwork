import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Connector } from "../../api";
import { AddConnectionModal } from "./AddConnectionModal";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const notion = {
  name: "notion", title: "Notion", mcp: true, fields: [], instructions: [],
  logo: "notion", brand_color: "#1f2328", tools: [],
} as unknown as Connector;

it("shows a failed browser sign-in and enables another attempt", async () => {
  const onClose = vi.fn();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: true,
    json: async () => String(url).endsWith("/mcp-connect") ? { ok: true, started: true } : {
      connectors: [{ ...notion, connected: true, mcp_status: "needs_auth", mcp_error: "Sign-in was cancelled." }],
    },
  } as Response)));
  render(<AddConnectionModal c={notion} onChanged={vi.fn()} onClose={onClose} />);
  fireEvent.click(screen.getByTestId("modal-mcp-one-click"));
  await waitFor(() => expect(screen.getByTestId("modal-mcp-one-click").textContent).toBe("Check your browser…"));
  await waitFor(() => expect(screen.getByText("Sign-in was cancelled.")).toBeTruthy(), { timeout: 3500 });
  expect((screen.getByTestId("modal-mcp-one-click") as HTMLButtonElement).disabled).toBe(false);
  expect(onClose).not.toHaveBeenCalled();
});
