/** "Works the same elsewhere" — the one page that makes MimiWork transferable.
 *
 * Owner ask 2026-08-23: someone who learns MimiWork should be able to sit down at Claude
 * Code, Claude Cowork or Codex and already know what to do. Every row is a concept this
 * app really has, next to what the same thing is called over there. No aspirational rows:
 * if MimiWork doesn't do it, it isn't in the table.
 */
import { Icon } from "./Icon";

type Row = {
  here: string;
  what: string;
  cowork: string;
  code: string;
  codex: string;
};

const ROWS: Row[] = [
  {
    here: "/ palette",
    what: "Type / in the message box for app commands, your saved commands and skills.",
    cowork: "/ commands",
    code: "/ slash commands",
    codex: "/ commands",
  },
  {
    here: "@ a file",
    what: "Type @ to point at a file inside a folder you granted.",
    cowork: "@ file mentions",
    code: "@ file mentions",
    codex: "@ file mentions",
  },
  {
    here: "Plan",
    what: "The coworker proposes a plan and waits for your approval before acting.",
    cowork: "Plan before acting",
    code: "Plan mode (⇧⇥)",
    codex: "Plan mode",
  },
  {
    here: "Ask for approval",
    what: "Every consequential action stops for a yes or no.",
    cowork: "Manual",
    code: "Default mode",
    codex: "Approval on request",
  },
  {
    here: "Full access",
    what: "Nothing pauses. Use it on a folder you'd be happy to hand over entirely.",
    cowork: "Skip",
    code: "Bypass permissions",
    codex: "Full auto",
  },
  {
    here: "AGENTS.md",
    what: "House rules for a folder, read at the start of every conversation. CLAUDE.md works too.",
    cowork: "Folder instructions",
    code: "CLAUDE.md",
    codex: "AGENTS.md",
  },
  {
    here: "Global instructions",
    what: "The same idea, but for every folder — Settings ▸ Instructions.",
    cowork: "Global instructions",
    code: "~/.claude/CLAUDE.md",
    codex: "~/.codex/AGENTS.md",
  },
  {
    here: "Skills",
    what: "A folder with a SKILL.md that teaches your way of doing something.",
    cowork: "Skills",
    code: "Skills",
    codex: "—",
  },
  {
    here: "Projects",
    what: "A folder with its own instructions, memory and conversations.",
    cowork: "Projects",
    code: "A repo you cd into",
    codex: "A repo you cd into",
  },
  {
    here: "Connectors",
    what: "Gmail, Slack, Drive, Calendar and MCP servers the coworker may use.",
    cowork: "Connectors",
    code: "MCP servers",
    codex: "MCP servers",
  },
  {
    here: "explore",
    what: "A read-only helper with its own context that researches and reports back.",
    cowork: "Sub-agents",
    code: "Subagents / Task tool",
    codex: "—",
  },
  {
    here: "/compact",
    what: "Condense a long conversation into a summary so there's room to keep going.",
    cowork: "Automatic",
    code: "/compact",
    codex: "/compact",
  },
];

const GESTURES: { keys: string; what: string }[] = [
  { keys: "/", what: "Commands and skills" },
  { keys: "@", what: "Point at a file" },
  { keys: "⇧⇥", what: "Cycle Plan → Ask for approval → Full access" },
  { keys: "⏎", what: "Send · ⇧⏎ new line" },
  { keys: "Esc", what: "Close a popup" },
];

export function TransferGuide() {
  return (
    <section data-testid="transfer-guide">
      <div className="mb-5">
        <h2 className="text-[15px] font-semibold text-ink">
          The same skills work in Claude Code, Cowork and Codex
        </h2>
        <p className="text-[12.5px] text-muted mt-1.5 leading-relaxed max-w-2xl">
          MimiWork deliberately uses the same words and gestures as the other agentic tools,
          so nothing you learn here is trapped here. This is the map.
        </p>
      </div>

      <div className="rounded-xl2 border border-line bg-panel p-4 mb-5">
        <div className="text-[12.5px] font-medium text-ink mb-2.5">In the message box</div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {GESTURES.map((g) => (
            <div key={g.keys} className="flex items-center gap-2">
              <kbd className="px-1.5 py-0.5 rounded-md border border-line bg-paper text-[11.5px] text-ink">
                {g.keys}
              </kbd>
              <span className="text-[12px] text-muted">{g.what}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl2 border border-line bg-panel overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[680px]">
          <thead>
            <tr className="text-[11.5px] uppercase tracking-wide text-faint">
              <th className="px-4 py-2.5 font-medium">In MimiWork</th>
              <th className="px-4 py-2.5 font-medium">Claude Cowork</th>
              <th className="px-4 py-2.5 font-medium">Claude Code</th>
              <th className="px-4 py-2.5 font-medium">Codex</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.here} className="border-t border-line align-top">
                <td className="px-4 py-3">
                  <div className="text-[13px] font-medium text-ink">{r.here}</div>
                  <div className="text-[12px] text-muted mt-1 leading-relaxed max-w-md">
                    {r.what}
                  </div>
                </td>
                <td className="px-4 py-3 text-[12.5px] text-muted">{r.cowork}</td>
                <td className="px-4 py-3 text-[12.5px] text-muted">{r.code}</td>
                <td className="px-4 py-3 text-[12.5px] text-muted">{r.codex}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[12px] text-muted mt-4 flex items-start gap-2 leading-relaxed">
        <Icon name="sparkle" size={14} className="text-faint mt-0.5 shrink-0" />
        <span>
          One difference worth knowing: those tools ask you to trust a folder from a
          terminal, while MimiWork asks in the app and remembers per folder. The permission
          question is the same one — who may change what, and when do you get asked.
        </span>
      </p>
    </section>
  );
}
