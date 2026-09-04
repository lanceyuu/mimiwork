import { test, expect } from "./fixtures";

// The registration password rule: a quiet grey hint until it is broken, then a red
// notice with the field outlined (owner ask 2026-09-04: "more noticeable, like more red").
test("a weak password turns the rule into a red notice and outlines the field", async ({ page }) => {
  await page.route("**/v1/qualitati/status", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, signed_in: false }) });
  });
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();
  await page.getByTestId("qualitati-mode-register").click();
  const hint = page.getByTestId("qualitati-reg-hint");
  await expect(hint).toHaveAttribute("data-state", "ok");
  await page.getByTestId("qualitati-reg-username").fill("newbie");
  await page.getByTestId("qualitati-reg-email").fill("n@example.com");
  await page.getByTestId("qualitati-reg-password").fill("weakpassword");
  await expect(hint).toHaveAttribute("data-state", "problem");
  await expect(hint).toContainText("Password needs an uppercase letter");
  await expect(page.getByTestId("qualitati-reg-password")).toHaveAttribute("aria-invalid", "true");
  await page.getByTestId("qualitati-card").scrollIntoViewIfNeeded();
  await page.getByTestId("qualitati-card").screenshot({ path: "test-results/register-warning.png" });
});
