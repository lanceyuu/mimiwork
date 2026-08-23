/** QualiTaTi account card: the three states a user actually sees. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QualitatiAccountCard } from "./QualitatiAccountCard";

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn() }));
vi.mock("../tauri", () => ({ openExternal }));

type Call = { url: string; method: string; body?: any };

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const SIGNED_OUT = { ok: true, signed_in: false };
const SIGNED_IN = {
  ok: true,
  signed_in: true,
  provider_configured: true,
  profile: { username: "shubin", email: "s@x.com", credits: 420, plan: "scholar" },
};

describe("QualitatiAccountCard", () => {
  it("signed out: shows the sign-in form, no credentials prefilled", async () => {
    stubFetch([{ match: "/v1/qualitati/status", json: SIGNED_OUT }]);
    render(<QualitatiAccountCard />);
    const user = await screen.findByTestId("qualitati-username");
    expect((user as HTMLInputElement).value).toBe("");
    expect(screen.getByTestId("qualitati-password")).toBeTruthy();
  });

  it("signs in and shows the live credit balance", async () => {
    const calls = stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_OUT },
      { match: "/v1/qualitati/login", method: "POST", json: SIGNED_IN },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.change(await screen.findByTestId("qualitati-username"), {
      target: { value: "shubin" },
    });
    fireEvent.change(screen.getByTestId("qualitati-password"), { target: { value: "pw" } });
    // After login the card refreshes status — now signed in.
    calls.length = 0;
    stubFetch([
      { match: "/v1/qualitati/login", method: "POST", json: SIGNED_IN },
      { match: "/v1/qualitati/status", json: SIGNED_IN },
    ]);
    fireEvent.click(screen.getByTestId("qualitati-signin"));
    await waitFor(() => expect(screen.getByTestId("qualitati-profile")).toBeTruthy());
    expect(screen.getByTestId("qualitati-profile").textContent).toContain("420 credits");
    expect(screen.getByTestId("qualitati-profile").textContent).toContain("scholar");
  });

  it("an MFA-protected account gets the code step", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_OUT },
      { match: "/v1/qualitati/login", method: "POST", json: { ok: true, mfa_required: true } },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.change(await screen.findByTestId("qualitati-username"), { target: { value: "u" } });
    fireEvent.change(screen.getByTestId("qualitati-password"), { target: { value: "p" } });
    fireEvent.click(screen.getByTestId("qualitati-signin"));
    await waitFor(() => expect(screen.getByTestId("qualitati-mfa")).toBeTruthy());
  });

  it("a wrong password shows the server's message, not a generic one", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_OUT },
      {
        match: "/v1/qualitati/login",
        method: "POST",
        json: { ok: false, signed_in: false, error: "Incorrect username or password" },
      },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.change(await screen.findByTestId("qualitati-username"), { target: { value: "u" } });
    fireEvent.change(screen.getByTestId("qualitati-password"), { target: { value: "x" } });
    fireEvent.click(screen.getByTestId("qualitati-signin"));
    await waitFor(() =>
      expect(screen.getByTestId("qualitati-error").textContent).toContain("Incorrect"),
    );
  });

  it("signed in: sign out calls the endpoint and returns to the form", async () => {
    const calls = stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/qualitati/logout", method: "POST", json: { ok: true, signed_in: false } },
    ]);
    render(<QualitatiAccountCard />);
    const out = await screen.findByTestId("qualitati-signout");
    calls.length = 0;
    stubFetch([
      { match: "/v1/qualitati/logout", method: "POST", json: { ok: true, signed_in: false } },
      { match: "/v1/qualitati/status", json: SIGNED_OUT },
    ]);
    fireEvent.click(out);
    await waitFor(() => expect(screen.getByTestId("qualitati-username")).toBeTruthy());
  });
});

describe("QualitatiAccountCard — create account", () => {
  it("opens the canonical Terms and Privacy Policy pages", async () => {
    stubFetch([{ match: "/v1/qualitati/status", json: SIGNED_OUT }]);
    render(<QualitatiAccountCard />);
    fireEvent.click(await screen.findByTestId("qualitati-mode-register"));

    fireEvent.click(screen.getByRole("button", { name: "Terms" }));
    fireEvent.click(screen.getByRole("button", { name: "Privacy Policy" }));

    expect(openExternal).toHaveBeenNthCalledWith(1, "https://qualitati.com/terms");
    expect(openExternal).toHaveBeenNthCalledWith(2, "https://qualitati.com/privacy-policy");
  });

  it("registers through the sidecar, then flips to sign-in with a verify-email notice", async () => {
    const calls = stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_OUT },
      {
        match: "/v1/qualitati/register",
        method: "POST",
        json: { ok: true, username: "newbie", email_sent: true, message: "…" },
      },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.click(await screen.findByTestId("qualitati-mode-register"));
    fireEvent.change(screen.getByTestId("qualitati-reg-username"), { target: { value: "newbie" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-email"), { target: { value: "n@x.com" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-password"), { target: { value: "weakpassword" } });
    expect(screen.getByTestId("qualitati-reg-hint").textContent).toContain("uppercase");
    fireEvent.change(screen.getByTestId("qualitati-reg-password"), { target: { value: "Str0ng!pw" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-confirm"), { target: { value: "Str0ng!pw" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-invite"), { target: { value: "ab12" } });
    // Terms gate: the button stays disabled until the box is ticked.
    expect((screen.getByTestId("qualitati-register") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("qualitati-reg-terms"));
    expect((screen.getByTestId("qualitati-register") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByTestId("qualitati-register"));

    await waitFor(() => expect(screen.getByTestId("qualitati-registered")).toBeTruthy());
    const reg = calls.find((c) => c.url.includes("/v1/qualitati/register"))!;
    expect(reg.body).toEqual({
      username: "newbie", email: "n@x.com", password: "Str0ng!pw", referrer_code: "AB12",
    });
    // Back on the sign-in face, username kept, password wiped.
    expect((screen.getByTestId("qualitati-username") as HTMLInputElement).value).toBe("newbie");
    expect((screen.getByTestId("qualitati-password") as HTMLInputElement).value).toBe("");
    expect(screen.getByTestId("qualitati-registered").textContent).toContain("n@x.com");
  });

  it("shows the server's reason when registration is refused", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_OUT },
      { match: "/v1/qualitati/register", method: "POST", json: { ok: false, error: "Username already registered" } },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.click(await screen.findByTestId("qualitati-mode-register"));
    fireEvent.change(screen.getByTestId("qualitati-reg-username"), { target: { value: "taken" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-email"), { target: { value: "t@x.com" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-password"), { target: { value: "Str0ng!pw" } });
    fireEvent.change(screen.getByTestId("qualitati-reg-confirm"), { target: { value: "Str0ng!pw" } });
    fireEvent.click(screen.getByTestId("qualitati-reg-terms"));
    fireEvent.click(screen.getByTestId("qualitati-register"));
    await waitFor(() =>
      expect(screen.getByTestId("qualitati-error").textContent).toContain("Username already registered"),
    );
    expect(screen.getByTestId("qualitati-register-form")).toBeTruthy(); // stays on the form
  });

  it("tells the signed-in user their QualiTaTi data is usable — and that it will ask first", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
    ]);
    render(<QualitatiAccountCard />);
    const note = await screen.findByTestId("qualitati-data-note");
    expect(note.textContent).toContain("Your QualiTaTi work is available here");
    expect(note.textContent).toContain("approval");
  });

  it("says nothing about data while signed out", async () => {
    stubFetch([{ match: "/v1/qualitati/status", json: SIGNED_OUT }]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-username");
    expect(screen.queryByTestId("qualitati-data-note")).toBeNull();
  });
});
