// Start-screen template tasks (§27): three concrete rows, no icon tiles, no "Set me up" list.
// Sub-lines are outcome-voiced; connection state lives in the dots + the trailing action.
// Gated row (source not live for this session) → "Configure ›" expands the rail's Access
// section (§32); ready row → click prefills the composer with the template stem.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("three rows, no Set-me-up; gated rows show Configure › and expand the rail's Access section", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("What should we produce?")).toBeVisible();

  await expect(page.locator(".deliverable-starter")).toHaveCount(3);
  await page.getByText("More ways to start", { exact: true }).click();
  // The three secondary workflows remain available.
  await expect(page.locator(".intro-more .task-card")).toHaveCount(3);
  await expect(page.getByText("Set me up (optional)")).toHaveCount(0);
  await expect(page.getByText("Give me access to a folder")).toHaveCount(0);

  // Fixture session state: canva is not connected → that row is gated, with the Configure
  // affordance visible AT REST (no hover needed — it IS the row's action). The skill row
  // needs no source at all, so it is always ready.
  const canva = page.getByTestId("intro-task-canva");
  await expect(canva).toContainText("Configure ›");
  await expect(canva.locator(".task-card-act")).toHaveCSS("opacity", "1");
  await expect(page.getByTestId("intro-task-skill")).toContainText("Start →");

  // Sub-lines describe the task's outcome, never connection state.
  await expect(canva).toContainText("I'll pull the design you pick and build the slides");
  await expect(canva).not.toContainText(/connect/i);

  // Configure → the rail's Access section expands (§32), not a bespoke setup surface.
  await canva.click();
  await expect(page.getByRole("region", { name: "Session access" })).toBeVisible();
  // No composer prefill happened on the gated click.
  await expect(page.getByPlaceholder(/Ask the coworker/)).toHaveValue("");
});

test("ready rows reveal Start → on hover and prefill the composer", async ({ page }) => {
  // Make every source live for this session (registered after the fixture's routes → wins).
  await page.route("**/v1/sessions/*/connections*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        connected: [
          { connector: "canva", enabled: true, detail: "" },
          { connector: "github", enabled: true, detail: "" },
          { connector: "slack", enabled: true, detail: "" },
        ],
        recommended: [],
        attention: 0,
      }),
    }),
  );
  await page.goto("/");

  await page.getByText("More ways to start", { exact: true }).click();
  const canva = page.getByTestId("intro-task-canva");
  await expect(canva).toContainText("Start →");
  // The action is hover-revealed on ready rows (hidden at rest).
  await expect(canva.locator(".task-card-act")).toHaveCSS("opacity", "0");
  await canva.hover();
  await expect(canva.locator(".task-card-act")).toHaveCSS("opacity", "1");

  await canva.click();
  await expect(page.getByPlaceholder(/Ask the coworker/)).toHaveValue(/Canva designs/);

  // The skill row needs no source; its prefill is the fill-in-the-blanks brand brief.
  const skill = page.getByTestId("intro-task-skill");
  await expect(skill).toContainText("Start →");
  await skill.click();
  await expect(page.getByPlaceholder(/Ask the coworker/)).toHaveValue(/Package my style guidelines/);
});

test("folder task opens the inline add-folder form; adding a folder prefills the composer", async ({
  page,
}) => {
  await page.goto("/");

  // No shared folder yet (the fixture root is the primary scratch) → the row expands the form.
  await page.getByText("More ways to start", { exact: true }).click();
  await page.getByTestId("intro-task-folder").click();
  const path = page.getByPlaceholder("Choose or paste a folder path…");
  await expect(path).toBeVisible();
  await path.fill("/Users/me/Reports");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  await expect(page.getByPlaceholder(/Ask the coworker/)).toHaveValue(
    /Work in this folder/,
  );
});
