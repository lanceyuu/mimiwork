import { useEffect, useState } from "react";
import { explainArtifact, type CodeNotes } from "../api";
import { useT } from "../i18n";
import { ReportProblem } from "./ReportProblem";

// A script read as research steps, for someone who does not read code (spec 2026-11-06).
// The code is never hidden, only folded: a note that a non-coder cannot check against
// the lines it describes would be asking them to take it on trust.

function CodeLines({ lines, from, to }: { lines: string[]; from: number; to: number }) {
  return (
    <pre className="code-block">
      {lines.slice(from - 1, to).map((text, i) => (
        <div key={from + i} className="code-line" data-line={from + i}>
          <span className="code-ln" aria-hidden="true">{from + i}</span>
          <code>{text || " "}</code>
        </div>
      ))}
    </pre>
  );
}

function rangeOf(sel: Selection | null): [number, number] | null {
  if (!sel || sel.isCollapsed || !sel.toString().trim()) return null;
  const pick = (n: Node | null): [number, number] | null => {
    const el = n && (n.nodeType === 1 ? (n as Element) : n.parentElement);
    const line = el?.closest("[data-line]");
    if (line) {
      const v = Number(line.getAttribute("data-line"));
      return [v, v];
    }
    const step = el?.closest("[data-start]");
    return step ? [Number(step.getAttribute("data-start")), Number(step.getAttribute("data-end"))] : null;
  };
  const a = pick(sel.anchorNode);
  const b = pick(sel.focusNode);
  return a && b ? [Math.min(a[0], b[0]), Math.max(a[1], b[1])] : null;
}

export function CodeView({
  sessionId,
  path,
  name,
  source,
  onAsk,
}: {
  sessionId: string;
  path: string;
  name: string;
  source: string;
  onAsk?: (text: string) => void;
}) {
  const t = useT();
  const lines = source.replace(/\n$/, "").split("\n");
  const [tab, setTab] = useState<"plain" | "code">("plain");
  const [notes, setNotes] = useState<CodeNotes | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [asking, setAsking] = useState<[number, number] | null>(null);

  // Saved notes for this exact file show at once; nothing is generated, or charged,
  // until the researcher asks. The caller keys this component by path, so a new file
  // starts from fresh state; a reloaded file whose notes no longer match clears them here.
  useEffect(() => {
    let live = true;
    explainArtifact(sessionId, path, true)
      .then((r) => { if (live) setNotes(r.ok ? r : null); })
      .catch(() => {});
    return () => { live = false; };
  }, [sessionId, path, source]);

  const explain = async () => {
    setPending(true);
    setFailed(false);
    try {
      const r = await explainArtifact(sessionId, path);
      if (r.ok) setNotes(r);
      else setFailed(true);
    } catch {
      setFailed(true);
    } finally {
      setPending(false);
    }
  };

  const toggle = (i: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const ask = () => {
    if (!asking || !onAsk) return;
    const [a, b] = asking;
    const quoted = lines.slice(a - 1, b).map((l, i) => `${a + i}: ${l}`).join("\n");
    onAsk(`${name}, ${t("Lines")} ${a}–${b}:\n\n\`\`\`\n${quoted}\n\`\`\`\n\n${t("What do these lines do to my data? Please explain in plain language.")}`);
    setAsking(null);
    window.getSelection()?.removeAllRanges();
  };

  // Lines no step covered that hold nothing but blank space are noise, not hidden code.
  const steps = (notes?.steps || []).filter(
    (s) => s.note || lines.slice(s.start - 1, s.end).some((l) => l.trim()),
  );

  return (
    <div className="code-view" onMouseUp={() => setAsking(onAsk ? rangeOf(window.getSelection()) : null)}>
      <div className="code-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "plain"} className={"code-tab" + (tab === "plain" ? " active" : "")} onClick={() => setTab("plain")}>
          {t("Plain language")}
        </button>
        <button role="tab" aria-selected={tab === "code"} className={"code-tab" + (tab === "code" ? " active" : "")} onClick={() => setTab("code")}>
          {t("Code")}
        </button>
      </div>
      {asking && (
        <div className="code-ask">
          <button className="btn sm" onClick={ask}>{t("Ask Mimi about lines")} {asking[0]}–{asking[1]}</button>
        </div>
      )}
      {tab === "code" ? (
        <CodeLines lines={lines} from={1} to={lines.length} />
      ) : !notes ? (
        <div className="code-explain-empty">
          <p>{t("Mimi can explain this script step by step in plain language.")}</p>
          <button className="btn sm" disabled={pending} onClick={() => void explain()}>
            {pending ? t("Explaining…") : t("Explain this script")}
          </button>
          {failed && <p className="rail-error">{t("Couldn't write notes for this file. Try again.")}<ReportProblem error={"Couldn't write notes for this file."} context="code view" /></p>}
        </div>
      ) : (
        <ol className="code-steps">
          {steps.map((s, i) => (
            <li key={s.start} className="code-step" data-start={s.start} data-end={s.end}>
              {s.note && <p className="code-note">{s.note}</p>}
              {s.choice && (
                <p className="code-choice">
                  <span className="code-choice-label">{t("Choice to check")}</span> {s.choice}
                </p>
              )}
              {s.note ? (
                <>
                  <button className="code-toggle" aria-expanded={open.has(i)} onClick={() => toggle(i)}>
                    {open.has(i) ? t("Hide code") : t("Show code")} · {t("Lines")} {s.start}–{s.end}
                  </button>
                  {open.has(i) && <CodeLines lines={lines} from={s.start} to={s.end} />}
                </>
              ) : (
                <CodeLines lines={lines} from={s.start} to={s.end} />
              )}
            </li>
          ))}
          {notes.truncated && (
            <li className="rail-muted">
              {t("Notes stop at line")} {notes.lines_explained}. {t("The Code tab shows the whole script.")}
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
