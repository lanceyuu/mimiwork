// The HubSpot detail page (M3.6 Step 4, UX-DECISIONS §21): multi-portal with
// Default/Sandbox/access tags and the hidden-fields denylist. Connects are the
// manual private-app token — the broker one-click (and its consent radios) went
// with the the hosted relay's removal.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openConnectors(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
}

async function connectPortal(page) {
  await page.getByPlaceholder("pat-…").fill("pat-na1-token");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
}

test("connect via the manual modal: the portal lands with its access tag", async ({
  page,
}) => {
  await openConnectors(page);
  await page.getByTestId("connector-hubspot").getByRole("button", { name: "Connect" }).click();
  const modal = page.getByTestId("add-connection-modal");
  await expect(modal.getByPlaceholder("pat-…")).toBeVisible();
  await connectPortal(page);

  await expect(page.getByTestId("connector-hubspot")).toContainText("Acme Inc", {
    timeout: 10_000,
  });
  await page.getByTestId("connector-hubspot").click();
  const row = page.getByTestId("hubspot-portal-111");
  await expect(row).toContainText("Default");
  await expect(page.getByTestId("hubspot-access-tag-111")).toContainText("read & write");
});

test("the modal is manual-only: token form, no pane pills, no one-click", async ({
  page,
}) => {
  await openConnectors(page);
  await page.getByTestId("connector-hubspot").getByRole("button", { name: "Connect" }).click();
  const modal = page.getByTestId("add-connection-modal");
  await expect(modal.getByPlaceholder("pat-…")).toBeVisible();
  await expect(modal.getByTestId("modal-pane-manual")).toHaveCount(0);
  await expect(modal.getByTestId("managed-connect")).toHaveCount(0);
});

test("second portal: sandbox tag, make-default, disconnect repoints", async ({ page }) => {
  await openConnectors(page);
  await page.getByTestId("connector-hubspot").getByRole("button", { name: "Connect" }).click();
  await connectPortal(page);
  await expect(page.getByTestId("connector-hubspot")).toContainText("Acme Inc", { timeout: 10_000 });
  await page.getByTestId("connector-hubspot").click();

  // add the sandbox portal from the page's header button
  await page.getByTestId("add-portal-btn").click();
  await connectPortal(page);
  const sandbox = page.getByTestId("hubspot-portal-222");
  await expect(sandbox).toContainText("Sandbox", { timeout: 10_000 });

  await page.getByTestId("hubspot-make-default-222").click();
  await expect(sandbox).toContainText("Default");
  await page.getByTestId("hubspot-disconnect-222").click();
  await expect(page.getByTestId("hubspot-portal-222")).toHaveCount(0);
  await expect(page.getByTestId("hubspot-portal-111")).toContainText("Default");
});

test("hidden fields round-trip and read back normalized", async ({ page }) => {
  await openConnectors(page);
  await page.getByTestId("connector-hubspot").getByRole("button", { name: "Connect" }).click();
  await connectPortal(page);
  await expect(page.getByTestId("connector-hubspot")).toContainText("Acme Inc", { timeout: 10_000 });
  await page.getByTestId("connector-hubspot").click();

  const row = page.getByTestId("hubspot-hidden-fields");
  await row.getByRole("textbox").fill("Salary");
  await row.getByRole("textbox").press("Enter");
  await expect(row).toContainText("salary"); // normalized lowercase from the PATCH echo
  await row.getByTitle("remove").click();
  await expect(row).not.toContainText("salary");
});
