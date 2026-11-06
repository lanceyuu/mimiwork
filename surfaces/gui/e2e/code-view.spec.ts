import { test, expect } from "./fixtures";

// The surface a non-coder uses to check an analysis (spec 2026-11-06): screenshot both
// tabs so the owner can judge the look, not just the behaviour.

const SOURCE = [
  "# MimiWork analysis log: every Python step Mimi ran in this conversation, in order.",
  "",
  "# Step 1 · 14:02",
  "df = pd.read_csv('survey.csv')",
  "",
  "# Step 2 · 14:03",
  "df = df[df['attention_check'] == 1]",
  "df['wtp'] = df['wtp'].clip(upper=df['wtp'].quantile(0.99))",
].join("\n");

const NOTES = {
  ok: true,
  path: "analysis_steps.py",
  steps: [
    { start: 1, end: 4, note: "Loads the survey answers from survey.csv.", choice: null },
    {
      start: 5,
      end: 8,
      note: "Keeps people who passed the attention check, then caps very high willingness-to-pay answers.",
      choice: "Capping at the 99th percentile is a choice to report in the method section.",
    },
  ],
  lines_explained: 8,
  truncated: false,
};

test("a researcher explains the analysis script and reads it step by step", async ({ page }, testInfo) => {
  await page.route("**/v1/sessions/*/artifacts", (r) =>
    r.fulfill({ json: { artifacts: [{ path: "analysis_steps.py", name: "analysis_steps.py", kind: "code", size: 300, modified_at: 2 }] } }),
  );
  await page.route("**/v1/sessions/*/artifacts/read?*", (r) =>
    r.fulfill({ json: { ok: true, path: "analysis_steps.py", kind: "code", content: SOURCE } }),
  );
  await page.route("**/v1/sessions/*/artifacts/explain", async (r) => {
    const body = r.request().postDataJSON();
    await r.fulfill({ json: body.cached_only ? { ok: false, cached: false } : NOTES });
  });

  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByText("analysis_steps.py").first().click();

  await page.getByRole("button", { name: "Explain this script" }).click();
  await expect(page.getByText("Choice to check")).toBeVisible();
  await page.getByRole("button", { name: /Show code/ }).nth(1).click();
  await page.screenshot({ path: testInfo.outputPath("code-view-plain.png") });

  await page.getByRole("tab", { name: "Code" }).click();
  await expect(page.locator("[data-line]")).toHaveCount(8);
  // Buttons fade their border over 0.15s app-wide; wait for the underline to land, which
  // also proves the right tab is marked.
  await expect(page.getByRole("tab", { name: "Code" })).toHaveCSS("border-bottom-color", "rgb(13, 148, 136)");
  await page.screenshot({ path: testInfo.outputPath("code-view-code.png") });
});
