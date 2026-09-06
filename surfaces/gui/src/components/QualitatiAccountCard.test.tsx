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
    // A broken rule is a red notice with the field outlined, not a grey hint (owner ask 2026-09-04).
    const hint = screen.getByTestId("qualitati-reg-hint");
    expect(hint.textContent).toContain("uppercase");
    expect(hint.getAttribute("data-state")).toBe("problem");
    expect(hint.getAttribute("role")).toBe("alert");
    expect(screen.getByTestId("qualitati-reg-password").getAttribute("aria-invalid")).toBe("true");
    fireEvent.change(screen.getByTestId("qualitati-reg-password"), { target: { value: "Str0ng!pw" } });
    expect(screen.getByTestId("qualitati-reg-hint").getAttribute("data-state")).toBe("ok");
    fireEvent.change(screen.getByTestId("qualitati-reg-confirm"), { target: { value: "Str0ng!p" } });
    expect(screen.getByTestId("qualitati-reg-hint").textContent).toContain("don't match");
    expect(screen.getByTestId("qualitati-reg-confirm").getAttribute("aria-invalid")).toBe("true");
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

  it("says why the Mimi models are missing and offers to connect them", async () => {
    // Signed in, credits visible, no gateway key — the reported dead end (2026-08-24).
    const calls = stubFetch([
      { match: "/v1/qualitati/status", json: { ...SIGNED_IN, provider_configured: false } },
      { match: "/v1/qualitati/reconnect", method: "POST", json: { ok: true, provider_configured: true } },
    ]);
    const onChanged = vi.fn();
    render(<QualitatiAccountCard onChanged={onChanged} />);
    const note = await screen.findByTestId("qualitati-models-missing");
    expect(note.textContent).toContain("aren't connected yet");

    fireEvent.click(screen.getByTestId("qualitati-reconnect"));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/v1/qualitati/reconnect"))).toBe(true),
    );
    // The picker has to re-read: that is where the three models appear.
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("says nothing about connecting when the models are already there", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: { ...SIGNED_IN, provider_configured: true } },
    ]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-profile");
    expect(screen.queryByTestId("qualitati-models-missing")).toBeNull();
  });

  it("shows the three Mimi tiers as soon as you are signed in", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/settings", json: { models: ["qualitati:mimi-puppy"] } },
    ]);
    render(<QualitatiAccountCard />);
    const strip = await screen.findByTestId("qualitati-models");
    expect(strip.textContent).toContain("Mimi Puppy");
    expect(strip.textContent).toContain("Mimi Hound");
    expect(strip.textContent).toContain("Mimi Wolf");
    // The one already curated says so; the others offer to join the picker.
    await waitFor(() =>
      expect(screen.getByTestId("qualitati-model-qualitati:mimi-puppy").textContent).toContain(
        "In the composer's picker",
      ),
    );
    expect(screen.getByTestId("qualitati-model-add-qualitati:mimi-wolf")).toBeTruthy();
    expect(screen.queryByTestId("qualitati-model-add-qualitati:mimi-puppy")).toBeNull();
  });

  it("Test asks the model to answer and reports what came back", async () => {
    const calls = stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/settings", json: { models: [] } },
      { match: "/v1/models/test", method: "POST", json: { ok: true, reply: "ready" } },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.click(await screen.findByTestId("qualitati-model-test-qualitati:mimi-hound"));
    await waitFor(() =>
      expect(
        screen.getByTestId("qualitati-model-result-qualitati:mimi-hound").textContent,
      ).toContain("Works"),
    );
    expect(calls.find((c) => c.url.includes("/v1/models/test"))!.body).toEqual({
      model: "qualitati:mimi-hound",
    });
  });

  it("a tier that refuses says why, in the row itself", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/settings", json: { models: [] } },
      {
        match: "/v1/models/test",
        method: "POST",
        json: { ok: false, error: "your account doesn't have access to mimi-wolf" },
      },
    ]);
    render(<QualitatiAccountCard />);
    fireEvent.click(await screen.findByTestId("qualitati-model-test-qualitati:mimi-wolf"));
    await waitFor(() =>
      expect(
        screen.getByTestId("qualitati-model-result-qualitati:mimi-wolf").textContent,
      ).toContain("doesn't have access"),
    );
  });

  it("says nothing about models while signed out", async () => {
    stubFetch([{ match: "/v1/qualitati/status", json: SIGNED_OUT }]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-username");
    expect(screen.queryByTestId("qualitati-models")).toBeNull();
  });
});

