// UX-015 (§33): tool calls render as English one-liners. The model does NOT emit a purpose
// per call — the stream is name+args+result — so the sentence is synthesized here from
// per-tool templates. `run_shell` is the exception: its optional `description` argument is
// model-written intent and is preferred when present. Fallback: "Used <tool> — <short args>".

import { shortArgs } from "./components/ApprovalCard";

// A one-line sentence in three segments so the UI can emphasize the object:
// "Read " + <b>runbook.md</b> + " from the shared folder".
export interface HumanLine {
  pre: string;
  obj?: string;
  post?: string;
}

const trunc = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
const baseName = (p: string) => p.replace(/\/+$/, "").split("/").pop() || p;

// send_message targets are "platform:chat" or "platform:chat:thread" — show the platform
// by name and the last human-ish segment of the chat id.
function messageTarget(target: string): { platform: string; tail: string } {
  const [platform, ...rest] = String(target).split(":");
  const chat = rest[0] || "";
  const tail = chat.includes("/") ? chat.split("/").pop() || chat : chat;
  const names: Record<string, string> = { slack: "Slack", telegram: "Telegram" };
  return { platform: names[platform] || platform, tail };
}

export function humanizeTool(name: string, args: any): HumanLine {
  const a = args && typeof args === "object" ? args : {};
  switch (name) {
    case "run_shell": {
      const cmd = trunc(String(a.command ?? ""), 60);
      const desc = typeof a.description === "string" && a.description.trim() ? a.description.trim() : "";
      const pre = a.run_in_background ? "Started in the background: " : "Ran ";
      return {
        pre,
        obj: cmd,
        ...(desc ? { post: ` — ${desc.charAt(0).toLowerCase()}${desc.slice(1)}` } : {}),
      };
    }
    case "shell_task_output":
      return { pre: "Checked on a background command" };
    case "shell_task_kill":
      return { pre: "Stopped a background command" };
    case "read_file":
      return { pre: "Read ", obj: baseName(String(a.path ?? "a file")) };
    case "write_file":
      return { pre: "Wrote ", obj: baseName(String(a.path ?? "a file")) };
    case "replace_in_file":
    case "apply_patch":
    case "apply_unified_diff":
      return { pre: "Edited ", obj: a.path ? baseName(String(a.path)) : "files" };
    case "grep":
      return { pre: "Searched the code for ", obj: `“${trunc(String(a.pattern ?? ""), 40)}”` };
    case "git_log":
      return { pre: "Looked through recent git history" };
    case "todo_write": {
      // `todos` is current; `items` renders histories from before the rename (the old
      // key breaks Together's GLM-5.2 chat template — see coworker/tools/todo.py).
      const items = Array.isArray(a.todos) ? a.todos : Array.isArray(a.items) ? a.items : [];
      if (items.length === 1) {
        const it = items[0] || {};
        const status = String(it.status || "").replace(/_/g, " ");
        return {
          pre: "Updated the plan — ",
          obj: `“${trunc(String(it.content ?? ""), 70)}”`,
          ...(status ? { post: ` → ${status}` } : {}),
        };
      }
      return { pre: `Updated the plan — ${items.length} items` };
    }
    case "send_message": {
      const { platform, tail } = messageTarget(String(a.target ?? ""));
      if (!tail) return { pre: "Sent a message" };
      return { pre: `Sent a ${platform} message to `, obj: tail };
    }
    case "web_search":
      return { pre: "Searched the web — ", obj: `“${trunc(String(a.query ?? ""), 60)}”` };
    case "web_fetch": {
      let host = String(a.url ?? "");
      try {
        host = new URL(host).host || host;
      } catch {
        /* keep raw */
      }
      return { pre: "Read a web page — ", obj: trunc(host, 50) };
    }
    case "explore":
      return { pre: "Sent a sub-agent to explore — ", obj: `“${trunc(String(a.task ?? a.prompt ?? ""), 60)}”` };
    case "load_skill":
      // SKILLS-SPEC §4.1 #4 — the trust line: the transcript always shows the moment a
      // skill's instructions were picked up, model-invoked or forced via /skill.
      return { pre: "Used skill: ", obj: String(a.name ?? "") };
    case "ask_user":
      return { pre: "Asked you a question" };
    case "propose_plan":
      return { pre: "Proposed a plan" };
    case "request_directory":
      return { pre: "Asked for folder access — ", obj: String(a.path ?? "") };
    default: {
      const rest = trunc(shortArgs(a), 80);
      return { pre: `Used ${name}`, ...(rest ? { post: ` — ${rest}` } : {}) };
    }
  }
}

