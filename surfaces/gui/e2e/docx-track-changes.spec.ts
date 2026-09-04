import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "./fixtures";

// A reviewed Word file previews with its tracked changes and comments (owner ask
// 2026-09-04). data/tracked-docx.json is the sidecar's real output (office_preview.py)
// for a file with two tracked insertions, one deletion and two comments.
const PREVIEW = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "data", "tracked-docx.json"), "utf8"));

test("insertions, deletions and comments are visible in the Word preview", async ({ page }) => {
  await page.route("**/v1/sessions/*/artifacts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ artifacts: [{ path: "Findings.docx", name: "Findings.docx", kind: "document", size: 2048, modified_at: 2 }] }),
    });
  });
  await page.route("**/v1/sessions/*/artifacts/read?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, path: "Findings.docx", kind: "docx", content: PREVIEW.html, paragraphs: PREVIEW.paragraphs }),
    });
  });
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByText("Findings.docx").first().click();
  const doc = page.getByTestId("artifact-docx");
  await expect(doc.locator(".doc-changes")).toContainText("Track changes: 2 insertions, 1 deletion · 2 comments");
  await expect(doc.locator("ins.doc-ins")).toHaveCount(2);
  await expect(doc.locator("del.doc-del")).toHaveText(", though the effect was modest");
  await expect(doc.locator("sup.doc-comment").first()).toHaveAttribute("title", "Shubin Yu: Say how they were recruited and when.");
  await page.screenshot({ path: "test-results/docx-track-changes.png" });
});
