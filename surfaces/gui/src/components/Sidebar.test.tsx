import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Sidebar } from "./Sidebar";
import type { SessionInfo } from "../types";

// Hermetic fetch stub routing by URL substring + method; records calls for POST assertions.
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

const PERSONAS = {
  personas: [
    { id: "cowork", name: "MimiWork", icon: "cowork", tagline: "general assistant", family: "knowledge", enabled: true, surfaced: true, default: true },
    { id: "ops", name: "Ops", icon: "ops", tagline: "incidents, runbooks", family: "code", enabled: true, surfaced: true, default: false },
    { id: "code", name: "Code", icon: "code", tagline: "repository work", family: "code", enabled: true, surfaced: true, default: false },
    { id: "secret", name: "Disabled One", icon: "cowork", tagline: "off", family: "knowledge", enabled: false, surfaced: false, default: false },
  ],
};

const SESSIONS: SessionInfo[] = [
  { session_id: "s-ops-1", title: "incident watch", workspace: "/w", agent: "ops", model: "m", mode: "interactive", updated_at: "2026-06-29", messages: 2 },
  { session_id: "s-cowork-1", title: "hi there", workspace: "", agent: "cowork", model: "m", mode: "interactive", updated_at: "2026-06-29", messages: 1 },
];

const baseProps = {
  agent: "cowork",
  workspace: "",
  surfaces: { cowork: true, chat: false, code: false },
  sessions: SESSIONS,
  projects: [],
  activeSession: "s-cowork-1",
  onSwitchAgent: vi.fn(),
  onNewSession: vi.fn(),
  onSelectSession: vi.fn(),
  onNewProject: vi.fn(),
  onOpenProject: vi.fn(),
  onRenameSession: vi.fn(),
  onMoveSession: vi.fn(),
  onForkSession: vi.fn(),
  onDeleteSession: vi.fn(),
  onArchiveSession: vi.fn(),
  onTogglePin: vi.fn(),
  onOpenModelSettings: vi.fn(),
    onManage: vi.fn(),
  onOpenPersona: vi.fn(),
  onManagePersonas: vi.fn(),
  onOpenScheduled: vi.fn(),
  onOpenAutomation: vi.fn(),
  onOpenIntegrations: vi.fn(),
  onOpenAudit: vi.fn(),
  onOpenInbox: vi.fn(),
  onOpenFiles: vi.fn(),
  onOpenApps: vi.fn(),
  onOpenApp: vi.fn(),
  appsActive: false,
  scheduledActive: false,
  integrationsActive: false,
  auditActive: false,
  inboxActive: false,
  filesActive: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("Sidebar group/filter control", () => {
  it("choosing Persona persists via setNavLayout and switches to the per-persona accordion", async () => {
    const calls = stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
      { match: "/v1/settings/nav-layout", method: "POST", json: { ok: true, nav_layout: "grouped" } },
    ]);
    render(<Sidebar {...baseProps} />);

    // personas load drives the surfaces; the RECENT header's group/filter control is always present.
    const control = await screen.findByLabelText("Group and filter conversations");

    // Open the popover and choose "Group by → Persona".
    fireEvent.click(control);
    fireEvent.click(await screen.findByText("Persona"));

    // POSTs the new layout pref.
    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST" && c.url.includes("/v1/settings/nav-layout"));
      expect(post).toBeTruthy();
      expect(post!.body).toMatchObject({ nav_layout: "grouped" });
    });

    // Close the popover (it stays open so you can group AND filter in one visit) before asserting
    // the accordion — otherwise "Ops" also matches the filter-by-coworker checkbox.
    fireEvent.click(control);

    // Grouped view = the per-persona accordion. The Ops header appears; expanding it lists its
    // session. (Persona configuration moved to Settings ▸ Personas, so there is no header gear.)
    const opsHeader = await screen.findByText("Ops");
    fireEvent.click(opsHeader);
    expect(screen.getByText("incident watch")).toBeTruthy();
    expect(screen.queryByTitle("About the Ops persona")).toBeNull();
  });
});

