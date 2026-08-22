/** Quickstart recipes: the research digest needs topics and lands a Monday cron. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AutomationQuickstart } from "./AutomationQuickstart";

vi.mock("../api", () => ({
  getConnectors: vi.fn(async () => []),
  getRecentChannels: vi.fn(async () => []),
}));

// jsdom has no scrollIntoView; the configure card calls it on pick.
Element.prototype.scrollIntoView = vi.fn();

afterEach(cleanup);

describe("AutomationQuickstart — Weekly research digest", () => {
  it("gates Create on topics and builds a Monday-08:00 digest from them", async () => {
    const onCreate = vi.fn();
    render(<AutomationQuickstart busy={false} onCreate={onCreate} />);
    fireEvent.click(await screen.findByTestId("qs-template-research"));
    await waitFor(() => expect(screen.getByTestId("ob-topics")).toBeTruthy());

    const create = screen.getByTestId("ob-create") as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    expect(screen.getByTestId("ob-create-hint").textContent).toContain("topics");

    fireEvent.change(screen.getByTestId("ob-topics"), {
      target: { value: "AI in consumer research; qualitative methods" },
    });
    expect(create.disabled).toBe(false);
    fireEvent.click(create);

    expect(onCreate).toHaveBeenCalledTimes(1);
    const payload = onCreate.mock.calls[0][0];
    expect(payload.title).toBe("Weekly research digest");
    expect(payload.cron).toBe("0 8 * * 1");
    expect(payload.instructions).toContain("AI in consumer research; qualitative methods");
    expect(payload.instructions).toContain("kb_search");
    expect(payload.instructions).toContain("Save it as the session deliverable.");
    expect(payload.permissions).toEqual([]); // read-only recipe → no grant
  });
});
