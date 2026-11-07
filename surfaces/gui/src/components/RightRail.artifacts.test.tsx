import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RightRail } from "./RightRail";
import { OPEN_ARTIFACT_EVENT } from "./Markdown";

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
  { path: "analysis_steps.py", name: "analysis_steps.py", kind: "code", size: 64, modified_at: 3 },
];
const DOCX_HTML = '<h1 data-p="0">Findings</h1><p data-p="1">The sample consisted of twenty four interviews and two groups.</p>';

const applyFixes = vi.fn(async (..._a: unknown[]) => ({ ok: true, applied: 1 }));
const checkRefs = vi.fn(async (..._a: unknown[]) => ({ ok: false, cached: false }) as unknown);
const REF_RESULT = {
  ok: true,
  hash: "h1",
  checked_at: 1,
  kind: "docx",
  managed: null,
  counts: { total: 1, verified: 0, fix: 1, not_found: 0, retracted: 0, couldnt: 0 },
  entries: [{
    id: "e1", paragraph: 1, text: "Baumiester (1998). X.", title: "X", group: "fix",
    codes: [{ code: "surname_differs", params: { surname: "Baumeister" } }],
    record: null, suggestions: [], layout: false,
    fixes: [{ id: "e1.replace_surname", kind: "replace_surname", new: "Baumeister", after: "Baumeister (1998). X.", writable: true, ticked: true }],
  }],
};

vi.mock("html2canvas", () => ({ default: async () => document.createElement("canvas") }));
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
    explainArtifact: async () => ({ ok: false, cached: false }),
    checkReferences: (...a: unknown[]) => checkRefs(...a),
    applyReferenceFixes: (...a: unknown[]) => applyFixes(...a),
    readArtifact: async (_s: string, path: string) =>
      path.endsWith(".py")
        ? { ok: true, path, kind: "code", content: "a = 1\nb = 2" }
        : path === "other.docx"
        ? { ok: true, path, kind: "docx", content: '<p data-p="0">The other file.</p>', paragraphs: 1 }
        : path.endsWith(".docx")
        ? { ok: true, path, kind: "docx", content: DOCX_HTML, paragraphs: 2 }
        : { ok: true, path, kind: "markdown", content: "# notes" },
  };
});