describe("Chronological list row actions (⋮ menu)", () => {
  // The Recent list sorts by updated_at desc with store order breaking ties, so index 0 = s-ops-1.
  const openOpsMenu = () => fireEvent.click(screen.getAllByTestId("row-menu")[0]);

  it("rename / pin / archive / two-step delete all live behind the row's single kebab", async () => {
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
    ]);
    render(<Sidebar {...baseProps} />);
    await screen.findByText("incident watch"); // flat Recent list rendered

    // Rename: menu item → inline input → Enter commits.
    openOpsMenu();
    fireEvent.click(screen.getByTestId("row-menu-rename"));
    const input = screen.getByDisplayValue("incident watch");
    fireEvent.change(input, { target: { value: "war room" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(baseProps.onRenameSession).toHaveBeenCalledWith("s-ops-1", "war room");

    // Pin moved inside the menu (unpinned session → "Pin").
    openOpsMenu();
    fireEvent.click(screen.getByTestId("row-menu-pin"));
    expect(baseProps.onTogglePin).toHaveBeenCalledWith("s-ops-1", true);

    // Archive.
    openOpsMenu();
    fireEvent.click(screen.getByTestId("row-menu-archive"));
    expect(baseProps.onArchiveSession).toHaveBeenCalledWith("s-ops-1", true);

    // Delete opens a dialog naming the chat. It used to arm in place ("Delete?"
    // replacing "Delete"), which put the confirm under a mouse already moving toward
    // it — the second click was often the first one's momentum (2026-08-31).
    openOpsMenu();
    fireEvent.click(screen.getByTestId("row-menu-delete"));
    expect(baseProps.onDeleteSession).not.toHaveBeenCalled();
    const dialog = screen.getByTestId("confirm-dialog");
    expect(dialog.textContent).toContain("Delete this chat?");
    // Cancel holds focus, not the destructive button: a reflex should produce the
    // safe answer.
    expect(document.activeElement).toBe(screen.getByTestId("confirm-cancel"));
    fireEvent.click(screen.getByTestId("confirm-accept"));
    expect(baseProps.onDeleteSession).toHaveBeenCalledWith("s-ops-1");
  });

  it("the kebab and its menu never select the row; Escape closes the menu", async () => {
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
    ]);
    render(<Sidebar {...baseProps} />);
    await screen.findByText("incident watch");

    openOpsMenu();
    fireEvent.click(screen.getByTestId("row-menu-pin"));
    expect(baseProps.onSelectSession).not.toHaveBeenCalled();

    openOpsMenu();
    expect(screen.getByTestId("row-menu-rename")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("row-menu-rename")).toBeNull();
  });
});

describe("From Slack group (§31)", () => {
  const SLACK_SESSION: SessionInfo = {
    session_id: "s-slack-1",
    title: "#general — check the deploy?",
    workspace: "",
    agent: "cowork",
    model: "m",
    mode: "interactive",
    updated_at: "2026-07-13",
    messages: 2,
    origin: "slack",
    origin_label: "#general · T0AB",
  };

  it("mention-spawned sessions list chronologically in Recent with the platform icon (no band)", async () => {
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
    ]);
    render(<Sidebar {...baseProps} sessions={[...SESSIONS, SLACK_SESSION]} />);
    await screen.findByText("incident watch"); // flat Recent rendered

    // No collapsed band — the session sits directly in the Recent list, exactly once…
    expect(screen.queryByTestId("from-slack-toggle")).toBeNull();
    const row = await screen.findByText("#general — check the deploy?");
    expect(screen.getAllByText("#general — check the deploy?")).toHaveLength(1);

    // …wearing the Slack logo in the row's indicator cluster.
    const cluster = row.closest(".group");
    expect(cluster?.querySelector('[data-logo="slack"]')).toBeTruthy();
  });
});

describe("New-session split button", () => {
  it("collapses to a plain button when only one persona is enabled", async () => {
    stubFetch([
      {
        match: "/v1/personas",
        method: "GET",
        json: { personas: [PERSONAS.personas[0], PERSONAS.personas[3]] }, // cowork + a disabled one
      },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
    ]);
    const { container } = render(<Sidebar {...baseProps} />);
    await screen.findByText("incident watch");

    // No ▾ — nothing to pick; the primary button starts the sole enabled persona.
    await waitFor(() => expect(screen.queryByLabelText("Choose a persona")).toBeNull());
    fireEvent.click(container.querySelector(".newsplit-primary")!);
    expect(baseProps.onNewSession).toHaveBeenCalledWith("cowork");
  });

  it("primary starts the last-used persona; the menu lists enabled personas + Manage personas…", async () => {
    localStorage.setItem("ocw.flag.personas", "1"); // Manage entry is launch-flagged off
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
    ]);
    const { container } = render(<Sidebar {...baseProps} />);
    await screen.findByLabelText("Group and filter conversations");

    // Primary action → a new session with the current (last-used) persona.
    fireEvent.click(container.querySelector(".newsplit-primary")!);
    expect(baseProps.onNewSession).toHaveBeenCalledWith("cowork");

    // ▾ opens the persona menu: enabled personas appear, the disabled one does not, plus a manage entry.
    fireEvent.click(screen.getByLabelText("Choose a persona"));
    const menu = (await screen.findByText("Start a session as")).closest(".newsplit-menu") as HTMLElement;
    const w = within(menu);
    expect(w.getByText("Ops")).toBeTruthy();
    expect(w.getByText("Code")).toBeTruthy();
    expect(w.queryByText("Disabled One")).toBeNull();
    expect(w.getByText("Manage personas…")).toBeTruthy();

    // Selecting a persona starts a session as that persona.
    fireEvent.click(w.getByText("Ops"));
    expect(baseProps.onNewSession).toHaveBeenCalledWith("ops");

    // "Manage personas…" opens the persona management surface.
    fireEvent.click(screen.getByLabelText("Choose a persona"));
    fireEvent.click(await screen.findByText("Manage personas…"));
    expect(baseProps.onManagePersonas).toHaveBeenCalled();
  });

  it("hides Manage personas… while the launch flag is off (the default)", async () => {
    localStorage.removeItem("ocw.flag.personas");
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
    ]);
    render(<Sidebar {...baseProps} />);
    await screen.findByLabelText("Group and filter conversations");
    fireEvent.click(screen.getByLabelText("Choose a persona"));
    const menu = (await screen.findByText("Start a session as")).closest(".newsplit-menu") as HTMLElement;
    expect(within(menu).getByText("Ops")).toBeTruthy();
    expect(within(menu).queryByText("Manage personas…")).toBeNull();
  });
});

