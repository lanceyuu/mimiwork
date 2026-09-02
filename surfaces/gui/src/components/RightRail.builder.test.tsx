/** Building an app: the conversation on the left, the app running on the right. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RightRail } from "./RightRail";

const APP = {
  id: "app-0000bbbb", title: "Translator", icon: "🌐", description: "", model: null,
  builder_session: "s-build", asks: 0, has_previous: true, created_at: 1, updated_at: 5,
};
const revert = vi.fn(async () => ({ ok: true, app: APP, html: "<p>old</p>" }));
vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return {
    ...actual,
    getArtifacts: async () => [],
    getRecoveryPoints: async () => [],
    getApps: async () => [APP],
    getApp: async () => ({ ok: true, app: APP, html: "<html><head></head><body>app</body></html>" }),
    revertApp: (...a: unknown[]) => revert(...(a as [])),
    askApp: vi.fn(),
    getAppState: async () => ({}),
    setAppState: vi.fn(),
  };
});
afterEach(cleanup);

describe("the builder's preview", () => {
  it("shows the app this conversation is building, wide, with undo and a way to its page", async () => {
    const onOpenApp = vi.fn();
    const onPreview = vi.fn();
    render(
      <RightRail sessionId="s-build" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onOpenApp={onOpenApp} onPreviewChange={onPreview} />,
    );
    await screen.findByTestId("app-builder");
    expect(screen.getByTestId("app-frame")).toBeTruthy();
    expect(document.querySelector(".right-rail.app-mode")).toBeTruthy();
    await waitFor(() => expect(onPreview).toHaveBeenCalledWith(true));
    fireEvent.click(screen.getByTestId("app-builder-open"));
    expect(onOpenApp).toHaveBeenCalledWith("app-0000bbbb");
    fireEvent.click(screen.getByTestId("app-builder-undo"));
    await waitFor(() => expect(revert).toHaveBeenCalledWith("app-0000bbbb"));
  });

  it("stays out of the way of conversations that build nothing", async () => {
    render(<RightRail sessionId="other" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    await screen.findByText("Progress");
    expect(screen.queryByTestId("app-builder")).toBeNull();
  });
});
