/** The Credits card: every section from the sidecar, the origin open first, links out. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(cleanup);
const openExternal = vi.fn();
vi.mock("../tauri", () => ({ openExternal: (...a: unknown[]) => openExternal(...(a as [])) }));
vi.mock("../api", () => ({
  getAbout: async () => ({
    version: "0.6.2",
    models: 1,
    providers: 1,
    releases: [],
    maintainer: "QualiTaTi",
    credits: [
      { title: "Where it comes from", blurb: "A fork.", items: [{ name: "OpenWorker", what: "The origin.", url: "https://github.com/andrewyng/openworker", license: "MIT" }] },
      { title: "Libraries", items: [{ name: "pdf.js", what: "PDF preview.", url: "https://mozilla.github.io/pdf.js/" }] },
    ],
  }),
}));
import { CreditsCard } from "./CreditsCard";

describe("CreditsCard", () => {
  it("shows the origin open, folds the rest, and opens a source on click", async () => {
    render(<CreditsCard card="card" label="label" />);
    await screen.findByTestId("credits-card");
    expect(screen.getByText("OpenWorker")).toBeTruthy();
    expect(screen.getByText("MIT")).toBeTruthy();
    expect(screen.queryByText("pdf.js")).toBeNull(); // folded
    fireEvent.click(screen.getByText("Libraries"));
    expect(screen.getByText("pdf.js")).toBeTruthy();
    fireEvent.click(screen.getByText("OpenWorker"));
    expect(openExternal).toHaveBeenCalledWith("https://github.com/andrewyung/openworker".replace("andrewyung", "andrewyng"));
  });
});
