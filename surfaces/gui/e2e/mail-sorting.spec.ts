import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

// Sorting: Mimi reads new mail to sort it and to write one line on each conversation. It
// sends mail text to the model, so it is off until the user says yes, knowing what it does.

async function openMail(page: Page) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  await expect(page.getByTestId("mail-row")).toHaveCount(3);
}

test("the first time, Mail asks before anything is sorted, and a no leaves it as it was", async ({ page }, testInfo) => {
  await openMail(page);
  const offer = page.getByTestId("mail-sorting-offer");
  await expect(offer).toContainText("reads each new email");
  await expect(offer).toContainText("spends credits");
  await expect(page.getByTestId("mail-tab-needs_reply")).toHaveCount(0);
  await expect(page.getByTestId("mail-row-summary")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("mail-sorting-offer.png") });

  await page.getByTestId("mail-sorting-no").click();
  await expect(offer).toHaveCount(0);
  await expect(page.getByTestId("mail-tab-needs_reply")).toHaveCount(0);
  // It is not asked again, here or after leaving and coming back.
  await page.reload();
  await page.getByTestId("nav-mail").click();
  await expect(page.getByTestId("mail-row")).toHaveCount(3);
  await expect(page.getByTestId("mail-sorting-offer")).toHaveCount(0);
});

test("once turned on, each conversation has its line and its tab, and settings can turn it off again", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-sorting-yes").click();
  await expect(page.getByTestId("mail-sorting-offer")).toHaveCount(0);
  const rows = page.getByTestId("mail-row");
  await expect(rows.first().getByTestId("mail-row-summary")).toHaveText("Ana asks to meet on Friday at ten.");
  await expect(page.getByTestId("mail-row-summary")).toHaveCount(2); // the newsletter has none
  await page.screenshot({ path: testInfo.outputPath("mail-sorted.png") });

  await page.getByTestId("mail-tab-needs_reply").click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Plan for Friday");
  await page.getByTestId("mail-tab-fyi").click();
  await expect(rows.first()).toContainText("Your invoice for October");
  await page.getByTestId("mail-tab-newsletters").click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("You have won");
  await page.getByTestId("mail-tab-all").click();
  await expect(rows).toHaveCount(3);

  // Settings: whose mail is never sent to be sorted, and the switch.
  await page.getByTestId("mail-sorting").click();
  const senders = page.getByTestId("mail-excluded");
  await senders.fill("bank");
  await page.getByTestId("mail-excluded-save").click();
  await expect(page.getByTestId("mail-settings-error")).toContainText('"bank" is not an address or a domain');
  await senders.fill("@bank.example\nana@example.com");
  await page.getByTestId("mail-excluded-save").click();
  await expect(page.getByTestId("mail-settings")).toContainText("Saved.");
  await expect(page.getByTestId("mail-settings-error")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("mail-sorting-settings.png") });

  await page.getByTestId("mail-tab-fyi").click();
  // The switch shows the new state once the change has been saved, so it is pressed, not set.
  await page.getByTestId("mail-sorting-switch").click();
  await expect(page.getByTestId("mail-sorting-switch")).not.toBeChecked();
  // The sorted tabs go, the list falls back to the whole inbox, and the lines go with them.
  await expect(page.getByTestId("mail-tab-fyi")).toHaveCount(0);
  await expect(rows).toHaveCount(3);
  await expect(page.getByTestId("mail-row-summary")).toHaveCount(0);
  await page.getByTestId("mail-settings-close").click();
  await expect(page.getByTestId("mail-settings")).toHaveCount(0);
});
