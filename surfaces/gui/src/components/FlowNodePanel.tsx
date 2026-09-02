/** What you can do with one node of an automation's flow diagram (owner ask 2026-09-02:
 *  "click a node and ask Mimi to revise it, rename it, things like that").
 *
 *  The instructions stay the source of truth, so anything that changes WHAT a step
 *  does — rename, remove, add one after, free-form feedback — goes through the same
 *  revise call: Mimi rewrites the prose with one precise request. Settings nodes
 *  (schedule, agent, model, grants, the outcome) change in place; they are fields.
 *  "Discuss with Mimi" hands the same context to a conversation instead, for the
 *  cases where you want to think out loud before anything changes. */
import { useState } from "react";
import type { Automation } from "../api";
import { flowNodes } from "./AutomationFlow";
import { MODES, fromCron, toCron } from "./RunSettings";

type Revise = (nodeTitle: string, comment: string) => Promise<{ ok: boolean; error?: string }>;

export function FlowNodePanel({
  task,
  nodeId,
  models,
  defaultModel,
  onClose,
  onRevise,
  onPatch,
  onRevoke,
  onDiscuss,
}: {
  task: Automation;
  nodeId: string;
  models: string[];
  defaultModel?: string;
  onClose: () => void;
  onRevise: Revise;
  onPatch: (changes: Record<string, unknown>) => Promise<void>;
  onRevoke: (entry: string) => Promise<void>;
  onDiscuss?: (prompt: string) => void;
}) {
  const f = flowNodes(task);
  const all = [f.trigger, f.agent, ...f.steps, ...f.subs, f.success, f.failure];
  const n = all.find((x) => x.id === nodeId);
  const [text, setText] = useState("");
  const [action, setAction] = useState<"comment" | "rename" | "insert" | "remove">("comment");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const cron = fromCron(task.schedule_raw?.cron);
  const [time, setTime] = useState(cron.time);
  const [freq, setFreq] = useState(cron.freq);
  if (!n) return null;

  const isStep = n.id.startsWith("step-");
  const isGrant = n.id.startsWith("grant-");
  const grant = isGrant ? (task.always_allowed || [])[parseInt(n.id.slice(6), 10)] : undefined;

  const ask = async (comment: string) => {
    setBusy(true);
    setError("");
    const res = await onRevise(n.title, comment);
    setBusy(false);
    if (!res.ok) setError(res.error || "The automation could not be updated.");
    else {
      setText("");
      setAction("comment");
    }
  };
  const submit = () => {
    const t = text.trim();
    if (action === "remove") return void ask(`Remove the step "${n.title}" entirely. Keep every other step exactly as it is.`);
    if (!t) return;
    if (action === "rename")
      return void ask(`Rename the step "${n.title}" to "${t}": change only how that step is worded so it reads as "${t}". Keep what it does and every other step as they are.`);
    if (action === "insert")
      return void ask(`Add a new step right after "${n.title}": ${t}. Keep every other step exactly as it is.`);
    void ask(t);
  };
  const discuss = () => {
    const t = text.trim();
    onDiscuss?.(
      `We are refining the automation "${task.title}" (id ${task.id}). About the part "${n.title}"` +
        (n.sub ? ` (${n.sub})` : "") +
        (t ? `: ${t}` : ": what should change here?") +
        `\n\nIts current instructions:\n${task.instructions}\n\nDiscuss it with me, and when we agree, save the new instructions with update_scheduled_task. Do not run the automation.`,
    );
    onClose();
  };
  const patch = async (changes: Record<string, unknown>) => {
    setBusy(true);
    setError("");
    try {
      await onPatch(changes);
    } catch {
      setError("Could not save that.");
    } finally {
      setBusy(false);
    }
  };

  const commentBox = (placeholder: string) => (
    <>
      <textarea
        autoFocus
        className="tmpl-input tmpl-textarea flow-note-text"
        data-testid="flow-note-text"
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
        }}
      />
      <div className="flow-note-actions">
        <button className="btn-primary sm" data-testid="flow-note-submit" disabled={busy || (!text.trim() && action !== "remove")} onClick={submit}>
          {busy ? "Updating…" : action === "rename" ? "Rename" : action === "insert" ? "Add the step" : "Ask Mimi to change it"}
        </button>
        {onDiscuss && (
          <button className="btn sm" data-testid="flow-note-discuss" disabled={busy} onClick={discuss}>
            Discuss with Mimi
          </button>
        )}
        {action !== "comment" && (
          <button className="link" onClick={() => setAction("comment")}>
            cancel
          </button>
        )}
      </div>
    </>
  );

  return (
    <div className="flow-note" data-testid="flow-note">
      <div className="flow-note-head">
        <span>
          {n.icon} <b>{n.title}</b>
          {n.sub ? <span className="dim"> · {n.sub}</span> : null}
        </span>
        <button className="link" onClick={onClose}>
          close
        </button>
      </div>

      {n.id === "trigger" && (
        <div className="flow-fields" data-testid="flow-trigger">
          <label className="tmpl-field">
            <span>At</span>
            <input type="time" className="tmpl-input tmpl-time" value={time} onChange={(e) => setTime(e.target.value)} />
          </label>
          <label className="tmpl-field">
            <span>Repeat</span>
            <select className="tmpl-input tmpl-select" value={freq} onChange={(e) => setFreq(e.target.value)}>
              <option value="daily">Every day</option>
              <option value="weekdays">Weekdays</option>
              <option value="weekends">Weekends</option>
            </select>
          </label>
          <button className="btn-primary sm self-end" data-testid="flow-trigger-save" disabled={busy} onClick={() => patch({ cron: toCron(time, freq) })}>
            Save schedule
          </button>
          <button className="btn sm self-end" data-testid="flow-trigger-toggle" disabled={busy} onClick={() => patch({ enabled: !task.enabled })}>
            {task.enabled ? "Pause" : "Resume"}
          </button>
        </div>
      )}

      {(n.id === "agent" || n.id === "model") && (
        <div className="flow-fields">
          <label className="tmpl-field">
            <span>Model</span>
            <select className="tmpl-input tmpl-select" data-testid="flow-model" value={task.model || ""} disabled={busy} onChange={(e) => patch({ model: e.target.value })}>
              <option value="">Default{defaultModel ? ` (${defaultModel})` : ""}</option>
              {models.map((m) => (
                <option value={m} key={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          {n.id === "agent" && (
            <label className="tmpl-field">
              <span>Permission</span>
              <select className="tmpl-input tmpl-select" data-testid="flow-mode" value={task.mode || "interactive"} disabled={busy} onChange={(e) => patch({ mode: e.target.value })}>
                {MODES.map((m) => (
                  <option value={m.value} key={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {n.id === "folder" && (
        <div className="dim" style={{ fontSize: 12.5 }}>
          Works in <code>{task.workspace}</code> — chosen when the automation was created. To have results saved somewhere else, say so below.
        </div>
      )}

      {isGrant && grant && (
        <div className="flow-fields">
          <span className="dim" style={{ fontSize: 12.5 }}>
            May use <code>{grant.tool}</code>
            {grant.target ? <> on <code>{grant.target}</code></> : null} without asking.
          </span>
          <button className="btn sm danger-btn self-end" data-testid="flow-revoke" disabled={busy} onClick={() => void onRevoke(grant.entry)}>
            Revoke
          </button>
        </div>
      )}

      {n.id === "output" && (
        <label className="flex items-center gap-2 text-[12.5px]">
          <input type="checkbox" data-testid="flow-notify" checked={task.notify_on_completion} disabled={busy} onChange={(e) => patch({ notify_on_completion: e.target.checked })} />
          Also leave me a note when a run finishes
        </label>
      )}

      {isStep && action === "comment" && (
        <div className="flow-quick">
          <button className="btn sm" data-testid="flow-rename" onClick={() => setAction("rename")}>
            Rename
          </button>
          <button className="btn sm" data-testid="flow-insert" onClick={() => setAction("insert")}>
            Add a step after
          </button>
          <button className="btn sm danger-btn" data-testid="flow-remove" onClick={() => setAction("remove")}>
            Remove
          </button>
        </div>
      )}

      {action === "remove" ? (
        <div className="flow-note-actions">
          <span className="text-[12.5px]">Remove “{n.title}” from the instructions?</span>
          <button className="btn sm danger-btn" data-testid="flow-remove-confirm" disabled={busy} onClick={submit}>
            {busy ? "Updating…" : "Remove it"}
          </button>
          <button className="link" onClick={() => setAction("comment")}>
            keep it
          </button>
        </div>
      ) : (
        commentBox(
          action === "rename"
            ? "New wording for this step, e.g. “Search last week's AI news”"
            : action === "insert"
              ? "What the new step should do, e.g. “check every link still opens”"
              : n.id === "failure"
                ? "What should happen when a run fails? e.g. “try once more, then leave me a note”"
                : n.id === "output"
                  ? "e.g. “save it as a PDF in the Reports folder, not markdown”"
                  : n.id === "trigger" || n.id === "model" || n.id === "agent" || isGrant
                    ? "Anything else about this? Mimi folds it into the instructions."
                    : "What should be different here? e.g. “only sources from the last 24 hours”",
        )
      )}
      {error && <div className="mcp-error">{error}</div>}
    </div>
  );
}
