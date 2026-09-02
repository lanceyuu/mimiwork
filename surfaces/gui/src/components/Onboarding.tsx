import { useEffect, useState } from "react";
import {
  getConnectors,
  qualitatiStatus,
  setOnboarded,
  type Connector,
} from "../api";
import { QualitatiAccountCard } from "./QualitatiAccountCard";
import { useT } from "../i18n";
import { ConnectorBadge } from "../connectors/ConnectorIcon";
import { chooseFolder } from "../tauri";
import { ProviderCards, ProviderForm, useProviderSetup } from "../providers/ProviderSetup";

// First-run onboarding (UX-DECISIONS §24 → §29 → §39): model → your tools → go.
// §39 (owner design, 2026-07-18): step 1 is a PROVIDER GALLERY — 13 real brand
// marks, two per row, each card wearing its own state — and step 2 is a
// two-state tools page whose post-sign-in body is a mini connector gallery with
// live one-click connects. Both steps share one frame rule: the header and
// footer never move; only the middle region swaps, at a fixed height.
// The gallery/form themselves live in providers/ProviderSetup.tsx, shared with
// Settings ▸ Models (UX-021) so the two surfaces can't drift.
// Replayable from Settings ▸ General ▸ "Run setup again".

// Step 2's benefit rows (§41): managed connectors with LIVE prod OAuth apps only,
// each framed by the job it does (detail copy stays ONE line even with a Connect
// pill — wrap made rows jump between states). gmail + google_calendar ship as one
// combined grayed "Coming soon" row — both ride the same Google app, gated on
// Google verification/CASA; give them rows when it lands.
const TOOL_ROWS = [
  { name: "outlook", benefit: "Stay on top of email", detail: "Outlook — triage mail, draft replies, run your calendar." },
  { name: "slack", benefit: "Keep up with Slack", detail: "Slack — catch up, answer mentions, post updates." },
  { name: "github", benefit: "Ship code", detail: "GitHub — review PRs, watch issues, reply to @mentions." },
  { name: "notion", benefit: "Keep your notes in reach", detail: "Notion — search pages, query databases, draft docs." },
  { name: "hubspot", benefit: "Keep the CRM current", detail: "HubSpot — update deals, log notes, prep calls." },
  { name: "attio", benefit: "Track every relationship", detail: "Attio — search records, read timelines, log notes." },
];
const TOOLS_SOON = ["gmail", "google_calendar"];

// The step-3 starter tasks (design spec 2026-08-20 §4): one click = a session with the
// picked folder granted and the prompt PREFILLED — never auto-sent; the user presses
// Enter, so the first action is still theirs. "Tidy" needs write access; the card says so.
const STARTERS = [
  {
    key: "summarize",
    icon: "📋",
    label: "Summarize what's in this folder",
    prompt:
      "Look through this folder and give me a short overview: what's in it, what seems " +
      "most important, and anything that looks unfinished or out of place.",
    needsWrite: false,
  },
  {
    key: "tidy",
    icon: "🧹",
    label: "Tidy and organize these files",
    prompt:
      "Propose a tidy structure for this folder (groups, naming, what to archive). " +
      "Show me the plan first — only move files after I approve.",
    needsWrite: true,
  },
  {
    key: "plan",
    icon: "🗓️",
    label: "Plan my week from what's here",
    prompt:
      "Based on the documents in this folder, draft a plan for my week: open threads, " +
      "deadlines you can infer, and a suggested order of attack.",
    needsWrite: false,
  },
] as const;

export type OnboardingStarter = { workspace: string; writable: boolean; prompt: string };

