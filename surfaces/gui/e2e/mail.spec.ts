import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

// Mail as a reader: the inbox as conversations, an email shown as it was sent, an
// attachment saved, a conversation archived, and search reaching mail outside the inbox.

async function openMail(page: Page) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  await expect(page.getByTestId("mail-row")).toHaveCount(3);
}

// The email sits in a frame where nothing can run, so the test reads and clicks it the
// way the app does: from outside.
const frameText = (page: Page) =>
  page.evaluate(() => {
    const frame = document.querySelector<HTMLIFrameElement>('[data-testid="mail-frame"]');
    return frame?.contentDocument?.body?.innerText ?? "";
  });

async function clickInFrame(page: Page, selector: string) {
  const point = await page.evaluate((sel) => {
    const frame = document.querySelector<HTMLIFrameElement>('[data-testid="mail-frame"]')!;
    const target = frame.contentDocument!.querySelector(sel)!;
    target.scrollIntoView({ block: "center" });
    const outer = frame.getBoundingClientRect();
    const inner = target.getBoundingClientRect();
    return { x: outer.x + inner.x + inner.width / 2, y: outer.y + inner.y + inner.height / 2 };
  }, selector);
  await page.mouse.click(point.x, point.y);
}

test("the inbox lists conversations, and one opens, saves its attachment and is archived", async ({ page }, testInfo) => {
  await openMail(page);
  const rows = page.getByTestId("mail-row");
  await expect(rows.first()).toContainText("Ana Lopez");
  await expect(rows.first()).toContainText("Plan for Friday");
  await expect(rows.first()).toHaveClass(/unread/);
  await expect(page.getByTestId("mail-sync-line")).toContainText("me@example.com");
  await expect(page.getByTestId("mail-sync-line")).toContainText("Last synced");
  await page.screenshot({ path: testInfo.outputPath("mail-list.png") });

  await rows.first().click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Plan for Friday");
  // Two messages; the newest, unread one is open and the earlier one is folded.
  await expect(page.getByTestId("mail-message")).toHaveCount(2);
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect.poll(() => frameText(page)).toContain("Friday at ten");
  // Opening it marks it read, and the list follows.
  await expect(rows.first()).not.toHaveClass(/unread/);
  await page.screenshot({ path: testInfo.outputPath("mail-reader.png") });

  await page.getByTestId("mail-attachment-save").click();
  await expect(page.getByTestId("mail-attachments")).toContainText("Saved to /Users/me/Downloads/plan.pdf");

  await page.getByTestId("mail-archive").click();
  await expect(rows).toHaveCount(2);
  await expect(page.getByTestId("mail-reader")).toHaveCount(0);
  await expect(rows.first()).toContainText("Your invoice for October");
});

test("a clicked link is not followed: the app shows where it goes and offers to open it", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-row").first().click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect(page.getByTestId("mail-link-card")).toHaveCount(0);

  await clickInFrame(page, "#agenda");
  await expect(page.getByTestId("mail-link-address")).toHaveText("https://example.com/agenda");
  await expect(page.getByTestId("mail-link-open")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mail-link-card.png") });
  // Still the email, not the page the link points at.
  expect(await frameText(page)).toContain("Friday at ten");

  await page.getByTestId("mail-link-card").getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("mail-link-card")).toHaveCount(0);
  // Closing lets go of the link, so clicking the same one again shows its address again.
  await clickInFrame(page, "#agenda");
  await expect(page.getByTestId("mail-link-address")).toHaveText("https://example.com/agenda");
});

test("search reaches mail outside the inbox and opens it alone, without Archive or Bin", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-search").fill("invoice");
  await page.getByTestId("mail-search").press("Enter");
  const rows = page.getByTestId("mail-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Invoice January");
  await expect(rows.first()).toContainText("Archive");

  await rows.first().click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect.poll(() => frameText(page)).toContain("Paid in full.");
  await expect(page.getByTestId("mail-subject")).toHaveText("Invoice January");
  await expect(page.getByTestId("mail-archive")).toHaveCount(0);
  await expect(page.getByTestId("mail-bin")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("mail-search.png") });

  await page.getByTestId("mail-search-clear").click();
  await expect(rows).toHaveCount(3);
});

test("with no mailbox connected, Mail says what to connect and where", async ({ page }, testInfo) => {
  await page.route("**/v1/mail/status", (route) =>
    route.fulfill({
      json: {
        ok: true, connected: false, address: "", syncing: false, revision: 0,
        last_sync: 0, last_error: "", can_archive: false, can_bin: false,
      },
    }),
  );
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  const welcome = page.getByTestId("mail-not-connected");
  await expect(welcome).toContainText("Connectors, Email");
  await expect(welcome).toContainText("app password");
  await page.screenshot({ path: testInfo.outputPath("mail-not-connected.png") });

  await page.getByTestId("mail-open-connectors").click();
  await expect(page.getByTestId("mail-page")).toHaveCount(0);
});
