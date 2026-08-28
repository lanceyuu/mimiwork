/** QualiTaTi account card (Settings → Models).
 *
 * Sign in with a QualiTaTi account and model calls can spend its credit balance:
 * the sidecar mints a personal API key and configures the `qualitati` provider,
 * so "Mimi Hound · QualiTaTi credits" appears in the model picker with no key-pasting.
 * Signed in, the card shows the live balance; signed out, a two-field form
 * (+ an MFA code step when the account has it enabled).
 *
 * The password goes to the local sidecar over loopback and from there straight
 * to QualiTaTi's /api/login — it is never stored anywhere.
 */
import { useEffect, useState } from "react";
import {
  QualitatiStatus,
  addModel,
  getSettings,
  qualitatiFootprint,
  qualitatiRegion,
  qualitatiSetRegion,
  qualitatiLogin,
  qualitatiLogout,
  qualitatiReconnect,
  qualitatiRegister,
  qualitatiStatus,
  qualitatiVerifyMfa,
  testModel,
  type ModelSettings,
  type QualitatiFootprint,
  type QualitatiRegion,
  type QualitatiRegisterResult,
} from "../api";
import mimiMark from "../assets/mimi/mimi-line.png";
import { openExternal } from "../tauri";

// Password policy mirrors QualiTaTi's server rule (auth.validate_password_complexity) so the
// form can say no BEFORE a round trip; the server's own message is still shown if it disagrees.
export function passwordPolicyProblem(pw: string): string | null {
  if (pw.length < 8) return "at least 8 characters";
  if (!/[A-Z]/.test(pw)) return "an uppercase letter";
  if (!/[a-z]/.test(pw)) return "a lowercase letter";
  if (!/[0-9]/.test(pw)) return "a number";
  if (!/[^A-Za-z0-9]/.test(pw)) return "a special character";
  return null;
}

// The gateway's three tiers, in the order a user meets them: free first, then by price.
const MIMI_TIERS = [
  { id: "qualitati:mimi-puppy", label: "Mimi Puppy", blurb: "free every day" },
  { id: "qualitati:mimi-hound", label: "Mimi Hound", blurb: "fast · spends credits" },
  { id: "qualitati:mimi-wolf", label: "Mimi Wolf", blurb: "powerful · spends credits" },
] as const;

