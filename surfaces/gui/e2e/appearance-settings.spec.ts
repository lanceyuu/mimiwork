import { test, expect } from "./fixtures";

test("font and background apply at once and survive a reload", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const card = page.getByTestId("look-card");
  await card.getByRole("radio", { name: "Serif" }).click();
  await card.getByRole("radio", { name: "Warm" }).click();

  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-font", "serif");
  await expect(html).toHaveAttribute("data-bg", "warm");
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(246, 242, 234)");
  expect(await page.evaluate(() => getComputedStyle(document.body).fontFamily)).toContain("Georgia");
  // Text size is the desktop webview's zoom; a browser tab keeps its own Cmd-plus.
  await expect(card.getByRole("radio", { name: "Larger" })).toHaveCount(0);

  await card.screenshot({ path: testInfo.outputPath("look-card.png") });
  await page.getByTestId("alerts-card").screenshot({ path: testInfo.outputPath("alerts-card.png") });
  await page.screenshot({ path: testInfo.outputPath("settings-serif-warm.png") });

  await page.reload();
  await expect(html).toHaveAttribute("data-bg", "warm");
  await expect(html).toHaveAttribute("data-font", "serif");
});

test("notification choices are remembered", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByTestId("alert-sound")).not.toBeChecked();
  await page.getByTestId("alert-sound").check();
  await page.getByTestId("alert-attention").uncheck();
  await page.reload();
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByTestId("alert-sound")).toBeChecked();
  await expect(page.getByTestId("alert-attention")).not.toBeChecked();
});
