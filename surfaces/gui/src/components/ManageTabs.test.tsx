// Models tab: a failed settings request is named and retriable — never an endless
// "Loading…" (Windows field report 2026-09-07: /v1/settings answered 500 and the page
// sat on the spinner text for good).
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModelsTab } from "./ManageTabs";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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
