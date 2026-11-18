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

test("what was sent is under its own tab, named for who it went to, and opens in the same reader", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-tab-sent").click();
  const rows = page.getByTestId("mail-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("To: Ben Carter");
  await expect(rows.first()).toContainText("Lunch on Thursday");
  await expect(rows.nth(1)).toContainText("To: Ana Lopez, Li Chen");
  // Nothing you sent is waiting to be read.
  await expect(page.locator(".mail-row.unread")).toHaveCount(0);

  await rows.first().click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Lunch on Thursday");
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect.poll(() => frameText(page)).toContain("lunch on Thursday at noon");
  // It is not in the inbox, so it cannot be archived or binned; it can be followed up.
  await expect(page.getByTestId("mail-archive")).toHaveCount(0);
  await expect(page.getByTestId("mail-bin")).toHaveCount(0);
  await expect(page.getByTestId("mail-reply")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mail-sent.png") });

  // A conversation you wrote in twice opens whole, the newest message unfolded.
  await rows.nth(1).click();
  await expect(page.getByTestId("mail-message")).toHaveCount(2);
  await expect.poll(() => frameText(page)).toContain("we start at nine");

  await page.getByTestId("mail-tab-all").click();
  await expect(rows).toHaveCount(3);
  await expect(page.getByTestId("mail-reader")).toHaveCount(0);
});

test("a mailbox with no Sent folder says so under Sent, not that nothing was sent", async ({ page }, testInfo) => {
  await page.route("**/v1/mail/status", (route) =>
    route.fulfill({
      json: {
        ok: true, connected: true, address: "me@example.com", syncing: false, revision: 1,
        last_sync: Math.floor(Date.now() / 1000) - 60, last_error: "", can_archive: true, can_bin: true,
        has_sent: false, sorting: false, sorting_asked: true,
      },
    }),
  );
  await openMail(page);
  await page.getByTestId("mail-tab-sent").click();
  await expect(page.getByTestId("mail-list-empty")).toHaveText("Mail could not find a Sent folder in this mailbox.");
  // The tab's underline fades across; the picture is taken with it where it ends up.
  await page.screenshot({ path: testInfo.outputPath("mail-no-sent-folder.png"), animations: "disabled" });
});

test("a question about the open conversation opens a chat that is handed the conversation", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-row").first().click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Plan for Friday");
  await expect.poll(() => frameText(page)).toContain("Friday at ten");
  await page.getByTestId("mail-ask").click();
  await expect(page.getByTestId("mail-ask-scope")).toContainText("the conversation you have open");
  await page.getByTestId("mail-ask-question").fill("What does Ana want from me?");
  await page.screenshot({ path: testInfo.outputPath("mail-ask.png"), animations: "disabled" });
  await page.getByTestId("mail-ask-question").press("Enter");

  // Mail gives way to a new chat, with the question asked once and the conversation beside it.
  await expect(page.getByTestId("mail-page")).toHaveCount(0);
  const bubble = page.locator(".bubble-user");
  await expect(bubble).toHaveCount(1);
  await expect(bubble).toContainText("What does Ana want from me?");
  await expect(bubble.locator(".msg-file")).toContainText("Plan for Friday.txt");
  const sent = (page as any).userMessages as { text: string; attachments?: { kind: string; text: string }[] }[];
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0].text).toBe("What does Ana want from me?");
  expect(sent[0].attachments).toHaveLength(1);
  expect(sent[0].attachments![0].kind).toBe("text");
  // Both messages of the conversation, the earlier one first.
  const handed = sent[0].attachments![0].text;
  expect(handed).toContain("From: Ana Lopez <ana@example.com>");
  expect(handed.indexOf("Can we plan Friday?")).toBeGreaterThan(-1);
  expect(handed.indexOf("Can we plan Friday?")).toBeLessThan(handed.indexOf("Friday at ten"));
  await page.screenshot({ path: testInfo.outputPath("mail-ask-chat.png"), animations: "disabled" });
});

test("a question asked with nothing open tells Mimi to look in the mailbox, and hands over no mail", async ({ page }, testInfo) => {
  await openMail(page);
  await expect(page.getByTestId("mail-ask-panel")).toHaveCount(0);
  await page.getByTestId("mail-ask").click();
  await expect(page.getByTestId("mail-ask-scope")).toContainText("look in your mailbox");
  await expect(page.getByTestId("mail-ask-send")).toBeDisabled();
  await page.getByTestId("mail-ask-question").fill("What did Ana ask me for last week?");
  await page.screenshot({ path: testInfo.outputPath("mail-ask-mailbox.png"), animations: "disabled" });
  await page.getByTestId("mail-ask-send").click();

  await expect(page.getByTestId("mail-page")).toHaveCount(0);
  await expect(page.locator(".bubble-user")).toContainText("What did Ana ask me for last week?");
  const sent = (page as any).userMessages as { text: string; attachments?: unknown[] }[];
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0].text).toBe("What did Ana ask me for last week?\n\nLook in my mailbox to answer this.");
  expect(sent[0].attachments).toBeUndefined();
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
