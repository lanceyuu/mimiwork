import { afterEach, describe, expect, it, vi } from "vitest";
import { alertUser, DEFAULT_ALERTS, setAlertPrefs } from "./alerts";

const shown: string[] = [];
class FakeNotification {
  static permission = "granted";
  static requestPermission = async () => "granted";
  constructor(title: string) {
    shown.push(title);
  }
}
vi.stubGlobal("Notification", FakeNotification);

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("alerts", () => {
  afterEach(() => {
    shown.length = 0;
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stays quiet while the user is looking at the window", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(true);
    alertUser("done", "Mimi finished", "body");
    await flush();
    expect(shown).toEqual([]);
  });

  it("notifies when the window is in the background", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(false);
    alertUser("done", "Mimi finished", "body");
    await flush();
    expect(shown).toEqual(["Mimi finished"]);
  });

  it("respects an event the user turned off, except for the test button", async () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(false);
    setAlertPrefs({ ...DEFAULT_ALERTS, attention: false });
    alertUser("attention", "Mimi needs you", "body");
    await flush();
    expect(shown).toEqual([]);
    alertUser("attention", "Mimi needs you", "body", true);
    await flush();
    expect(shown).toEqual(["Mimi needs you"]);
  });
});

describe("text size", () => {
  it("drives the desktop webview's zoom", async () => {
    const setZoom = vi.fn(async () => undefined);
    vi.stubGlobal("__TAURI__", { webview: { getCurrentWebview: () => ({ setZoom }) } });
    const { setLook } = await import("./theme");
    setLook("size", "larger");
    expect(setZoom).toHaveBeenCalledWith(1.25);
    vi.unstubAllGlobals();
  });
});