// The approval card's headline (§35): the ask, phrased as the action being decided.
// run_shell leads with the model's own description ("Run a command — fetch stock data").
export function humanizeApprovalTitle(name: string, args: any): HumanLine {
  const a = args && typeof args === "object" ? args : {};
  switch (name) {
    case "write_file":
      return { pre: "Write ", obj: baseName(String(a.path ?? "a file")) };
    case "replace_in_file":
    case "apply_patch":
    case "apply_unified_diff":
      return { pre: "Edit ", obj: a.path ? baseName(String(a.path)) : "files" };
    case "run_shell": {
      const desc = typeof a.description === "string" && a.description.trim() ? a.description.trim() : "";
      return {
        pre: "Run a command",
        ...(desc ? { post: ` — ${desc.charAt(0).toLowerCase()}${desc.slice(1)}` } : {}),
      };
    }
    case "send_message": {
      const { tail } = messageTarget(String(a.target ?? ""));
      return tail ? { pre: "Send a message to ", obj: tail } : { pre: "Send a message" };
    }
    case "send_file": {
      const { tail } = messageTarget(String(a.target ?? ""));
      return tail ? { pre: "Send a file to ", obj: tail } : { pre: "Send a file" };
    }
    case "create_scheduled_task":
      return a.title
        ? { pre: "Create the automation ", obj: `“${trunc(String(a.title), 60)}”` }
        : { pre: "Create an automation" };
    case "save_skill":
      // SKILLS-SPEC §5.2/§7: "Add", never "install"; destination is "your skills".
      return a.name
        ? { pre: "Add skill ", obj: String(a.name), post: " to your skills" }
        : { pre: "Add a skill to your skills" };
    default:
      return { pre: `Use ${name}` };
  }
}

// Approvals with no executed tool call (typically declined): the ask, phrased as intent.
export function humanizeAsk(name: string, args: any): HumanLine {
  const a = args && typeof args === "object" ? args : {};
  switch (name) {
    case "run_shell":
      return { pre: "Wanted to run ", obj: trunc(String(a.command ?? ""), 60) };
    case "write_file":
      return { pre: "Wanted to write ", obj: baseName(String(a.path ?? "a file")) };
    case "replace_in_file":
    case "apply_patch":
    case "apply_unified_diff":
      return { pre: "Wanted to edit ", obj: a.path ? baseName(String(a.path)) : "files" };
    case "send_message": {
      const { platform, tail } = messageTarget(String(a.target ?? ""));
      if (!tail) return { pre: "Wanted to send a message" };
      return { pre: `Wanted to message `, obj: tail, post: ` on ${platform}` };
    }
    default:
      return { pre: `Wanted to use ${name}` };
  }
}

// "Working for 1m 24s" / "Worked for 12s" — the elapsed clock on a turn (and the
// pre-first-token waiting row in App).
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// One line for a run of tool calls between two pieces of narration — "Read 3 files, ran a
// command, searched the web" — the collapsed shape of activity in the turn view. Categories
// keep first-seen order; counts appear only where they mean something.
const STEP_KINDS: Record<string, [string, string] | [string]> = {
  read_file: ["read a file", "read {n} files"],
  write_file: ["edited a file", "edited {n} files"],
  replace_in_file: ["edited a file", "edited {n} files"],
  apply_patch: ["edited a file", "edited {n} files"],
  apply_unified_diff: ["edited a file", "edited {n} files"],
  run_shell: ["ran a command", "ran {n} commands"],
  shell_task_output: ["ran a command", "ran {n} commands"],
  shell_task_kill: ["ran a command", "ran {n} commands"],
  grep: ["searched the code"],
  git_log: ["searched the code"],
  web_search: ["searched the web"],
  web_fetch: ["read a web page", "read {n} web pages"],
  load_skill: ["used a skill", "used {n} skills"],
  explore: ["sent a sub-agent", "sent {n} sub-agents"],
  todo_write: ["updated the plan"],
  send_message: ["sent a message", "sent {n} messages"],
  // An approval that never became a call (declined, or still pending) — "ask:<tool>".
  ask: ["asked for permission", "asked for permission {n} times"],
};

export function summarizeSteps(names: string[]): string {
  const counts = new Map<string, number>();
  for (const name of names) {
    const kind = STEP_KINDS[name.startsWith("ask:") ? "ask" : name];
    const key = kind ? kind[0] : "used {n} tools";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const parts = [...counts].map(([key, n]) => {
    const plural = Object.values(STEP_KINDS).find((k) => k[0] === key)?.[1];
    if (key === "used {n} tools") return n === 1 ? "used a tool" : `used ${n} tools`;
    return n > 1 && plural ? plural.replace("{n}", String(n)) : key;
  });
  const line = parts.join(", ");
  return line.charAt(0).toUpperCase() + line.slice(1);
}
