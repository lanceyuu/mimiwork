// The generic multi-account detail page (AccountsDetail), exercised via Notion —
// the pattern all batch-2 connectors share (accounts.py layer: AccountRow shape,
// Default badge, per-account ×). Connects are manual-token only since the managed
// broker went with the MimiWork Cloud removal.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openConnectors(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
}

async function connectFirstWorkspace(page) {
  await openConnectors(page);
  // Available row → modal → manual token form
  await page
    .getByTestId("connector-notion")
    .getByRole("button", { name: "Connect", exact: true })
    .click();
  await page.getByPlaceholder("ntn_…").fill("ntn_token");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
  await expect(page.getByTestId("connector-notion")).toContainText("Rohit's Workspace", {
    timeout: 10_000,
  });
}

test("manual connect, add a second workspace from the page; first stays default", async ({
  page,
}) => {
  await connectFirstWorkspace(page);
  await page.getByTestId("connector-notion").click();
  await expect(page.getByTestId("accounts-detail")).toBeVisible();

  await page.getByTestId("add-account-btn").click();
  await page.getByPlaceholder("ntn_…").fill("ntn_second");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
  const first = page.getByTestId("account-ws-1");
  const second = page.getByTestId("account-ws-2");
  await expect(second).toBeVisible({ timeout: 10_000 });
  await expect(first).toContainText("Rohit's Workspace");
  await expect(first).toContainText("Default");
  await expect(second).not.toContainText("Default");
  // list row summarizes the multi-account state
  await page.getByTestId("connectors-breadcrumb").click();
  await expect(page.getByTestId("connector-notion")).toContainText("2 accounts");
});

test("Make default moves the badge; disconnecting the default repoints it", async ({
  page,
}) => {
  await connectFirstWorkspace(page);
  await page.getByTestId("connector-notion").click();
  await page.getByTestId("add-account-btn").click();
  await page.getByPlaceholder("ntn_…").fill("ntn_second");
  await page.getByRole("button", { name: "Connect", exact: true }).last().click();
  await expect(page.getByTestId("account-ws-2")).toBeVisible({ timeout: 10_000 });

  await page.getByTestId("account-make-default-ws-2").click();
  await expect(page.getByTestId("account-ws-2")).toContainText("Default");
  await expect(page.getByTestId("account-ws-1")).not.toContainText("Default");

  await page.getByTestId("account-disconnect-ws-2").click();
  await expect(page.getByTestId("account-ws-2")).toHaveCount(0);
  await expect(page.getByTestId("account-ws-1")).toContainText("Default");
});

test("the connect modal is the manual token form — no sign-in gate anywhere", async ({
  page,
}) => {
  await openConnectors(page);
  await page
    .getByTestId("connector-notion")
    .getByRole("button", { name: "Connect", exact: true })
    .click();
  await expect(page.getByPlaceholder("ntn_…")).toBeVisible();
  await expect(page.getByTestId("inline-cloud-sign-in")).toHaveCount(0);
});
