import { test, expect } from "./fixtures";

test("a silent task shows a live status and can be stopped with Escape", async ({ page }) => {
  await page.goto("/");
  await page.getByTitle("Weekly plan 1").first().click();
  const box = page.getByPlaceholder(/Ask the coworker|steer it mid-run/);
  await box.fill("wait silently");
  await box.press("Enter");
  const status = page.getByTestId("task-status");
  await expect(status).toContainText("Waiting for the model");
  await expect(page.getByRole("button", { name: "Stop task" })).toBeVisible();
  await page.screenshot({ path: "test-results/task-status-silent.png" });
  await expect(page.getByRole("button", { name: "Visualize this task" })).toHaveCount(0);
  await expect(page.getByTestId("task-elapsed")).toHaveText(/[1-9]\d*s/);
  await box.press("Escape");
  await expect(page.getByText("Interrupted.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
});

test("Steer is visible alongside Stop task while typing a newer instruction", async ({ page }) => {
  await page.goto("/");
  await page.getByTitle("Weekly plan 1").first().click();
  const box = page.getByPlaceholder(/Ask the coworker|steer it mid-run/);
  await box.fill("stream the epic");
  await box.press("Enter");
  await expect(page.getByText("The epic scrolls ever onward", { exact: false }).first()).toBeVisible();
  await box.fill("only write a one-line answer");
  await expect(page.getByRole("button", { name: "Stop task" })).toBeVisible();
  await page.screenshot({ path: "test-results/task-controls-steer.png" });
  await page.getByRole("button", { name: "Steer", exact: true }).click();
  await expect(page.getByText("Echo: only write a one-line answer", { exact: false })).toBeVisible();
});

test("Force stop uses a separate connection and reports a failed delivery before retrying", async ({ page }) => {
  let send: (type: string, data?: object) => void = () => {};
  let live = false;
  let stopping = false;
  const since = Date.now() / 1000;
  await page.routeWebSocket(/\/ws\/session\//, (ws) => {
    send = (type, data = {}) => ws.send(JSON.stringify({ type, data }));
    send("ready", { running: false });
    ws.onMessage((raw) => {
      const msg = JSON.parse(String(raw));
      if (msg.type === "user_message") {
        live = true;
        send("turn_start", { input: msg.text, running_since: since });
        send("tool_proposed", { name: "mcp__canva__list-folder-items", arguments: {} });
        send("tool_started", { name: "mcp__canva__list-folder-items" });
      } else if (msg.type === "interrupt") {
        stopping = true;
        send("interrupt_requested");
      } else if (msg.type === "ping") {
        send("session_status", { running: live, running_since: since, phase: stopping ? "stopping" : "tool" });
      }
    });
  });
  let attempts = 0;
  await page.route(/\/v1\/sessions\/[^/]+\/interrupt\?/, async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("force")).toBe("true");
    expect(Number(url.searchParams.get("running_since"))).toBe(since);
    if (++attempts === 1) {
      await route.fulfill({ status: 503, body: "unavailable" });
      return;
    }
    live = false;
    send("tool_finished", { name: "mcp__canva__list-folder-items", status: "indeterminate", result_preview: "Task stopped. An operation already started may still finish." });
    send("interrupted");
    send("turn_done");
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/");
  await page.getByTitle("Weekly plan 1").first().click();
  const box = page.getByPlaceholder(/Ask the coworker/);
  await box.fill("check my connected service");
  await box.press("Enter");
  await page.getByRole("button", { name: "Stop task" }).click();
  await expect(page.getByTestId("task-status")).toContainText("Stopping the current task");
  await page.screenshot({ path: "test-results/task-controls-force-stop.png" });
  await page.getByRole("button", { name: "Force stop" }).click();
  await expect(page.getByRole("alert")).toContainText("could not be delivered");
  await page.getByRole("button", { name: "Force stop" }).click();
  await expect(page.getByText("Interrupted.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  expect(attempts).toBe(2);
});
