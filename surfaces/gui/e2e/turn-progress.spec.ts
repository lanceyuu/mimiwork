import { test, expect } from "./fixtures";

// "It is not very clear which stage the model is" (owner, 2026-09-05): a live turn is open —
// the narration reads as paragraphs, each run of tool calls folds to one line, the step in
// progress sits at the bottom with a spinner, and the header is a clock. Once the turn ends
// it folds to "Worked for …" above the answer.
test("a live turn shows its narration, folded activity and the current step; then folds", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByPlaceholder(/Ask the coworker/).fill("work the report");
  await page.keyboard.press("Enter");

  const head = page.getByTestId("turn-head");
  await expect(head).toHaveText(/^Working for \d+s$/);
  // The verifying step is the one that takes a while — it must be visible, spinning.
  await expect(page.getByTestId("step-running")).toBeVisible();
  await expect(page.getByText(/open the document and count its sections/i)).toBeVisible();
  // Narration is in view, not behind a disclosure; earlier runs are folded to one line each.
  await expect(page.getByTestId("turn-narration").first()).toContainText("read the two source files");
  const summaries = page.getByTestId("turn-activity-summary");
  await expect(summaries.first()).toHaveText(/Read 2 files, searched the code/);
  await expect(summaries.nth(1)).toHaveText(/Ran a command, edited a file/);
  await page.screenshot({ path: "test-results/turn-progress-live.png" });

  // The turn ends: the group folds to its duration, the answer is a bubble below it.
  await expect(head).toHaveText(/^Worked for \d+s$/);
  await expect(page.getByTestId("turn-narration")).toHaveCount(0);
  await expect(page.locator(".bubble-assistant").last()).toContainText("Q2 summary.docx");
  await page.screenshot({ path: "test-results/turn-progress-done.png" });

  // Reopening shows the same story; opening an activity line shows the humanized rows.
  await page.locator("summary.stepgroup-head").last().click();
  await summaries.first().click();
  await expect(page.getByText("sales-q2.csv")).toBeVisible();
  await page.screenshot({ path: "test-results/turn-progress-expanded.png" });
});
