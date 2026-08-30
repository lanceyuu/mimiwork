import { useEffect, useMemo, useState } from "react";
import { setTourSeen } from "../api";
import { useT } from "../i18n";

// First-run tour (owner ask 2026-08-29): five spotlights over the REAL interface —
// no screenshots, no modal deck. Each step finds its live element; a step whose
// element isn't on screen is skipped rather than pointing at nothing. Dismissing
// marks tour_seen server-side, so it shows once — and is replayable from
// Settings ▸ General.

type Step = {
  key: string;
  title: string;
  body: string;
  find: () => HTMLElement | null;
};

const byTestId = (id: string) => () =>
  document.querySelector<HTMLElement>(`[data-testid="${id}"]`);

const STEPS: Step[] = [
  {
    key: "composer",
    title: "Ask for the outcome, not the steps",
    body:
      "“Read these transcripts and write a themed summary as summary.docx” gets you a " +
      "finished file. Press / for commands and skills, @ to point at a file, or drop files " +
      "straight in. And if Mimi heads the wrong way mid-run — just type; it steers without restarting.",
    find: () => document.querySelector<HTMLElement>(".composer textarea, textarea"),
  },
  {
    key: "modes",
    title: "Three gears, one key",
    body:
      "Shift+Tab cycles Plan (propose first, touch nothing), Ask for approval (the default), " +
      "and Full access. For anything with stakes, start in Plan — one minute reading a plan " +
      "beats twenty redoing the work.",
    find: () => {
      const buttons = Array.from(document.querySelectorAll<HTMLElement>("button"));
      return (
        buttons.find((b) => /Ask for approval|Plan|Full access/.test(b.textContent || "")) || null
      );
    },
  },
  {
    key: "workspace",
    title: "Your folder is the workspace",
    body:
      "Mimi reads here and saves finished files here — visible in Finder or Explorer, not " +
      "hidden in the app. Nothing outside the folders you grant is readable.",
    find: byTestId("topbar-workspace"),
  },
  {
    key: "panel",
    title: "Watch the work happen",
    body:
      "The right panel shows the live plan (Progress), every finished file (Artifacts), and " +
      "exactly which folders this conversation can touch (Access).",
    find: byTestId("access-section"),
  },
  {
    key: "menu",
    title: "Everything else lives here",
    body:
      "Connectors (Slack, Qualtrics, your QualiTaTi data), Automations that run on a " +
      "schedule, the Activity page with real credit costs, your Files — and Settings, where " +
      "you can replay this tour anytime.",
    find: byTestId("account-row"),
  },
];

export function Tour({ onDone }: { onDone: () => void }) {
  const t = useT();
  const steps = useMemo(() => STEPS.filter((s) => s.find()), []);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const step = steps[i];

  useEffect(() => {
    if (!step) return;
    const el = step.find();
    if (!el) { setI((n) => n + 1); return; }
    el.scrollIntoView?.({ block: "nearest" });
    const measure = () => setRect(el.getBoundingClientRect());
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [step]);

  const finish = () => {
    setTourSeen().catch(() => undefined);
    onDone();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      if (e.key === "Enter" || e.key === "ArrowRight")
        setI((n) => (n + 1 < steps.length ? n + 1 : (finish(), n)));
      if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps.length]);

  if (!step || !rect) return null;

  const pad = 6;
  const below = rect.bottom + 190 < window.innerHeight;
  const tipTop = below ? rect.bottom + 14 : undefined;
  const tipBottom = below ? undefined : window.innerHeight - rect.top + 14;
  const tipLeft = Math.max(16, Math.min(rect.left, window.innerWidth - 356));

  return (
    <div className="fixed inset-0 z-[80]" data-testid="tour" role="dialog" aria-label="Tour">
      {/* the spotlight: one hole punched by a giant shadow */}
      <div
        style={{
          position: "absolute",
          left: rect.left - pad,
          top: rect.top - pad,
          width: rect.width + pad * 2,
          height: rect.height + pad * 2,
          borderRadius: 10,
          boxShadow: "0 0 0 9999px rgba(15,18,25,0.55)",
          border: "2px solid var(--accent)",
          pointerEvents: "none",
          transition: "all 200ms ease",
        }}
      />
      <div
        className="absolute w-[340px] rounded-xl bg-panel border border-line shadow-2xl p-4"
        style={{ left: tipLeft, top: tipTop, bottom: tipBottom }}
        data-testid={`tour-step-${step.key}`}
      >
        <div className="text-[10px] font-semibold tracking-wide text-accent uppercase mb-1">
          {i + 1} / {steps.length}
        </div>
        <div className="text-[14px] font-semibold mb-1">{t(step.title)}</div>
        <div className="text-[12.5px] text-muted leading-relaxed">{t(step.body)}</div>
        <div className="flex items-center gap-2 mt-3">
          <button className="text-[12px] text-faint hover:text-muted" onClick={finish} data-testid="tour-skip">
            {t("Skip tour")}
          </button>
          <div className="ml-auto flex gap-2">
            {i > 0 && (
              <button className="px-3 py-1.5 rounded-full border border-line text-[12.5px]" onClick={() => setI(i - 1)}>
                {t("Back")}
              </button>
            )}
            <button
              className="px-4 py-1.5 rounded-full bg-ink text-panel text-[12.5px]"
              onClick={() => (i + 1 < steps.length ? setI(i + 1) : finish())}
              data-testid="tour-next"
            >
              {i + 1 < steps.length ? t("Next") : t("Done")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
