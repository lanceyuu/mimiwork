import { describe, expect, it } from "vitest";
import { humanizeTool } from "./humanize";

describe("humanizeTool for the paper tools", () => {
  it("says what was searched, cited and checked in plain words", () => {
    expect(humanizeTool("find_papers", { query: "brand love" })).toEqual({ pre: "Searched for papers — ", obj: "“brand love”" });
    expect(humanizeTool("check_references", { path: "drafts/paper.docx" }).obj).toBe("paper.docx");
    expect(humanizeTool("cite_paper", null).obj).toBe("");
  });
});
