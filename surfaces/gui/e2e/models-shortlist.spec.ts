import { test, expect } from "./fixtures";

// Settings ▸ Models ▸ OpenRouter: a live catalog of free models folds to a shortlist
// (owner ask 2026-09-06 — "not all 100 at once"); Show all opens the rest, and the add
// box autocompletes every id so a model further down is one keystroke away.
test("OpenRouter's free-model catalog folds to a shortlist with Show all", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();
  await page.getByTestId("set-provider-openrouter").click();

  const rows = page.locator(".mlist-row");
  await expect(rows).toHaveCount(6);
  await expect(page.getByTestId("mlist-more")).toHaveText("Show all 13");
  await expect(page.getByPlaceholder("Add or search a model…")).toBeVisible();
  await page.screenshot({ path: "test-results/models-shortlist.png" });

  await page.getByTestId("mlist-more").click();
  await expect(rows).toHaveCount(13);
  await expect(page.getByTestId("mlist-more")).toHaveText("Show fewer");
  await page.screenshot({ path: "test-results/models-all.png" });
});
