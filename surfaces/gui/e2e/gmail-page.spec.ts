// The Gmail detail page (M3.6 Step 3, UX-DECISIONS §21): multi-account with a
// Default badge, per-account disconnect, direct one-click add (no modal — Gmail
// has one connect mode), and the "Never show agents" filter lists.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openConnectors(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
}

async function connectFirstAccount(page) {
  await openConnectors(page);
  // gmail starts disconnected → Available row → modal → manual token connect
  // (the managed one-click went with the the hosted relay's removal).
  await page.getByTestId("connector-gmail").getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByPlaceholder("").first(); // modal open
  await page.locator(".conn-field input").first().fill("ya29.token");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
  await expect(page.getByTestId("connector-gmail")).toContainText("rohit@gmail.com", {
    timeout: 10_000,
  });
}

test("connect, then add a second account from the page; first stays default", async ({
  page,
}) => {
  await connectFirstAccount(page);
  await page.getByTestId("connector-gmail").click();
  await expect(page.getByTestId("gmail-detail")).toBeVisible();

  await page.getByTestId("add-account-btn").click();
  await page.locator(".conn-field input").first().fill("ya29.second");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
  const rohit = page.getByTestId("gmail-account-rohit@gmail.com");
  const work = page.getByTestId("gmail-account-work@dlai.com");
  await expect(work).toBeVisible({ timeout: 10_000 });
  await expect(rohit).toContainText("Default");
  await expect(work).not.toContainText("Default");
  // list row summarizes the multi-account state
  await page.getByTestId("connectors-breadcrumb").click();
  await expect(page.getByTestId("connector-gmail")).toContainText("2 accounts");
});

test("Make default moves the badge; disconnecting the default repoints it", async ({
  page,
}) => {
  await connectFirstAccount(page);
  await page.getByTestId("connector-gmail").click();
  await page.getByTestId("add-account-btn").click();
  await page.locator(".conn-field input").first().fill("ya29.second");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
  await expect(page.getByTestId("gmail-account-work@dlai.com")).toBeVisible({ timeout: 10_000 });

  await page.getByTestId("gmail-make-default-work@dlai.com").click();
  await expect(page.getByTestId("gmail-account-work@dlai.com")).toContainText("Default");
  await expect(page.getByTestId("gmail-account-rohit@gmail.com")).not.toContainText("Default");

  await page.getByTestId("gmail-disconnect-work@dlai.com").click();
  await expect(page.getByTestId("gmail-account-work@dlai.com")).toHaveCount(0);
  await expect(page.getByTestId("gmail-account-rohit@gmail.com")).toContainText("Default");
});

test("Never show agents: sender + label chips round-trip", async ({ page }) => {
  await connectFirstAccount(page);
  await page.getByTestId("connector-gmail").click();

  const senders = page.getByTestId("gmail-filter-senders");
  await senders.getByRole("textbox").fill("ceo@corp.com");
  await senders.getByRole("textbox").press("Enter");
  await expect(senders).toContainText("ceo@corp.com");

  const labels = page.getByTestId("gmail-filter-labels");
  await labels.getByRole("textbox").fill("Personal");
  await labels.getByRole("textbox").press("Enter");
  await expect(labels).toContainText("Personal");

  // chips survive a reload (persisted through the PATCH route, re-read on load)
  await page.reload();
  await openConnectors(page);
  await page.getByTestId("connector-gmail").click();
  await expect(page.getByTestId("gmail-filter-senders")).toContainText("ceo@corp.com");
  // remove round-trips too
  await page.getByTestId("gmail-filter-senders").getByTitle("remove").click();
  await expect(page.getByTestId("gmail-filter-senders")).not.toContainText("ceo@corp.com");
});
