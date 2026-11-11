import { afterEach, expect, test, vi } from "vitest";
import { dragWindowFrom } from "./tauri";

afterEach(() => {
  delete (globalThis as any).__TAURI__;
});

test("a press on a panel's top strip moves the window, a press on its buttons does not", () => {
  const invoke = vi.fn().mockResolvedValue(true);
  (globalThis as any).__TAURI__ = { core: { invoke } };
  const strip = document.createElement("div");
  strip.innerHTML = "<button><svg></svg></button><span>notes.md</span>";

  dragWindowFrom({ button: 0, target: strip.querySelector("svg") });
  dragWindowFrom({ button: 2, target: strip.querySelector("span") });
  expect(invoke).not.toHaveBeenCalled();

  dragWindowFrom({ button: 0, target: strip.querySelector("span") });
  expect(invoke).toHaveBeenCalledWith("start_window_drag", undefined);
});

test("in a browser a press on the strip does nothing", () => {
  expect(() => dragWindowFrom({ button: 0, target: document.createElement("div") })).not.toThrow();
});
