import { test, expect } from "./fixtures";

// "Visualize this task" (owner ask 2026-09-06): after a turn that did work, one button under the
// answer asks the show-me skill for a diagram of the process; the Mermaid fence it answers
// with is drawn inline, not shown as code.
test("visualize this task: button after a working turn → diagram drawn in the reply", async ({ page }) => {
  await page.goto("/");
  const box = page.getByPlaceholder(/Ask Mimi/);
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

// Owner ask 2026-09-29: a long flowchart is shrunk to fit the column and cannot be read.
test("the drawn diagram can be enlarged, panned by scrolling, and put back", async ({ page }) => {
  await page.goto("/");
  const box = page.getByPlaceholder(/Ask Mimi/);
  await box.fill("work the report");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByTestId("show-me").click();
  const picture = page.locator('[data-testid="mermaid"] svg');
  await expect(picture).toBeVisible({ timeout: 15_000 });
  const width = async () => (await picture.boundingBox())!.width;
  const normal = await width();

  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Zoom in" }).click();
  // Mermaid's own inline max-width must not hold the picture at its drawn size.
  await expect.poll(width).toBeGreaterThan(normal * 1.9);
  // The picture outgrows its frame and the frame scrolls; the conversation does not widen.
  const frame = page.locator(".md-mermaid-frame");
  const fits = await frame.evaluate((f) => ({ scrolls: f.scrollWidth > f.clientWidth, page: document.documentElement.scrollWidth <= window.innerWidth }));
  expect(fits).toEqual({ scrolls: true, page: true });
  await page.screenshot({ path: "test-results/show-me-zoomed.png", fullPage: false });

  await page.getByRole("button", { name: "Reset view" }).click();
  await expect.poll(width).toBeCloseTo(normal, 0);
  await expect(page.getByRole("button", { name: "Reset view" })).toHaveCount(0);
});
