/** QualiTaTi account card (Settings → Models).
 *
 * Sign in with a QualiTaTi account and model calls can spend its credit balance:
 * the sidecar mints a personal API key and configures the `qualitati` provider,
 * so "Mimi · QualiTaTi credits" appears in the model picker with no key-pasting.
 * Signed in, the card shows the live balance; signed out, a two-field form
 * (+ an MFA code step when the account has it enabled).
 *
 * The password goes to the local sidecar over loopback and from there straight
 * to QualiTaTi's /api/login — it is never stored anywhere.
 */
import { useEffect, useState } from "react";
import {
  QualitatiStatus,
  qualitatiLogin,
  qualitatiLogout,
  qualitatiStatus,
  qualitatiVerifyMfa,
} from "../api";
import mimiMark from "../assets/mimi/mimi-line.png";

export function QualitatiAccountCard({ onChanged }: { onChanged?: () => void }) {
  const [state, setState] = useState<QualitatiStatus | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<"idle" | "busy" | "mfa">("idle");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => qualitatiStatus().then(setState).catch(() => setState(null));
  useEffect(() => {
    refresh();
  }, []);

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
              ? "Model calls with “Mimi” spend your QualiTaTi credits."
              : "Sign in to use your QualiTaTi credits as a model provider — no API key needed."}
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
      ) : phase === "mfa" ? (
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
      )}
      {error && (
        <div className="mt-1.5 text-[12px] text-danger" data-testid="qualitati-error">
          {error}
        </div>
      )}
    </div>
  );
}
