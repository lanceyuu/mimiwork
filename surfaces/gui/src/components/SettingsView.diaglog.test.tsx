/** "Copy diagnostic log" — the sidecar log tail lands on the clipboard so a user can paste it
 *  into a bug report, even when the sidecar is dead (Windows "Connection lost", 2026-09-20). */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const readServerLog = vi.fn(async () => "Traceback: engine exploded");
const revealServerLog = vi.fn(async () => undefined);
vi.mock("../tauri", () => ({
  isTauri: () => true,
  platformOS: () => "windows",
  readServerLog: () => readServerLog(),
  revealServerLog: () => revealServerLog(),
}));
import { DiagnosticLog } from "./SettingsView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DiagnosticLog", () => {
  it("copies the log tail with a platform header", async () => {
    const writeText = vi.fn(async (_t: string) => undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText }, userAgent: "ua" });
    render(<DiagnosticLog />);
    fireEvent.click(screen.getByTestId("settings-copy-log"));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const text = writeText.mock.calls[0][0];
    expect(text).toContain("MimiWork windows");
    expect(text).toContain("engine exploded");
    expect(screen.getByText(/paste it into your message/)).toBeTruthy();
  });

  it("opens the log's folder", () => {
    render(<DiagnosticLog />);
    fireEvent.click(screen.getByTestId("settings-show-log"));
    expect(revealServerLog).toHaveBeenCalledTimes(1);
  });
});