export function Onboarding({
  onDone,
  __startStep = 0,
}: {
  onDone: (next?: "work" | "gallery" | "automations", starter?: OnboardingStarter) => void;
  // Test-only: render pre-advanced to a step (the earlier steps need live provider state).
  __startStep?: number;
}) {
  const t = useT();
  const [step, setStep] = useState(__startStep);
  // Step 0 (owner ask 2026-08-29): the account comes FIRST — register or sign in with
  // QualiTaTi right here, models included, nothing to configure. Bring-your-own-key is
  // the fallback path behind one link, not the opening question.
  const [byok, setByok] = useState(false);
  const [qtSignedIn, setQtSignedIn] = useState(false);
  useEffect(() => {
    if (step !== 0 || qtSignedIn) return;
    let stop = false;
    const poll = () =>
      qualitatiStatus()
        .then((s) => !stop && s?.signed_in && setQtSignedIn(true))
        .catch(() => undefined);
    poll();
    const t = window.setInterval(poll, 2500);
    return () => { stop = true; window.clearInterval(t); };
  }, [step, qtSignedIn]);
  // -- step 3: first task (folder + starter cards) --------------------------------
  const [folder, setFolder] = useState<string | null>(null);
  const [writable, setWritable] = useState(false);

  // -- step 1: model (provider gallery ⇄ key form, shared machinery) ---------------
  const ps = useProviderSetup();
  const [skipConfirm, setSkipConfirm] = useState(false);

  const anyReady =
    ps.providers.some((p) => p.configured && p.needs_key) || ps.keylessOk.size > 0;
  // In the form with typed-but-untested input, Next verifies+saves first (tester
  // catch 2026-07-12: a manual Test-then-Continue two-step reads as a puzzle).
  const nextFromForm = !!ps.sel && ps.dirty && ps.secretFilled;
  const canNext = qtSignedIn || anyReady || nextFromForm;

  const advance = async () => {
    if (nextFromForm && !ps.credentialed) {
      ps.cancelBackTimer();
      if (!(await ps.runTestAndSave())) return;
    }
    setStep(1);
  };

  // -- step 2: connect your everyday tools (§39 two-state page) -------------------
  const [connectors, setConnectors] = useState<Connector[]>([]);

  // The onboarding tools page is informational now: connectors are set up with
  // the user's own credentials from the Connectors page (the managed one-click
  // path went with the hosted relay).
  useEffect(() => {
    if (step !== 1) return;
    getConnectors().then(setConnectors).catch(() => {});
  }, [step]);

  const finish = async (
    next?: "work" | "gallery" | "automations",
    starter?: OnboardingStarter,
  ) => {
    await setOnboarded(true).catch(() => {});
    onDone(next, starter);
  };

  const pickFolder = async () => {
    const p = await chooseFolder();
    if (p) setFolder(p);
  };

  // -- shared bits ----------------------------------------------------------------
  const dots = (
    <div className="flex justify-center gap-2 mb-6">
      {[0, 1, 2].map((i) => (
        <span key={i} className={"w-1.5 h-1.5 rounded-full " + (i <= step ? "bg-accent" : "bg-line")} />
      ))}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 bg-ink/30 grid place-items-center" data-testid="onboarding">
      {/* FIXED height across all three steps (owner call 2026-07-12, reaffirmed §39: the
          modal must never resize — the gallery⇄form swap happens inside this box). */}
      <div className="w-[600px] max-w-[92vw] h-[560px] max-h-[88vh] rounded-2xl border border-line bg-panel shadow-2xl p-8 flex flex-col">
        {dots}

        {step === 0 && (
          <section data-testid="ob-step-model" className="flex-1 min-h-0 flex flex-col">
            {/* Persistent header — stays put while the region below swaps (§39). */}
            <h1 className="text-[19px] font-semibold">{t("Welcome to MimiWork")}<span className="beta-tag">BETA</span></h1>
            <p className="text-[13px] text-muted mt-0.5 mb-4">
              {byok
                ? "Pick a model provider — MimiWork runs on your own key, and your key and your data stay on this computer."
                : t("Create your QualiTaTi account — or sign in — and the Mimi models are ready to work, free tier included. No API keys.")}
            </p>

            {!byok ? (
              /* ---- QualiTaTi account first (owner ask 2026-08-29) ---- */
              <div className="flex-1 min-h-0 overflow-y-auto pr-1" data-testid="ob-qualitati">
                <QualitatiAccountCard />
                <button
                  className="mt-3 text-[12.5px] text-faint hover:text-muted underline"
                  data-testid="ob-byok"
                  onClick={() => setByok(true)}
                >
                  {t("I'll use my own API key instead (OpenAI, Anthropic, Gemini…)")}
                </button>
              </div>
            ) : !ps.sel ? (
              /* ---- the provider GALLERY (bring-your-own-key path) ---- */
              <div className="flex-1 min-h-0 overflow-y-auto pr-1" data-testid="ob-provider-gallery">
                <ProviderCards ps={ps} tp="ob" />
                <button
                  className="mt-3 text-[12.5px] text-faint hover:text-muted underline"
                  onClick={() => setByok(false)}
                >
                  {t("← Back to QualiTaTi sign-in")}
                </button>
              </div>
            ) : (
              /* ---- one provider's key form, same box ---- */
              <div className="flex-1 min-h-0 overflow-y-auto pr-1">
                <ProviderForm ps={ps} tp="ob" />
              </div>
            )}

            {/* Persistent footer (§39). */}
            <div className="flex items-center gap-3 pt-5">
              {!skipConfirm ? (
                <button className="text-[12.5px] text-faint hover:text-muted" onClick={() => setSkipConfirm(true)}>
                  {t("Skip setup")}
                </button>
              ) : (
                <span className="text-[12.5px] text-muted">
                  Nothing works without a model —{" "}
                  <button className="text-accent" onClick={() => finish()}>
                    {t("skip anyway")}
                  </button>
                </span>
              )}
              <button
                className="ml-auto px-6 py-2 rounded-full bg-ink text-panel text-[13px] disabled:opacity-40"
                disabled={!canNext || ps.verify.state === "testing"}
                onClick={advance}
                data-testid="ob-continue"
              >
                {ps.verify.state === "testing" ? t("Checking…") : t("Next")}
              </button>
            </div>
            <p className="text-[11px] text-faint mt-3">
              Models can be enabled or hidden anytime in Settings ▸ Models.
            </p>
          </section>
        )}

        {step === 1 && (
          /* §41 (owner design, 2026-07-19, supersedes §39's card gallery): BENEFIT ROWS are
             the connect surface — one row set, two states, ZERO layout shift. Pre-sign-in the
             rows make the case and a pinned band asks for sign-in; after sign-in the band's
             slot keeps its place but flips to a green congrats, and every row grows a quiet
             Connect pill. The gated Google pair is ONE combined grayed row. */
          <section data-testid="ob-step-tools" className="flex-1 min-h-0 flex flex-col">
            <h1 className="text-[19px] font-semibold">Connect your everyday tools</h1>
            <p className="text-[13px] text-muted mt-0.5 mb-3">
              Chat can only advise. Connected, your coworker does the actual work:
            </p>

            <div className="flex-1 min-h-0 overflow-y-auto pr-1" data-testid="ob-tool-gallery">
              {TOOL_ROWS.map(({ name, benefit, detail }) => {
                const c = connectors.find((x) => x.name === name);
                if (!c) return null;
                return (
                  <div
                    key={name}
                    className="flex items-center gap-3 py-2 border-b border-paper last:border-0"
                    data-testid={`ob-tool-${name}`}
                  >
                    <ConnectorBadge connector={c} size={34} title={c.title} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13.5px] font-semibold leading-tight">{benefit}</span>
                      <span className="block text-[12px] text-muted truncate">{detail}</span>
                    </span>
                    {c.connected && (
                      <span className="text-[12px] text-ok font-medium shrink-0">✓ Connected</span>
                    )}
                  </div>
                );
              })}
              {/* The gated Google pair: one combined grayed row, both states (§41). */}
              <div className="flex items-center gap-3 py-2" data-testid="ob-tool-google-soon">
                <span className="flex gap-1.5 opacity-40 grayscale">
                  {TOOLS_SOON.map((n) => {
                    const c = connectors.find((x) => x.name === n);
                    return c ? <ConnectorBadge key={n} connector={c} size={28} title={c.title} /> : null;
                  })}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-semibold leading-tight text-faint">
                    Gmail &amp; Google Calendar
                  </span>
                  <span className="block text-[12px] text-faint truncate">
                    Coming soon — pending Google&rsquo;s app verification.
                  </span>
                </span>

              </div>
            </div>

            {/* The band is PINNED outside the scroll area and its slot never moves: the ask
                pre-sign-in, a green congrats after — zero layout shift at the moment the user
                returns from the browser (§41). */}
            <div className="mt-3.5 rounded-xl border border-line bg-paper px-4 py-3 shrink-0">
              <span className="block text-[13px] font-semibold text-ink mb-0.5">
                Connect them when you need them
              </span>
              <span className="block text-[12.5px] text-muted">
                Every tool connects from the Connectors page with your own tokens or a
                local one-click sign-in — nothing goes through a third-party cloud.
              </span>
            </div>

            <div className="flex items-center mt-3.5">
              <button
                className="ml-auto px-6 py-2 rounded-full bg-ink text-panel text-[13px] shrink-0"
                onClick={() => setStep(2)}
                data-testid="ob-continue-tools"
              >
                Next
              </button>
            </div>
            <p className="text-[11px] text-faint mt-3">
              30+ more tools on the Connectors page — add or remove anytime. Tokens stay on
              this computer.
            </p>
          </section>
        )}

        {step === 2 && (
          /* §42 (design spec 2026-08-20 §4): the last step hands over a FIRST TASK, not a
             menu. Pick a folder → three starter cards light up; one click opens a session
             with the folder granted and the prompt prefilled (never auto-sent). The old
             "automation / blank session" doors survive as quiet footer links. */
          <section data-testid="ob-step-first-task" className="flex-1 min-h-0 flex flex-col overflow-y-auto">
            <h1 className="text-[19px] font-semibold">Give Mimi her first task</h1>
            <p className="text-[13px] text-muted mt-0.5 mb-4">
              Pick a folder Mimi may look at — everything stays on this computer, and she
              only ever sees folders you hand her.
            </p>

            {!folder ? (
              <button
                className="w-full flex items-center gap-3 rounded-xl2 border border-dashed border-line hover:border-accent bg-panel px-4 py-3.5"
                onClick={pickFolder}
                data-testid="ob-pick-folder"
              >
                <span className="w-9 h-9 rounded-lg bg-accentSoft text-accent grid place-items-center text-[15px] shrink-0">
                  📁
                </span>
                <span className="flex-1 min-w-0 text-left">
                  <b className="block text-[13.5px]">Choose a folder</b>
                  <span className="text-[12px] text-muted">
                    Your course folder, a project, this week's mess — any folder works.
                  </span>
                </span>
                <span className="text-faint self-center">›</span>
              </button>
            ) : (
              <div
                className="flex items-center gap-3 rounded-xl2 border border-line bg-paper px-4 py-3"
                data-testid="ob-folder-picked"
              >
                <span className="w-9 h-9 rounded-lg bg-okSoft text-ok grid place-items-center text-[15px] shrink-0">
                  📁
                </span>
                <span className="flex-1 min-w-0">
                  <b className="block text-[13.5px] truncate" title={folder}>
                    {folder.split(/[\\/]/).filter(Boolean).pop()}
                  </b>
                  <label className="flex items-center gap-1.5 text-[12px] text-muted cursor-pointer">
                    <input
                      type="checkbox"
                      checked={writable}
                      onChange={(e) => setWritable(e.target.checked)}
                      data-testid="ob-folder-writable"
                    />
                    Allow Mimi to edit and organize files in it
                  </label>
                </span>
                <button className="text-[12px] text-accent shrink-0" onClick={pickFolder}>
                  Change
                </button>
              </div>
            )}

            <p className="text-[12.5px] text-muted mt-4 mb-1.5">
              {folder ? "Now pick her first task:" : "Then pick her first task:"}
            </p>
            <div className="space-y-2">
              {STARTERS.map((s) => {
                const blocked = !folder || (s.needsWrite && !writable);
                return (
                  <button
                    key={s.key}
                    className={
                      "w-full flex items-start gap-3 rounded-xl2 border px-4 py-3 text-left " +
                      (blocked
                        ? "border-line opacity-45 cursor-not-allowed"
                        : "border-line hover:border-accent bg-panel")
                    }
                    disabled={blocked}
                    title={
                      !folder
                        ? "Choose a folder first"
                        : s.needsWrite && !writable
                          ? "Needs the edit permission above"
                          : undefined
                    }
                    onClick={() =>
                      folder && finish("work", { workspace: folder, writable, prompt: s.prompt })
                    }
                    data-testid={`ob-starter-${s.key}`}
                  >
                    <span className="text-[16px] shrink-0">{s.icon}</span>
                    <span className="flex-1 min-w-0">
                      <b className="block text-[13.5px]">{s.label}</b>
                      {s.needsWrite && (
                        <span className="text-[11.5px] text-faint">Uses the edit permission</span>
                      )}
                    </span>
                    <span className="text-faint self-center">›</span>
                  </button>
                );
              })}
            </div>

            <div className="flex items-center justify-center gap-4 mt-auto pt-5">
              <button
                className="text-[12.5px] text-muted hover:text-ink"
                onClick={() => finish("automations")}
                data-testid="ob-cta-automation"
              >
                Create an automation instead
              </button>
              <span className="text-faint">·</span>
              <button
                className="text-[12.5px] text-muted hover:text-ink"
                // A picked folder must survive THIS exit too, not only the starter
                // cards — otherwise "choose a folder, then open a blank session" quietly
                // threw the choice away (review catch 2026-09-02). No prompt: blank means
                // blank.
                onClick={() =>
                  finish("work", folder ? { workspace: folder, writable, prompt: "" } : undefined)
                }
                data-testid="ob-start"
              >
                Just open a blank session
              </button>
            </div>
            <p className="text-[11px] text-faint text-center mt-3">
              Replay this setup anytime: Settings ▸ Appearance ▸ Run setup again.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
