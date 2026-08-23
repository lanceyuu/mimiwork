import { useEffect, useState } from "react";
import mimiMark from "../assets/mimi/mimi-line.png";
import { getConnectors, getSessionConnections } from "../api";
import type { Attachment } from "../types";
import { ConnectorIcon } from "../connectors/ConnectorIcon";
import { indexConnectors, visualFor, type ConnectorMap } from "../connectors/visuals";
import { useRoots } from "../useRoots";
import { AddFolderForm } from "./AddFolderForm";

// Empty-state for a fresh Cowork session (§27): a greeting, exactly three concrete template
// tasks, and the composer — nothing else. Each task carries its own setup: no icon tiles (the
// title is the row), connector dots on the sub-line (brand color = connected and enabled for
// this session, grayscale = not — §23's vocabulary), and sub-line copy that is always the task's
// OUTCOME, never connection state. Sources ready → "Start →" on hover, click prefills the
// composer. Not ready → "Configure ›" always visible (for a gated row the setup action IS the
// row's meaning), opening the §23 Session settings drawer — no second setup surface here.

// The three starters are the three ways in (owner call 2026-08-23): work in a folder,
// work with something you've connected, and teach the coworker your way of doing things.
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
        <img src={mimiMark} alt="" className="intro-mimi" draggable={false} /> What should we produce?
      </h1>
      <p className="intro-lede">
        Pick a task to start — I'll do the work and save the result. Or just type what you need
        below.
      </p>

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
    </div>
  );
}
