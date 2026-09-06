import { test, expect } from "./fixtures";

// The account card's footprint line leads with the signed-in person's OWN rough share
// this month (owner ask 2026-09-07) and keeps Scaleway's service-wide measurement under it.
test("footprint: personal estimate first, measured service figure second", async ({ page }) => {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/v1/qualitati/status", (r) =>
    r.fulfill(json({ ok: true, signed_in: true, provider_configured: true, profile: { username: "shubin", email: "s@x.com", credits: 420, plan: "scholar" } })),
  );
  await page.route("**/v1/qualitati/region", (r) => r.fulfill(json({ ok: true, region: "eu", configured: true })));
  await page.route("**/v1/qualitati/footprint", (r) =>
    r.fulfill(
      json({
        ok: true,
        carbon_g: 812.5,
        water_l: 3.2,
        scope: "whole Mimi service, all users, month to date",
        measured_by: "Scaleway Environmental Footprint (fr-par, Paris)",
        you: { carbon_g: 0.55, water_l: 0.018, energy_wh: 10, tokens_in: 100000, tokens_out: 10000, calls: 2, region: "eu", method: "rough estimate" },
      }),
    ),
  );
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();
  const line = page.getByTestId("qualitati-footprint");
  await expect(line).toContainText("Your impact this month, roughly: 550 mg CO₂e");
  await expect(line).toContainText("Whole Mimi service, measured by Scaleway");
  await page.getByTestId("qualitati-card").scrollIntoViewIfNeeded();
  await page.getByTestId("qualitati-card").screenshot({ path: "test-results/footprint.png" });
});
