import { test, expect } from "./fixtures";

// Deleting an automation asks first. The card's trash icon used to delete on the click
// itself, with no question at all, from a list you scroll past (owner ask 2026-08-31).

test("the card's trash icon asks before deleting, and cancelling keeps it", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-automations").click();

  const card = page.getByTestId("automation-card-delete").first();
  await expect(card).toBeVisible();
  await card.click();

  const dialog = page.getByTestId("confirm-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Daily AI News");
  // Nothing has happened yet.
  await expect(page.getByText("Daily AI News").first()).toBeVisible();

  await page.getByTestId("confirm-cancel").click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Daily AI News").first()).toBeVisible();
});

test("confirming deletes it", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-automations").click();
  await page.getByTestId("automation-card-delete").first().click();
  await page.getByTestId("confirm-accept").click();
  await expect(page.getByTestId("confirm-dialog")).toHaveCount(0);
  await expect(page.getByText("Daily AI News")).toHaveCount(0);
});

test("the detail page's Delete asks too", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("scheduled-task-1").click();
  await expect(page.getByRole("heading", { name: "Daily AI News" })).toBeVisible();

  await page.getByTestId("automation-detail-delete").click();
  const dialog = page.getByTestId("confirm-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Daily AI News");

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Daily AI News" })).toBeVisible();
});
