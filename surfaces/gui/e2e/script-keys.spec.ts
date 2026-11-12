import { test, expect } from "./fixtures";

// Keys for a person's own scripts live on the Models page: saved by name, and only the
// name is ever shown again.
test("Settings: a key for your own scripts is saved by name and never shown back", async ({ page }, testInfo) => {
  let names: string[] = ["HF_TOKEN"];
  await page.route("**/v1/script-keys**", async (route) => {
    const request = route.request();
    if (request.method() === "POST") names = [...names, request.postDataJSON().name].sort();
    if (request.method() === "DELETE") names = names.filter((n) => !request.url().endsWith("/" + n));
    await route.fulfill({ json: { ok: true, names } });
  });
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();

  const card = page.getByTestId("script-keys-card");
  await card.scrollIntoViewIfNeeded();
  await card.getByLabel("Name").fill("openrouter_api_key");
  await card.getByLabel("Key", { exact: true }).fill("sk-not-a-real-key");
  await card.getByRole("button", { name: "Save" }).click();

  await expect(card.getByText("OPENROUTER_API_KEY")).toBeVisible();
  await expect(card.getByLabel("Key", { exact: true })).toHaveValue("");
  await expect(page.getByText("sk-not-a-real-key")).toHaveCount(0);
  await card.screenshot({ path: testInfo.outputPath("script-keys-card.png") });

  await card.getByRole("button", { name: "Remove HF_TOKEN" }).click();
  await expect(card.getByText("HF_TOKEN")).toHaveCount(0);
});
