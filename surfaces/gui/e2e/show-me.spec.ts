import { test, expect } from "./fixtures";

// "Show me how" (owner ask 2026-09-06): after a turn that did work, one button under the
// answer asks the show-me skill for a diagram of the process; the Mermaid fence it answers
// with is drawn inline, not shown as code.
test("show me how: button after a working turn → diagram drawn in the reply", async ({ page }) => {
  await page.goto("/");
  const box = page.getByPlaceholder(/Ask the coworker/);
  await expect(box).toBeVisible();
  // A plain chat turn offers nothing to draw.
  await box.fill("hello");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Echo: hello/)).toBeVisible();
  await expect(page.getByTestId("show-me")).toHaveCount(0);

  await box.fill("work the report");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/three sections you asked for/)).toBeVisible({ timeout: 10_000 });
  const btn = page.getByTestId("show-me");
  await expect(btn).toBeVisible();
  await page.screenshot({ path: "test-results/show-me-button.png", fullPage: false });

  await btn.click();
  // The user bubble shows the force-run the way the composer's /skill pick does.
  await expect(page.getByText(/^\/show-me /).first()).toBeVisible();
  await expect(page.locator('[data-testid="mermaid"] svg')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("show-me")).toHaveCount(0); // a diagram turn is talk, not work
  await page.screenshot({ path: "test-results/show-me-diagram.png", fullPage: false });
});
