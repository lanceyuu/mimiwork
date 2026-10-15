// A team of coding agents: each start asks first and says the agent gets its own branch; while
// Mimi watches, the running step shows one line per agent; feedback rounds read as steps.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("Mimi starts two agents, watches both, and sends one back with feedback", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/Ask Mimi/).fill("please run the team");
  await page.getByRole("button", { name: "Send" }).click();

  const note = page.getByTestId("delegate-note");
  await expect(note).toContainText("Codex works on its own in analysis-scripts");
  await expect(note).toContainText("gets its own branch");
  await expect(note).toContainText("your own OpenAI account, not QualiTaTi credits");
  await page.screenshot({ path: "test-results/team-approval.png", fullPage: false });
  await page.getByRole("button", { name: "Yes", exact: true }).last().click();

  await expect(page.getByTestId("delegate-note")).toContainText("your own Claude account");
  await page.getByRole("button", { name: "Yes", exact: true }).last().click();

  const board = page.getByTestId("step-progress");
  await expect(board).toContainText("Codex · csv export:");
  await expect(board).toContainText("Claude Code · usage guide:");
  await page.screenshot({ path: "test-results/team-watching.png", fullPage: false });

  await expect(page.getByText(/Both branches are ready/)).toBeVisible();
  await expect(page.getByTestId("step-progress")).toHaveCount(0);
  await page.getByTestId("turn-head").click();
  await expect(page.getByText(/Sent feedback/).first()).toBeVisible();
  await page.screenshot({ path: "test-results/team-done.png", fullPage: false });
});
