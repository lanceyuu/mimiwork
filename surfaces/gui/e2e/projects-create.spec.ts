import { test, expect } from "./fixtures";

// The Projects band's "+" creates a PLACE, not a conversation (owner catch 2026-08-22: it used
// to open the same folder gate as New session and drop you into a chat). Now: a project-worded
// gate, and a successful pick lands on the Project page with the current conversation untouched.
test("New project opens a project gate and lands on the Project page, not a session", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("projects-new").click();

  await expect(page.getByTestId("gate-title")).toHaveText("New project");
  await expect(page.getByTestId("gate-submit")).toHaveText("Create project");
  await expect(page.getByTestId("gate-submit")).toBeDisabled();

  await page.getByTestId("gate-path").fill("/tmp/My thesis");
  await page.getByTestId("gate-submit").click();

  await expect(page.getByTestId("project-view")).toBeVisible();
  await expect(page.getByTestId("gate-title")).toHaveCount(0);
});
