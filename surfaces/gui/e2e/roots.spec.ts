// Guards the per-session directory RO/RW gate (§ roots), which since §32 lives in the rail's
// Access section under "Folders" (folder access is standing session config, not per-message
// attachment — the composer's folder popover is gone). The section lists the primary writable
// workspace, and adding a folder is read-write by default (owner ask 2026-09-02: a folder you
// hand Mimi is where her work goes) with an explicit untick for reference material.
import { test, expect } from "./fixtures";

test("working directories: add folders with the read-only / read-write gate", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Draft the launch note").first().click();

  // Expand the rail's Access section.
  await page.getByTestId("access-toggle").click();
  const dirs = page.getByTestId("drawer-directories");
  await expect(dirs.getByText("Folders")).toBeVisible();

  // The primary is the writable scratch workspace (Cowork shows it as "Temporary space").
  await expect(dirs.getByText("Temporary space")).toBeVisible();

  // Add a folder — the gate defaults to read-write (Allow writes ON); untick for read-only.
  // The Browse button works in the BROWSER too (sidecar-opened native picker; owner report
  // 2026-07-04).
  await dirs.getByRole("button", { name: "Give access to a folder" }).click();
  await dirs.getByRole("button", { name: "Choose location" }).click();
  await expect(dirs.getByPlaceholder(/Choose or paste a folder path/)).toHaveValue(
    "/tmp/picked-folder",
  );
  const allowWrites = dirs.locator(".addfolder-write input[type=checkbox]");
  await expect(allowWrites).toBeChecked();
  await allowWrites.uncheck();
  await dirs.getByPlaceholder(/Choose or paste a folder path/).fill("/tmp/ro-data");
  await dirs.getByRole("button", { name: "Add", exact: true }).click();

  const roRow = dirs.locator(".root-row").filter({ hasText: "/tmp/ro-data" });
  await expect(roRow.getByRole("button", { name: "Read-only" })).toBeVisible();

  // Add another with the default left alone → it lands read-write.
  await dirs.getByRole("button", { name: "Give access to a folder" }).click();
  await dirs.getByPlaceholder(/Choose or paste a folder path/).fill("/tmp/rw-data");
  await expect(dirs.locator(".addfolder-write input[type=checkbox]")).toBeChecked();
  await dirs.getByRole("button", { name: "Add", exact: true }).click();

  const rwRow = dirs.locator(".root-row").filter({ hasText: "/tmp/rw-data" });
  await expect(rwRow.getByRole("button", { name: "Read-write" })).toBeVisible();

  // Flip the read-only one to read-write via its access button (upsert re-add).
  await roRow.getByRole("button", { name: "Read-only" }).click();
  await expect(roRow.getByRole("button", { name: "Read-write" })).toBeVisible();

  // Remove a non-primary folder — the primary can't be removed.
  await rwRow.getByTitle("Remove").click();
  await expect(dirs.locator(".root-row").filter({ hasText: "/tmp/rw-data" })).toHaveCount(0);
});
