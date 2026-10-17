import { expect } from "@playwright/test";
import { test } from "./fixtures";

// Failures and confirmations the app used to report through window.alert() (a native
// modal that froze the window and carried the server's wording) or not at all. Each
// one now shows in the page, next to what the user did. Audit of 2026-10-16.

// Any native dialog fails the test: the point is that none appear.
test.beforeEach(async ({ page }) => {
  page.on("dialog", (d) => {
    throw new Error(`unexpected native dialog: ${d.message()}`);
  });
});

async function dragOnto(page: any, sourceSel: string, targetSel: string) {
  await page.evaluate(
    ([src, dst]: [string, string]) => {
      const from = document.querySelector(src) as HTMLElement;
      const to = document.querySelector(dst) as HTMLElement;
      const dt = new DataTransfer();
      from.dispatchEvent(new DragEvent("dragstart", { dataTransfer: dt, bubbles: true }));
      to.dispatchEvent(new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true }));
      to.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    },
    [sourceSel, targetSel],
  );
}

test("a conversation that cannot be filed says so in plain words, without a dialog", async ({ page }, testInfo) => {
  await page.route("**/v1/sessions/*/project", (route) =>
    route.fulfill({ json: { ok: false, error: "sqlite3.OperationalError: database is locked" } }),
  );
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("projects-new").click();
  await page.getByTestId("project-name").fill("Thesis");
  await page.getByTestId("project-name").blur();
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await expect(page.getByTestId("project-row").first()).toContainText("Thesis");

  await dragOnto(page, '[title="Weekly plan 1"]', '[data-testid="project-row"]');
  const notice = page.getByTestId("app-notice");
  await expect(notice).toContainText("could not be moved into the project");
  await expect(notice).not.toContainText("sqlite3");
  await page.screenshot({ path: testInfo.outputPath("filing-failed.png"), animations: "disabled" });
  await notice.getByTitle("Dismiss").click();
  await expect(notice).toHaveCount(0);
});

test("sharing a blueprint reports where it was saved, in the page", async ({ page }, testInfo) => {
  await page.route("**/v1/automations/*/blueprint", (route) =>
    route.fulfill({ json: { ok: true, path: "/Users/me/Daily AI News.mimiflow.json" } }),
  );
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByTestId("account-menu").getByRole("button", { name: "Automations", exact: true }).click();
  await page.getByText("Daily AI News").first().click();
  await page.getByTestId("share-blueprint").click();
  await expect(page.getByTestId("inline-notice")).toContainText("Blueprint saved to /Users/me/Daily AI News.mimiflow.json");
  await page.screenshot({ path: testInfo.outputPath("blueprint-shared.png"), animations: "disabled" });
});

test("importing a file that is not a blueprint says so on the Automations page", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByTestId("account-menu").getByRole("button", { name: "Automations", exact: true }).click();
  await page.getByTestId("import-blueprint").setInputFiles({
    name: "notes.json",
    mimeType: "application/json",
    buffer: Buffer.from("not json at all"),
  });
  await expect(page.getByTestId("inline-notice")).toContainText("That file could not be read");
});

test("a setup starter whose folder never attaches still lands in the composer, with the reason", async ({ page }, testInfo) => {
  test.setTimeout(30_000);
  await page.route("**/v1/sessions/*/roots", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ json: { ok: false, error: "unknown session" } })
      : route.fallback(),
  );
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByTestId("account-menu").getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Run setup again" }).click();
  await page.getByTestId("ob-continue-language").click();
  await page.getByTestId("ob-byok").click();
  await page.getByTestId("ob-continue").click();
  await page.getByTestId("ob-continue-tools").click();
  await expect(page.getByTestId("ob-step-first-task")).toBeVisible();
  await page.getByTestId("ob-pick-folder").click();
  await page.screenshot({ path: testInfo.outputPath("starter-icons.png"), animations: "disabled" });
  await page.getByTestId("ob-starter-summarize").click();

  // Fifteen tries 400 ms apart, then the terminal branch.
  const notice = page.getByTestId("app-notice");
  await expect(notice).toContainText("could not open the folder “picked-folder”", { timeout: 15_000 });
  await expect(page.locator("textarea").first()).toHaveValue(/give me a short overview/);
  await page.screenshot({ path: testInfo.outputPath("starter-folder-failed.png"), animations: "disabled" });
});

test("Activity tells a filter that matched nothing apart from an empty log", async ({ page }, testInfo) => {
  await page.route("**/v1/audit**", (route) => route.fulfill({ json: { events: [] } }));
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByTestId("account-menu").getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByTestId("activity-empty")).toContainText("No audit events yet.");
  await expect(page.getByText("What ran. Tool arguments")).toBeVisible();
  await page.getByPlaceholder("session id").fill("typo");
  await page.getByRole("button", { name: "Filter", exact: true }).click();
  await expect(page.getByTestId("activity-empty")).toContainText("Nothing matches these filters.");
  await page.screenshot({ path: testInfo.outputPath("activity-filtered.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByTestId("activity-empty")).toContainText("No audit events yet.");
  await expect(page.getByPlaceholder("session id")).toHaveValue("");
});

test("a model that cannot be added says the change was not saved", async ({ page }, testInfo) => {
  await page.route("**/v1/settings/models/add", (route) => route.abort());
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();
  await page.getByTestId("set-provider-openrouter").click();
  await page.getByPlaceholder(/Add or search a model|Add another model/).fill("vendor/new-model");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.locator(".mlist-problem")).toContainText("That change was not saved");
  await page.locator(".mlist").screenshot({ path: testInfo.outputPath("model-not-saved.png") });
});

test("while a task runs, a message with a file says it waits for a new task", async ({ page }, testInfo) => {
  await page.goto("/");
  const box = page.getByPlaceholder(/Ask Mimi/);
  await box.fill("please run a tool");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("The coworker wants to run a command.").first()).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles({
    name: "brief.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("notes"),
  });
  const note = page.getByTestId("steer-waits");
  await expect(note).toContainText("Files and skills start a new task");
  await expect(page.getByRole("button", { name: "Steer" })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("steer-waits.png"), animations: "disabled" });
});
