// An automation's own model and permission level (owner ask, 2026-08-25). A session
// has always had both; an automation inherited whatever the app default was, so
// "post the weekly report" and "summarise my inbox" ran at the same level of trust.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openAutomations(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByTestId("account-menu").getByRole("button", { name: "Automations", exact: true }).click();
  await expect(page.getByText("Recurring tasks MimiWork runs on a schedule.")).toBeVisible();
}

test("a new automation can pin a model and a permission level", async ({ page }) => {
  await openAutomations(page);
  await page.getByRole("button", { name: /New automation/ }).click();

  const form = page.getByTestId("new-automation-form");
  await form.getByPlaceholder("Title", { exact: false }).fill("Weekly CRM report");
  await form.getByPlaceholder("What should it do each run?", { exact: false }).fill("Write the report.");

  // Defaults: the app's model, and asking — never full access by inheritance.
  await expect(form.getByTestId("auto-model")).toHaveValue("");
  await expect(form.getByTestId("auto-mode")).toHaveValue("interactive");
  await expect(form).toContainText("Parks the question in your Inbox");

  await form.getByTestId("auto-model").selectOption("gpt-5.5");
  await form.getByTestId("auto-mode").selectOption("auto");
  await expect(form).toContainText("Runs everything without asking");

  const [request] = await Promise.all([
    page.waitForRequest((r) => r.url().endsWith("/v1/automations") && r.method() === "POST"),
    page.getByRole("button", { name: /Create automation/ }).click(),
  ]);
  const body = request.postDataJSON();
  expect(body.model).toBe("gpt-5.5");
  expect(body.mode).toBe("auto");

  // The detail the create lands on says what it will run as.
  await expect(page.getByTestId("task-run-settings")).toContainText("gpt-5.5");
  await expect(page.getByTestId("task-run-settings")).toContainText("Full access");
});

test("an existing automation's model and level can be changed later", async ({ page }) => {
  await openAutomations(page);
  await page.locator(".sched-card", { hasText: "Daily AI News" }).click();
  await expect(page.getByTestId("task-run-settings")).toContainText("default model");
  await expect(page.getByTestId("task-run-settings")).toContainText("Ask for approval");

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByTestId("auto-model").selectOption("gpt-4o-mini");
  await page.getByTestId("auto-mode").selectOption("plan");

  const [request] = await Promise.all([
    page.waitForRequest((r) => /\/v1\/automations\/task-1$/.test(r.url()) && r.method() === "PATCH"),
    page.getByRole("button", { name: "Save", exact: true }).click(),
  ]);
  expect(request.postDataJSON()).toMatchObject({ model: "gpt-4o-mini", mode: "plan" });
  await expect(page.getByTestId("task-run-settings")).toContainText("gpt-4o-mini");
  await expect(page.getByTestId("task-run-settings")).toContainText("Plan only");
});
