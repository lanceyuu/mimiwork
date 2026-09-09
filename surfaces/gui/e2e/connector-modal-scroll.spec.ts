import { test, expect } from "./fixtures";

// A tall setup form (Email/IMAP: four instructions, seven fields) scrolls inside the modal
// on a laptop-height window — the SMTP port used to sit below the window edge with no way
// down (owner hit 2026-09-09).
test("a tall connector form scrolls inside its modal", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 640 });
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
  await page.getByTestId("connector-email").getByRole("button", { name: "Connect" }).click();
  const modal = page.getByTestId("add-connection-modal");
  await expect(modal).toBeVisible();
  const card = modal.locator("div.overflow-y-auto");
  const overflow = await card.evaluate((el) => el.scrollHeight - el.clientHeight);
  expect(overflow).toBeGreaterThan(100); // the form really is taller than the window
  const last = modal.locator("input").last();
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeInViewport();
  await page.screenshot({ path: "test-results/connector-modal-scrolled.png" });
});
