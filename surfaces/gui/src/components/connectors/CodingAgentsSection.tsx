import { useCallback, useEffect, useState } from "react";
import {
  getCodingAgents,
  setCodingAgent,
  signInCodingAgent,
  testCodingAgent,
  type CodingAgent,
} from "../../api";
import { useT } from "../../i18n";
import { openExternal } from "../../tauri";
import { CHIP_OFF, CHIP_OK, CHIP_WARN, FOOT, GRP, PILL_ACCENT, PILL_LINE, ROW } from "./ui";

// Claude Code and Codex, connected like any other tool: installed where, signed in as whom,
// a real test call, and the model and effort Mimi's hand-offs will use. Delegation reads the
// same status, so what this page says is what start_agent will find.

type TestResult = { ok: boolean; reply?: string; seconds?: number; error?: string };

export function CodingAgentsSection() {
  const t = useT();
  const [agents, setAgents] = useState<CodingAgent[] | null>(null);
  const [failed, setFailed] = useState(false);
  // Agents whose browser sign-in is under way: the page polls until they report signed in.
  const [waiting, setWaiting] = useState<Record<string, boolean>>({});

  const refresh = useCallback(() => {
    getCodingAgents()
      .then((a) => {
        setAgents(a);
        setFailed(false);
        setWaiting((w) => {
          const next = { ...w };
          for (const x of a) if (x.signed_in) delete next[x.key];
          return next;
        });
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(refresh, [refresh]);
  const pending = Object.keys(waiting).length > 0;
  useEffect(() => {
    if (!pending) return;
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [pending, refresh]);

  if (failed && !agents) {
    return (
      <div className="text-[13px] text-muted flex items-center gap-3" data-testid="coding-agents-error">
        {t("Could not load the coding agents. Try again.")}
        <button className={PILL_LINE} onClick={refresh}>
          {t("Try again")}
        </button>
      </div>
    );
  }
  if (!agents) return <div className="text-[13px] text-muted">{t("Loading…")}</div>;

  return (
    <div className="space-y-6">
      {agents.map((a) => (
        <AgentCard
          key={a.key}
          a={a}
          waiting={!!waiting[a.key]}
          onSignInStarted={() => setWaiting((w) => ({ ...w, [a.key]: true }))}
          onChanged={refresh}
        />
      ))}
      <div className="flex justify-end">
        <button className={PILL_LINE} onClick={refresh} data-testid="coding-agents-refresh">
          {t("Check again")}
        </button>
      </div>
    </div>
  );
}

function statusOf(a: CodingAgent): { label: string; chip: string } {
  if (!a.installed) return { label: "Not installed", chip: CHIP_OFF };
  if (a.error) return { label: "Needs attention", chip: CHIP_WARN };
  if (!a.signed_in) return { label: "Not signed in", chip: CHIP_WARN };
  return { label: "Connected", chip: CHIP_OK };
}

function AgentCard({
  a,
  waiting,
  onSignInStarted,
  onChanged,
}: {
  a: CodingAgent;
  waiting: boolean;
  onSignInStarted: () => void;
  onChanged: () => void;
}) {
  const t = useT();
  const status = statusOf(a);
  const [model, setModel] = useState(a.model);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);
  const [signIn, setSignIn] = useState<{ url?: string; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);

  const save = (next: { model: string; effort: string }) => {
    setSaved(false);
    setCodingAgent(a.key, next)
      .then((r) => {
        setSaveError(r.ok ? "" : r.error || "");
        if (r.ok) {
          setSaved(true);
          onChanged();
        }
      })
      .catch(() => setSaveError(t("Could not save. Try again.")));
  };

  const startSignIn = () => {
    setSignIn(null);
    signInCodingAgent(a.key)
      .then((r) => {
        setSignIn(r.started ? { url: r.url } : { error: r.error });
        if (r.started) onSignInStarted();
      })
      .catch(() => setSignIn({ error: t("Could not start the sign-in. Try again.") }));
  };

  const runTest = () => {
    setTesting(true);
    setResult(null);
    testCodingAgent(a.key)
      .then(setResult)
      .catch(() => setResult({ ok: false, error: t("The test could not reach MimiWork. Try again.") }))
      .finally(() => setTesting(false));
  };

  const connected = a.installed && a.signed_in && !a.error;

  return (
    <section data-testid={`coding-agent-${a.key}`}>
      <div className="flex items-center gap-2 px-1 mb-1.5">
        <h3 className="text-[14px] font-semibold">{a.label}</h3>
        <span className={status.chip} data-testid="coding-agent-status">
          {t(status.label)}
        </span>
      </div>

      {a.error && (
        <div
          className="mb-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-[12.5px] text-danger"
          role="alert"
          data-testid="coding-agent-error"
        >
          {a.error}
        </div>
      )}

      <div className={GRP}>
        <div className={ROW}>
          <span className="w-24 shrink-0 text-[13px] text-muted">{t("Installed")}</span>
          {a.installed ? (
            <span className="min-w-0 text-[12.5px]">
              <span className="font-mono break-all" data-no-translate>{a.path}</span>
              {a.version && <span className="text-faint" data-no-translate> · {a.version}</span>}
            </span>
          ) : (
            <span className="min-w-0 text-[12.5px]">
              {t("Not found on this computer.")} {t("To install it, run this in a terminal, then check again:")}
              <Command text={a.install_command} />
            </span>
          )}
        </div>

        <div className={ROW}>
          <span className="w-24 shrink-0 text-[13px] text-muted">{t("Signed in")}</span>
          <div className="min-w-0 flex-1 text-[12.5px]">
            {!a.installed ? (
              <span className="text-faint">{t("Install it first.")}</span>
            ) : a.signed_in ? (
              <span data-no-translate>{a.account || t("Signed in")}</span>
            ) : (
              <div className="space-y-1.5">
                <div className="flex items-center gap-3">
                  <span>{t("Not signed in")}</span>
                  <button className={PILL_ACCENT} onClick={startSignIn} data-testid="coding-agent-sign-in">
                    {t("Sign in")}
                  </button>
                </div>
                {waiting && (
                  <div className="text-muted" data-testid="coding-agent-sign-in-waiting">
                    {t("Finish signing in in your browser. This page updates when you are done.")}{" "}
                    {signIn?.url && (
                      <button className="text-accent underline" onClick={() => openExternal(signIn.url!)}>
                        {t("Open the sign-in page")}
                      </button>
                    )}
                  </div>
                )}
                {signIn?.error && <div className="text-danger">{signIn.error}</div>}
                <div className="text-faint">
                  {t("Or run this in a terminal:")} <Command text={a.sign_in_command} />
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={ROW}>
          <label className="w-24 shrink-0 text-[13px] text-muted" htmlFor={`model-${a.key}`}>
            {t("Model")}
          </label>
          <input
            id={`model-${a.key}`}
            className="min-w-0 flex-1 rounded-md border border-line bg-paper px-2 py-1 text-[12.5px]"
            value={model}
            placeholder={t("Default: {model}").replace("{model}", a.defaults.model || t("the agent's own choice"))}
            onChange={(e) => setModel(e.target.value)}
            onBlur={() => model !== a.model && save({ model, effort: a.effort })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            data-testid="coding-agent-model"
          />
        </div>

        <div className={ROW}>
          <label className="w-24 shrink-0 text-[13px] text-muted" htmlFor={`effort-${a.key}`}>
            {t("Effort")}
          </label>
          <select
            id={`effort-${a.key}`}
            className="rounded-md border border-line bg-paper px-2 py-1 text-[12.5px]"
            value={a.effort}
            onChange={(e) => save({ model, effort: e.target.value })}
            data-testid="coding-agent-effort"
          >
            <option value="">
              {a.defaults.effort ? t("Default: {model}").replace("{model}", a.defaults.effort) : t("Default")}
            </option>
            {a.efforts.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
          {saved && <span className="text-[12px] text-ok">{t("Saved")}</span>}
          {saveError && <span className="text-[12px] text-danger">{saveError}</span>}
        </div>

        <div className={ROW}>
          <span className="w-24 shrink-0 text-[13px] text-muted">{t("Test")}</span>
          <div className="min-w-0 flex-1 text-[12.5px] space-y-1">
            <div className="flex items-center gap-3">
              <button
                className={PILL_LINE}
                disabled={!connected || testing}
                onClick={runTest}
                data-testid="coding-agent-test"
              >
                {testing ? t("Testing…") : t("Test")}
              </button>
              <span className="text-faint">
                {t("Makes one small real call on your own account. It can take a minute or two.")}
              </span>
            </div>
            {result && (
              <div className={result.ok ? "text-ok" : "text-danger"} data-testid="coding-agent-test-result">
                {result.ok
                  ? t("It answered in {s} seconds.").replace("{s}", String(result.seconds ?? ""))
                  : result.error}
              </div>
            )}
          </div>
        </div>
      </div>
      <p className={FOOT}>
        {a.key === "claude_code"
          ? t("Runs on your own Claude account, not QualiTaTi credits.")
          : t("Runs on your own OpenAI account, not QualiTaTi credits.")}
      </p>
    </section>
  );
}

function Command({ text }: { text: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <span className="mt-1 flex items-center gap-2">
      <code className="rounded bg-paper border border-line px-1.5 py-0.5 text-[12px] break-all">{text}</code>
      <button
        className="text-[12px] text-accent shrink-0"
        onClick={() =>
          navigator.clipboard
            ?.writeText(text)
            .then(() => setCopied(true))
            .catch(() => {})
        }
      >
        {copied ? t("Copied") : t("Copy")}
      </button>
    </span>
  );
}
