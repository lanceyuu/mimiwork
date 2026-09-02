/** The bridge: an app's `Mimi.ask` becomes one sidecar call, answered back into the
 *  frame; anything malformed or from elsewhere is ignored; the frame is never
 *  same-origin. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

afterEach(cleanup);

const askApp = vi.fn(async () => ({ ok: true, text: "Bonjour" }));
const setAppState = vi.fn(async () => ({ ok: true }));
vi.mock("../api", () => ({
  askApp: (...a: unknown[]) => askApp(...(a as [])),
  getAppState: async () => ({ tone: "warm" }),
  setAppState: (...a: unknown[]) => setAppState(...(a as [])),
}));

import { AppFrame, frameDocument } from "./AppFrame";

const APP = { id: "app-0000aaaa", title: "Translator" };

function post(win: Window, data: unknown, source: Window | null = win) {
  window.dispatchEvent(new MessageEvent("message", { data, source: source as any }));
}

describe("AppFrame", () => {
  it("sandboxes the app with scripts only — never same-origin, never network", () => {
    render(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" />);
    const frame = screen.getByTestId("app-frame") as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    const doc = frameDocument(APP, "<html><head></head><body>hi</body></html>");
    expect(doc).toContain("Content-Security-Policy");
    expect(doc).toContain("connect-src 'none'");
    expect(doc).toContain('"id":"app-0000aaaa"');
    // The bridge lands inside <head> when there is one, at the top otherwise.
    expect(doc.indexOf("<head>")).toBeLessThan(doc.indexOf("window.Mimi"));
    expect(frameDocument(APP, "<p>bare</p>").startsWith("<meta")).toBe(true);
  });

  it("answers an ask from the frame with the model's text", async () => {
    render(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" />);
    const frame = screen.getByTestId("app-frame") as HTMLIFrameElement;
    const win = frame.contentWindow!;
    const reply = vi.spyOn(win, "postMessage");
    post(win, { mimi: 1, id: 7, kind: "ask", payload: { prompt: "hello", system: "" } });
    await waitFor(() => expect(reply).toHaveBeenCalled());
    expect(askApp).toHaveBeenCalledWith("app-0000aaaa", "hello", "");
    expect(reply.mock.calls[0][0]).toEqual({ mimi: 1, id: 7, result: "Bonjour" });
  });

  it("ignores messages that are not from its own frame, or not the bridge's shape", async () => {
    render(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" />);
    const frame = screen.getByTestId("app-frame") as HTMLIFrameElement;
    const win = frame.contentWindow!;
    const reply = vi.spyOn(win, "postMessage");
    askApp.mockClear();
    post(win, { mimi: 1, id: 1, kind: "ask", payload: { prompt: "x" } }, window);
    post(win, { mimi: 1, id: 2, kind: "delete-everything", payload: {} });
    post(win, "nonsense");
    await new Promise((r) => setTimeout(r, 20));
    expect(askApp).not.toHaveBeenCalled();
    expect(reply).not.toHaveBeenCalled();
  });

  it("state must be an object; a list is refused before it reaches the sidecar", async () => {
    render(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" />);
    const win = (screen.getByTestId("app-frame") as HTMLIFrameElement).contentWindow!;
    const reply = vi.spyOn(win, "postMessage");
    post(win, { mimi: 1, id: 3, kind: "state.set", payload: { value: [1, 2] } });
    await waitFor(() => expect(reply).toHaveBeenCalled());
    expect(reply.mock.calls[0][0]).toMatchObject({ id: 3, error: "state must be an object" });
    expect(setAppState).not.toHaveBeenCalled();
    post(win, { mimi: 1, id: 4, kind: "state.get", payload: {} });
    await waitFor(() => expect(reply).toHaveBeenCalledTimes(2));
    expect(reply.mock.calls[1][0]).toEqual({ mimi: 1, id: 4, result: { tone: "warm" } });
  });
});


describe("AppFrame — the creator's log and suggestion chips", () => {
  it("reports every ask the app makes, with timing and the reply", async () => {
    const onAsk = vi.fn();
    render(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" onAsk={onAsk} />);
    const win = (screen.getByTestId("app-frame") as HTMLIFrameElement).contentWindow!;
    post(win, { mimi: 1, id: 9, kind: "ask", payload: { prompt: "hello", system: "be brief" } });
    await waitFor(() => expect(onAsk).toHaveBeenCalled());
    const entry = onAsk.mock.calls[0][0];
    expect(entry).toMatchObject({ prompt: "hello", system: "be brief", reply: "Bonjour" });
    expect(typeof entry.ms).toBe("number");
  });

  it("delivers a clicked suggestion into the page", () => {
    const { rerender } = render(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" suggestion={null} />);
    const win = (screen.getByTestId("app-frame") as HTMLIFrameElement).contentWindow!;
    const into = vi.spyOn(win, "postMessage");
    rerender(<AppFrame app={APP} html="<html><head></head><body>hi</body></html>" suggestion={{ text: "Into French", nonce: 1 }} />);
    expect(into).toHaveBeenCalledWith({ mimi: 1, kind: "suggestion", text: "Into French" }, "*");
    // The bridge inside the page knows the shape and offers Mimi.onSuggestion.
    expect(frameDocument(APP, "<html><head></head></html>")).toContain("onSuggestion");
  });
});
