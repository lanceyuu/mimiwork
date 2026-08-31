// Cold-boot behaviour. The splash shows MIMI — one of her poses, a different one each
// launch (owner ask 2026-08-31); it used to be a six-point star, correct as a mark but
// nobody's face. And the model picker recovers when the mount-time settings fetch loses
// the race against the sidecar boot — previously "Loading models…" stuck until the user
// visited Settings.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("boot splash shows Mimi, and a different pose next launch", async ({ page }) => {
  // Hold health long enough to observe the splash.
  await page.route("**/v1/health", async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.fallback();
  });
  await page.goto("/");
  const mark = page.locator(".boot-mark");
  await expect(mark).toBeVisible();
  const img = mark.locator("img");
  await expect(img).toBeVisible();
  await expect(mark).not.toContainText("✦");
  const first = await img.getAttribute("src");
  await expect(page.getByText(/Starting MimiWork|Restoring your session/)).toBeVisible();

  // Next launch, next pose — the whole point of the change.
  await page.reload();
  await expect(page.locator(".boot-mark img")).toBeVisible();
  expect(await page.locator(".boot-mark img").getAttribute("src")).not.toBe(first);
});

test("model picker recovers when settings fetches die during sidecar boot", async ({ page }) => {
  // Real cold-start shape: EVERY request fails until the sidecar is up (health included),
  // then everything answers. The mount-time settings fetches all lose that race and are
  // swallowed — the post-health reload must populate the picker without a Settings visit.
  let sidecarUp = false;
  await page.route("**/v1/health", async (route) => {
    await new Promise((r) => setTimeout(r, 700));
    sidecarUp = true;
    await route.fallback();
  });
  await page.route("**/v1/settings", async (route) => {
    if (route.request().method() === "GET" && !sidecarUp) {
      await route.abort();
      return;
    }
    await route.fallback();
  });
  await page.goto("/");
  await expect(page.locator(".dd").filter({ hasText: "Claude Opus 4.8" })).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByTestId("models-loading")).toHaveCount(0);
});
