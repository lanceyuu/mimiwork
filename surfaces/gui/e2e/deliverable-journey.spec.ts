import { test, expect } from "./fixtures";

for (const [task, format] of [["word", ".docx"], ["spreadsheet", ".xlsx"], ["slides", ".pptx"]]) {
  test(`${task} starter prepares an editable request without sending it`, async ({ page }, testInfo) => {
    await page.goto("/");
    await expect(page.getByTestId(`intro-task-${task}`)).toBeVisible();
    await expect(page.getByTestId("intro-task-canva")).not.toBeVisible();
    await page.getByTestId(`intro-task-${task}`).click();
    const composer = page.getByPlaceholder(/Ask the coworker/);
    await expect(composer).toHaveValue(new RegExp(format.replace(".", "\\.")));
    await expect(composer).toBeFocused();
    await expect(page.locator(".msg.user")).toHaveCount(0);
    if (task === "word") {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.screenshot({ path: testInfo.outputPath("word-starter.png"), animations: "disabled" });
    }
  });
}

for (const ext of ["docx", "xlsx", "pptx"]) {
  test(`a saved ${ext} can be opened, located, and revised from its file row`, async ({ page }, testInfo) => {
    const path = `results/Finished report.${ext}`;
    const actions: unknown[] = [];
    await page.route("**/v1/sessions/*/artifacts", r => r.fulfill({ json: { artifacts: [
      { name: `Finished report.${ext}`, path, kind: "office", tier: 0, size: 2048, modified_at: 1788600000 },
    ] } }));
    await page.route("**/v1/sessions/*/artifacts/reveal", r => {
      actions.push(r.request().postDataJSON());
      return r.fulfill({ json: { ok: true } });
    });
    await page.route("**/v1/sessions/*/artifacts/read?*", r => r.fulfill({ json: { ok: true, kind: "text", content: "Preview of the saved file" } }));
    await page.goto("/");
    await expect(page.getByText("Your files are saved. Open one to review it, or ask for changes.")).toBeVisible();
    await page.getByRole("button", { name: `Show in folder: Finished report.${ext}`, exact: true }).click();
    await expect.poll(() => actions.length).toBe(1);
    expect(actions[0]).toEqual({ path, mode: "reveal" });
    await page.getByRole("button", { name: `Revise: Finished report.${ext}`, exact: true }).click();
    await expect(page.getByPlaceholder(/Ask the coworker/)).toHaveValue(new RegExp(`Finished report\\.${ext}`));
    await expect(page.getByPlaceholder(/Ask the coworker/)).toHaveValue(/Keep the original and save a revised copy/);
    if (ext === "docx") await page.screenshot({ path: testInfo.outputPath("saved-file-actions.png"), animations: "disabled" });
    await page.locator(".artifact-row").click();
    await expect(page.getByText("Preview of the saved file")).toBeVisible();
  });
}
