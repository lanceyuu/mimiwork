// Claude Code and Codex on the Connectors page, connected like any other tool: where each is
// installed, who it is signed in as, a real test call, and the model and effort it will use.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

async function openCodingAgents(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
  await page.getByTestId("connectors-tab-agents").click();
}

test("shows both agents with their install place, sign-in and settings", async ({ page }) => {
  await openCodingAgents(page);
  const claude = page.getByTestId("coding-agent-claude_code");
  const codex = page.getByTestId("coding-agent-codex");
  await expect(claude.getByTestId("coding-agent-status")).toHaveText("Connected");
  await expect(claude).toContainText("/Users/me/.local/bin/claude");
  await expect(claude).toContainText("me@example.com");
  await expect(codex.getByTestId("coding-agent-status")).toHaveText("Not signed in");
  await expect(codex).toContainText("codex login");
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
  await expect(page.getByTestId("coding-agents-together")).toContainText("review the other's branch");
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
  await expect(runs.getByTestId("coding-agent-run")).toHaveCount(2);
  await expect(runs).toContainText("codex resume 01a14b45-ec04-7822-990e-feaaf12fb9ad");
  await expect(runs).toContainText("Its folder has been removed");
  await page.screenshot({ path: "test-results/coding-agents-runs.png" });
});
