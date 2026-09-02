import { test, expect } from "./fixtures";

// Apps (spec 2026-09-03): a sidebar section like Automations. Adding a starter opens it
// running in its own frame; the frame is sandboxed with scripts only — never same-origin.

test("a starter becomes an app that runs in a sandboxed frame, and appears in the sidebar", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-apps").click();
  await expect(page.getByTestId("apps-empty")).toBeVisible();

  await page.getByTestId("app-starter-translator").getByText("Add").click();
  const frame = page.getByTestId("app-frame");
  await expect(frame).toBeVisible();
  await expect(frame).toHaveAttribute("sandbox", "allow-scripts");
  await expect(page.getByTestId("app-title")).toHaveText("Translator");
  await expect(page.getByTestId("apps-band")).toContainText("Translator");

  // Back to the overview: the card is there, delete asks first.
  await page.getByLabel("Back to apps").click();
  await expect(page.getByTestId("apps-empty")).toHaveCount(0);
  await page.getByTestId("app-card-delete").first().click();
  await expect(page.getByTestId("confirm-dialog")).toContainText("Translator");
  await page.getByTestId("confirm-accept").click();
  await expect(page.getByTestId("apps-empty")).toBeVisible();
});

test("describing an app opens a conversation under the mimi-apps skill", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-apps").click();
  await page.getByTestId("apps-wish").fill("a flashcard drill for French verbs");
  await page.getByTestId("apps-build-go").click();
  await expect(page.getByText("/mimi-apps Build me an app: a flashcard drill for French verbs")).toBeVisible();
});
