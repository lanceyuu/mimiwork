import { test, expect } from "./fixtures";
import { MAIL_MESSAGES } from "./mail-data";
import type { Page } from "@playwright/test";

// Comments and the reply: select a passage of an email, comment on it, have Mimi write
// one reply from the comments, edit it and send it. The email sits in a frame where
// nothing can run, so the tests select with the pointer, as a person does, and read the
// frame from outside, as the app does. This file runs in WebKit as well as Chromium.

async function openMail(page: Page) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  await expect(page.getByTestId("mail-row")).toHaveCount(3);
}

async function openPlan(page: Page) {
  await page.getByTestId("mail-row").first().click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
}

/** Where a word sits on the page, in whichever shown email holds it: its left edge, its
 *  right edge and its middle. */
async function wordBox(page: Page, word: string) {
  const box = await page.evaluate((wanted) => {
    for (const frame of document.querySelectorAll<HTMLIFrameElement>('[data-testid="mail-frame"]')) {
      const doc = frame.contentDocument!;
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const at = (node.textContent || "").indexOf(wanted);
        if (at < 0) continue;
        const range = doc.createRange();
        range.setStart(node, at);
        range.setEnd(node, at + wanted.length);
        const inner = range.getBoundingClientRect();
        const outer = frame.getBoundingClientRect();
        const y = outer.y + inner.y + inner.height / 2;
        return { left: outer.x + inner.x, right: outer.x + inner.x + inner.width, y };
      }
    }
    return null;
  }, word);
  expect(box, `"${word}" is in a shown email`).not.toBeNull();
  return box!;
}

/** Double-click a word in a shown email, which selects it. */
async function selectWord(page: Page, word: string) {
  const box = await wordBox(page, word);
  await page.mouse.dblclick((box.left + box.right) / 2, box.y);
}

const marked = (page: Page) =>
  page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLIFrameElement>('[data-testid="mail-frame"]')).flatMap((frame) =>
      Array.from(frame.contentDocument?.querySelectorAll("mark[data-mail-comment]") ?? []).map((m) => m.textContent),
    ),
  );

async function comment(page: Page, word: string, note: string) {
  await selectWord(page, word);
  await expect(page.getByTestId("mail-comment-add")).toBeEnabled();
  await page.getByTestId("mail-comment-add").click();
  await expect(page.getByTestId("mail-comment").last()).toContainText(word);
  await page.getByTestId("mail-comment-note").last().fill(note);
}

test("two passages are commented on, Mimi writes one reply from them, and it is edited and sent", async ({ page }, testInfo) => {
  const saved: { url: string; body: any }[] = [];
  page.on("request", (req) => {
    if (req.method() === "PUT" && req.url().includes("/v1/mail/")) saved.push({ url: req.url(), body: req.postDataJSON() });
  });
  await openMail(page);
  await openPlan(page);
  // Nothing is selected yet, and there is nothing to write a reply from.
  await expect(page.getByTestId("mail-comment-add")).toBeDisabled();
  await expect(page.getByTestId("mail-write-reply")).toBeDisabled();
  await expect(page.getByTestId("mail-write-hint")).toBeVisible();

  await comment(page, "meet", "Yes, ten works.");
  await comment(page, "attached", "Thanks, I have it.");
  await expect(page.getByTestId("mail-comment")).toHaveCount(2);
  // Each passage is marked in the email itself.
  await expect.poll(() => marked(page)).toEqual(["meet", "attached"]);
  await expect(page.getByTestId("mail-write-hint")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("mail-comments.png") });

  await page.getByTestId("mail-write-reply").click();
  const body = page.getByTestId("mail-draft-body");
  await expect(body).toHaveValue("Hi Ana,\n\nYes, ten works. Thanks, I have it.\n\nBest,\nMe");
  await expect(page.getByTestId("mail-draft-to")).toHaveValue("Ana Lopez <ana@example.com>");
  await expect(page.getByTestId("mail-draft-subject")).toHaveValue("Re: Plan for Friday");
  // The comments were saved before Mimi was asked, both of them, in the order made.
  const notes = saved.filter((s) => s.url.endsWith("/comments")).at(-1)!.body;
  expect(notes.comments.map((c: any) => [c.message_id, c.quote, c.note])).toEqual([
    ["<2@example.com>", "meet", "Yes, ten works."],
    ["<2@example.com>", "attached", "Thanks, I have it."],
  ]);
  await page.screenshot({ path: testInfo.outputPath("mail-reply-draft.png") });

  // Rewrite, with one line on how.
  await page.getByTestId("mail-rewrite-guidance").fill("shorter");
  await page.getByTestId("mail-rewrite").click();
  await expect(body).toHaveValue("Hi Ana, Yes, ten works. Thanks, I have it. Me");

  // The text is the user's to change, and what is sent is what is on screen.
  await body.fill("Hi Ana, ten works, and thanks for the plan. See you Friday.");
  await page.getByTestId("mail-send").click();
  await expect(page.getByTestId("mail-notice")).toHaveText("Sent.");
  await expect(page.getByTestId("mail-reader")).toHaveCount(0);
  expect(saved.filter((s) => s.url.includes("/drafts/")).at(-1)!.body.body).toBe(
    "Hi Ana, ten works, and thanks for the plan. See you Friday.",
  );
  // The reply answered the comments, so they are gone, and so is the draft.
  await openPlan(page);
  await expect(page.getByTestId("mail-comment")).toHaveCount(0);
  await expect(page.getByTestId("mail-composer")).toHaveCount(0);
  await expect(page.getByTestId("mail-reply")).toBeVisible();
});

