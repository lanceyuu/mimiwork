import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReferencesView } from "./ReferencesView";
import type { RefCheck, RefEntry } from "../api";

// The References tab (spec 2026-11-07): nothing runs before a click, and a fix Mimi
// cannot write safely is shown for the researcher to copy.

const check = vi.fn();
const apply = vi.fn();
const open = vi.fn();
vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return { ...actual, checkReferences: (...a: unknown[]) => check(...a), applyReferenceFixes: (...a: unknown[]) => apply(...a) };
});
vi.mock("../tauri", async () => ({ ...(await vi.importActual<Record<string, unknown>>("../tauri")), openExternal: (u: string) => open(u) }));

const row = (over: Partial<RefEntry>): RefEntry => ({
  id: "e1",
  paragraph: 1,
  text: "Baumiester, R. (1998). Ego depletion. JPSP.",
  title: "Ego depletion",
  group: "verified",
  codes: [],
  record: { doi: "10.1000/a", title: "Ego depletion", link: "https://doi.org/10.1000/a" },
  fixes: [],
  suggestions: [],
  layout: false,
  ...over,
});

const RESULT: RefCheck = {
  ok: true,
  hash: "h1",
  checked_at: Date.UTC(2026, 10, 7, 12) / 1000,
  kind: "docx",
  managed: null,
  unread: 0,
  not_checked: 0,
  counts: { total: 4, verified: 1, fix: 1, not_found: 1, retracted: 1, couldnt: 0 },
  entries: [
    row({ id: "v", group: "verified", codes: [{ code: "year_differs", params: { years: [1999] } }] }),
    row({
      id: "f",
      group: "fix",
      codes: [{ code: "surname_differs", params: { surname: "Baumeister" } }],
      fixes: [
        { id: "f.replace_surname", kind: "replace_surname", new: "Baumeister", after: "Baumeister, R. (1998).", writable: true, ticked: true },
        { id: "f.add_doi", kind: "add_doi", new: " https://doi.org/10.1000/a", after: "… https://doi.org/10.1000/a", writable: false, ticked: false },
      ],
    }),
    row({ id: "n", group: "not_found", codes: [{ code: "not_found", params: {} }], record: null, title: "A lost paper" }),
    row({ id: "r", group: "retracted", codes: [{ code: "retracted", params: { year: 2010, notice: "10.1000/n", via: "crossref" } }] }),
  ],
};

beforeEach(() => {
  check.mockReset();
  apply.mockReset();
  open.mockReset();
});
afterEach(cleanup);

const view = (isWord = true, onWritten = vi.fn()) =>
  render(<ReferencesView sessionId="s1" path="paper.docx" isWord={isWord} onWritten={onWritten} />);

describe("the References tab", () => {
  it("offers a check without running one when the file has no saved result", async () => {
    check.mockResolvedValue({ ok: false, cached: false });
    view();
    expect(await screen.findByRole("button", { name: "Check references" })).toBeTruthy();
    expect(check).toHaveBeenCalledTimes(1);
    expect(check.mock.calls[0]).toEqual(["s1", "paper.docx", { cachedOnly: true }]);
  });

  it("shows a saved result with its date and the groups in order", async () => {
    check.mockResolvedValue(RESULT);
    view();
    expect(await screen.findByText(/Checked on 7 November 2026/)).toBeTruthy();
    const groups = Array.from(document.querySelectorAll("[data-testid^='refs-group-']")).map((g) => g.getAttribute("data-testid"));
    expect(groups).toEqual(["refs-group-retracted", "refs-group-fix", "refs-group-not_found", "refs-group-verified"]);
    expect(screen.getByText("4 references: 1 verified, 1 needs a fix, 1 not found, 1 retracted.")).toBeTruthy();
  });

  it("keeps verified entries folded until opened", async () => {
    check.mockResolvedValue(RESULT);
    view();
    const head = await screen.findByRole("button", { name: "Verified (1)" });
    expect(screen.queryByText(/often a preprint/)).toBeNull();
    fireEvent.click(head);
    expect(screen.getByText(/often a preprint/)).toBeTruthy();
  });

  it("ticks what Mimi can write and offers Copy for the rest", async () => {
    check.mockResolvedValue(RESULT);
    view();
    const box = (await screen.findByLabelText("Change the surname to Baumeister")) as HTMLInputElement;
    expect(box.checked).toBe(true);
    expect(screen.getByText("… https://doi.org/10.1000/a")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Copy" }).length).toBeGreaterThan(0);
  });

  it("sends only the ticked, writable fixes and reloads the preview", async () => {
    check.mockResolvedValue(RESULT);
    apply.mockResolvedValue({ ok: true, applied: 1 });
    const onWritten = vi.fn();
    view(true, onWritten);
    fireEvent.click(await screen.findByRole("button", { name: "Write 1 fix into the Word file" }));
    await waitFor(() => expect(apply).toHaveBeenCalledWith("s1", "paper.docx", "h1", ["f.replace_surname"]));
    expect(await screen.findByText(/1 fix written as tracked changes/)).toBeTruthy();
    expect(onWritten).toHaveBeenCalled();
  });

  it("says why a write was refused", async () => {
    check.mockResolvedValue(RESULT);
    apply.mockResolvedValue({ ok: false, error: "changed" });
    view();
    fireEvent.click(await screen.findByRole("button", { name: "Write 1 fix into the Word file" }));
    expect(await screen.findByText("The file changed since the check. Check again.")).toBeTruthy();
    apply.mockResolvedValue({ ok: false, error: "busy" });
    fireEvent.click(screen.getByRole("button", { name: "Write 1 fix into the Word file" }));
    expect(await screen.findByText("Wait until Mimi has finished, then try again.")).toBeTruthy();
  });

  it("sends a list made by a citation tool back to that tool, with no Write button", async () => {
    check.mockResolvedValue({ ...RESULT, managed: "Zotero" });
    view();
    expect(await screen.findByText("This list is made by Zotero. Fix the entries in Zotero, then refresh the bibliography in Word.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Write/ })).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("gives a PDF suggestions only", async () => {
    check.mockResolvedValue({ ...RESULT, kind: "pdf" });
    view(false);
    await screen.findByText(/Checked on/);
    expect(screen.queryByRole("button", { name: /Write/ })).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("links a not-found entry to Google Scholar and never calls it fake", async () => {
    check.mockResolvedValue(RESULT);
    view();
    fireEvent.click(await screen.findByRole("button", { name: "Search Google Scholar" }));
    expect(open).toHaveBeenCalledWith("https://scholar.google.com/scholar?q=A%20lost%20paper");
    expect(document.body.textContent).not.toMatch(/fake/i);
  });

  it("runs a fresh check on Check again and shows a failed read plainly", async () => {
    check.mockResolvedValueOnce(RESULT).mockResolvedValueOnce({ ok: false, error: "read_failed" });
    view();
    fireEvent.click(await screen.findByRole("button", { name: "Check again" }));
    await waitFor(() => expect(check).toHaveBeenLastCalledWith("s1", "paper.docx", { fresh: true }));
    expect(await screen.findByText("Couldn't read the reference list. Try again.")).toBeTruthy();
  });
});