describe("Footer account row — QualiTaTi identity", () => {
  it("signed out: row says Not signed in; the menu's sign-in opens Settings → Models", async () => {
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      { match: "/v1/qualitati/status", json: { ok: true, signed_in: false } },
    ]);
    const onOpenModelSettings = vi.fn();
    render(<Sidebar {...baseProps} onOpenModelSettings={onOpenModelSettings} />);
    const row = await screen.findByTestId("account-row");
    expect(row.textContent).toContain("Not signed in");

    fireEvent.click(row);
    fireEvent.click(await screen.findByTestId("account-sign-in"));
    expect(onOpenModelSettings).toHaveBeenCalled();
  });

  it("signed in: row shows the QualiTaTi username and the menu shows the balance", async () => {
    stubFetch([
      { match: "/v1/personas", method: "GET", json: PERSONAS },
      {
        match: "/v1/qualitati/status",
        json: {
          ok: true,
          signed_in: true,
          provider_configured: true,
          profile: { username: "shubin", credits: 420, plan: "scholar" },
        },
      },
    ]);
    render(<Sidebar {...baseProps} />);
    const row = await screen.findByTestId("account-row");
    await waitFor(() => expect(row.textContent).toContain("shubin"));

    fireEvent.click(row);
    const header = await screen.findByTestId("account-qt-header");
    expect(header.textContent).toContain("420 credits");
    expect(header.textContent).toContain("QualiTaTi");
  });
});

describe("Sidebar brand footer", () => {
  it("carries the wordmark + powered-by line at the bottom, not in the title strip", async () => {
    stubFetch([]);
    render(<Sidebar {...baseProps} />);
    const footer = await screen.findByTestId("brand-footer");
    expect(footer.textContent).toContain("MimiWork");
    expect(footer.textContent).toContain("Powered by QualiTaTi.com");
    expect(footer.querySelector("img")).toBeTruthy();
  });
});

describe("Sidebar projects band", () => {
  it("lists live projects, hides archived, and opens the project page", async () => {
    stubFetch([]);
    const onOpenProject = vi.fn();
    render(
      <Sidebar
        {...baseProps}
        onOpenProject={onOpenProject}
        projects={[
          { id: "grp_p_thesis", name: "Thesis", emoji: "🎓", pinned: true, archived: false, sessions: 3, last_activity: "", has_instructions: true },
          { id: "grp_p_old", name: "Old", emoji: "", pinned: false, archived: true, sessions: 0, last_activity: "", has_instructions: false },
        ]}
      />,
    );
    const band = await screen.findByTestId("projects-band");
    const rows = band.querySelectorAll('[data-testid="project-row"]');
    expect(rows.length).toBe(1);
    expect(rows[0].textContent).toContain("Thesis");
    // The row's NAME opens the project; the chevron beside it only expands.
    fireEvent.click(rows[0].querySelectorAll("button")[1]);
    expect(onOpenProject).toHaveBeenCalledWith("grp_p_thesis");
  });
});

