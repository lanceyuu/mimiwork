// Claude Code, Codex and opencode on the Connectors page, connected like any other tool: where each is
// installed, who it is signed in as, a real test call, and the model and effort it will use.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openCodingAgents(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
  await page.getByTestId("connectors-tab-agents").click();
}

test("shows all three agents with their install place, sign-in and settings", async ({ page }) => {
  await openCodingAgents(page);
  const claude = page.getByTestId("coding-agent-claude_code");
  const codex = page.getByTestId("coding-agent-codex");
  const opencode = page.getByTestId("coding-agent-opencode");
  await expect(opencode.getByTestId("coding-agent-status")).toHaveText("Connected");
  await expect(opencode).toContainText("/Users/me/.opencode/bin/opencode");
  await expect(claude.getByTestId("coding-agent-status")).toHaveText("Connected");
  await expect(claude).toContainText("/Users/me/.local/bin/claude");
  await expect(claude).toContainText("me@example.com");
  await expect(codex.getByTestId("coding-agent-status")).toHaveText("Not signed in");
  await expect(codex).toContainText("codex login");
  // The page scrolls inside its own pane, so a tall window is what fits all three in one picture.
  await page.setViewportSize({ width: 1280, height: 2700 });
  await page.screenshot({ path: "test-results/coding-agents.png", fullPage: true });
});

test("signing Codex in from the page turns it connected without leaving the app", async ({ page }) => {
  await openCodingAgents(page);
  const codex = page.getByTestId("coding-agent-codex");
  await codex.getByTestId("coding-agent-sign-in").click();
  await expect(codex.getByTestId("coding-agent-status")).toHaveText("Connected", { timeout: 10_000 });
  await expect(codex).toContainText("ChatGPT");
});

test("a chosen effort is saved and the Test button reports the real call", async ({ page }) => {
  await openCodingAgents(page);
  const claude = page.getByTestId("coding-agent-claude_code");
  await claude.getByTestId("coding-agent-effort").selectOption("max");
  await expect(claude).toContainText("Saved");
  await claude.getByTestId("coding-agent-test").click();
  await expect(claude.getByTestId("coding-agent-test-result")).toHaveText("It answered in 6.2 seconds.");
  await page.screenshot({ path: "test-results/coding-agents-tested.png", fullPage: true });
});

test("each agent offers Latest first, then its own models, and the page says they can work together", async ({ page }) => {
  await openCodingAgents(page);
  await expect(page.getByTestId("coding-agents-together")).toContainText("review another's branch");
  const codexModel = page.getByTestId("coding-agent-codex").getByTestId("coding-agent-model-select");
  await expect(codexModel.locator("option").first()).toHaveText("Latest (currently gpt-6.1-sol)");
  await codexModel.selectOption("gpt-6-astra");
  await expect(page.getByTestId("coding-agent-codex")).toContainText("Saved");
  const claudeModel = page.getByTestId("coding-agent-claude_code").getByTestId("coding-agent-model-select");
  await expect(claudeModel.locator("option").nth(2)).toHaveText("Latest Opus (claude-opus-5)");
  await claudeModel.selectOption("__custom");
  await expect(page.getByTestId("coding-agent-claude_code").getByTestId("coding-agent-model")).toBeVisible();
  await page.screenshot({ path: "test-results/coding-agents-models.png", fullPage: true });
  await page.getByTestId("coding-agent-codex").getByTestId("coding-agent-test").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/coding-agents-codex-models.png" });
});

test("recent hand-offs show each session with a command that reopens it in its own CLI", async ({ page }) => {
  await openCodingAgents(page);
  const runs = page.getByTestId("coding-agent-runs");
  await runs.scrollIntoViewIfNeeded();
  await expect(runs.getByTestId("coding-agent-run")).toHaveCount(3);
  await expect(runs).toContainText("opencode --session ses_eb0eba29cffeV3qX7zbZa88CCb");
  await expect(runs).toContainText("codex resume 01a14b45-ec04-7822-990e-feaaf12fb9ad");
  await expect(runs).toContainText("Its folder has been removed");
  await page.screenshot({ path: "test-results/coding-agents-runs.png" });
});

test("Claude Code hand-offs skip your own hooks by default, and the switch turns them back on", async ({ page }) => {
  await openCodingAgents(page);
  const hooks = page.getByTestId("coding-agent-claude_code").getByTestId("coding-agent-hooks");
  await hooks.scrollIntoViewIfNeeded();
  await expect(hooks).toContainText("Off for hand-offs (faster)");
  await page.screenshot({ path: "test-results/coding-agents-hooks.png" });
  await hooks.getByRole("switch").click();
  await expect(hooks).toContainText("On for hand-offs");
  await expect(page.getByTestId("coding-agent-codex").getByTestId("coding-agent-hooks")).toHaveCount(0);
});

test("opencode offers its newest free model first, its own models, its providers, and says it does not stop to ask", async ({ page }) => {
  await openCodingAgents(page);
  const opencode = page.getByTestId("coding-agent-opencode");
  await opencode.scrollIntoViewIfNeeded();
  const model = opencode.getByTestId("coding-agent-model-select");
  await expect(model.locator("option").first()).toHaveText("Latest free model (currently opencode/nemotron-3.5-super-vl-free)");
  await expect(model.locator("option").nth(2)).toHaveText("GPT-6 Luna · github-copilot");
  await expect(opencode.getByTestId("coding-agent-providers")).toContainText("GitHub Copilot");
  await expect(opencode.getByTestId("coding-agent-providers")).toContainText("opencode auth login");
  await expect(opencode.getByTestId("coding-agent-unattended")).toContainText("opencode does not stop to ask");
  await model.selectOption("github-copilot/gpt-6-luna");
  await expect(opencode).toContainText("Saved");
  await opencode.getByTestId("coding-agent-effort").selectOption("none");
  await opencode.getByTestId("coding-agent-test").click();
  await expect(opencode.getByTestId("coding-agent-test-result")).toContainText("It answered in");
  await expect(opencode.getByTestId("coding-agent-hooks")).toHaveCount(0);
  await opencode.screenshot({ path: "test-results/coding-agents-opencode.png" });
});
