import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "./fixtures";

// The References tab with a checked list (spec 2026-11-07): screenshot it so the owner can
// judge the look, not just the behaviour.
const PREVIEW = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "data", "tracked-docx.json"), "utf8"));

const entry = (id: string, group: string, text: string, codes: unknown[], extra: Record<string, unknown> = {}) => ({
  id,
  paragraph: 1,
  text,
  title: text.split(". ")[1] || text,
  group,
  codes,
  record: { doi: "10.1000/x", title: "x", link: "https://doi.org/10.1000/x" },
  fixes: [],
  suggestions: [],
  layout: false,
  ...extra,
});

const RESULT = {
  ok: true,
  hash: "h1",
  checked_at: Date.UTC(2026, 10, 7, 12) / 1000,
  kind: "docx",
  managed: null,
  unread: 0,
  not_checked: 0,
  counts: { total: 6, verified: 3, fix: 1, not_found: 1, retracted: 1, couldnt: 0 },
  entries: [
    entry("r", "retracted", "Wakefield, A. J., et al. (1998). Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children. The Lancet, 351, 637–641.", [{ code: "retracted", params: { year: 2010, notice: "10.1016/s0140-6736(10)60175-4", via: "crossref" } }]),
    entry("f", "fix", "Baumiester, R. F., Bratslavsky, E., Muraven, M., & Tice, D. M. (1998). Ego depletion: Is the active self a limited resource? JPSP, 74(5), 1252–1265.", [{ code: "surname_differs", params: { surname: "Baumeister" } }, { code: "doi_missing", params: { doi: "10.1037/0022-3514.74.5.1252" } }], {
      fixes: [
        { id: "f.replace_surname", kind: "replace_surname", new: "Baumeister", after: "", writable: true, ticked: true },
        { id: "f.add_doi", kind: "add_doi", new: " https://doi.org/10.1037/0022-3514.74.5.1252", after: "", writable: true, ticked: true },
      ],
    }),
    entry("n", "not_found", "Hansen, K. (2004). Forbrukeratferd i norske husholdninger. Oslo: Cappelen.", [{ code: "not_found", params: {} }], { record: null }),
    entry("v1", "verified", "Vaswani, A., et al. (2017). Attention is all you need. NeurIPS.", [{ code: "found_copy", params: {} }]),
    entry("v2", "verified", "Bandura, A. (1977). Self-efficacy. Psychological Review, 84, 191–215.", []),
    entry("v3", "verified", "Kahneman, D., & Tversky, A. (1979). Prospect theory. Econometrica, 47, 263–291.", []),
  ],
};

test("a researcher checks the references of a Word file", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await page.route("**/v1/sessions/*/artifacts", (r) =>
    r.fulfill({ json: { artifacts: [{ path: "Findings.docx", name: "Findings.docx", kind: "document", size: 2048, modified_at: 2 }] } }),
  );
  await page.route("**/v1/sessions/*/artifacts/read?*", (r) =>
    r.fulfill({ json: { ok: true, path: "Findings.docx", kind: "docx", content: PREVIEW.html, paragraphs: PREVIEW.paragraphs } }),
  );
  await page.route("**/v1/sessions/*/artifacts/references", async (r) => {
    const body = r.request().postDataJSON();
    await r.fulfill({ json: body.cached_only ? { ok: false, cached: false } : RESULT });
  });

  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByText("Findings.docx").first().click();
  await page.getByRole("tab", { name: "References" }).click();
  await expect(page.getByRole("button", { name: "Check references" })).toBeVisible();
  // Buttons fade their border over 0.15s app-wide; wait for the underline to land.
  await expect(page.getByRole("tab", { name: "References" })).toHaveCSS("border-bottom-color", "rgb(13, 148, 136)");
  await page.screenshot({ path: testInfo.outputPath("references-before.png") });

  await page.getByRole("button", { name: "Check references" }).click();
  await expect(page.getByText("6 references: 3 verified, 1 needs a fix, 1 not found, 1 retracted.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("references-checked.png") });
});

test("a researcher whose reference check fails can report it to the team", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await page.route("**/v1/sessions/*/artifacts", (r) =>
    r.fulfill({ json: { artifacts: [{ path: "Findings.docx", name: "Findings.docx", kind: "document", size: 2048, modified_at: 2 }] } }),
  );
  await page.route("**/v1/sessions/*/artifacts/read?*", (r) =>
    r.fulfill({ json: { ok: true, path: "Findings.docx", kind: "docx", content: PREVIEW.html, paragraphs: PREVIEW.paragraphs } }),
  );
  await page.route("**/v1/sessions/*/artifacts/references", async (r) => {
    const body = r.request().postDataJSON();
    await r.fulfill({ json: body.cached_only ? { ok: false, cached: false } : { ok: false, error: "read_failed" } });
  });
  const reports: Array<{ error: string; context: string }> = [];
  await page.route("**/v1/report", async (r) => {
    reports.push(r.request().postDataJSON());
    await r.fulfill({ json: { ok: true } });
  });

  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByText("Findings.docx").first().click();
  await page.getByRole("tab", { name: "References" }).click();
  await page.getByRole("button", { name: "Check references" }).click();
  await page.getByRole("button", { name: "Report this problem" }).click();
  await expect(page.getByText("Send this error to the QualiTaTi team?")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("references-report-confirm.png") });

  await page.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByText("Sent — thank you.")).toBeVisible();
  expect(reports).toHaveLength(1);
  expect(reports[0].context).toBe("references");
  await page.screenshot({ path: testInfo.outputPath("references-report-sent.png") });
});
