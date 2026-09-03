import { useEffect, useState } from "react";
import { connectEvents, getActivity, interruptSession, type ActivityRow } from "../api";
import { Icon } from "./Icon";

// Mission control (design spec 2026-08-20 §2): one live "Now" band at the top of the
// sidebar — every running session and automation plus anything waiting on the user.
// Renders NOTHING while the app is quiet, so the sidebar stays clean; while work is
// live it's the single at-a-glance answer to "what is Mimi doing right now".
// Data: /v1/activity items, refreshed on every activity flip frame + a slow poll
// (the flip broadcast only fires on busy/needs-user transitions, not per item).

function elapsed(startedAt?: number): string {
  if (!startedAt) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

export function MissionControl(props: {
  onSelectSession: (id: string, workspace: string, agent: string) => void;
  onOpenAutomation: (id: string) => void;
  onOpenInbox: () => void;
}) {
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [, setTick] = useState(0); // re-render so the elapsed labels stay honest

  useEffect(() => {
    let alive = true;
    const refresh = () =>
      getActivity()
        .then((a) => alive && setRows(a.items ?? []))
        .catch(() => undefined);
    refresh();
    const stop = connectEvents((msg) => {
      if (msg.type === "activity") refresh();
    });
    const poll = window.setInterval(refresh, 5000);
    const clock = window.setInterval(() => setTick((t) => t + 1), 30000);
    return () => {
      alive = false;
      stop();
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, []);

  if (rows.length === 0) return null;

  const stopSession = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    void interruptSession(id).catch(() => undefined);
  };

  return (
    <div data-testid="mission-control">
      <div className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wide text-faint flex items-center gap-1.5">
        <span className="mc-live-dot" aria-hidden />
        Now
      </div>
      <div className="space-y-0.5">
        {rows.map((r) => (
          <div
            key={`${r.kind}:${r.id}`}
            className={
              "w-full flex items-center rounded-lg text-[12.5px] group " +
              (r.kind === "approval" ? "mc-approval" : "text-muted hover:text-ink")
            }
          >
            <button
              type="button"
              data-testid={`mc-${r.kind}`}
              className="min-w-0 flex-1 flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left hover:bg-paper"
              title={
                r.kind === "approval"
                  ? "Waiting for you — open the conversation"
                  : r.kind === "automation"
                    ? "Automation running — view it"
                    : "Session working — open it"
              }
              onClick={() => {
                if (r.kind === "session")
                  props.onSelectSession(r.id, r.workspace || "", r.agent || "cowork");
                else if (r.kind === "automation") props.onOpenAutomation(r.id);
                // A prompt waits INSIDE its conversation (the card renders there); the
                // cross-session Inbox only lists unattended ones, so it read as empty.
                else if (r.session_id)
                  props.onSelectSession(r.session_id, r.workspace || "", r.agent || "cowork");
                else props.onOpenInbox();
              }}
            >
              <Icon
                name={r.kind === "automation" ? "clock" : r.kind === "approval" ? "inbox" : "chat"}
                size={13}
                className="shrink-0"
              />
              <span className="flex-1 truncate">{r.title}</span>
              {r.kind !== "approval" && (
                <span className="text-[11px] text-faint shrink-0">{elapsed(r.started_at)}</span>
              )}
            </button>
            {r.kind === "session" && (
              <button
                type="button"
                aria-label="Stop this session"
                title="Stop"
                className="mc-stop opacity-0 group-hover:opacity-100 focus:opacity-100 shrink-0 mr-2"
                onClick={(e) => stopSession(e, r.id)}
              >
                <Icon name="stop" size={12} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
