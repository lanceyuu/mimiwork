/** The Apps section: build from a sentence, open one, ask Mimi to change it. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

afterEach(cleanup);

const APP = {
  id: "app-0000aaaa", title: "Translator", icon: "🌐", description: "Translates.", model: null,
  builder_session: "sess-9", asks: 3, created_at: 1, updated_at: 1,
};
vi.mock("../api", () => ({
  getApps: async () => [APP],
  getApp: async () => ({ ok: true, app: APP, html: "<html><head></head><body>hi</body></html>" }),
  listAppStarters: async () => [],
  getSettings: async () => ({ models: ["a:b"], model: "a:b" }),
  importApp: vi.fn(),
  updateApp: vi.fn(),
  deleteApp: vi.fn(),
  exportApp: vi.fn(),
  announceAppsChanged: vi.fn(),
  askApp: vi.fn(),
  getAppState: async () => ({}),
  setAppState: vi.fn(),
}));

import { AppsView } from "./AppsView";

describe("AppsView", () => {
  it("a sentence becomes a build request for Mimi", async () => {
    const onBuild = vi.fn();
    render(<AppsView onBuild={onBuild} />);
    fireEvent.change(await screen.findByTestId("apps-wish"), { target: { value: "a word counter" } });
    fireEvent.click(screen.getByTestId("apps-build-go"));
    expect(onBuild).toHaveBeenCalledWith("Build me an app: a word counter");
  });

  it("opening an app runs it, and a comment goes back to the session that built it", async () => {
    const onBuild = vi.fn();
    render(<AppsView onBuild={onBuild} />);
    fireEvent.click(await screen.findByTestId("app-card-app-0000aaaa"));
    await screen.findByTestId("app-frame");
    expect(screen.getByTestId("app-title").textContent).toBe("Translator");
    fireEvent.click(screen.getByTestId("app-improve"));
    fireEvent.change(screen.getByTestId("app-note-text"), { target: { value: "add a copy button" } });
    fireEvent.click(screen.getByTestId("app-note-submit"));
    await waitFor(() => expect(onBuild).toHaveBeenCalled());
    const [prompt, session] = onBuild.mock.calls[0];
    expect(prompt).toContain("Change the app Translator (id app-0000aaaa): add a copy button");
    expect(prompt).toContain("<body>hi</body>"); // the current file rides along
    expect(session).toBe("sess-9");
  });
});
