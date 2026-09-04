import { test, expect } from "./fixtures";

// "Is it still working?" (owner, 2026-09-04): while a turn runs, the waiting line
// carries a clock that keeps moving, so a long tool step reads as in progress, not hung.
test("the waiting line counts up while a turn is in flight", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByPlaceholder(/Ask the coworker/).fill("please run a tool");
  await page.keyboard.press("Enter");
  const elapsed = page.getByTestId("waiting-elapsed");
  await expect(elapsed).toBeVisible();
  await expect(elapsed).toHaveText(/^\d+s$/);
  await page.waitForTimeout(2100);
  const later = await elapsed.textContent();
  expect(parseInt(later || "0", 10)).toBeGreaterThanOrEqual(2);
  await page.screenshot({ path: "test-results/working-elapsed.png" });
});
