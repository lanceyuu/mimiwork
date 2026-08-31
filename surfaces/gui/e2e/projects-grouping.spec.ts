import { test, expect } from "./fixtures";

// A project GROUPS conversations (2026-08-31). Filing one moves it out of the flat list
// and under its project; the folder its files live in is never involved.

/** Drag one element onto another with a real, shared DataTransfer.
 *
 *  Playwright's dragTo simulates mouse movement, and Chrome does not carry a custom
 *  MIME type through that path — the sidebar's drop handler checks for its own type, so
 *  the drop silently never fires. Dispatching the three events with one DataTransfer
 *  exercises the app's actual handlers, which is the point of the test. */
async function dragOnto(page: any, sourceSel: string, targetSel: string) {
  await page.evaluate(
    ([src, dst]: [string, string]) => {
      const from = document.querySelector(src) as HTMLElement;
      const to = document.querySelector(dst) as HTMLElement;
      if (!from || !to) throw new Error(`drag: missing ${!from ? src : dst}`);
      const dt = new DataTransfer();
      from.dispatchEvent(new DragEvent("dragstart", { dataTransfer: dt, bubbles: true }));
      to.dispatchEvent(new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true }));
      to.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    },
    [sourceSel, targetSel],
  );
}

async function makeProject(page: any, name: string) {
  await page.getByTestId("projects-new").click();
  const field = page.getByTestId("project-name");
  await expect(field).toBeVisible();
  await field.fill(name);
  await field.blur();
  // Back to the conversation list.
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await expect(page.getByTestId("project-row").first()).toContainText(name);
}

test("filing a conversation moves it out of the list and under its project", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await makeProject(page, "Thesis");

  await expect(page.getByTitle("Weekly plan 1")).toHaveCount(1);
  await dragOnto(page, '[title="Weekly plan 1"]', '[data-testid="project-row"]');

  // It leaves the flat list…
  await expect(
    page.getByTestId("session-row").filter({ hasText: "Weekly plan 1" }),
  ).toHaveCount(0);
  // …and the project's own count picks it up.
  await expect(page.getByTestId("project-row").first()).toContainText("1");
  // …and it is there when the project is expanded.
  await page.getByTestId("project-toggle").first().click();
  await expect(
    page.getByTestId("project-session-row").filter({ hasText: "Weekly plan 1" }),
  ).toHaveCount(1);
});

test("search still reaches a conversation after it has been filed", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await makeProject(page, "Fieldwork");

  await dragOnto(page, '[title="Weekly plan 2"]', '[data-testid="project-row"]');
  await expect(
    page.getByTestId("session-row").filter({ hasText: "Weekly plan 2" }),
  ).toHaveCount(0);

  // Grouping organises; it must never hide something from search.
  await page.getByRole("button", { name: "Search" }).click();
  await page.keyboard.type("Weekly plan 2");
  await expect(page.getByText("Weekly plan 2").first()).toBeVisible();
});
