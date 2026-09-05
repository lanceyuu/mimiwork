import { test, expect } from "./fixtures";

// "Is it still working?" (owner, 2026-09-04): while a turn runs, a clock keeps moving, so a
// long tool step reads as in progress, not hung. Since 2026-09-05 the clock is the live
// turn's header ("Working for 12s") once a tool call exists; the waiting row before the
// first token keeps its own.
test("the turn's clock counts up while a step is in flight", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByPlaceholder(/Ask the coworker/).fill("please run a tool");
  await page.keyboard.press("Enter");
  const head = page.getByTestId("turn-head");
  await expect(head).toHaveText(/^Working for \d+s$/);
  await expect(page.getByTestId("waiting-elapsed")).toHaveCount(0);
  await page.waitForTimeout(2100);
  const later = (await head.textContent())?.match(/(\d+)s/)?.[1];
  expect(parseInt(later || "0", 10)).toBeGreaterThanOrEqual(2);
  await page.screenshot({ path: "test-results/working-elapsed.png" });
});
