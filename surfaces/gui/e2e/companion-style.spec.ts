import { test, expect, mockApi } from "./fixtures";

test("the saved Mimi choice updates the floating pet in another window", async ({ page, context }, testInfo) => {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const card = page.getByTestId("companion-style-card");
  await expect(card.getByRole("radio", { name: "Classic Mimi" })).toBeChecked();

  const pet = await context.newPage();
  await mockApi(pet);
  let pending = 0;
  await pet.route("**/v1/activity", (route) => route.fulfill({ json: { busy: pending > 0, pending_input: pending, running_sessions: 0, running_automations: 0 } }));
  await pet.goto("/#companion");
  await expect(pet.getByTestId("companion-sprite")).toHaveAttribute("data-style", "classic");
  await card.getByRole("radio", { name: "Teal Mimi" }).check();
  await expect(pet.getByTestId("companion-sprite")).toHaveAttribute("data-style", "teal");
  await expect(pet.getByTestId("companion-sprite")).toHaveAttribute("data-row", "0");
  const atlasSize = await pet.getByTestId("companion-sprite").locator(":scope > div").evaluate(async (element) => {
    const image = new Image();
    image.src = getComputedStyle(element).backgroundImage.slice(5, -2);
    await image.decode();
    return [image.naturalWidth, image.naturalHeight];
  });
  expect(atlasSize).toEqual([1536, 2288]);
  await card.screenshot({ path: testInfo.outputPath("mimi-style-settings.png") });
  await pet.getByTestId("companion-pet-zone").screenshot({ path: testInfo.outputPath("teal-mimi.png") });

  pending = 1;
  await pet.reload();
  await expect(pet.getByTestId("companion-sprite")).toHaveAttribute("data-row", "6");
  await expect(pet.getByTestId("companion-bubble")).toContainText("need your OK");
  await expect(pet.getByTestId("companion-zzz")).toHaveCount(0);
  await page.reload();
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("radio", { name: "Teal Mimi" })).toBeChecked();
  await page.getByRole("radio", { name: "Classic Mimi" }).check();
  await expect(pet.getByTestId("companion-sprite")).toHaveAttribute("data-style", "classic");
  await expect(pet.getByTestId("companion-sprite")).toHaveAttribute("data-phase", "alert");
  await pet.close();
});