describe("Sidebar drag-to-project", () => {
  it("dropping a session row on a project row asks App to move it there", async () => {
    stubFetch([]);
    const onMoveSession = vi.fn();
    const project = {
      id: "grp_thesis", name: "Thesis", emoji: "", pinned: false, archived: false,
      sessions: 0, last_activity: "", has_instructions: false,
    };
    render(<Sidebar {...baseProps} projects={[project as any]} onMoveSession={onMoveSession} />);
    const row = (await screen.findAllByTestId("session-row"))[0];
    const target = screen.getAllByTestId("project-row")[0];
    const store: Record<string, string> = {};
    const dt = {
      setData: (k: string, v: string) => { store[k] = v; },
      getData: (k: string) => store[k] ?? "",
      types: [] as string[],
      effectAllowed: "", dropEffect: "",
    };
    fireEvent.dragStart(row, { dataTransfer: dt });
    dt.types = Object.keys(store);
    fireEvent.dragOver(target, { dataTransfer: dt });
    expect(target.getAttribute("data-drop-active")).toBe("true");
    fireEvent.drop(target, { dataTransfer: dt });
    // Filed under the GROUP — the session's folder is not part of this at all.
    expect(onMoveSession).toHaveBeenCalledWith(baseProps.sessions[0].session_id, "grp_thesis");
    expect(target.getAttribute("data-drop-active")).toBeNull();
  });
});

describe("Sidebar archived projects", () => {
  it("folds archived projects under the band; opening one goes to its page", async () => {
    stubFetch([]);
    const onOpenProject = vi.fn();
    const mk = (name: string, archived: boolean) => ({
      id: `grp_${name}`, name, emoji: "", pinned: false, archived,
      sessions: 0, last_activity: "", has_instructions: false,
    });
    render(
      <Sidebar
        {...baseProps}
        projects={[mk("Live", false), mk("Old thesis", true)] as any}
        onOpenProject={onOpenProject}
      />,
    );
    await screen.findByTestId("projects-band");
    expect(screen.getAllByTestId("project-row").map((r) => r.textContent)).toEqual(["Live"]);
    const toggle = screen.getByTestId("projects-archived-toggle");
    expect(toggle.textContent).toContain("1 archived");
    expect(screen.queryByTestId("project-row-archived")).toBeNull();
    fireEvent.click(toggle);
    const row = screen.getByTestId("project-row-archived");
    expect(row.textContent).toContain("Old thesis");
    fireEvent.click(row);
    expect(onOpenProject).toHaveBeenCalledWith("grp_Old thesis");
  });
});

describe("Sidebar — a project groups conversations (2026-08-31)", () => {
  const GROUP = {
    id: "grp_thesis", name: "Thesis", emoji: "🎓", pinned: false, archived: false,
    sessions: 1, last_activity: "", has_instructions: false,
  };

  it("a filed conversation leaves the flat list and appears under its project", async () => {
    stubFetch([]);
    const filed = { ...baseProps.sessions[0], project_id: "grp_thesis" };
    const rest = baseProps.sessions.slice(1);
    render(<Sidebar {...baseProps} sessions={[filed, ...rest]} projects={[GROUP as any]} />);

    // Gone from the flat list — a list that shows everything twice is not organised.
    const flat = await screen.findAllByTestId("session-row");
    expect(flat.map((r) => r.getAttribute("title") || r.textContent).join(" ")).not.toContain(
      filed.title,
    );

    // And present once its project is expanded.
    fireEvent.click(screen.getAllByTestId("project-toggle")[0]);
    const inside = screen.getAllByTestId("project-session-row");
    expect(inside.map((r) => r.textContent).join(" ")).toContain(filed.title);
  });

  it("projects sit BELOW the conversations", async () => {
    stubFetch([]);
    render(<Sidebar {...baseProps} projects={[GROUP as any]} />);

    const band = await screen.findByTestId("projects-band");
    const row = screen.getAllByTestId("session-row")[0];
    // Node.compareDocumentPosition: FOLLOWING means the band comes after the row.
    expect(row.compareDocumentPosition(band) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("dragging a conversation OUT of a project files it back to the flat list", async () => {
    stubFetch([]);
    const onMoveSession = vi.fn();
    const filed = { ...baseProps.sessions[0], project_id: "grp_thesis" };
    render(
      <Sidebar
        {...baseProps}
        sessions={[filed, ...baseProps.sessions.slice(1)]}
        projects={[GROUP as any]}
        onMoveSession={onMoveSession}
      />,
    );
    fireEvent.click((await screen.findAllByTestId("project-toggle"))[0]);
    const inside = screen.getAllByTestId("project-session-row")[0];
    expect(inside.getAttribute("draggable")).toBe("true");
  });

  it("with no projects yet, the band invites the gesture rather than naming a folder", async () => {
    stubFetch([]);
    render(<Sidebar {...baseProps} projects={[]} />);
    const band = await screen.findByTestId("projects-band");
    expect(band.textContent).toContain("Drag a conversation here");
    expect(band.textContent).not.toContain("folder");
  });
});
