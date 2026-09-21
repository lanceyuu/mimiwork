// "Report this problem" (owner ask 2026-09-21): an error notice carries a button that asks
// before anything leaves the machine, then posts to the sidecar's /v1/report.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("error notice → Report this problem → confirm → sent", async ({ page }) => {
  const posted: unknown[] = [];
  await page.route("**/v1/report", async (route) => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/");
  await page.getByText("Draft the launch note").first().click();
  const box = page.getByPlaceholder(/Ask Mimi/);
  await box.fill("please fail the turn");
  await box.press("Enter");

  await expect(page.getByText("Error: model unreachable").first()).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: "test-results/report-problem-notice.png" });
  await page.getByTestId("report-problem").click();
  await expect(page.getByText(/Send this error to the QualiTaTi team/)).toBeVisible();
  await page.screenshot({ path: "test-results/report-problem-confirm.png" });
  expect(posted).toHaveLength(0);
  await page.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByText(/Sent — thank you/)).toBeVisible();
  expect(posted[0]).toEqual({ error: "Error: model unreachable", context: "conversation" });
});