describe("model region (GDPR switch)", () => {
  // Owner correction 2026-08-28: the option lives HERE, in the app's Settings —
  // not on the qualitati.com Profile page.
  const REGION_US = { ok: true, region: "us", configured: false };

  it("signed in: shows both regions with the current one active", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/qualitati/region", json: REGION_US },
    ]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-region");
    expect(screen.getByTestId("qualitati-region-us").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("qualitati-region-eu").getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByText(/Paris/)).toBeTruthy();
  });

  it("clicking GDPR saves it via PUT and marks it active", async () => {
    const calls = stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/qualitati/region", method: "GET", json: REGION_US },
      { match: "/v1/qualitati/region", method: "PUT", json: { ok: true, region: "eu", configured: true } },
    ]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-region");
    fireEvent.click(screen.getByTestId("qualitati-region-eu"));
    await waitFor(() =>
      expect(screen.getByTestId("qualitati-region-eu").getAttribute("aria-pressed")).toBe("true"),
    );
    const put = calls.find((c) => c.method === "PUT" && c.url.includes("/v1/qualitati/region"));
    expect(put?.body).toEqual({ region: "eu" });
  });

  it("a failed save falls back to the truth instead of lying", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/qualitati/region", method: "GET", json: REGION_US },
      { match: "/v1/qualitati/region", method: "PUT", json: { ok: false, error: "offline" } },
    ]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-region");
    fireEvent.click(screen.getByTestId("qualitati-region-eu"));
    await waitFor(() =>
      expect(screen.getByTestId("qualitati-region-us").getAttribute("aria-pressed")).toBe("true"),
    );
  });

  it("signed out: no region section", async () => {
    stubFetch([{ match: "/v1/qualitati/status", json: SIGNED_OUT }]);
    render(<QualitatiAccountCard />);
    await screen.findByTestId("qualitati-username");
    expect(screen.queryByTestId("qualitati-region")).toBeNull();
  });
});

// The footprint line leads with the account's OWN rough share (owner ask 2026-09-07) and
// keeps the service-wide measurement under it; the estimate alone is enough to show it.
describe("QualitatiAccountCard footprint", () => {
  it("shows the personal estimate first, the measured service figure second", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      {
        match: "/v1/qualitati/footprint",
        json: {
          ok: true,
          carbon_g: 812.5,
          water_l: 3.2,
          you: { carbon_g: 0.55, water_l: 0.018, energy_wh: 10, tokens_in: 100000, tokens_out: 10000, calls: 2, region: "eu", method: "rough" },
        },
      },
    ]);
    render(<QualitatiAccountCard />);
    const line = await screen.findByTestId("qualitati-footprint");
    expect(line.textContent).toContain("Your impact this month, roughly: 550 mg CO₂e · 18.0 mL water · from 2 calls on the French grid");
    expect(line.textContent).toContain("Whole Mimi service, measured by Scaleway, Paris 🇫🇷: 812.50 g CO₂e · 3.20 L water");
  });
  it("stands on the estimate alone when the measurement is down", async () => {
    stubFetch([
      { match: "/v1/qualitati/status", json: SIGNED_IN },
      { match: "/v1/qualitati/footprint", json: { ok: true, you: { carbon_g: 2, water_l: 0.05, energy_wh: 5, tokens_in: 1, tokens_out: 1, calls: 1, region: "us", method: "rough" } } },
    ]);
    render(<QualitatiAccountCard />);
    const line = await screen.findByTestId("qualitati-footprint");
    expect(line.textContent).toContain("2.00 g CO₂e");
    expect(line.textContent).toContain("from 1 call on the US grid");
    expect(line.textContent).not.toContain("Whole Mimi service");
  });
});
