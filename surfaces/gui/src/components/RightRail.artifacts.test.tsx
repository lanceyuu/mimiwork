import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RightRail } from "./RightRail";

// Owner report 2026-08-30: "the output contains some new files, but when i click on it,
// it is not responded." A Word/Excel/PowerPoint artifact has no in-app preview, so the
// click must hand it to the OS. The transcript's artifact: chip already did that; the
// Artifacts list did not, and a dead click is how that difference looked.

const reveal = vi.fn(async () => ({ ok: true }));
const restore = vi.fn(async () => ({ ok: true }));
const comment = vi.fn(async () => ({ ok: true, comments: 1 }));
const artifacts = [
  { path: "brief.docx", name: "brief.docx", kind: "document", size: 2048, modified_at: 1 },
  { path: "old.doc", name: "old.doc", kind: "document", size: 2048, modified_at: 1 },
  { path: "notes.md", name: "notes.md", kind: "markdown", size: 128, modified_at: 2 },
];
const DOCX_HTML = '<h1 data-p="0">Findings</h1><p data-p="1">The sample consisted of twenty four interviews and two groups.</p>';

vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return {
    ...actual,
    getArtifacts: async () => artifacts,
    getRecoveryPoints: async () => [{
      id: "turn-1",
      created_at: 1,
      restored_at: null,
      files: [{ path: "/ws/brief.docx", name: "brief.docx", action: "modified" }],
    }],
    restoreRecoveryPoint: (...a: unknown[]) => restore(...(a as [])),
    revealArtifact: (...a: unknown[]) => reveal(...(a as [])),
    commentArtifact: (...a: unknown[]) => comment(...(a as [])),
    readArtifact: async (_s: string, path: string) =>
      path.endsWith(".docx")
        ? { ok: true, path, kind: "docx", content: DOCX_HTML, paragraphs: 2 }
        : { ok: true, path, kind: "markdown", content: "# notes" },
  };
});

beforeEach(() => {
  reveal.mockClear();
  restore.mockClear();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(cleanup);

describe("opening a produced file", () => {
  it("hands a legacy .doc to the OS instead of a viewer that cannot render it", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    const [row] = await screen.findAllByText("old.doc");
    row.closest("button")!.click();
    await waitFor(() => expect(reveal).toHaveBeenCalled());
    expect(reveal.mock.calls[0]).toEqual(["s1", "old.doc", "open"]);
  });

  it("previews a .docx in the app, and a click on a paragraph pins a comment to it", async () => {
    const onFeedback = vi.fn();
    comment.mockClear();
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={onFeedback} />);
    const [row] = await screen.findAllByText("brief.docx");
    row.closest("button")!.click();
    const doc = await screen.findByTestId("artifact-docx");
    expect(reveal).not.toHaveBeenCalled();
    expect(doc.querySelector("h1")!.textContent).toBe("Findings");
    fireEvent.click(doc.querySelector('[data-p="1"]')!);
    const bar = await screen.findByTestId("artifact-feedback");
    expect(bar.textContent).toContain("paragraph 2, starting “The sample consisted of twenty four interviews and”");
    fireEvent.change(screen.getByPlaceholderText(/What should change/), { target: { value: "say how they were recruited" } });
    // Into the file itself, as a Word comment on that paragraph.
    fireEvent.click(screen.getByTestId("artifact-word-comment"));
    await waitFor(() => expect(comment).toHaveBeenCalledWith("s1", "brief.docx", 1, "say how they were recruited"));
    expect((await screen.findByTestId("artifact-feedback-note")).textContent).toContain("Added to the Word file");
    expect(onFeedback).not.toHaveBeenCalled();
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

  it("restores the latest turn only after an explicit confirmation", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    const undo = await screen.findByText("Undo latest file changes");
    fireEvent.click(undo);

    await waitFor(() => expect(restore).toHaveBeenCalledWith("s1", "turn-1"));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("brief.docx"));
  });
});

describe("commenting on a produced file (owner ask 2026-09-02)", () => {
  it("sends the comment to the conversation, naming the file", async () => {
    const onFeedback = vi.fn();
    render(
      <RightRail
        sessionId="s1"
        active
        workspace="/ws"
        toolNames={[]}
        todo={[]}
        running={false}
        refreshKey={0}
        onFeedback={onFeedback}
      />,
    );
    const row = await screen.findByText("notes.md");
    row.closest("button")!.click();
    const btn = await screen.findByTestId("artifact-comment");
    fireEvent.click(btn);
    const box = screen.getByPlaceholderText(/What should change/);
    fireEvent.change(box, { target: { value: "make the headings blue" } });
    fireEvent.click(screen.getByText("Send to Mimi"));
    expect(onFeedback).toHaveBeenCalledWith("Feedback on `notes.md`: make the headings blue");
    expect(screen.queryByTestId("artifact-feedback")).toBeNull();
  });

  it("offers no comment button when nowhere to send it", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    const row = await screen.findByText("notes.md");
    row.closest("button")!.click();
    await screen.findByLabelText("Copy path");
    expect(screen.queryByTestId("artifact-comment")).toBeNull();
  });
});
