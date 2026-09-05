import { useEffect, useState } from "react";
import mimiMark from "../assets/mimi/mimi-line.png";
import { getConnectors, getSessionConnections } from "../api";
import type { Attachment } from "../types";
import { ConnectorIcon } from "../connectors/ConnectorIcon";
import { indexConnectors, visualFor, type ConnectorMap } from "../connectors/visuals";
import { useRoots } from "../useRoots";
import { AddFolderForm } from "./AddFolderForm";
import { useT } from "../i18n";

// Start with the file the user wants to take away. Source setup and custom workflows
// stay available below, so a first task does not require choosing an integration.
const DELIVERABLES = [
  {
    id: "word", title: "Summarize into Word", format: "Word",
    description: "Turn interviews or notes into a clear, editable report",
    prompt: "Summarize the interviews or notes I provide into an editable Word document (.docx). Ask me to attach the source files or share their folder if they are not available yet. Identify the main themes, preserve quoted wording, and link findings to their sources. Separate evidence from interpretation and flag missing information. Save the report in this task's folder, check the document for formatting and source accuracy, and tell me what you checked with a link to the finished file.",
  },
  {
    id: "spreadsheet", title: "Clean a spreadsheet", format: "Excel",
    description: "Get an organized workbook with a record of changes",
    prompt: "Clean the spreadsheet or CSV I provide and save a new Excel workbook (.xlsx). Ask me to attach the source file or share its folder if it is not available yet. Inspect the columns, missing values, duplicates, and inconsistent formats. Preserve the original and ask before making ambiguous changes or removing data. Include a change log, compare row counts, check formulas and totals where present, and link the finished workbook with a summary of the checks.",
  },
  {
    id: "slides", title: "Turn notes into slides", format: "PowerPoint",
    description: "Build an editable presentation with a clear story",
    prompt: "Turn the notes or document I provide into an editable PowerPoint presentation (.pptx). Ask me to attach the source material if it is not available yet, and ask who the audience is and how long the presentation should be. Use a clear narrative, concise slides, and speaker notes. Preserve source facts and do not invent figures or citations. Save the deck in this task's folder, check for overflowing text and missing content, and link the finished file with a summary of what you checked.",
  },
];

const FOLDER_PROMPT =
  "Work in this folder: read what's here, tell me what matters, and suggest what to produce next.";
const CANVA_PROMPT =
  "Look at my Canva designs, then build a slide deck that matches the one I point you at. " +
  "Start by listing what's there so I can pick.";
// Deliberately a fill-in-the-blanks brief, not a finished sentence: the user replaces the
// bracketed bits and sends. Packaging your own style is the highest-leverage first skill —
// once encoded, every deck, doc and sheet comes out in it without being asked.
const SKILL_PROMPT = `Package my style guidelines into a skill, so every presentation, document and spreadsheet you make comes out in my style without me asking.

Colors: [paste your hex codes — e.g. dark #141413 for text, #faf9f5 for backgrounds, an accent or two]
Fonts: headings [font], body text [font], with fallbacks if they aren't installed
Rules: [anything that matters — when to use each accent, heading sizes, spacing, what to avoid]

Ask me about anything that's missing, then save it as a skill and show me an example slide and page in it.`;

export function SessionIntro({
  sessionId,
  onOpenSessionSettings,
  onPrefill,
}: {
  sessionId: string;
  // Opens the §23 Session settings drawer (sources section) — the gated rows' Configure target.
  onOpenSessionSettings: () => void;
  onPrefill: (text: string, attachments?: Attachment[]) => void;
}) {
  const t = useT();
  const { roots, busy, error, addRoot } = useRoots(sessionId);
  const [live, setLive] = useState<Set<string>>(new Set());
  const [byName, setByName] = useState<ConnectorMap>({});
  const [addingFolder, setAddingFolder] = useState(false);

  useEffect(() => {
    // Live = what this session can touch right now (connected AND not muted here) — the same
    // truth the §23 glance renders, so the dots here can never disagree with the row above.
    getSessionConnections(sessionId)
      .then((c) => setLive(new Set(c.connected.filter((x) => x.enabled).map((x) => x.connector))))
      .catch(() => {});
    getConnectors()
      .then((list) => setByName(indexConnectors(list)))
      .catch(() => {});
  }, [sessionId]);

  const shared = roots.filter((r) => !r.primary);
  const canvaReady = live.has("canva");

  const dot = (name: string, on: boolean) => (
    <span className={"task-dot" + (on ? "" : " off")} key={name}>
      <ConnectorIcon connector={visualFor(name, "connector", byName)} size={12} />
    </span>
  );

  const pickFolder = () => {
    // A shared folder already exists → straight to the prompt; otherwise share one first.
    if (shared.length > 0) onPrefill(FOLDER_PROMPT);
    else setAddingFolder((v) => !v);
  };

  return (
    <div className="intro">
      <h1 className="greeting">
        <img src={mimiMark} alt="" className="intro-mimi" draggable={false} /> {t("What should we produce?")}
      </h1>
      <p className="intro-lede">
        {t("Choose a result, then attach your files or share a folder. You can edit the request before sending.")}
      </p>

      <div className="intro-tasks" aria-label={t("Start with a file")}>
        {DELIVERABLES.map((task) => (
          <button key={task.id} className="task-card deliverable-starter" data-testid={`intro-task-${task.id}`} onClick={() => onPrefill(task.prompt)}>
            <span className="task-card-body">
              <span className="task-card-title">{t(task.title)}</span>
              <span className="task-card-sub">{t(task.description)}</span>
            </span>
            <span className="task-card-act">{task.format}</span>
          </button>
        ))}
      </div>
      <details className="intro-more">
        <summary>{t("More ways to start")}</summary>
        <div className="intro-tasks">
        <button className="task-card" data-testid="intro-task-folder" onClick={pickFolder}>
          <span className="task-card-body">
            <span className="task-card-title">Work in a folder</span>
            <span className="task-card-sub">I'll read what's there and produce what you need</span>
          </span>
          <span className="task-card-act">Pick a folder →</span>
        </button>
        {addingFolder && (
          <div className="intro-addfolder">
            <AddFolderForm
              startOpen
              busy={busy}
              onAdd={async (path, writable) => {
                const ok = await addRoot(path, writable);
                if (ok !== false) onPrefill(FOLDER_PROMPT);
                return ok;
              }}
              onDismiss={() => setAddingFolder(false)}
            />
            {error && <div className="roots-err">{error}</div>}
          </div>
        )}

        <button
          className={"task-card" + (canvaReady ? "" : " gated")}
          data-testid="intro-task-canva"
          onClick={() => (canvaReady ? onPrefill(CANVA_PROMPT) : onOpenSessionSettings())}
        >
          <span className="task-card-body">
            <span className="task-card-title">Build a deck from my Canva designs</span>
            <span className="task-card-sub">
              {dot("canva", canvaReady)}
              I'll pull the design you pick and build the slides
            </span>
          </span>
          <span className="task-card-act">{canvaReady ? "Start →" : "Configure ›"}</span>
        </button>

        {/* No source to connect: teaching the coworker your style needs nothing but you. */}
        <button
          className="task-card"
          data-testid="intro-task-skill"
          onClick={() => onPrefill(SKILL_PROMPT)}
        >
          <span className="task-card-body">
            <span className="task-card-title">Package your style guidelines into a skill</span>
            <span className="task-card-sub">
              Your colors, fonts and rules — applied to everything from then on
            </span>
          </span>
          <span className="task-card-act">Start →</span>
        </button>
        </div>
      </details>
    </div>
  );
}
