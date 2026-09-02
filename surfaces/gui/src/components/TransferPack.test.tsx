/** TRANSFER PACK (GUI, part 2) — the two surfaces that carry the vocabulary: the guide
 *  that maps MimiWork onto Claude Code / Cowork / Codex, the global-instructions editor
 *  (Cowork's "Global instructions"), and importing skills a user already wrote for
 *  Claude Code. Owner ask 2026-08-23.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SettingsView } from "./SettingsView";
import { SkillsTab } from "./SkillsTab";
import { TransferGuide } from "./TransferGuide";

type Call = { url: string; method: string; body: any };

function stubFetch(routes: { match: string; method?: string; json: any }[]) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method || "GET").toUpperCase();
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      for (const r of routes) {
        if (url.includes(r.match) && (!r.method || r.method === method)) {
          return { ok: true, json: async () => r.json } as Response;
        }
      }
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the transfer guide", () => {
  it("names each concept's equivalent in the other tools", () => {
    render(<TransferGuide />);
    const guide = screen.getByTestId("transfer-guide");
    for (const term of ["Claude Cowork", "Claude Code", "Codex"]) {
      expect(guide.textContent).toContain(term);
    }
    // The rows are things this app really has.
    expect(guide.textContent).toContain("AGENTS.md");
    expect(guide.textContent).toContain("Plan mode (⇧⇥)");
    expect(guide.textContent).toContain("⇧⇥");
  });

  it("is reachable from Settings", async () => {
    stubFetch([]);
    render(<SettingsView initialTab="transfer" />);
    await waitFor(() => expect(screen.getByTestId("transfer-guide")).toBeTruthy());
  });
});

describe("global instructions", () => {
  it("loads the file, saves an edit, and shows where it lives", async () => {
    const calls = stubFetch([
      { match: "/v1/instructions", method: "GET", json: { instructions: "Be brief.", path: "/state/AGENTS.md" } },
      { match: "/v1/instructions", method: "PUT", json: { ok: true } },
    ]);
    render(<SettingsView initialTab="instructions" />);
    const box = (await screen.findByTestId("global-instructions-text")) as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toBe("Be brief."));
    expect(screen.getByText("/state/AGENTS.md")).toBeTruthy();

    // Nothing to save until the text actually changes.
    expect((screen.getByText("Saved") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(box, { target: { value: "Be brief. Use metric units." } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(
        calls.find((c) => c.method === "PUT" && c.url.includes("/v1/instructions"))?.body,
      ).toEqual({ instructions: "Be brief. Use metric units." }),
    );
  });
});

describe("importing Claude Code skills", () => {
  const IMPORTABLE = {
    skills: [
      {
        name: "brand-voice",
        description: "Write in the house voice",
        source: "Claude Code",
        path: "/home/.claude/skills/brand-voice",
        installed: false,
      },
      {
        name: "ad-copy",
        description: "Write ads",
        source: "plugin: marketing",
        path: "/home/.claude/plugins/marketing/skills/ad-copy",
        installed: true,
      },
    ],
  };

  it("lists what this Mac already has and imports the chosen one", async () => {
    const calls = stubFetch([
      { match: "/v1/skills/importable", json: IMPORTABLE },
      { match: "/v1/skills/import", method: "POST", json: { ok: true, name: "brand-voice" } },
      { match: "/v1/skills", json: { skills: [] } },
    ]);
    render(<SkillsTab />);
    fireEvent.click(await screen.findByRole("button", { name: /Add skill/ }));
    fireEvent.click(screen.getByTestId("skill-import-claude"));

    await waitFor(() => expect(screen.getByText("brand-voice")).toBeTruthy());
    expect(screen.getByText("plugin: marketing")).toBeTruthy(); // plugin bundles are named
    // Already-installed skills can't be imported twice.
    const buttons = screen.getAllByRole("button").filter((b) => b.textContent === "Installed");
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getAllByText("Import")[0]);
    await waitFor(() =>
      expect(calls.find((c) => c.url.includes("/v1/skills/import") && c.method === "POST")?.body)
        .toMatchObject({ path: "/home/.claude/skills/brand-voice" }),
    );
  });

  it("says so plainly when there is nothing to import", async () => {
    stubFetch([
      { match: "/v1/skills/importable", json: { skills: [] } },
      { match: "/v1/skills", json: { skills: [] } },
    ]);
    render(<SkillsTab />);
    fireEvent.click(await screen.findByRole("button", { name: /Add skill/ }));
    fireEvent.click(screen.getByTestId("skill-import-claude"));
    await waitFor(() => expect(screen.getByText(/Nothing found/)).toBeTruthy());
  });
});