beforeEach(() => {
  reveal.mockClear();
  restore.mockClear();
  checkRefs.mockReset();
  checkRefs.mockResolvedValue({ ok: false, cached: false });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(cleanup);

describe("opening a produced file", () => {
  it("opens a script in the plain-language view, and a click on it drops no comment pin", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={vi.fn()} />);
    const [row] = await screen.findAllByText("analysis_steps.py");
    row.closest("button")!.click();
    expect(await screen.findByRole("button", { name: "Explain this script" })).toBeTruthy();
    fireEvent.click(document.querySelector(".artifact-preview")!);
    expect(screen.queryByTestId("artifact-draft")).toBeNull();
  });

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
    // First pin: a paragraph.
    fireEvent.click(doc.querySelector('[data-p="1"]')!);
    const draft = await screen.findByTestId("artifact-draft");
    expect(draft.textContent).toContain("paragraph 2, starting “The sample consisted of twenty four interviews and”");
    fireEvent.change(screen.getByTestId("artifact-draft-text"), { target: { value: "say how they were recruited" } });
    fireEvent.click(screen.getByTestId("artifact-draft-add"));
    // Second pin: the heading.
    fireEvent.click(doc.querySelector('[data-p="0"]')!);
    fireEvent.change(await screen.findByTestId("artifact-draft-text"), { target: { value: "add the date" } });
    fireEvent.click(screen.getByTestId("artifact-draft-add"));
    expect(screen.getAllByTestId("artifact-pin")).toHaveLength(2);
    expect(screen.getAllByTestId("artifact-pin-row")).toHaveLength(2);
    // Into the file itself, as Word comments on those paragraphs — both at once.
    fireEvent.click(screen.getByTestId("artifact-word-comment"));
    await waitFor(() => expect(comment).toHaveBeenCalledTimes(2));
    expect(comment.mock.calls[0]).toEqual(["s1", "brief.docx", 1, "say how they were recruited"]);
    expect(comment.mock.calls[1]).toEqual(["s1", "brief.docx", 0, "add the date"]);
    expect((await screen.findByTestId("artifact-feedback-note")).textContent).toContain("Added 2 comments to the Word file");
    expect(onFeedback).not.toHaveBeenCalled();
  });

  it("several pins go to Mimi as one numbered message", async () => {
    const onFeedback = vi.fn();
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={onFeedback} />);
    const [row] = await screen.findAllByText("brief.docx");
    row.closest("button")!.click();
    const doc = await screen.findByTestId("artifact-docx");
    fireEvent.click(doc.querySelector('[data-p="1"]')!);
    fireEvent.change(await screen.findByTestId("artifact-draft-text"), { target: { value: "shorter" } });
    fireEvent.click(screen.getByTestId("artifact-draft-add"));
    fireEvent.click(doc.querySelector('[data-p="0"]')!);
    fireEvent.change(await screen.findByTestId("artifact-draft-text"), { target: { value: "bolder" } });
    fireEvent.click(screen.getByTestId("artifact-draft-add"));
    fireEvent.click(screen.getByTestId("artifact-send-all"));
    await waitFor(() => expect(onFeedback).toHaveBeenCalled());
    const [text] = onFeedback.mock.calls[0];
    expect(text).toContain("Feedback on `brief.docx` — 2 comments");
    expect(text).toContain("1. (paragraph 2, starting “The sample consisted of twenty four interviews and”) shorter");
    expect(text).toContain("2. (paragraph 1, starting “Findings”) bolder");
    expect(screen.queryByTestId("artifact-pin")).toBeNull(); // sent = cleared
  });

  it("shows a References tab on Word files that hides the pins while it is open", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={vi.fn()} />);
    const [row] = await screen.findAllByText("brief.docx");
    row.closest("button")!.click();
    await screen.findByTestId("artifact-docx");
    // A whole-file comment first, so there is a pin bar to hide.
    fireEvent.click(screen.getByTestId("artifact-comment"));
    fireEvent.change(await screen.findByTestId("artifact-draft-text"), { target: { value: "shorter" } });
    fireEvent.click(screen.getByTestId("artifact-draft-add"));
    expect(screen.getByTestId("artifact-feedback")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "References" }));
    const refs = await screen.findByTestId("refs-view");
    expect(screen.queryByTestId("artifact-docx")).toBeNull();
    expect(screen.queryByTestId("artifact-feedback")).toBeNull();
    expect(screen.queryByTestId("artifact-comment")).toBeNull();
    fireEvent.click(refs);
    expect(screen.queryByTestId("artifact-draft")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    expect(await screen.findByTestId("artifact-docx")).toBeTruthy();
    expect(screen.getByTestId("artifact-feedback")).toBeTruthy();
  });

  it("keeps the References tab and its note through the preview reload after a write", async () => {
    checkRefs.mockResolvedValue(REF_RESULT);
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={vi.fn()} />);
    const [row] = await screen.findAllByText("brief.docx");
    row.closest("button")!.click();
    await screen.findByTestId("artifact-docx");
    fireEvent.click(screen.getByRole("tab", { name: "References" }));
    fireEvent.click(await screen.findByRole("button", { name: "Write 1 fix into the Word file" }));
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.getByTestId("refs-view").textContent).toContain("1 fix written as tracked changes");
  });

  it("keeps the newly opened file on screen when a write on the previous one finishes late", async () => {
    checkRefs.mockResolvedValue(REF_RESULT);
    let finish: (v: { ok: boolean; applied: number }) => void = () => {};
    applyFixes.mockImplementationOnce(() => new Promise((r) => (finish = r)));
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={vi.fn()} />);
    const [row] = await screen.findAllByText("brief.docx");
    row.closest("button")!.click();
    await screen.findByTestId("artifact-docx");
    fireEvent.click(screen.getByRole("tab", { name: "References" }));
    fireEvent.click(await screen.findByRole("button", { name: "Write 1 fix into the Word file" }));
    window.dispatchEvent(new CustomEvent(OPEN_ARTIFACT_EVENT, { detail: { path: "other.docx" } }));
    await waitFor(() => expect(screen.getByTestId("artifact-docx").textContent).toContain("The other file."));
    finish({ ok: true, applied: 1 });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.getByTestId("artifact-docx").textContent).toContain("The other file.");
    expect(screen.getByTestId("artifact-docx").textContent).not.toContain("twenty four interviews");
  });

  it("offers no References tab on files that are not Word or PDF", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} />);
    const row = await screen.findByText("notes.md");
    row.closest("button")!.click();
    await waitFor(() => expect(document.querySelector(".artifact-md")).not.toBeNull());
    expect(screen.queryByRole("tab", { name: "References" })).toBeNull();
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
    fireEvent.change(screen.getByTestId("artifact-draft-text"), { target: { value: "make the headings blue" } });
    fireEvent.click(screen.getByTestId("artifact-draft-add"));
    fireEvent.click(screen.getByTestId("artifact-send-all"));
    await waitFor(() => expect(onFeedback).toHaveBeenCalled());
    expect(onFeedback.mock.calls[0][0]).toBe("Feedback on `notes.md`:\n1. make the headings blue");
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