test("a comment and an unsent reply are still there when the conversation is opened again", async ({ page }, testInfo) => {
  await openMail(page);
  await openPlan(page);
  await comment(page, "attached", "Got it.");
  await page.getByTestId("mail-free-note").fill("Wish her a good trip.");
  await page.getByTestId("mail-reply-all").click();
  await expect(page.getByTestId("mail-draft-cc")).toHaveValue("Team <team@example.com>");
  await page.getByTestId("mail-draft-body").fill("Half a thought");

  await page.getByTestId("mail-row").nth(1).click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Your invoice for October");
  await expect(page.getByTestId("mail-comment")).toHaveCount(0);

  await openPlan(page);
  await expect(page.getByTestId("mail-comment")).toHaveCount(1);
  await expect(page.getByTestId("mail-comment-note")).toHaveValue("Got it.");
  await expect(page.getByTestId("mail-free-note")).toHaveValue("Wish her a good trip.");
  await expect(page.getByTestId("mail-draft-body")).toHaveValue("Half a thought");
  await expect.poll(() => marked(page)).toEqual(["attached"]);

  // Removing the comment takes its mark off the email.
  await page.getByTestId("mail-comment-remove").click();
  await expect(page.getByTestId("mail-comment")).toHaveCount(0);
  await expect.poll(() => marked(page)).toEqual([]);

  // Discarding asks first, and brings Reply back.
  await page.getByTestId("mail-discard").click();
  await expect(page.getByText("Discard this draft?")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mail-discard-dialog.png") });
  await page.getByRole("button", { name: "Discard" }).last().click();
  await expect(page.getByTestId("mail-composer")).toHaveCount(0);
  await expect(page.getByTestId("mail-reply")).toBeVisible();
});

test("a new message is kept under Drafts until it is sent", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-new").click();
  await expect(page.getByTestId("mail-composer")).toBeVisible();
  await expect(page.getByTestId("mail-send")).toBeDisabled();
  // A new message has no comments to be rewritten from.
  await expect(page.getByTestId("mail-rewrite")).toHaveCount(0);
  await page.getByTestId("mail-draft-to").fill("ben@example.com");
  await page.getByTestId("mail-draft-subject").fill("Lunch on Thursday");
  await page.getByTestId("mail-draft-body").fill("Are you free at noon?");
  // Its row in the list follows what is typed.
  await expect(page.getByTestId("mail-row").first()).toContainText("Lunch on Thursday");
  await page.screenshot({ path: testInfo.outputPath("mail-new-message.png") });

  // Leaving saves it. It is listed under Drafts, and opens again with what was typed.
  await page.getByTestId("mail-tab-all").click();
  await expect(page.getByTestId("mail-row")).toHaveCount(3);
  await page.getByTestId("mail-tab-drafts").click();
  const rows = page.getByTestId("mail-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("ben@example.com");
  await expect(rows.first()).toContainText("Lunch on Thursday");
  await page.screenshot({ path: testInfo.outputPath("mail-drafts-tab.png") });
  await rows.first().click();
  await expect(page.getByTestId("mail-draft-body")).toHaveValue("Are you free at noon?");

  await page.getByTestId("mail-send").click();
  await expect(page.getByTestId("mail-notice")).toHaveText("Sent.");
  await expect(page.getByTestId("mail-list-empty")).toHaveText("No drafts.");
});

test("when Mimi cannot write the reply the reason is shown and the comments stay", async ({ page }, testInfo) => {
  await page.route("**/v1/mail/reply", (route) =>
    route.fulfill({ json: { ok: false, error: "Mimi could not write the reply. Your account is out of quota for mimi-wolf." } }),
  );
  await openMail(page);
  await openPlan(page);
  await page.getByTestId("mail-free-note").fill("Say yes.");
  await page.getByTestId("mail-write-reply").click();
  await expect(page.getByTestId("mail-draft-error")).toContainText("Mimi could not write the reply. Your account is out of quota");
  await expect(page.getByTestId("report-problem")).toBeVisible();
  await expect(page.getByTestId("mail-free-note")).toHaveValue("Say yes.");
  // The reply that was started only to be written is not left behind, here or under Drafts.
  await expect(page.getByTestId("mail-composer")).toHaveCount(0);
  await expect(page.getByTestId("mail-reply")).toBeVisible();
  await expect(page.getByTestId("mail-tab-drafts")).toHaveText("Drafts");
  await page.screenshot({ path: testInfo.outputPath("mail-reply-error.png") });
});

test("in a narrow window the comments sit beneath the email", async ({ page }, testInfo) => {
  await openMail(page);
  await openPlan(page);
  // Side by side while there is room.
  const beside = (await page.getByTestId("mail-comments").boundingBox())!;
  expect(beside.x).toBeGreaterThan((await page.getByTestId("mail-reader").boundingBox())!.x + 300);
  await page.setViewportSize({ width: 1040, height: 900 });
  const reader = (await page.getByTestId("mail-reader").boundingBox())!;
  const comments = (await page.getByTestId("mail-comments").boundingBox())!;
  expect(comments.y).toBeGreaterThanOrEqual(reader.y + reader.height);
  await page.screenshot({ path: testInfo.outputPath("mail-narrow.png") });
});

test("with two messages open, the comment goes on the one selected last", async ({ page }) => {
  const saved: any[] = [];
  page.on("request", (req) => {
    if (req.method() === "PUT" && req.url().endsWith("/comments")) saved.push(req.postDataJSON());
  });
  await openMail(page);
  await openPlan(page);
  // The earlier message is folded; open it too.
  await page.getByTestId("mail-message").first().getByRole("button").first().click();
  await expect(page.getByTestId("mail-frame")).toHaveCount(2);
  await expect.poll(() => page.evaluate(() => document.querySelectorAll('[data-testid="mail-frame"][style*="visible"]').length)).toBe(2);

  // Select in the earlier one, then the later one, then the earlier one again. Each
  // email keeps its own selection, so the app has to follow which was made last.
  await selectWord(page, "Can");
  await expect(page.getByTestId("mail-comment-add")).toBeEnabled();
  await selectWord(page, "meet");
  await page.waitForTimeout(600);
  await selectWord(page, "Can");
  await page.waitForTimeout(600);
  await page.getByTestId("mail-comment-add").click();
  await expect(page.getByTestId("mail-comment")).toHaveCount(1);
  await page.getByTestId("mail-comment-note").fill("Yes.");
  await expect.poll(() => saved.at(-1)?.comments).toEqual([{ message_id: "<1@example.com>", quote: "Can", note: "Yes." }]);
  await expect.poll(() => marked(page)).toEqual(["Can"]);
});

test("a passage dragged across a link and a sentence is commented on whole", async ({ page, browserName }) => {
  test.skip(browserName !== "webkit", "the test tool's pointer stalls in the middle of a drag in Chromium");
  await openMail(page);
  await openPlan(page);
  const from = await wordBox(page, "Shall");
  const to = await wordBox(page, "attached");
  await page.mouse.move(from.left + 1, from.y);
  await page.mouse.down();
  await page.mouse.move(to.right - 1, to.y, { steps: 10 });
  await page.mouse.up();
  await expect(page.getByTestId("mail-comment-add")).toBeEnabled();
  await page.getByTestId("mail-comment-add").click();
  await expect(page.getByTestId("mail-comment")).toContainText("Shall we meet on Friday at ten? The plan is attached");
  await expect.poll(() => marked(page).then((parts) => parts.join(""))).toBe("Shall we meet on Friday at ten? The plan is attached");
});

test("while a message is on its way nothing can be sent twice or changed, and leaving does not lose the outcome", async ({ page }) => {
  let sends = 0;
  await page.route("**/v1/mail/drafts/*/send", async (route) => {
    sends += 1;
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await route.fallback();
  });
  await openMail(page);
  await openPlan(page);
  await page.getByTestId("mail-reply").click();
  await page.getByTestId("mail-draft-body").fill("See you Friday.");
  const send = page.getByTestId("mail-send");
  await send.click();
  await expect(send).toBeDisabled();
  await expect(send).toHaveText("Sending…");
  await send.click({ force: true }).catch(() => undefined);
  // The comments are held still too: a note typed now would outlive the send that clears them.
  await expect(page.getByTestId("mail-free-note")).toBeDisabled();
  await expect(page.getByTestId("mail-draft-body")).toBeDisabled();

  // The user does not wait, and opens another conversation.
  await page.getByTestId("mail-row").nth(1).click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Your invoice for October");
  // The message went. They are told, and what they are reading stays open.
  await expect(page.getByTestId("mail-notice")).toHaveText("Sent.");
  await expect(page.getByTestId("mail-subject")).toHaveText("Your invoice for October");
  expect(sends).toBe(1);
});

test("what the user typed can be put back after Mimi writes over it", async ({ page }) => {
  await openMail(page);
  await openPlan(page);
  await page.getByTestId("mail-reply").click();
  const body = page.getByTestId("mail-draft-body");
  await body.fill("My own words.");
  await page.getByTestId("mail-free-note").fill("Say yes.");
  await page.getByTestId("mail-write-reply").click();
  await expect(body).toHaveValue("Hi Ana,\n\nSay yes.\n\nBest,\nMe");
  await page.getByTestId("mail-restore").click();
  await expect(body).toHaveValue("My own words.");
  await expect(page.getByTestId("mail-restore")).toHaveCount(0);
});

test("a draft says when its send was cut short and when the conversation has moved on", async ({ page }, testInfo) => {
  await openMail(page);
  await openPlan(page);
  await page.getByTestId("mail-reply").click();
  await page.getByTestId("mail-draft-body").fill("Half a thought");
  await page.getByTestId("mail-row").nth(1).click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Your invoice for October");
  // As the backend would answer for a reply started on the first message and cut short mid-send.
  await page.route("**/v1/mail/drafts/draft-1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const draft = {
      id: "draft-1", thread_key: "a1a1a1a1a1a1a1a1", to: "Ana Lopez <ana@example.com>", cc: "",
      subject: "Re: Plan for Friday", body: "Half a thought", answers: "Ana Lopez <ana@example.com>",
      answers_id: "<1@example.com>", reply: true, interrupted: true, updated_at: 0,
    };
    await route.fulfill({ json: { ok: true, draft } });
  });
  await page.route("**/v1/mail/drafts/draft-1/send", (route) =>
    route.fulfill({ json: { ok: true, note: "Sent, but no copy could be saved in your Sent folder." } }),
  );
  await openPlan(page);
  await expect(page.getByTestId("mail-draft-interrupted")).toContainText("Check Sent before sending again");
  await expect(page.getByTestId("mail-draft-older")).toContainText("answers an earlier message");
  await page.getByTestId("mail-composer").scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("mail-draft-warnings.png") });
  // Neither locks it.
  await page.getByTestId("mail-send").click();
  await expect(page.getByTestId("mail-notice")).toHaveText("Sent, but no copy could be saved in your Sent folder.");
  await page.screenshot({ path: testInfo.outputPath("mail-sent-note.png") });
});

test("an email built to break the highlighting costs nothing", async ({ page }) => {
  // A highlight of the app's own kind, planted by the sender, holding more children than
  // can be handed over one by one. Before the fix this replaced the whole app with its
  // error screen in Chromium, every time the conversation was opened.
  const html = `<p>Hi there</p><mark data-mail-comment>${"<br>".repeat(140_000)}</mark><p>Bye</p>`;
  await page.route("**/v1/mail/message?*uid=3*", (route) =>
    route.fulfill({ json: { ok: true, ...MAIL_MESSAGES["INBOX/3"], draft: "", html } }),
  );
  await openMail(page);
  await page.getByTestId("mail-row").nth(1).click();
  await expect(page.getByTestId("mail-frame")).toBeVisible({ timeout: 20_000 });
  await selectWord(page, "there");
  await page.getByTestId("mail-comment-add").click();
  await expect.poll(() => marked(page)).toEqual(["there"]);
  await expect(page.getByTestId("mail-page")).toBeVisible();
  await expect(page.getByText("unexpected error")).toHaveCount(0);
});
