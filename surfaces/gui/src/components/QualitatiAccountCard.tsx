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
  qualitatiFootprint,
  qualitatiLogin,
  qualitatiLogout,
  qualitatiRegister,
  qualitatiStatus,
  qualitatiVerifyMfa,
  type QualitatiFootprint,
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

export function QualitatiAccountCard({ onChanged }: { onChanged?: () => void }) {
  const [state, setState] = useState<QualitatiStatus | null>(null);
  const [footprint, setFootprint] = useState<QualitatiFootprint | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<"idle" | "busy" | "mfa">("idle");
  const [error, setError] = useState<string | null>(null);
  // Signed-out card has two faces: sign in (default) and create account — the same
  // registration qualitati.com/register offers, minus leaving the app. §(owner ask 2026-08-21)
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [confirm, setConfirm] = useState("");
  const [invite, setInvite] = useState("");
  const [terms, setTerms] = useState(false);
  const [registered, setRegistered] = useState<string | null>(null);

  const refresh = () => qualitatiStatus().then(setState).catch(() => setState(null));
  useEffect(() => {
    refresh();
  }, []);
  // The footprint line loads once per Settings visit, only when signed in —
  // measured Scaleway data for the whole Mimi service (server caches 1h).
  useEffect(() => {
    if (state?.signed_in && footprint === null) {
      qualitatiFootprint().then(setFootprint).catch(() => setFootprint({ ok: false }));
    }
  }, [state?.signed_in, footprint]);

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
          {state.signed_in && state.provider_configured === false && (
            <span className="text-danger/80">provider not configured — sign in again</span>
          )}
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
