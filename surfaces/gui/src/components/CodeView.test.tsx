import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CodeView } from "./CodeView";

// The panel a non-coder uses to check an analysis (spec 2026-11-06).

const SOURCE = "import pandas as pd\ndf = pd.read_csv('survey.csv')\ndf = df[df.attention == 1]\nprint(df.mean())";
const NOTES = {
  ok: true,
  steps: [
    { start: 1, end: 2, note: "Loads the survey answers.", choice: null },
    { start: 3, end: 3, note: "Keeps only people who passed the attention check.", choice: "Dropping people who failed the check is a choice to report." },
    { start: 4, end: 4, note: "", choice: null },
  ],
  lines_explained: 4,
  truncated: false,
};
const explain = vi.fn();
vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return { ...actual, explainArtifact: (...a: unknown[]) => explain(...a) };
});

beforeEach(() => explain.mockReset());
afterEach(cleanup);

const view = (onAsk = vi.fn()) =>
  render(<CodeView sessionId="s1" path="analysis_steps.py" name="analysis_steps.py" source={SOURCE} onAsk={onAsk} />);
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

describe("the plain-language code view", () => {
  it("offers to explain a script it has no notes for, without calling the model on open", async () => {
    explain.mockResolvedValue({ ok: false, cached: false });
    view();
    expect(((await screen.findByRole("button", { name: "Explain this script" })) as HTMLButtonElement).disabled).toBe(false);
    expect(explain).toHaveBeenCalledTimes(1);
    expect(explain.mock.calls[0]).toEqual(["s1", "analysis_steps.py", true]);
  });

  it("shows saved notes at once, each above its folded code", async () => {
    explain.mockResolvedValue(NOTES);
    view();
    expect(await screen.findByText("Keeps only people who passed the attention check.")).toBeTruthy();
    expect(screen.getByText("Choice to check")).toBeTruthy();
    expect(screen.queryByText("df = df[df.attention == 1]")).toBeNull();
  });

  it("reveals a step's own lines, numbered, on Show code", async () => {
    explain.mockResolvedValue(NOTES);
    view();
    await screen.findByText("Loads the survey answers.");
    fireEvent.click(screen.getAllByRole("button", { name: /Show code/ })[1]);
    const line = screen.getByText("df = df[df.attention == 1]").closest("[data-line]")!;
    expect(line.getAttribute("data-line")).toBe("3");
  });

  it("shows every line, numbered, on the Code tab", async () => {
    explain.mockResolvedValue({ ok: false, cached: false });
    view();
    fireEvent.click(await screen.findByRole("tab", { name: "Code" }));
    expect(document.querySelectorAll("[data-line]")).toHaveLength(4);
  });

  it("disables Explain while it runs, and offers a retry when it fails", async () => {
    explain.mockResolvedValueOnce({ ok: false, cached: false });
    let finish: (v: unknown) => void = () => {};
    explain.mockReturnValueOnce(new Promise((r) => (finish = r)));
    view();
    fireEvent.click(await screen.findByRole("button", { name: "Explain this script" }));
    await waitFor(() => expect(button("Explaining…").disabled).toBe(true));
    finish({ ok: false, error: "the model could not write notes" });
    expect(await screen.findByText("Couldn't write notes for this file. Try again.")).toBeTruthy();
    expect(button("Explain this script").disabled).toBe(false);
  });

  it("sends the selected lines, with the file name, when Ask Mimi is clicked", async () => {
    explain.mockResolvedValue(NOTES);
    const onAsk = vi.fn();
    view(onAsk);
    const note = await screen.findByText("Keeps only people who passed the attention check.");
    const range = document.createRange();
    range.selectNodeContents(note);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(note);
    fireEvent.click(screen.getByRole("button", { name: /Ask Mimi about lines 3–3/ }));
    const text = onAsk.mock.calls[0][0] as string;
    expect(text).toContain("analysis_steps.py");
    expect(text).toContain("3: df = df[df.attention == 1]");
  });
});
