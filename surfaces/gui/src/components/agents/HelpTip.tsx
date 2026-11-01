/** A "?" that opens a short note, and the notes themselves.
 *
 *  Building a team of agents asks for words most users have never needed: router, effort,
 *  loop. The owner asked (2026-11-01) for help right where each choice is made, not in a
 *  manual. It opens on click rather than hover so it also works by keyboard and touch, and
 *  so it stays open while the user reads it. The note spans its positioned parent (the
 *  field, the toolbar), so it never runs off the narrow side panel. */
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { AgentNodeKind } from "../../api";

export function HelpTip({ title, children, testId }: { title: string; children: ReactNode; testId?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <span className="help-tip" ref={ref}>
      <button
        type="button"
        className={`help-tip-btn${open ? " open" : ""}`}
        data-testid={testId}
        aria-label={`Help: ${title}`}
        aria-expanded={open}
        // Inside a <label>, a click would also focus the field; the tip is not the field.
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        ?
      </button>
      {open && (
        <span className="help-tip-pop" role="note">
          <span className="help-tip-title">{title}</span>
          {children}
        </span>
      )}
    </span>
  );
}

export const KIND_HELP: Record<AgentNodeKind, string> = {
  agent: "Does one job with its own model, effort and tools. Most teams are made of these.",
  coding:
    "Hands the work to Claude Code, Codex, Cursor, Gemini CLI or opencode in a project folder. Use it to change or review code.",
  router:
    "Reads the request and sends it down one of its connections. Label each connection with when to choose it.",
  orchestrator:
    "Plans the work and gives parts of it to the helpers connected to it (dashed lines). Helpers run only when the lead asks them.",
  review: "The run stops here and asks you to approve, send it back with a comment, or stop.",
};

export function KindsTip() {
  return (
    <HelpTip title="What can I add?" testId="help-kinds">
      <ul className="help-tip-list">
        {(Object.keys(KIND_HELP) as AgentNodeKind[]).map((k) => (
          <li key={k}>
            <b>{KIND_NAMES[k]}</b> {KIND_HELP[k]}
          </li>
        ))}
      </ul>
    </HelpTip>
  );
}

const KIND_NAMES: Record<AgentNodeKind, string> = {
  agent: "Mimi agent.",
  coding: "Coding agent.",
  router: "Router.",
  orchestrator: "Lead agent.",
  review: "Human review.",
};

export function BuildGuideTip() {
  return (
    <HelpTip title="How to build a team" testId="help-guide">
      <ol className="help-tip-list">
        <li>Add agents from this bar, or start from a pattern on the Agents page.</li>
        <li>Click an agent to name it and tell it what to do.</li>
        <li>
          Connect two agents by dragging from the small dot on an agent's right edge to the next agent. Work
          flows along the arrows.
        </li>
        <li>For a checker that sends work back, connect it back to the earlier agent and set how many rounds.</li>
        <li>Anything that stops the team from running is shown in red on its agent. When none is left, press Run.</li>
      </ol>
      <span className="help-tip-foot">
        Start small: two or three agents. Run it once on a real example, then improve the agent whose step let
        you down.
      </span>
    </HelpTip>
  );
}

/** One note per setting in the side panel. */
export const FIELD_HELP: Record<string, { title: string; text: string }> = {
  name: {
    title: "Name",
    text: "A plain job title, like \"Check the facts\". It shows on the diagram and in the run's progress.",
  },
  instructions: {
    title: "What should it do?",
    text:
      "Write it like a note to a new colleague: what it receives, what it must produce, and how good looks. " +
      "A checker should say what it checks against. Each agent gets the original task and the previous " +
      "agent's work on its own, so you do not need to repeat them.",
  },
  review: {
    title: "What should the person check?",
    text: "Shown to you with the draft when the run reaches this step, in the chat or your Inbox.",
  },
  model: {
    title: "Model",
    text:
      "Leave it on the chat's model unless this step needs something different. Cheap, fast models suit " +
      "sorting and look-ups; stronger ones suit writing and checking. Each agent spends credits on its own model.",
  },
  effort: {
    title: "Thinking effort",
    text:
      "How hard the model thinks before it answers. Low for sorting and quick look-ups, High for checking, " +
      "planning and hard writing. Higher is slower and costs more. Default lets the model decide, and some " +
      "models ignore this setting.",
  },
  tools: {
    title: "Tools it may use",
    text:
      "Tick only what this step needs. Agents change files only inside folders open in the chat. Anything " +
      "that runs a command or leaves your computer waits for your approval in the Inbox.",
  },
  coding: {
    title: "Coding agent",
    text:
      "Which coding tool does the work. It must be installed and signed in under Connectors, Coding agents. " +
      "Coding agents in one team share one copy of the project on its own branch, so a reviewer sees the " +
      "builder's changes.",
  },
  codingModel: {
    title: "Its model",
    text: "The model that coding tool uses. Its own setting is what you chose on the Coding agents page.",
  },
  folder: {
    title: "Project folder",
    text:
      "The project the coding agent works on. Your folder itself is not changed: the work happens on a " +
      "separate branch you can review and merge. Mimi asks for access to this folder when the team runs.",
  },
  connections: {
    title: "Sends its work to",
    text:
      "Where this agent's answer goes next. Several connections run at the same time, and an agent with " +
      "several incoming connections waits for all of them. \"Loops back\" makes it a checker: it starts its " +
      "answer with PASS to move on, or sends the work back with its notes, up to the number of times you set. " +
      "An agent with no outgoing connection gives the final result.",
  },
  routerConnections: {
    title: "Choices",
    text:
      "The router picks exactly one of these for each request. Label each one with when to choose it, for " +
      "example \"refund request\". Labels must differ.",
  },
  helpers: {
    title: "Assigns work to",
    text:
      "The helpers this lead agent may call, as often as it needs. They run only when the lead asks and " +
      "report back to it, not to the next agent.",
  },
};

export function FieldTip({ field }: { field: keyof typeof FIELD_HELP }) {
  const h = FIELD_HELP[field];
  return (
    <HelpTip title={h.title} testId={`help-${field}`}>
      {h.text}
    </HelpTip>
  );
}
