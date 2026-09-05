import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SkillsTab } from "./SkillsTab";

// SKILLS-SPEC §5/§6 GUI — Settings ▸ Skills: list + badges + rich-skill file counts, form
// validation, the doors (write form / upload-with-preview / doorway-to-conversation).

type Call = { url: string; method: string; body: any };

function stubFetch(routes: { match: string; method?: string; json: any }[]) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method || "GET").toUpperCase();
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    for (const r of routes) {
      if (url.includes(r.match) && (!r.method || r.method === method)) {
        return { ok: true, json: async () => r.json } as Response;
      }
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

const ROW = {
  name: "weekly-report",
  description: "Monday status report",
  instructions: "1. Collect updates\n2. Write it up",
  scope: "global",
  source: "local",
  enabled: true,
  path: "/skills/weekly-report",
};

const UPLOADED_ROW = {
  ...ROW,
  name: "greet",
  description: "says hello",
  source: "uploaded",
  enabled: false,
};

const QUALITATI_ROW = {
  ...ROW,
  name: "qualitati-list-projects",
  description: "List QualiTaTi projects before starting research work",
  instructions: "Use the QualiTaTi project list tool.",
  path: "/skills/qualitati-list-projects",
};

const LIST = { skills: [ROW, UPLOADED_ROW] };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// The single add-action: open the "Add skill" menu, pick a door (SKILLS-SPEC §5).
const openWriteForm = async () => {
  fireEvent.click(await screen.findByRole("button", { name: /Add skill/ }));
  fireEvent.click(screen.getByText("Write it myself"));
};

describe("SkillsTab", () => {
  it("presents skills under their own name — Skills, not Workflows", async () => {
    stubFetch([{ match: "/v1/skills", method: "GET", json: LIST }]);
    render(<SkillsTab />);
    expect(await screen.findByRole("heading", { name: "Skills" })).toBeTruthy();
    expect(screen.getByLabelText("Search skills")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Add skill/ })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Search skills"), {
      target: { value: "Monday" },
    });
    expect(screen.getByText("weekly-report")).toBeTruthy();
    expect(screen.queryByText("greet")).toBeNull();
  });

  it("keeps built-in QualiTaTi tools collapsed until asked for", async () => {
    stubFetch([
      {
        match: "/v1/skills",
        method: "GET",
        json: { skills: [ROW, QUALITATI_ROW] },
      },
    ]);
    render(<SkillsTab />);
    const disclosure = await screen.findByRole("button", {
      name: /Built-in QualiTaTi tools/,
    });
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("List Projects")).toBeNull();

    fireEvent.click(disclosure);
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("List Projects")).toBeTruthy();
    expect(screen.getByText("Built in")).toBeTruthy();
  });

  it("opens built-in tools when a search matches, then folds them away when cleared", async () => {
    stubFetch([
      {
        match: "/v1/skills",
        method: "GET",
        json: { skills: [ROW, QUALITATI_ROW] },
      },
    ]);
    render(<SkillsTab />);
    const search = screen.getByLabelText("Search skills");
    const disclosure = await screen.findByRole("button", {
      name: /Built-in QualiTaTi tools/,
    });

    fireEvent.change(search, { target: { value: "research" } });
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("List Projects")).toBeTruthy();
    expect(screen.queryByText("weekly-report")).toBeNull();

    fireEvent.change(search, { target: { value: "" } });
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("List Projects")).toBeNull();
  });

  it("renders rows with provenance badges and dims disabled skills", async () => {
    stubFetch([{ match: "/v1/skills", method: "GET", json: LIST }]);
    render(<SkillsTab />);
    expect(await screen.findByText("weekly-report")).toBeTruthy();
    expect(screen.getByText("Monday status report")).toBeTruthy();
    expect(screen.queryByText("global")).toBeNull(); // no scope badges — global-only (§4.7)
    expect(screen.getByText("uploaded")).toBeTruthy(); // provenance badge stays
    const toggles = screen.getAllByRole("switch");
    expect((toggles[0] as HTMLInputElement).checked).toBe(true);
    expect((toggles[1] as HTMLInputElement).checked).toBe(false);
  });

  it("blocks Save until name and instructions are filled", async () => {
    stubFetch([{ match: "/v1/skills", method: "GET", json: { skills: [] } }]);
    render(<SkillsTab />);
    await openWriteForm();
    const save = screen.getByText("Save skill") as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "greet" } });
    expect(save.disabled).toBe(true); // instructions still empty
    fireEvent.change(screen.getByLabelText("Instructions"), {
      target: { value: "Say hello." },
    });
    expect(save.disabled).toBe(false);
  });

  it("creates a skill (global, no scope field) and refreshes the list", async () => {
    const calls = stubFetch([
      { match: "/v1/skills", method: "GET", json: { skills: [] } },
      { match: "/v1/skills", method: "POST", json: { ok: true } },
    ]);
    render(<SkillsTab />);
    await openWriteForm();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "greet" } });
    fireEvent.change(screen.getByLabelText("Instructions"), {
      target: { value: "Say hello." },
    });
    fireEvent.click(screen.getByText("Save skill"));
    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/v1/skills"));
      expect(post?.body).toMatchObject({ name: "greet", instructions: "Say hello." });
      expect(post?.body.workspace).toBeUndefined(); // global-only: no scope/workspace sent
    });
    // list re-fetched after save
    expect(calls.filter((c) => c.method === "GET" && c.url.includes("/v1/skills")).length).toBeGreaterThan(1);
  });

  it("edit prefills the form (name locked, body loaded) and PATCHes on save", async () => {
    const calls = stubFetch([
      { match: "/v1/skills", method: "GET", json: LIST },
      { match: "/v1/skills/weekly-report", method: "PATCH", json: { ok: true } },
    ]);
    render(<SkillsTab />);
    await screen.findByText("weekly-report");
    fireEvent.click(screen.getAllByTitle("Edit")[0]);
    const name = screen.getByLabelText("Name") as HTMLInputElement;
    expect(name.value).toBe("weekly-report");
    expect(name.disabled).toBe(true);
    const body = screen.getByLabelText("Instructions") as HTMLTextAreaElement;
    expect(body.value).toContain("Collect updates");
    fireEvent.change(body, { target: { value: "New steps" } });
    fireEvent.click(screen.getByText("Save skill"));
    await waitFor(() => {
      const patch = calls.find((c) => c.method === "PATCH");
      expect(patch?.url).toContain("/v1/skills/weekly-report");
      expect(patch?.body.instructions).toBe("New steps");
    });
  });

  it("delete is two-step: arm, then DELETE on confirm", async () => {
    const calls = stubFetch([
      { match: "/v1/skills", method: "GET", json: LIST },
      { match: "/v1/skills/weekly-report", method: "DELETE", json: { ok: true } },
    ]);
    render(<SkillsTab />);
    await screen.findByText("weekly-report");
    // arm via the trash button (renders "Confirm delete" once armed)
    fireEvent.click(screen.getByLabelText("Delete weekly-report"));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    const confirm = await screen.findByText("Confirm delete");
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(calls.some((c) => c.method === "DELETE" && c.url.includes("weekly-report"))).toBe(true);
    });
  });

  it("the enabled switch PATCHes {enabled} and teaches the off rule + physics footnote", async () => {
    const calls = stubFetch([
      { match: "/v1/skills", method: "GET", json: LIST },
      { match: "/v1/skills/weekly-report", method: "PATCH", json: { ok: true } },
    ]);
    render(<SkillsTab />);
    await screen.findByText("weekly-report");
    fireEvent.click(screen.getByLabelText("weekly-report enabled"));
    await waitFor(() => {
      const patch = calls.find((c) => c.method === "PATCH");
      expect(patch?.body).toMatchObject({ enabled: false });
    });
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("weekly-report"); // name-first — WHICH skill
    expect(status.textContent).toContain("turned off everywhere");
    expect(status.textContent).toContain("clean slate"); // the guaranteed remedy, in place
  });

  it("upload shows the parsed preview and installs nothing until confirmed", async () => {
    const calls = stubFetch([
      { match: "/v1/skills/upload/confirm", method: "POST", json: { ok: true } },
      {
        match: "/v1/skills/upload",
        method: "POST",
        json: {
          ok: true,
          token: "t1",
          name: "greet",
          description: "says hello",
          instructions: "Say hello warmly.",
          files: ["notes.txt"],
        },
      },
      { match: "/v1/skills", method: "GET", json: { skills: [] } },
    ]);
    render(<SkillsTab />);
    const input = (await screen.findByLabelText("Upload a skill archive")) as HTMLInputElement;
    const file = new File([new Uint8Array([80, 75, 3, 4])], "greet.zip", { type: "application/zip" });
    fireEvent.change(input, { target: { files: [file] } });
    await screen.findByText("Review before installing");
    expect(screen.getByText("Say hello warmly.")).toBeTruthy();
    expect(screen.getByText(/notes\.txt/)).toBeTruthy();
    expect(calls.some((c) => c.url.includes("/upload/confirm"))).toBe(false); // preview ≠ install
    fireEvent.click(screen.getByText("Install skill"));
    await waitFor(() => {
      const confirm = calls.find((c) => c.url.includes("/upload/confirm"));
      expect(confirm?.body).toMatchObject({ token: "t1" });
    });
  });

  it("Add skill menu: three doors; Create with MimiWork hands off to a conversation", async () => {
    const calls = stubFetch([{ match: "/v1/skills", method: "GET", json: { skills: [] } }]);
    const onCreateSkill = vi.fn();
    render(<SkillsTab onCreateSkill={onCreateSkill} />);
    fireEvent.click(await screen.findByRole("button", { name: /Add skill/ }));
    // The three doors (§5), each with its teaching subtitle.
    expect(screen.getByText("Write it myself")).toBeTruthy();
    expect(screen.getByText("Import a file")).toBeTruthy();
    expect(screen.getByText(/you review before it installs/)).toBeTruthy();
    expect(screen.getByText(/asks before adding it to\s+your skills/)).toBeTruthy();
    fireEvent.click(screen.getByText("Create with MimiWork"));
    // Straight to the conversation — the composer is where you describe it (§5.2).
    expect(onCreateSkill).toHaveBeenCalledWith("");
    // Settings never drafts: no POST of any kind happened.
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("offers no scope UI at all — skills are global (§4.7)", async () => {
    stubFetch([{ match: "/v1/skills", method: "GET", json: { skills: [] } }]);
    render(<SkillsTab />);
    await openWriteForm();
    expect(screen.queryByText("Available in")).toBeNull();
    expect(screen.queryByLabelText("Everywhere")).toBeNull();
    expect(screen.queryByLabelText("Only one project")).toBeNull();
    expect(screen.queryByText(/Move to/)).toBeNull();
  });

  it("shows the new-session confirmation line after creating a skill", async () => {
    stubFetch([
      { match: "/v1/skills", method: "GET", json: { skills: [] } },
      { match: "/v1/skills", method: "POST", json: { ok: true } },
    ]);
    render(<SkillsTab />);
    await openWriteForm();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "greet" } });
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "x" } });
    fireEvent.click(screen.getByText("Save skill"));
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("greet"); // name-first — WHICH skill
    expect(status.textContent).toContain("can now use it in every conversation");
  });

  it("the list is the page: no standing add-surfaces, no drafting remnants", async () => {
    stubFetch([{ match: "/v1/skills", method: "GET", json: { skills: [] } }]);
    render(<SkillsTab onCreateSkill={vi.fn()} />);
    await screen.findByRole("button", { name: /Add skill/ });
    // No permanently-open description box or draft-era UI (§5.2/§9) — adding is menu-only.
    expect(screen.queryByLabelText("Describe the skill")).toBeNull();
    expect(screen.queryByText("Start a conversation")).toBeNull();
    expect(screen.queryByText("Ask MimiWork to revise")).toBeNull();
    expect(screen.queryByText(/Not a chat/)).toBeNull();
    // The menu closes after picking a door.
    await openWriteForm();
    expect(screen.queryByText("Write it myself")).toBeNull();
    expect(screen.getByText("Save skill")).toBeTruthy();
  });

  it("surfaces server-side validation errors", async () => {
    stubFetch([
      { match: "/v1/skills", method: "GET", json: { skills: [] } },
      { match: "/v1/skills", method: "POST", json: { ok: false, error: "A skill named 'x' already exists in that scope." } },
    ]);
    render(<SkillsTab />);
    await openWriteForm();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "y" } });
    fireEvent.click(screen.getByText("Save skill"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/already exists/)).toBeTruthy();
  });
});

