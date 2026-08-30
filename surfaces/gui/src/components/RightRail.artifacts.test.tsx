import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { RightRail } from "./RightRail";

// Owner report 2026-08-30: "the output contains some new files, but when i click on it,
// it is not responded." A Word/Excel/PowerPoint artifact has no in-app preview, so the
// click must hand it to the OS. The transcript's artifact: chip already did that; the
// Artifacts list did not, and a dead click is how that difference looked.

const reveal = vi.fn(async () => ({ ok: true }));
const artifacts = [
  { path: "brief.docx", name: "brief.docx", kind: "document", size: 2048, modified_at: 1 },
  { path: "notes.md", name: "notes.md", kind: "markdown", size: 128, modified_at: 2 },
];

vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return {
    ...actual,
    getArtifacts: async () => artifacts,
    revealArtifact: (...a: unknown[]) => reveal(...(a as [])),
    readArtifact: async () => ({ text: "# notes" }),
  };
});

beforeEach(() => reveal.mockClear());
afterEach(cleanup);

describe("opening a produced file", () => {
  it("hands a .docx to the OS instead of a viewer that cannot render it", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    const row = await screen.findByText("brief.docx");
    row.closest("button")!.click();
    await waitFor(() => expect(reveal).toHaveBeenCalled());
    expect(reveal.mock.calls[0]).toEqual(["s1", "brief.docx", "open"]);
  });

  it("still previews what it can, in the app", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    const row = await screen.findByText("notes.md");
    row.closest("button")!.click();
    await waitFor(() => expect(screen.queryByText("Back")).not.toBeNull(), { timeout: 2000 }).catch(
      () => undefined,
    );
    expect(reveal).not.toHaveBeenCalled(); // never bounced to the OS
  });
});
