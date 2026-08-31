import { test, expect } from "./fixtures";

// Right-click a file MimiWork produced (owner ask 2026-08-31): open it in the program that
// owns it, or show it where it lives. Left-click keeps its meaning — the in-app preview.

/** Open any conversation whose transcript carries a produced-file chip.
 *
 *  The transcript is stubbed HERE rather than in the shared fixture: seeding an extra
 *  session there changes the counts several other specs assert on. */
async function openTranscriptWithChip(page: any) {
  await page.route("**/v1/sessions/*/messages", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        messages: [
          { role: "user", content: "write the brief" },
          {
            role: "assistant",
            content: "Done — [Launch brief](<artifact:reports/Launch brief.docx>)",
          },
        ],
      }),
    });
  });
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  const chip = page.getByTestId("artifact-chip").first();
  await expect(chip).toBeVisible();
  return chip;
}

test("right-click offers Open and Show, and Show asks the server to reveal it", async ({ page }) => {
  const posts: any[] = [];
  await page.route("**/v1/sessions/*/artifacts/reveal", async (route) => {
    posts.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });

  const chip = await openTranscriptWithChip(page);
  await chip.click({ button: "right" });

  const menu = page.getByTestId("artifact-menu");
  await expect(menu).toBeVisible();
  await expect(page.getByTestId("artifact-menu-open")).toBeVisible();

  await page.getByTestId("artifact-menu-reveal").click();
  await expect(menu).toHaveCount(0);
  await expect.poll(() => posts.length).toBe(1);
  // The path survives its spaces on the way through markdown's URL encoding.
  expect(posts[0]).toEqual({ path: "reports/Launch brief.docx", mode: "reveal" });
});

test("Open file asks to open, not to reveal", async ({ page }) => {
  const posts: any[] = [];
  await page.route("**/v1/sessions/*/artifacts/reveal", async (route) => {
    posts.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });

  const chip = await openTranscriptWithChip(page);
  await chip.click({ button: "right" });
  await page.getByTestId("artifact-menu-open").click();

  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].mode).toBe("open");
});

test("the menu names the file manager the person in front of the machine uses", async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__OCW_PLATFORM__ = "macos";
  });
  const chip = await openTranscriptWithChip(page);
  await chip.click({ button: "right" });
  await expect(page.getByTestId("artifact-menu-reveal")).toContainText("Finder");
});

test("Escape and clicking away close the menu without doing anything", async ({ page }) => {
  let calls = 0;
  await page.route("**/v1/sessions/*/artifacts/reveal", async (route) => {
    calls += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });

  const chip = await openTranscriptWithChip(page);
  await chip.click({ button: "right" });
  await expect(page.getByTestId("artifact-menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("artifact-menu")).toHaveCount(0);

  await chip.click({ button: "right" });
  await expect(page.getByTestId("artifact-menu")).toBeVisible();
  await page.mouse.click(700, 560);
  await expect(page.getByTestId("artifact-menu")).toHaveCount(0);

  expect(calls).toBe(0);
});
