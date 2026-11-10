import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { TRACKER } from "./mail-data";

// An email is untrusted. These three tests open a hostile one and check that nothing in it
// runs, loads or navigates. They run in WebKit as well as Chromium (see playwright.config.ts),
// because the macOS app is a WebKit webview and the two treat a sandboxed frame differently.

// A retry would let a test that fails only sometimes pass, and "sometimes unsafe" is unsafe.
test.describe.configure({ retries: 0 });

const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

/** Open the hostile email and return the list every request to its sender's server lands in. */
async function openHostile(page: Page): Promise<string[]> {
  const asked: string[] = [];
  // Counted where a request would leave the browser. A request the policy refuses never
  // gets this far, though the browser still reports having considered it.
  await page.route(`${TRACKER}/**`, (route) => {
    asked.push(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 200, contentType: "image/png", body: PIXEL });
  });
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  await page.getByTestId("mail-row").filter({ hasText: "You have won" }).click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  return asked;
}

const inFrame = <T>(page: Page, read: string) =>
  page.evaluate(`(() => {
    const frame = document.querySelector('[data-testid="mail-frame"]');
    const doc = frame.contentDocument, win = frame.contentWindow;
    return (${read});
  })()`) as Promise<T>;

async function clickInFrame(page: Page, selector: string) {
  const point = await page.evaluate((sel) => {
    const frame = document.querySelector<HTMLIFrameElement>('[data-testid="mail-frame"]')!;
    const target = Document.prototype.querySelector.call(frame.contentDocument!, sel)!;
    target.scrollIntoView({ block: "center" });
    const outer = frame.getBoundingClientRect();
    const inner = target.getBoundingClientRect();
    return { x: outer.x + inner.x + inner.width / 2, y: outer.y + inner.y + inner.height / 2 };
  }, selector);
  await page.mouse.click(point.x, point.y);
}

test("an email's script, its onerror handler and its meta refresh do not run", async ({ page }) => {
  const asked = await openHostile(page);
  // Long enough for a refresh set to zero seconds, and for a script, to have acted.
  await page.waitForTimeout(1500);
  expect(asked).toEqual([]);
  expect(await inFrame<string>(page, "String(win.__ran)")).toBe("undefined");
  expect(await inFrame<string>(page, "win.location.href")).toBe("about:srcdoc");
  expect(await inFrame<string>(page, "Document.prototype.querySelector.call(doc, '#hello').textContent")).toContain("You have won");
});

test("an email's remote image, stylesheet and background are not requested until Show images", async ({ page }) => {
  const asked = await openHostile(page);
  await page.waitForTimeout(1000);
  expect(asked).toEqual([]);

  await page.getByTestId("mail-show-images").click();
  await expect.poll(() => asked).toContain("/pixel.png");
  await page.waitForTimeout(500);
  // Images, and nothing else: no stylesheet, no script, no page.
  expect(asked.filter((path) => !path.endsWith(".png"))).toEqual([]);
});

test("clicking a link in an email requests nothing and shows the address instead", async ({ page }) => {
  const asked = await openHostile(page);
  for (const [selector, address] of [
    ["#plain", `${TRACKER}/plain`],
    ["#self", `${TRACKER}/self`],
    ["#svg-text", `${TRACKER}/svg`],
  ]) {
    await clickInFrame(page, selector);
    await expect(page.getByTestId("mail-link-address")).toHaveText(address);
  }

  // A link that gets its address from an SVG animation has none here: the animation is gone.
  await clickInFrame(page, "#smil-text");
  await expect(page.getByTestId("mail-link-card")).toHaveCount(0);
  // A link inside a template, or after a noscript trick, is not in the email at all.
  const text = await inFrame<string>(page, "Document.prototype.querySelector.call(doc, 'body').innerText");
  expect(text).not.toContain("Shadow link");
  expect(text).not.toContain("Noscript link");

  await page.waitForTimeout(500);
  expect(asked).toEqual([]);
  expect(await inFrame<string>(page, "win.location.href")).toBe("about:srcdoc");
});
