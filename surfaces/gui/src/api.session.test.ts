import { afterEach, expect, it, vi } from "vitest";
import { Session } from "./api";

class Socket {
  static CONNECTING = 0;
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 0;
  onmessage: ((event: { data: string }) => void) | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = 3; this.onclose?.(); });
  constructor() { Socket.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  receive(type: string, data: object) { this.onmessage?.({ data: JSON.stringify({ type, data }) }); }
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); Socket.instances = []; });

it("a silent socket reconnects without replaying a sent user request", () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", Socket);
  const onClose = vi.fn();
  const session = new Session("s1", "", "cowork", { onEvent: vi.fn(), onClose });
  const socket = Socket.instances[0];
  socket.open();
  session.userMessage("do it once");
  vi.advanceTimersByTime(25_000);
  expect(onClose).toHaveBeenCalledOnce();
  vi.advanceTimersByTime(1500);
  const next = Socket.instances[1];
  next.open();
  expect(next.send).not.toHaveBeenCalled();
  session.close();
  vi.advanceTimersByTime(30_000);
  expect(Socket.instances).toHaveLength(2);
});

it("force stop uses authenticated HTTP and targets the current task even with a broken socket", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("__COWORKER_API_TOKEN__", "test-token");
  const request = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }));
  vi.stubGlobal("fetch", request);
  const session = new Session("s1", "", "cowork", { onEvent: vi.fn() });
  const socket = Socket.instances[0];
  socket.open();
  socket.receive("turn_start", { running_since: 123.456 });
  socket.close();
  await session.interrupt(true);
  const [url, init] = request.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toContain("/s1/interrupt?force=true&running_since=123.456");
  expect(new Headers(init.headers).get("X-OpenWorker-Token")).toBe("test-token");
  session.close();
});
