// The GitHub detail page after the managed-relay removal: a request/response
// connector on a manual personal access token. No installations, no waiting
// rows — those were features of the removed cloud relay.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openConnectors(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
}

test("connects with a manual personal access token", async ({ page }) => {
  await openConnectors(page);
  await page.getByTestId("connector-github").getByRole("button", { name: "Connect" }).click();
  const modal = page.getByTestId("add-connection-modal");
  await expect(modal.getByPlaceholder("")).toBeVisible();
  await modal.locator(".conn-field input").first().fill("ghp_token");
  await modal.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByTestId("connector-github")).toContainText("Connected", {
    timeout: 10_000,
  });
});

test("the connect modal offers no one-click and no sign-in gate", async ({ page }) => {
  await openConnectors(page);
  await page.getByTestId("connector-github").getByRole("button", { name: "Connect" }).click();
  const modal = page.getByTestId("add-connection-modal");
  await expect(modal.getByTestId("modal-install-github-app")).toHaveCount(0);
  await expect(modal.getByTestId("inline-cloud-sign-in")).toHaveCount(0);
  await expect(modal.locator(".conn-field input").first()).toBeVisible();
});
