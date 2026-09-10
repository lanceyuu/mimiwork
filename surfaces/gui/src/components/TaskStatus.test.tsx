import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { TaskStatus, progressFromEvent } from "./TaskStatus";

afterEach(cleanup);

it("a heartbeat keeps the connection alive without inventing progress", () => {
  const now = Date.now();
  const progress = progressFromEvent({ phase: "model", lastActivity: now - 30_000 }, {
    type: "session_status", data: { phase: "model", last_activity_at: (now - 30_000) / 1000 },
  });
  expect(progress.lastActivity).toBe(now - 30_000);
  render(<TaskStatus running connected since={now - 30_000} progress={progress} lastReceived={now} stopping={false} />);
  expect(screen.getByText(/Connection active. No new output for/)).toBeTruthy();
  expect(screen.getByText("Waiting for the model…")).toBeTruthy();
});

it("a stale connection never claims that Mimi is still making progress", () => {
  const now = Date.now();
  render(<TaskStatus running connected since={now - 30_000} progress={{ phase: "thinking", lastActivity: now - 30_000 }} lastReceived={now - 21_000} stopping={false} />);
  expect(screen.getByText("Connection lost. Reconnecting…")).toBeTruthy();
  expect(screen.queryByText("Thinking…")).toBeNull();
});

it("a summary heartbeat cannot erase the current compaction stage", () => {
  vi.spyOn(Date, "now").mockReturnValueOnce(1000);
  const current = progressFromEvent({ phase: "model", lastActivity: 0 }, { type: "compacting", data: {} });
  expect(progressFromEvent(current, { type: "session_status", data: { phase: "compacting", last_activity_at: 1 } })).toEqual(current);
  vi.restoreAllMocks();
});
