import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Tour } from "./Tour";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

function stubFetch() {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: (init?.method || "GET").toUpperCase() });
    return { ok: true, json: async () => ({ ok: true, tour_seen: true }) } as Response;
  }));
  return calls;
}

function mountTargets() {
  // The live elements the spotlights anchor to, minus the ones this test omits on purpose.
  document.body.innerHTML = `
    <textarea></textarea>
    <button>Ask for approval</button>
    <div data-testid="topbar-workspace">demo</div>
    <button data-testid="account-row">account</button>`;
}

describe("Tour", () => {
  it("walks the steps that exist and skips the ones that don't", () => {
    stubFetch();
    mountTargets(); // no access-section → the "panel" step must be skipped, not pointed at nothing
    const done = vi.fn();
    render(<Tour onDone={done} />);
    expect(screen.getByTestId("tour-step-composer")).toBeTruthy();
    expect(screen.getByText("1 / 4")).toBeTruthy(); // 5 defined, 4 present
    fireEvent.click(screen.getByTestId("tour-next"));
    expect(screen.getByTestId("tour-step-modes")).toBeTruthy();
    fireEvent.click(screen.getByTestId("tour-next"));
    fireEvent.click(screen.getByTestId("tour-next"));
    expect(screen.getByTestId("tour-step-menu")).toBeTruthy();
    fireEvent.click(screen.getByTestId("tour-next")); // "Done"
    expect(done).toHaveBeenCalled();
  });

  it("finishing marks tour_seen on the server", () => {
    const calls = stubFetch();
    mountTargets();
    render(<Tour onDone={() => undefined} />);
    fireEvent.click(screen.getByTestId("tour-skip"));
    expect(calls.some((c) => c.url.includes("/v1/settings/tour-seen") && c.method === "POST")).toBe(true);
  });

  it("renders nothing when no targets exist (never a black screen)", () => {
    stubFetch();
    const { container } = render(<Tour onDone={() => undefined} />);
    expect(container.querySelector('[data-testid="tour"]')).toBeNull();
  });
});
