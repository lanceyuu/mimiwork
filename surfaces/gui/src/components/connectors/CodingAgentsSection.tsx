import { useCallback, useEffect, useState } from "react";
import {
  getCodingAgentRuns,
  getCodingAgents,
  setCodingAgent,
  signInCodingAgent,
  testCodingAgent,
  type CodingAgent,
  type CodingAgentRun,
} from "../../api";
import { useT } from "../../i18n";
import { openExternal } from "../../tauri";
import { CHIP_OFF, CHIP_OK, CHIP_WARN, FOOT, GRP, PILL_ACCENT, PILL_LINE, ROW } from "./ui";

// Claude Code and Codex, connected like any other tool: installed where, signed in as whom,
// a real test call, and the model and effort Mimi's hand-offs will use. Delegation reads the
// same status, so what this page says is what start_agent will find.

type TestResult = { ok: boolean; reply?: string; seconds?: number; error?: string; model?: string };
// The dropdown's value for a model typed by hand.
const CUSTOM = "__custom";

export function CodingAgentsSection() {
  const t = useT();
  const [agents, setAgents] = useState<CodingAgent[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [runs, setRuns] = useState<CodingAgentRun[]>([]);
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
    getCodingAgentRuns()
      .then(setRuns)
      .catch(() => {}); // the list is a convenience; the agents above still work without it
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
      {/* What start_agent / wait_for_agents / message_agent do together today; Mimi relays
          between the agents, they never talk to each other directly. */}
      <div className="rounded-xl2 border border-line bg-panel px-4 py-3 text-[12.5px]" data-testid="coding-agents-together">
        <div className="font-semibold text-[13px] mb-1">{t("Claude Code and Codex can work together")}</div>
        <p className="text-muted">
          {t(
            "Ask Mimi to use both on one job. Mimi splits the work and gives each agent its own part on its own branch, can have one review the other's branch, and passes what one found back to the other as feedback until the work is right. You see each agent's progress while they work.",
          )}
        </p>
      </div>
      {agents.map((a) => (
        <AgentCard
          key={a.key}
          a={a}
          waiting={!!waiting[a.key]}
          onSignInStarted={() => setWaiting((w) => ({ ...w, [a.key]: true }))}
          onChanged={refresh}
        />
      ))}
      <RecentRuns runs={runs} />
      <div className="flex justify-end">
        <button className={PILL_LINE} onClick={refresh} data-testid="coding-agents-refresh">
          {t("Check again")}
        </button>
      </div>
    </div>
  );
}

function modelHint(a: CodingAgent): string {
  if (a.key === "claude_code")
    return "Claude Code cannot list its models. Latest is the model Claude Code recommends for your account, and each family follows its newest model as your installed Claude Code knows it. Updating Claude Code moves them forward.";
  if (a.models_listed) return "From Codex's own model list, newest first. Latest follows that list as it changes.";
  return "Codex did not share its model list. Type a model name, or leave it empty for Codex's own default.";
}

// Codex says which effort levels each model takes; the chosen (or latest) model decides.
function effortsFor(a: CodingAgent): string[] {
  const id = a.model || a.latest;
  const m = a.models.find((x) => x.id === id);
  return m?.efforts?.length ? m.efforts : a.efforts;
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
  const known = a.models.some((m) => m.id === a.model);
  // Shown while the user is typing a name of their own (or one is already saved).
  const [custom, setCustom] = useState(!!a.model && !known);
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
          <label className="w-24 shrink-0 self-start pt-1 text-[13px] text-muted" htmlFor={`model-${a.key}`}>
            {t("Model")}
          </label>
          <div className="min-w-0 flex-1 space-y-1.5">
            {a.models.length > 0 && (
              <select
                id={`model-${a.key}`}
                className="max-w-full rounded-md border border-line bg-paper px-2 py-1 text-[12.5px]"
                value={custom ? CUSTOM : a.model}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === CUSTOM) {
                    setCustom(true);
                    setModel("");
                    return;
                  }
                  setCustom(false);
                  setModel(v);
                  save({ model: v, effort: a.effort });
                }}
                data-testid="coding-agent-model-select"
              >
                <option value="">
                  {a.latest ? t("Latest (currently {model})").replace("{model}", a.latest) : t("Latest")}
                </option>
                {a.models.map((m) => (
                  <option key={m.id} value={m.id} title={m.description}>
                    {m.resolved ? `${t(m.label)} (${m.resolved})` : t(m.label)}
                  </option>
                ))}
                <option value={CUSTOM}>{t("Custom…")}</option>
              </select>
            )}
            {(custom || a.models.length === 0) && (
              <input
                id={a.models.length ? undefined : `model-${a.key}`}
                className="w-full rounded-md border border-line bg-paper px-2 py-1 text-[12.5px]"
                value={model}
                placeholder={t("Type a model name, or leave empty for the latest")}
                onChange={(e) => setModel(e.target.value)}
                onBlur={() => model !== a.model && save({ model, effort: a.effort })}
                onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                data-testid="coding-agent-model"
              />
            )}
            <p className="text-[12px] text-faint">{t(modelHint(a))}</p>
          </div>
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
            {effortsFor(a).map((e) => (
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
                  ? (result.model ? t("It answered in {s} seconds, using {model}.") : t("It answered in {s} seconds."))
                      .replace("{s}", String(result.seconds ?? ""))
                      .replace("{model}", result.model ?? "")
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

const RUN_STATUS: Record<CodingAgentRun["status"], { label: string; chip: string }> = {
  running: { label: "Working now", chip: CHIP_OK },
  finished: { label: "Done", chip: CHIP_OK },
  failed: { label: "Did not finish", chip: CHIP_WARN },
  stopped: { label: "Stopped", chip: CHIP_OFF },
};

// Each hand-off is a real Claude Code or Codex conversation, but neither app lists it where
// people look (it lives under the agent's own copy of the project, and Codex hides runs it
// did not start interactively). The command opens it there, to read it or carry on by hand.
function RecentRuns({ runs }: { runs: CodingAgentRun[] }) {
  const t = useT();
  return (
    <section data-testid="coding-agent-runs">
      <h3 className="text-[14px] font-semibold px-1 mb-0.5">{t("Recent hand-offs")}</h3>
      <p className="text-[12px] text-muted px-1 mb-2">
        {t("Each hand-off is a conversation in Claude Code or Codex itself. Run its command in a terminal to read it or carry on yourself.")}
      </p>
      {runs.length === 0 ? (
        <div className="text-[12.5px] text-faint px-1">
          {t("No hand-offs yet. When Mimi gives work to Claude Code or Codex, it appears here.")}
        </div>
      ) : (
        <div className={GRP}>
          {runs.map((r) => {
            const st = RUN_STATUS[r.status] ?? RUN_STATUS.stopped;
            return (
              <div key={r.job} className="px-4 py-2.5 text-[12.5px]" data-testid="coding-agent-run">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-medium shrink-0">{r.agent}</span>
                  <span className="truncate" data-no-translate>{r.name}</span>
                  <span className={st.chip}>{t(st.label)}</span>
                  <span className="ml-auto text-faint shrink-0">{new Date(r.at * 1000).toLocaleString()}</span>
                </div>
                <div className="text-faint mt-0.5">
                  {r.branch && <span data-no-translate>{r.branch} · </span>}
                  {t("Session")} <span className="font-mono" data-no-translate>{r.session_id}</span>
                </div>
                <Command text={r.resume_command} />
                {!r.folder_exists && (
                  <div className="text-faint mt-0.5">
                    {t("Its folder has been removed; the conversation can still be read.")}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
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