describe("SkillsTab — rich-skill disclosure (§6)", () => {
  it("shows a file count only when a skill bundles resources", async () => {
    stubFetch([
      {
        match: "/v1/skills",
        method: "GET",
        json: {
          skills: [
            { name: "plain", description: "d", instructions: "i", scope: "global", source: "local", enabled: true, path: "/p", files: 0 },
            { name: "rich", description: "d", instructions: "i", scope: "global", source: "uploaded", enabled: true, path: "/r", files: 3 },
          ],
        },
      },
    ]);
    render(<SkillsTab />);
    const note = await screen.findByTitle("Show folder");
    expect(note.textContent).toContain("3 files");
    // The one-file skill carries no count at all — only rich skills are marked.
    expect(screen.getAllByTitle("Show folder")).toHaveLength(1);
  });

  // ── the skill store: browsing, honest counts, and reading before installing ──────
  const STORE_ROUTES = (results: any[], total = results.length) => [
    { match: "/v1/skills/store/categories", json: { categories: [
      { key: "recommended", label: "Recommended", count: 3 },
      { key: "research", label: "Research", count: 513 },
      { key: "writing", label: "Writing & editing", count: 207 },
    ] } },
    { match: "/v1/skills/store/preview", json: {
      ok: true, name: "lit-review", repo: "acme/skills", description: "Reads papers",
      allowed_tools: ["WebSearch", "Write"], instructions: "# Literature review\n\nStep one.",
      truncated: false, flagged: false, url: "https://github.com/acme/skills",
    } },
    { match: "/v1/skills/store", json: { results, total, offset: 0 } },
    { match: "/v1/skills", json: { skills: [ROW] } },
  ];
  const ENTRY = {
    name: "lit-review", description: "Structured literature search", repo: "acme/skills",
    path: "skills/lit-review", installed: false, also_in: 2,
  };

  const openStore = async () => {
    fireEvent.click(await screen.findByRole("button", { name: /Add skill/ }));
    fireEvent.click(screen.getByTestId("skill-store-open"));
  };

  it("opens on a shelf instead of an empty page, and says how many there are", async () => {
    const calls = stubFetch(STORE_ROUTES([ENTRY], 513));
    render(<SkillsTab />);
    await openStore();
    // Shelves arrive with counts, and one is already loaded — no typing required.
    await screen.findByTestId("skill-store-shelves");
    expect(screen.getByTestId("skill-store-shelf-research").textContent).toContain("513");
    expect((await screen.findByTestId("skill-store-count")).textContent).toContain("of 513");
    expect(screen.getByTestId("skill-store-more")).toBeTruthy();
    expect(calls.some((c) => c.url.includes("category=recommended"))).toBe(true);
  });

  it("shelf clicks and typed searches both go through the same list", async () => {
    const calls = stubFetch(STORE_ROUTES([ENTRY], 30));
    render(<SkillsTab />);
    await openStore();
    fireEvent.click(await screen.findByTestId("skill-store-shelf-writing"));
    await waitFor(() => expect(calls.some((c) => c.url.includes("category=writing"))).toBe(true));
    fireEvent.change(screen.getByTestId("skill-store-search"), { target: { value: "seo audit" } });
    await waitFor(() => expect(calls.some((c) => c.url.includes("q=seo+audit"))).toBe(true));
    // The shelves step aside while a query is typed — one filter at a time.
    expect(screen.queryByTestId("skill-store-shelves")).toBeNull();
  });

  it("reads a skill's own instructions before anything is installed", async () => {
    const calls = stubFetch(STORE_ROUTES([ENTRY]));
    render(<SkillsTab />);
    await openStore();
    fireEvent.click(await screen.findByTestId("skill-store-preview-lit-review"));
    const panel = await screen.findByTestId("skill-store-preview");
    expect(panel.textContent).toContain("Literature review");
    expect(panel.textContent).toContain("WebSearch"); // what it wants to use
    expect(calls.some((c) => c.url.includes("/v1/skills/store/install"))).toBe(false);
    // …and installing from the panel is the same install as the row's button.
    fireEvent.click(screen.getByTestId("skill-store-preview-install"));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/v1/skills/store/install"))).toBe(true),
    );
  });

  it("shows where else a skill is listed instead of repeating the row", async () => {
    stubFetch(STORE_ROUTES([ENTRY]));
    render(<SkillsTab />);
    await openStore();
    const row = await screen.findByTestId("skill-store-install-lit-review");
    expect(row.closest("div")!.parentElement!.textContent).toContain("+2 more collections");
  });

  it("keeps the latest search when an older response arrives late", async () => {
    let finish!: (value: unknown) => void;
    const slow = new Promise((resolve) => { finish = resolve; });
    stubFetch([
      { match: "q=slow", json: slow },
      { match: "q=sepia", json: { results: [{ ...ENTRY, name: "sepia" }], total: 1 } },
      ...STORE_ROUTES([ENTRY]),
    ]);
    render(<SkillsTab />);
    await openStore();
    await screen.findByTestId("skill-store-install-lit-review");
    fireEvent.change(screen.getByLabelText("Search the skill store"), { target: { value: "slow" } });
    fireEvent.change(screen.getByLabelText("Search the skill store"), { target: { value: "sepia" } });
    await screen.findByTestId("skill-store-install-sepia");
    await act(async () => { finish({ results: [ENTRY], total: 1 }); });
    expect(screen.queryByTestId("skill-store-install-lit-review")).toBeNull();
    expect(screen.getByTestId("skill-store-install-sepia")).toBeTruthy();
  });

  it("offers retry when the store fails instead of claiming no skills match", async () => {
    stubFetch(STORE_ROUTES([ENTRY]));
    render(<SkillsTab />);
    await openStore();
    await screen.findByTestId("skill-store-install-lit-review");
    vi.mocked(fetch).mockRejectedValueOnce(new Error("offline"));
    fireEvent.change(screen.getByLabelText("Search the skill store"), { target: { value: "sepia" } });
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load skills");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByText("Could not load skills. Try again.")).toBeNull());
  });


  it("lets a reader inspect an example, output, and requirements before installing", async () => {
    stubFetch(STORE_ROUTES([{ ...ENTRY, example_prompt: "Summarize my evidence", expected_output: "A sourced draft", requirements: "Source notes", install_checked_at: "2026-09-05" }]));
    render(<SkillsTab />);
    await openStore();
    const summary = await screen.findByText("Example and requirements");
    fireEvent.click(summary);
    expect(summary.parentElement!.textContent).toContain("Summarize my evidence");
    expect(summary.parentElement!.textContent).toContain("A sourced draft");
    expect(summary.parentElement!.textContent).toContain("Source notes");
    expect(summary.parentElement!.textContent).toContain("Installation checked: 2026-09-05");
  });

});
