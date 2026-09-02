import { test, expect } from "./fixtures";

// The flow diagram's nodes are buttons: a click opens the node's panel (rename, remove,
// change the schedule, ask Mimi…). This runs in a real browser on purpose — pointer
// capture once retargeted every node click to the svg, invisibly to jsdom (2026-09-02).

test("clicking a node opens its panel; the schedule node edits in place", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-automations").click();
  await page.getByText("Daily AI News").first().click();
  await page.getByTestId("automation-flow").waitFor();

  await page.getByTestId("flow-node-step-0").click();
  const panel = page.getByTestId("flow-note");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("flow-rename")).toBeVisible();

  await page.getByTestId("flow-node-trigger").click();
  await expect(page.getByTestId("flow-trigger")).toBeVisible();

  // Dragging a node moves it and does not open a panel for it.
  await page.getByTestId("flow-node-agent").click();
  await expect(page.getByTestId("flow-model")).toBeVisible();
  const box = (await page.getByTestId("flow-node-output").boundingBox())!;
  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + 120, box.y + 60, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByTestId("flow-model")).toBeVisible(); // still the agent's panel
  await expect(page.getByTestId("flow-reset")).toBeVisible();
});