export function QualitatiAccountCard({ onChanged }: { onChanged?: () => void }) {
  const [state, setState] = useState<QualitatiStatus | null>(null);
  const [footprint, setFootprint] = useState<QualitatiFootprint | null>(null);
  const [region, setRegion] = useState<QualitatiRegion | null>(null);
  const [regionSaving, setRegionSaving] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<"idle" | "busy" | "mfa">("idle");
  const [error, setError] = useState<string | null>(null);
  // Signed-out card has two faces: sign in (default) and create account — the same
  // registration qualitati.com/register offers, minus leaving the app. §(owner ask 2026-08-21)
  const [reconnecting, setReconnecting] = useState(false);
  const [reconnectError, setReconnectError] = useState<string | null>(null);
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [confirm, setConfirm] = useState("");
  const [invite, setInvite] = useState("");
  const [terms, setTerms] = useState(false);
  const [registered, setRegistered] = useState<string | null>(null);
  // The three tiers, shown right here once signed in. A user who has just signed in should
  // SEE the models they can now use — hunting for them in the composer's picker (and not
  // finding them, when the curated list didn't pick them up) is how this went wrong twice.
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [tested, setTested] = useState<Record<string, { ok: boolean; text: string }>>({});
  const refreshSettings = () => getSettings().then(setSettings).catch(() => setSettings(null));

  const refresh = () => qualitatiStatus().then(setState).catch(() => setState(null));
  useEffect(() => {
    refresh();
  }, []);
  // Which tiers are already in the picker — read once signed in, and again after a
  // sign-in/reconnect flips that.
  useEffect(() => {
    if (state?.signed_in) void refreshSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.signed_in]);
  // The footprint line loads once per Settings visit, only when signed in —
  // measured Scaleway data for the whole Mimi service (server caches 1h).
  useEffect(() => {
    if (state?.signed_in && footprint === null) {
      qualitatiFootprint().then(setFootprint).catch(() => setFootprint({ ok: false }));
    }
    if (state?.signed_in && region === null) {
      qualitatiRegion().then(setRegion).catch(() => setRegion({ ok: false }));
    }
  }, [state?.signed_in, footprint, region]);

  const finish = (result: QualitatiStatus) => {
    if (!result.ok) {
      setError(result.error || "sign-in failed");
      setPhase("idle");
      return;
    }
    if (result.mfa_required) {
      setError(null);
      setPhase("mfa");
      return;
    }
    setError(null);
    setPassword("");
    setCode("");
    setPhase("idle");
    refresh();
    onChanged?.();
  };

  const submit = async () => {
    setPhase("busy");
    finish(await qualitatiLogin(username, password).catch(() => ({ ok: false, signed_in: false, error: "server unreachable" })));
  };
  const submitMfa = async () => {
    setPhase("busy");
    finish(await qualitatiVerifyMfa(code).catch(() => ({ ok: false, signed_in: false, error: "server unreachable" })));
  };

  const policy = passwordPolicyProblem(password);
  const canRegister =
    phase !== "busy" &&
    !!username.trim() &&
    /.+@.+\..+/.test(email) &&
    !policy &&
    password === confirm &&
    terms;
  const submitRegister = async () => {
    setPhase("busy");
    setError(null);
    const r = await qualitatiRegister({
      username: username.trim(),
      email: email.trim(),
      password,
      ...(invite.trim() ? { referrer_code: invite.trim().toUpperCase() } : {}),
    }).catch((): QualitatiRegisterResult => ({ ok: false, error: "server unreachable" }));
    setPhase("idle");
    if (!r.ok) {
      setError(r.error || "registration failed");
      return;
    }
    // QualiTaTi emails a verification link; sign-in works after it's clicked. Flip back to
    // the sign-in face with the username kept, password cleared (never retained past the call).
    setRegistered(
      r.email_sent === false
        ? "Account created, but the verification email could not be sent — contact support@qualitati.com."
        : `Account created — check ${email.trim()} for the verification link, then sign in here.`,
    );
    setPassword("");
    setConfirm("");
    setMode("signin");
  };

  if (!state) return null;

  return (
    <div
      className="rounded-xl border border-line bg-panel px-4 py-3.5 mb-4"
      data-testid="qualitati-card"
    >
      <div className="flex items-center gap-2.5">
        <img src={mimiMark} alt="" className="w-[26px] h-[26px] shrink-0" draggable={false} />
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-semibold">QualiTaTi account</div>
          <div className="text-[12px] text-muted truncate">
            {state.signed_in
              ? "“Mimi Puppy” is free for use; “Mimi Hound” (fast) and “Mimi Wolf” (powerful) spend your credits."
              : "Sign in for free Mimi Puppy every day — plus your QualiTaTi credits for Hound and Wolf. No API key needed."}
          </div>
        </div>
        {state.signed_in && (
          <button
            className="text-[12.5px] text-muted hover:text-ink hover:underline underline-offset-2 shrink-0"
            data-testid="qualitati-signout"
            onClick={async () => {
              await qualitatiLogout();
              refresh();
              onChanged?.();
            }}
          >
            Sign out
          </button>
        )}
      </div>

      {state.signed_in ? (
        <div className="mt-2.5 flex items-center gap-3 text-[12.5px]" data-testid="qualitati-profile">
          <span className="font-medium">{state.profile?.username ?? state.username}</span>
          {state.profile ? (
            <>
              <span className="px-1.5 py-0.5 rounded-md bg-accentSoft/50 text-[11.5px] font-semibold">
                {state.profile.credits ?? 0} credits
              </span>
              {state.profile.plan && <span className="text-faint">{state.profile.plan} plan</span>}
            </>
          ) : (
            <span className="text-faint">{state.error ?? "balance unavailable"}</span>
          )}
        </div>
      ) : null}
      {/* Signed in, but no gateway key — so the three Mimi models are missing from the
        * picker and nothing on screen said why (user report 2026-08-24). Say it, and offer
        * the repair: the sign-in worked, only the key didn't, so no password is needed. */}
      {state.signed_in && state.provider_configured === false ? (
        <div
          className="mt-2.5 rounded-lg border border-warnInk/20 bg-warnSoft/60 px-3 py-2 text-[12px] leading-relaxed"
          data-testid="qualitati-models-missing"
          role="status"
        >
          <span className="text-ink font-medium">
            The Mimi models aren't connected yet.
          </span>{" "}
          <span className="text-muted">
            You're signed in, but this computer has no key for the model gateway — that's why
            “Mimi Puppy”, “Hound” and “Wolf” aren't in the picker.
          </span>
          <div className="mt-1.5 flex items-center gap-3">
            <button
              className="text-[12px] px-2.5 py-1 rounded-lg bg-accent text-white disabled:opacity-40"
              data-testid="qualitati-reconnect"
              disabled={reconnecting}
              onClick={async () => {
                setReconnecting(true);
                const out = await qualitatiReconnect().catch(() => ({
                  ok: false,
                  error: "could not reach the server",
                }));
                setReconnecting(false);
                if (out.ok) {
                  await refresh();
                  onChanged?.();
                } else {
                  setReconnectError(out.error || "could not connect the models");
                }
              }}
            >
              {reconnecting ? "Connecting…" : "Connect the models"}
            </button>
            {reconnectError && <span className="text-danger/90">{reconnectError}</span>}
          </div>
        </div>
      ) : null}
      {/* Signing in buys credits AND opens the account's research data. Say so once, here,
        * with the guarantee attached: nothing is fetched until you approve that fetch. */}
      {state.signed_in ? (
        <div
          className="mt-2.5 rounded-lg border border-line bg-paper px-3 py-2 text-[12px] leading-relaxed"
          data-testid="qualitati-data-note"
        >
          <span className="text-ink font-medium">Your QualiTaTi work is available here.</span>{" "}
          <span className="text-muted">
            Ask for a project, an interview transcript, or a survey's responses and Mimi can
            pull them in to analyse — <span className="text-ink">each retrieval asks your
            approval first</span>, and nothing is fetched on its own.
          </span>
        </div>
      ) : null}
      {/* The three tiers, with a Test that really asks the model to answer. */}
      {state.signed_in ? (
        <div className="mt-2.5" data-testid="qualitati-models">
          <div className="text-[11px] uppercase tracking-[0.05em] text-faint font-semibold mb-1.5">
            Your Mimi models
          </div>
          <div className="rounded-lg border border-line overflow-hidden">
            {MIMI_TIERS.map((tier, i) => {
              const inPicker = (settings?.models ?? []).includes(tier.id);
              const result = tested[tier.id];
              return (
                <div
                  key={tier.id}
                  className={
                    "flex items-center gap-3 px-3 py-2 bg-paper" +
                    (i > 0 ? " border-t border-line" : "")
                  }
                  data-testid={`qualitati-model-${tier.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] text-ink font-medium">
                      {tier.label}{" "}
                      <span className="text-[11.5px] font-normal text-muted">{tier.blurb}</span>
                    </div>
                    {result ? (
                      <div
                        className={
                          "text-[11.5px] mt-0.5 " + (result.ok ? "text-accent" : "text-danger")
                        }
                        data-testid={`qualitati-model-result-${tier.id}`}
                      >
                        {result.text}
                      </div>
                    ) : (
                      <div className="text-[11.5px] text-faint mt-0.5">
                        {inPicker ? "In the composer's picker" : "Not in the picker yet"}
                      </div>
                    )}
                  </div>
                  {!inPicker && (
                    <button
                      className="text-[12px] px-2.5 py-1 rounded-lg border border-line hover:border-lineStrong shrink-0"
                      data-testid={`qualitati-model-add-${tier.id}`}
                      onClick={async () => {
                        await addModel(tier.id).catch(() => undefined);
                        await refreshSettings();
                        onChanged?.();
                      }}
                    >
                      Add
                    </button>
                  )}
                  <button
                    className="text-[12px] px-2.5 py-1 rounded-lg border border-line hover:border-lineStrong shrink-0 disabled:opacity-40"
                    data-testid={`qualitati-model-test-${tier.id}`}
                    disabled={testing === tier.id}
                    onClick={async () => {
                      setTesting(tier.id);
                      const out = await testModel(tier.id).catch(
                        (): Awaited<ReturnType<typeof testModel>> => ({
                          ok: false,
                          error: "could not reach the server",
                        }),
                      );
                      setTesting(null);
                      setTested((cur) => ({
                        ...cur,
                        [tier.id]: {
                          ok: !!out.ok,
                          text: out.ok
                            ? `Works — it answered “${out.reply || "…"}”`
                            : out.error || "no answer",
                        },
                      }));
                    }}
                  >
                    {testing === tier.id ? "Testing…" : "Test"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      {state.signed_in && region?.ok ? (
        <div className="mt-3" data-testid="qualitati-region">
          <div className="text-[12px] font-medium text-ink mb-1">Model region</div>
          <div className="flex gap-2">
            {(
              [
                {
                  id: "us" as const,
                  title: "Default · US",
                  blurb: "DigitalOcean — cheaper credits",
                },
                {
                  id: "eu" as const,
                  title: "Strict GDPR · Paris 🇫🇷",
                  blurb: "Scaleway — data stays in Europe, costs more",
                },
              ]
            ).map((opt) => {
              const active = region.region === opt.id;
              return (
                <button
                  key={opt.id}
                  className={
                    "flex-1 rounded-lg border px-2.5 py-2 text-left transition-colors " +
                    (active
                      ? "border-accent bg-accent/5"
                      : "border-line hover:border-accent/50")
                  }
                  data-testid={`qualitati-region-${opt.id}`}
                  aria-pressed={active}
                  disabled={regionSaving}
                  onClick={async () => {
                    if (active || regionSaving) return;
                    setRegionSaving(true);
                    const prev = region;
                    setRegion({ ...region, region: opt.id, configured: true });
                    const out = await qualitatiSetRegion(opt.id).catch(() => ({ ok: false }));
                    if (!out.ok) setRegion(prev); // saving failed — show the truth
                    setRegionSaving(false);
                  }}
                >
                  <div className="text-[12px] font-medium text-ink">{opt.title}</div>
                  <div className="text-[11px] text-muted">{opt.blurb}</div>
                </button>
              );
            })}
          </div>
          <div className="mt-1 text-[11px] text-muted">
            Applies to this account's next message, on every device.
          </div>
        </div>
      ) : null}
      {state.signed_in && footprint?.ok && footprint.carbon_g !== undefined ? (
        <div
          className="mt-2 flex items-center gap-1.5 text-[11.5px] text-muted"
          data-testid="qualitati-footprint"
          title={`${footprint.scope ?? ""} — ${footprint.measured_by ?? ""}`}
        >
          <span aria-hidden>🌱</span>
          <span>
            Environmental impact this month, whole Mimi service:{" "}
            <span className="text-ink font-medium tabular-nums">
              {footprint.carbon_g < 1
                ? `${(footprint.carbon_g * 1000).toFixed(0)} mg`
                : `${footprint.carbon_g.toFixed(2)} g`}{" "}
              CO₂e
            </span>{" "}
            ·{" "}
            <span className="text-ink font-medium tabular-nums">
              {((footprint.water_l ?? 0) * 1000).toFixed(1)} mL
            </span>{" "}
            water · measured by Scaleway, Paris 🇫🇷
          </span>
        </div>
      ) : null}
      {state.signed_in ? null : phase === "mfa" ? (
        <div className="mt-2.5 flex items-center gap-2">
          <input
            className="input w-[140px]"
            placeholder="MFA code"
            value={code}
            inputMode="numeric"
            autoFocus
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && code && submitMfa()}
            data-testid="qualitati-mfa"
          />
          <button className="btn btn-primary text-[12.5px]" disabled={!code} onClick={submitMfa}>
            Verify
          </button>
        </div>
      ) : (
        <>
          <div className="mt-2.5 flex items-center gap-1 text-[12px]" role="tablist" aria-label="Account">
            {(["signin", "register"] as const).map((m) => (
              <button
                key={m}
                role="tab"
                aria-selected={mode === m}
                data-testid={`qualitati-mode-${m}`}
                className={
                  "px-2.5 py-1 rounded-md font-medium " +
                  (mode === m ? "bg-paper text-ink" : "text-muted hover:text-ink")
                }
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
              >
                {m === "signin" ? "Sign in" : "Create account"}
              </button>
            ))}
            <span className="flex-1" />
            <button
              className="text-[11.5px] text-faint hover:text-ink"
              onClick={() => openExternal("https://qualitati.com")}
            >
              qualitati.com ↗
            </button>
          </div>
          {registered && mode === "signin" && (
            <div
              className="mt-2 rounded-lg border border-ok-line bg-ok-soft px-2.5 py-1.5 text-[12px]"
              data-testid="qualitati-registered"
            >
              {registered}
            </div>
          )}
          {mode === "signin" ? (
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <input
                className="input w-[170px]"
                placeholder="Username"
                value={username}
                autoComplete="username"
                onChange={(e) => setUsername(e.target.value)}
                data-testid="qualitati-username"
              />
              <input
                className="input w-[170px]"
                placeholder="Password"
                type="password"
                value={password}
                autoComplete="current-password"
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && username && password && submit()}
                data-testid="qualitati-password"
              />
              <button
                className="btn btn-primary text-[12.5px]"
                disabled={phase === "busy" || !username || !password}
                onClick={submit}
                data-testid="qualitati-signin"
              >
                {phase === "busy" ? "Signing in…" : "Sign in"}
              </button>
            </div>
          ) : (
            <div className="mt-2.5 grid grid-cols-2 gap-2 max-w-[360px]" data-testid="qualitati-register-form">
              <input
                className="input"
                placeholder="Username"
                value={username}
                autoComplete="username"
                onChange={(e) => setUsername(e.target.value)}
                data-testid="qualitati-reg-username"
              />
              <input
                className="input"
                placeholder="Email"
                type="email"
                value={email}
                autoComplete="email"
                onChange={(e) => setEmail(e.target.value)}
                data-testid="qualitati-reg-email"
              />
              <input
                className="input"
                placeholder="Password"
                type="password"
                value={password}
                autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)}
                data-testid="qualitati-reg-password"
              />
              <input
                className="input"
                placeholder="Confirm password"
                type="password"
                value={confirm}
                autoComplete="new-password"
                onChange={(e) => setConfirm(e.target.value)}
                data-testid="qualitati-reg-confirm"
              />
              <input
                className="input col-span-2"
                placeholder="Invite code (optional)"
                value={invite}
                onChange={(e) => setInvite(e.target.value)}
                data-testid="qualitati-reg-invite"
              />
              <div className="col-span-2 text-[11.5px] text-faint" data-testid="qualitati-reg-hint">
                {password && policy
                  ? `Password needs ${policy}.`
                  : confirm && password !== confirm
                    ? "Passwords don't match."
                    : "8+ characters with upper & lower case, a number and a symbol."}
              </div>
              <label className="col-span-2 flex items-start gap-2 text-[12px] text-muted cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-[3px]"
                  checked={terms}
                  onChange={(e) => setTerms(e.target.checked)}
                  data-testid="qualitati-reg-terms"
                />
                <span>
                  I agree to QualiTaTi's{" "}
                  <button
                    type="button"
                    className="underline underline-offset-2 hover:text-ink"
                    onClick={() => openExternal("https://qualitati.com/terms")}
                  >
                    Terms
                  </button>{" "}
                  and{" "}
                  <button
                    type="button"
                    className="underline underline-offset-2 hover:text-ink"
                    onClick={() => openExternal("https://qualitati.com/privacy-policy")}
                  >
                    Privacy Policy
                  </button>
                  .
                </span>
              </label>
              <div className="col-span-2 flex items-center gap-2">
                <button
                  className="btn btn-primary text-[12.5px] whitespace-nowrap"
                  disabled={!canRegister}
                  onClick={submitRegister}
                  data-testid="qualitati-register"
                >
                  {phase === "busy" ? "Creating…" : "Create free account"}
                </button>
                <span className="text-[11.5px] text-faint">
                  Free plan · monthly member points included
                </span>
              </div>
            </div>
          )}
        </>
      )}
      {error && (
        <div className="mt-1.5 text-[12px] text-danger" data-testid="qualitati-error">
          {error}
        </div>
      )}
    </div>
  );
}
