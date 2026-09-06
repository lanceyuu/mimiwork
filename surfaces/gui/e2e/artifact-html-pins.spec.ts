import { writeFileSync } from "node:fs";
import { test, expect } from "./fixtures";

// Comments on an HTML file Mimi produced (owner report 2026-09-04: "not stable to annotate
// and add comment to a html"). The preview is an iframe, which swallows clicks — so a
// click INSIDE the page must drop a pin there, the marker must live in the page (scrolls
// with it), and Send must ship the numbered screenshot with the notes.

const HTML = `<!doctype html><html><body style="margin:0;padding:24px;font-family:sans-serif">
<h1 id="title">Stimulus A — flagship store</h1>
<p>The first paragraph explains the setting of the study.</p>
<div style="height:1400px"></div>
<p id="deep">A paragraph far down the page, reachable only by scrolling.</p>
</body></html>`;

async function openHtmlArtifact(page: any, html = HTML) {
  await page.route("**/v1/sessions/*/artifacts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        artifacts: [{ path: "stimulus_A.html", name: "stimulus_A.html", kind: "html", size: 512, modified_at: 2 }],
      }),
    });
  });
  await page.route("**/v1/sessions/*/artifacts/read?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, path: "stimulus_A.html", kind: "html", content: html }),
    });
  });
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByText("stimulus_A.html").first().click();
  const frame = page.frameLocator(".artifact-frame");
  await expect(frame.locator("#title")).toBeVisible();
  return frame;
}

test("untrusted HTML cannot execute scripts or read the parent token, including after reload", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "__COWORKER_API_TOKEN__", { value: "dummy-preview-secret" });
  });
  const attack = `parent.document.body.dataset.stolenToken = parent.__COWORKER_API_TOKEN__;
    document.body.dataset.scriptRan = 'yes';`;
  const html = HTML.replace("</body>", `<script>${attack}</script>
    <img src="data:image/png;base64,broken" onerror="${attack}">
    <button id="attack" onclick="${attack}">Try script</button>
    <iframe id="nested" sandbox="allow-scripts allow-same-origin" srcdoc="<script>parent.parent.document.body.dataset.stolenToken = 'nested';</script>"></iframe>
    </body>`);
  const frame = await openHtmlArtifact(page, html);
  for (let attempt = 0; attempt < 2; attempt++) {
    await expect(frame.locator("#nested")).toBeAttached();
    await frame.locator("#attack").click();
    await expect(frame.locator("body")).not.toHaveAttribute("data-script-ran", "yes");
    await expect(page.locator("body")).not.toHaveAttribute("data-stolen-token");
    // The host's annotation listener must still work even though document code cannot run.
    await expect(page.getByTestId("artifact-draft")).toBeVisible();
    if (attempt === 0) await page.getByRole("button", { name: "Reload preview" }).click();
  }
});

test("a click inside the HTML preview pins a comment there, and Send ships it with a screenshot", async ({ page }) => {
  const frame = await openHtmlArtifact(page);

  await frame.locator("#title").click();
  const draft = page.getByTestId("artifact-draft");
  await expect(draft).toBeVisible();
  await expect(draft).toContainText("h1 “Stimulus A — flagship store”");
  await page.getByTestId("artifact-draft-text").fill("make this title smaller");
  await page.getByTestId("artifact-draft-add").click();

  // The marker is painted in the page itself, numbered.
  await expect(frame.locator("[data-mimi-pin]")).toHaveCount(1);
  await expect(frame.locator("[data-mimi-pin]")).toHaveText("1");
  await expect(page.getByTestId("artifact-pin-row")).toHaveCount(1);

  // A second pin far down the page: the frame scrolls, the marker stays with its text.
  await frame.locator("#deep").scrollIntoViewIfNeeded();
  await frame.locator("#deep").click();
  await page.getByTestId("artifact-draft-text").fill("cut this one");
  await page.getByTestId("artifact-draft-add").click();
  await expect(frame.locator("[data-mimi-pin]")).toHaveCount(2);
  const pinTop = await frame.locator("[data-mimi-pin='2']").evaluate((el: HTMLElement) => parseFloat(el.style.top));
  const textTop = await frame.locator("#deep").evaluate((el: HTMLElement) => el.getBoundingClientRect().top + el.ownerDocument.defaultView!.scrollY);
  expect(Math.abs(pinTop - textTop)).toBeLessThan(40);

  await page.screenshot({ path: "test-results/html-pins.png" });

  await page.getByTestId("artifact-send-all").click();
  const bubble = page.locator(".bubble-user").last();
  await expect(bubble).toContainText("Feedback on `stimulus_A.html` — 2 comments");
  await expect(bubble).toContainText("1. (h1 “Stimulus A — flagship store”) make this title smaller");
  await expect(bubble).toContainText("2. (p “A paragraph far down the page, reachable only…”) cut this one");
  // The numbered screenshot rode along.
  await expect(bubble.locator("img.msg-img")).toHaveCount(1);
  const src = await bubble.locator("img.msg-img").getAttribute("src");
  expect(src).toMatch(/^data:image\/jpeg/);
  // Keep the capture where a person can look at it (the model sees exactly this).
  writeFileSync("test-results/html-pins-shot.jpg", Buffer.from(src!.split(",")[1], "base64"));
  await expect(frame.locator("[data-mimi-pin]")).toHaveCount(0);
});
