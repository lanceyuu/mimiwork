import { test, expect } from "./fixtures";

// Agents (agent systems): pick a pattern from the gallery, edit the diagram, see it save,
// run it in a chat, and watch the run light up the agents back on the Agents page.

test("a pattern becomes an editable system that saves, runs in a chat and shows its run", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-agents").click();

  // The gallery: nine patterns in the deck's four groups, each with a small picture.
  const gallery = page.getByTestId("agents-gallery");
  for (const group of ["Flow", "Loops", "Capabilities", "Collaboration"]) await expect(gallery).toContainText(group);
  await expect(gallery.locator(".ag-pattern")).toHaveCount(9);
  await expect(page.getByTestId("agent-pattern-reflection").locator(".ag-node")).toHaveCount(2);
  await page.screenshot({ path: testInfo.outputPath("agents-overview.png"), fullPage: true });

  await page.getByTestId("agent-pattern-sequence").click();
  await expect(page.getByTestId("agent-system-title")).toHaveText("Sequence");
  await expect(page.getByTestId("agent-canvas").locator(".ag-node")).toHaveCount(3);
  await expect(page.getByTestId("agents-band")).toContainText("Sequence");
  // Connections are drawn once the nodes are measured.
  await expect(page.locator(".react-flow__edge")).toHaveCount(2);

  // Add a Mimi agent: it opens its settings, saves, and the server's problem is pinned on it.
  const saved = page.waitForRequest((r) => r.method() === "PATCH" && r.url().includes("/v1/agent-systems/"));
  await page.getByTestId("agent-add-agent").click();
  await saved;
  const added = page.getByTestId("agent-node-n4");
  await expect(added.getByTestId("agent-node-problem")).toHaveText("Tell this agent what to do.");
  await expect(page.getByTestId("agent-save-state")).toHaveText("Saved");

  // Fill it in: instructions, a model, high effort, a tool, and a connection from the last step.
  await page.getByTestId("node-name").fill("Check the tone");
  await page.getByTestId("node-instructions").fill("Make sure the reply is warm and short.");
  await page.getByTestId("node-model").selectOption({ index: 1 });
  await page.getByTestId("node-effort").selectOption("high");
  await page.getByTestId("node-tools").getByLabel("Files", { exact: true }).check();
  await expect(added.getByTestId("agent-node-problem")).toHaveCount(0);
  await page.getByTestId("agent-node-draft").click();
  await page.getByTestId("node-connect").selectOption({ label: "Check the tone" });
  await expect(page.locator(".react-flow__edge")).toHaveCount(3);
  await page.getByTestId("agent-node-n4").click();
  await expect(page.getByTestId("node-inspector")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("agents-canvas-inspector.png") });

  // Each choice has a "?" note; the effort one explains the levels, the toolbar one the steps.
  await page.getByTestId("help-effort").click();
  await expect(page.getByRole("note")).toContainText("Low for sorting");
  await page.screenshot({ path: testInfo.outputPath("agents-help-effort.png") });
  await page.keyboard.press("Escape");
  await page.getByTestId("help-guide").click();
  await expect(page.getByRole("note")).toContainText("How to build a team");
  await page.screenshot({ path: testInfo.outputPath("agents-help-guide.png") });
  await page.keyboard.press("Escape");
  await page.getByTestId("help-kinds").click();
  await expect(page.getByRole("note")).toContainText("Lead agent.");
  await page.screenshot({ path: testInfo.outputPath("agents-help-kinds.png") });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("note")).toHaveCount(0);

  // The saved design is what the canvas shows (autosave waits for a pause, so poll).
  const stored = () => page.evaluate(async () => (await (await fetch("/v1/agent-systems")).json()).systems[0]);
  await expect
    .poll(async () => (await stored()).edges.some((e: any) => e.from === "draft" && e.to === "n4" && e.kind === "flow"))
    .toBe(true);
  expect((await stored()).nodes.find((n: any) => n.id === "n4")).toMatchObject({
    name: "Check the tone", effort: "high", tools: ["files"],
  });

  // A coding agent shows its own fields.
  await page.getByTestId("agent-add-coding").click();
  await expect(page.getByTestId("node-agent")).toBeVisible();
  await expect(page.getByTestId("node-folder")).toBeVisible();
  await expect(page.getByTestId("agent-node-n5").getByTestId("agent-node-problem")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("agents-coding-node.png") });
  await page.getByTestId("node-delete").click();
  await expect(page.getByTestId("agent-node-n5")).toHaveCount(0);

  // Run: a chat opens asking Mimi to run it on the input.
  await page.getByTestId("agent-system-run").click();
  await page.getByTestId("agent-run-input").fill("Can I check in after midnight?");
  await page.screenshot({ path: testInfo.outputPath("agents-run-box.png") });
  await page.getByTestId("agent-run-go").click();
  await expect(page.getByText(/\/mimi-agents Run the agent system "Sequence"/)).toBeVisible();

  // Back on the system: the run's status and each agent's state.
  await page.getByTestId("nav-agents").click();
  await page.locator('[data-testid^="agent-system-card-"]').first().click();
  await expect(page.getByTestId("agent-run-status")).toContainText("Running");
  await expect(page.getByTestId("agent-node-extract")).toHaveAttribute("data-state", "done");
  await expect(page.getByTestId("agent-node-policy")).toHaveAttribute("data-state", "working");
  await page.screenshot({ path: testInfo.outputPath("agents-run-status.png") });
});

test("describing a need opens a conversation under the mimi-agents skill", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-agents").click();
  await page.getByTestId("agents-wish").fill("sort guest emails and let me approve refunds");
  await page.getByTestId("agents-describe-go").click();
  await expect(
    page.getByText("/mimi-agents Design an agent system for me: sort guest emails and let me approve refunds"),
  ).toBeVisible();
});

test("a system can be duplicated and deleted from its page", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-agents").click();
  await page.getByTestId("agent-pattern-routing").click();
  await expect(page.getByTestId("agent-system-title")).toHaveText("Routing");
  await page.getByTestId("agent-system-duplicate").click();
  await expect(page.getByTestId("agent-system-title")).toHaveText("Routing (copy)");
  await page.getByTestId("agent-system-delete").click();
  await page.getByTestId("confirm-accept").click();
  await expect(page.getByTestId("agents-gallery")).toBeVisible();
  await expect(page.locator('[data-testid^="agent-system-card-"]')).toHaveCount(1);
});
