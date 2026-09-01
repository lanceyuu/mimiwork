import { test, expect } from "./fixtures";

// Right-click a dot in the memory graph to forget it (owner ask 2026-08-31).

const GRAPH = {
  nodes: [
    { id: "m:1", kind: "memory", label: "Participants are coded P01-P24", scope: "global", memory_id: 1, degree: 2 },
    { id: "m:2", kind: "memory", label: "Uses Stata 18", scope: "workspace", memory_id: 2, degree: 1 },
    { id: "t:method", kind: "tag", label: "#method", degree: 2 },
  ],
  edges: [
    { source: "m:1", target: "t:method" },
    { source: "m:2", target: "t:method" },
  ],
};

async function openGraph(page: any) {
  await page.route("**/v1/memory/graph", async (r: any) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(GRAPH) }),
  );
  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTestId("account-row").click();
  await page.getByTestId("account-menu").getByRole("button", { name: "Settings", exact: true }).click();
  // Memory is one of the set-once sections, behind "More".
  await page.getByTestId("settings-more").click();
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  await page.getByRole("button", { name: /Graph/ }).click();
  await expect(page.getByTestId("memory-graph-canvas")).toBeVisible();
  await page.waitForTimeout(2500); // let the force layout settle
}

/** Right-click the global-scope memory dot.
 *
 *  Node positions live inside the simulation's closure and keep moving, so a fixed
 *  coordinate is a race and the dots are too small to sweep for. Find the teal the
 *  graph actually painted, and dispatch the contextmenu at that point in the SAME
 *  evaluate — sampling and clicking as two steps lets the layout drift between them. */
async function rightClickTealNode(page: any) {
  const found = await page.evaluate(() => {
    const el = document.querySelector(
      "[data-testid='memory-graph-canvas']",
    ) as HTMLCanvasElement;
    const dpr = window.devicePixelRatio || 1;
    const img = el.getContext("2d")!.getImageData(0, 0, el.width, el.height).data;
    const hits: { x: number; y: number }[] = [];
    for (let i = 0; i < img.length; i += 4) {
      // #0d9488 — the teal a global-scope memory dot is filled with.
      if (
        img[i + 3] > 200 &&
        Math.abs(img[i] - 13) < 12 &&
        Math.abs(img[i + 1] - 148) < 12 &&
        Math.abs(img[i + 2] - 136) < 12
      ) {
        hits.push({ x: ((i / 4) % el.width) / dpr, y: Math.floor(i / 4 / el.width) / dpr });
      }
    }
    if (!hits.length) return null;
    const p = hits[Math.floor(hits.length / 2)]; // the middle of the dot, not its edge
    const r = el.getBoundingClientRect();
    el.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: r.left + p.x,
        clientY: r.top + p.y,
      }),
    );
    return p;
  });
  expect(found, "the graph painted no memory dot").not.toBeNull();
}

test("right-clicking a memory offers Forget, and confirming deletes it", async ({ page }) => {
  const deletes: string[] = [];
  // DELETE only — this pattern also matches /v1/memory/graph, and swallowing that
  // leaves the graph empty with no canvas to click.
  await page.route("**/v1/memory/*", async (r: any) => {
    if (r.request().method() !== "DELETE") return r.fallback();
    deletes.push(new URL(r.request().url()).pathname);
    await r.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });
  await openGraph(page);
  await rightClickTealNode(page);

  await expect(page.getByTestId("memory-graph-menu")).toBeVisible();
  await page.getByTestId("memory-graph-forget").click();

  // The confirm names the fact — "delete this node" means nothing when the dot is one
  // of two hundred.
  const dialog = page.getByTestId("confirm-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Participants are coded P01-P24");

  await page.getByTestId("confirm-accept").click();
  await expect.poll(() => deletes.length).toBe(1);
  expect(deletes[0]).toContain("/v1/memory/1");
});

test("cancelling forgets nothing", async ({ page }) => {
  let deletes = 0;
  await page.route("**/v1/memory/*", async (r: any) => {
    if (r.request().method() !== "DELETE") return r.fallback();
    deletes += 1;
    await r.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
  });
  await openGraph(page);
  await rightClickTealNode(page);
  await page.getByTestId("memory-graph-forget").click();
  await page.getByTestId("confirm-cancel").click();

  await expect(page.getByTestId("confirm-dialog")).toHaveCount(0);
  expect(deletes).toBe(0);
});

test("right-clicking empty space opens nothing", async ({ page }) => {
  await openGraph(page);
  const box = (await page.getByTestId("memory-graph-canvas").boundingBox())!;
  // A corner: the layout pulls nodes toward the middle, so this is background.
  await page.mouse.click(box.x + 12, box.y + 12, { button: "right" });
  await expect(page.getByTestId("memory-graph-menu")).toHaveCount(0);
});
