// A team of coding agents: each start asks first and says the agent gets its own branch; while
// Mimi watches, the running step shows one line per agent; feedback rounds read as steps.
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("Mimi starts two agents, watches both, and sends one back with feedback", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/Ask Mimi/).fill("please run the team");
  await page.getByRole("button", { name: "Send" }).click();

  const note = page.getByTestId("delegate-note");
  await expect(note).toContainText("Codex works on its own in analysis-scripts");
  await expect(note).toContainText("gets its own branch");
  await expect(note).toContainText("your own OpenAI account, not QualiTaTi credits");
  await page.screenshot({ path: "test-results/team-approval.png", fullPage: false });
  await page.getByRole("button", { name: "Yes", exact: true }).last().click();

  await expect(page.getByTestId("delegate-note")).toContainText("your own Claude account");
  await page.getByRole("button", { name: "Yes", exact: true }).last().click();

  const board = page.getByTestId("step-progress");
  await expect(board).toContainText("Codex · csv export:");
  await expect(board).toContainText("Claude Code · usage guide:");
  await page.screenshot({ path: "test-results/team-watching.png", fullPage: false });

  await expect(page.getByText(/Both branches are ready/)).toBeVisible();
  await expect(page.getByTestId("step-progress")).toHaveCount(0);
  await page.getByTestId("turn-head").click();
  await expect(page.getByText(/Sent feedback/).first()).toBeVisible();
  await page.screenshot({ path: "test-results/team-done.png", fullPage: false });
});

// Coordinating agents from a chat: once Mimi proposes a hand-off, the side panel lists the
// connected agents with their models, so a model can change before the approval (owner ask
// 2026-10-24) and the change saves to the same settings as the Coding agents page.
test("the chat's side panel sets each agent's model while Mimi coordinates them", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/Ask Mimi/).fill("please run the team");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("delegate-note")).toContainText("Codex works on its own");

  const team = page.getByTestId("agent-team");
  await expect(team.getByTestId("agent-team-claude_code")).toBeVisible();
  await expect(team.getByTestId("agent-team-cursor")).toBeVisible();
  await expect(team.getByTestId("agent-team-gemini")).toHaveCount(0); // not signed in
  await expect(team.getByTestId("agent-team-codex")).toHaveCount(0); // not signed in
  const opencode = team.getByTestId("agent-team-opencode");
  await opencode.getByTestId("agent-team-model").selectOption("opencode/big-pickle");
  await expect(opencode).toContainText("Saved");
  await team.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/team-panel.png" });

  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
  await page.getByTestId("connectors-tab-agents").click();
  await expect(page.getByTestId("coding-agent-opencode").getByTestId("coding-agent-model-select")).toHaveValue("opencode/big-pickle");
});

// Every attended approval is also a pending item in the session's Inbox (visibility
// "inline"). The composer docked that item as a second card, so each request showed
// twice (owner report 2026-10-18). Only the live card may show.
test("a permission request shows once, not again above the composer", async ({ page }) => {
  await page.route(/\/v1\/inbox\?.*session_id=.*/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "inline-1", session_id: "s", kind: "approval", visibility: "inline",
            title: "Run `start_agent`?", body: "", state: "pending", resolution: null,
            inbox: "default", created_at: "", resolved_at: null,
            data: { tool: "start_agent", arguments: { agent: "codex", task: "csv export" } },
          },
        ],
      }),
    }),
  );
  await page.goto("/");
  await page.getByPlaceholder(/Ask Mimi/).fill("please run the team");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("delegate-note")).toHaveCount(1);
  await page.waitForTimeout(4500); // one session-Inbox poll cycle
  await expect(page.getByTestId("delegate-note")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Yes", exact: true })).toHaveCount(1);
  await page.screenshot({ path: process.env.ONE_SHOT || "test-results/one-approval.png" });
});
