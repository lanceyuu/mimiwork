// Drawing a picture (owner ask 2026-09-29): the transcript and the approval card name the
// action and the file, never the tool.
import { describe, expect, it } from "vitest";
import { humanizeApprovalTitle, humanizeTool } from "./humanize";

describe("generate_image in plain language", () => {
  it("says which picture was drawn", () => {
    expect(humanizeTool("generate_image", { prompt: "a dog", output: "figures/dog-ad.png" })).toEqual({
      pre: "Drew ",
      obj: "dog-ad.png",
    });
  });

  it("asks before drawing, naming the file", () => {
    expect(humanizeApprovalTitle("generate_image", { prompt: "a dog", output: "figures/dog-ad.png" })).toEqual({
      pre: "Draw a picture — ",
      obj: "dog-ad.png",
    });
  });

  it("stays safe on missing args", () => {
    expect(humanizeTool("generate_image", null)).toEqual({ pre: "Drew ", obj: "a picture" });
    expect(humanizeApprovalTitle("generate_image", {})).toEqual({ pre: "Draw a picture" });
  });
});
