import { test, expect } from "./fixtures";

// A project GROUPS conversations (2026-08-31) — it has no folder, so "+" no longer opens a
// folder gate. It makes the group and takes you to it, where you name it.
test("New project creates a group and opens it — no folder gate", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("projects-new").click();

  // No directory is ever asked for.
  await expect(page.getByTestId("gate-title")).toHaveCount(0);
  await expect(page.getByTestId("project-name")).toBeVisible();
});

test("the empty Projects band invites the gesture rather than naming a folder", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  const band = page.getByTestId("projects-band");
  await expect(band).toContainText("Drag a conversation here");
  await expect(band).not.toContainText("folder");
});

test("projects sit below the conversations, not above them", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  const band = await page.getByTestId("projects-band").boundingBox();
  const row = await page.getByTestId("session-row").first().boundingBox();
  expect(band && row && band.y).toBeGreaterThan(row!.y);
});
