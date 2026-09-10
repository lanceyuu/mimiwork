import { useEffect, useState } from "react";
import { formatElapsed } from "../humanize";
import { useT } from "../i18n";
import type { WsEvent } from "../types";

export type TaskProgress = { phase: string; lastActivity: number };

export function progressFromEvent(current: TaskProgress, event: WsEvent): TaskProgress {
  if (event.type === "session_status" || event.type === "ready") return {
    phase: event.data?.phase || current.phase,
    lastActivity: event.data?.last_activity_at ? event.data.last_activity_at * 1000 : current.lastActivity,
  };
  const phases: Record<string, string> = {
    turn_start: "model", iteration_end: "model", assistant_message: "model",
    assistant_delta: "responding", reasoning_delta: "thinking", tool_started: "tool",
    permission_required: "waiting", directory_requested: "waiting",
    question_requested: "waiting", plan_proposed: "waiting", compacting: "compacting",
    compacted: "model", interrupt_requested: "stopping", steer_queued: "steering",
  };
  const phase = event.type === "notice" && event.data?.kind === "steering" ? "model" : phases[event.type];
  return phase || event.type === "tool_finished" || event.type === "notice"
    ? { phase: phase || current.phase, lastActivity: Date.now() } : current;
}

const LABELS: Record<string, string> = {
  model: "Waiting for the model…", thinking: "Thinking…", responding: "Writing a response…",
  tool: "Running a step…", waiting: "Waiting for your response…",
  compacting: "Summarizing earlier messages…", steering: "Updating the task with your message…",
  stopping: "Stopping the current task…",
};

export function TaskStatus({ running, connected, since, progress, lastReceived, stopping, error }: {
  running: boolean; connected: boolean; since: number | null; progress: TaskProgress;
  lastReceived: number; stopping: boolean; error?: string;
}) {
  const t = useT();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!running && connected && !error) return null;
  const responsive = connected && now - lastReceived < 20_000;
  const label = !responsive ? "Connection lost. Reconnecting…"
    : stopping ? LABELS.stopping : LABELS[progress.phase] || LABELS.model;
  const quiet = progress.lastActivity && now - progress.lastActivity >= 15_000;
  return (
    <div className="px-3 pb-2 text-xs text-muted" data-testid="task-status">
      <div className="flex items-center gap-2" role="status">
        {responsive && running && <span className="spinner" />}
        <span>{t(label)}</span>
        {running && since && <span className="text-faint tabular-nums" data-testid="task-elapsed">{formatElapsed(Math.max(0, now - since))}</span>}
      </div>
      {running && responsive && quiet && progress.phase !== "waiting" && !stopping && (
        <p className="mt-1 text-faint">{t("Connection active. No new output for")} {formatElapsed(now - progress.lastActivity)}.</p>
      )}
      {running && !responsive && <p className="mt-1">{t("The task may still be running. You can still try Stop task.")}</p>}
      {error && <p className="mt-1 text-danger" role="alert">{error}</p>}
    </div>
  );
}
