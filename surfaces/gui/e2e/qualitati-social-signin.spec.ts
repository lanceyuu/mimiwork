import { test, expect } from "./fixtures";

// Google/Microsoft sign-in on the account card (2026-10-08): two branded buttons above
// the username form, and a waiting line while the browser finishes.
test("the account card offers Google and Microsoft, then waits for the browser", async ({ page }) => {
  await page.route("**/v1/qualitati/status*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, signed_in: false }) }),
  );
  await page.route("**/v1/qualitati/social?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ providers: ["google", "microsoft"] }) }),
  );
  await page.route("**/v1/qualitati/social/start", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, url: "about:blank" }) }),
  );
  await page.route("**/v1/qualitati/social/poll", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ pending: true }) }),
  );
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();
  const card = page.getByTestId("qualitati-card");
  await expect(page.getByTestId("qualitati-social-google")).toHaveText("Continue with Google");
  await expect(page.getByTestId("qualitati-social-microsoft")).toHaveText("Continue with Microsoft");
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: "test-results/social-signin.png" });

  await page.getByTestId("qualitati-social-google").click();
  await expect(page.getByTestId("qualitati-social-waiting")).toContainText("Finish signing in with Google");
  await card.screenshot({ path: "test-results/social-signin-waiting.png" });
});
