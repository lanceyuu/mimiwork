// Handing a task to Claude Code / Codex: the approval says the agent works on its own and on
// whose account; once approved, the running step shows what the agent is doing right now.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("a hand-off asks first, then shows the agent's live progress until it reports back", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/Ask Mimi/).fill("please hand this to codex");
  await page.getByRole("button", { name: "Send" }).click();

  const note = page.getByTestId("delegate-note");
  await expect(note).toContainText("Codex works on its own in analysis-scripts");
  await expect(note).toContainText("your own OpenAI account, not QualiTaTi credits");
  await expect(page.getByText("runs on its own · your own account")).toBeVisible();
  await page.screenshot({ path: "test-results/delegate-approval.png", fullPage: false });

  await page.getByRole("button", { name: "Yes", exact: true }).last().click();
  await expect(page.getByTestId("step-progress")).toHaveText(/Changed report.py|Running: pytest -q/);
  await expect(page.getByText(/Handed a task to Codex/)).toBeVisible();
  await page.screenshot({ path: "test-results/delegate-progress.png", fullPage: false });

  await expect(page.getByText("Codex fixed the off-by-one in report.py and the tests pass.")).toBeVisible();
  await expect(page.getByTestId("step-progress")).toHaveCount(0);
});
