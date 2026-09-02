/** The pieces an automation's settings are made of, shared by the detail page, its
 *  editor, the flow diagram's node panel and the Apps creator: the three permission
 *  levels, the time-of-day ⇄ cron helpers, and the Model + Permission control. */

// Parse a simple "min hour * * dow" cron back into the time + frequency the editor uses.
// Falls back to 09:00 / daily for anything it doesn't recognize (e.g. agent-written crons).
export function fromCron(cron?: string | null): { time: string; freq: string } {
  const parts = (cron || "").trim().split(/\s+/);
  if (parts.length !== 5) return { time: "09:00", freq: "daily" };
  const [m, h, , , dow] = parts;
  const hh = String(Math.min(23, Math.max(0, parseInt(h, 10) || 9))).padStart(2, "0");
  const mm = String(Math.min(59, Math.max(0, parseInt(m, 10) || 0))).padStart(2, "0");
  const freq = dow === "1-5" ? "weekdays" : dow === "0,6" || dow === "6,0" ? "weekends" : "daily";
  return { time: `${hh}:${mm}`, freq };
}


// Map a simple time-of-day + frequency selection to a 5-field cron string.
export function toCron(time: string, freq: string): string {
  const [h, m] = (time || "09:00").split(":").map((x) => parseInt(x, 10) || 0);
  const dow = freq === "weekdays" ? "1-5" : freq === "weekends" ? "0,6" : "*";
  return `${m} ${h} * * ${dow}`;
}

// The three permission levels, in the composer's own words — what you learned in
// a session is what an automation means. The difference: nobody is watching at
// 7am, so "ask" parks its question in the Inbox and the run waits there.
export const MODES: { value: string; label: string; hint: string }[] = [
  { value: "interactive", label: "Ask for approval", hint: "Parks the question in your Inbox and waits." },
  { value: "auto", label: "Full access", hint: "Runs everything without asking." },
  { value: "plan", label: "Plan only", hint: "Proposes what it would do; never acts." },
];

export function modeLabel(mode?: string): string {
  return MODES.find((m) => m.value === (mode || "interactive"))?.label ?? "Ask for approval";
}

export function RunSettings({
  model,
  mode,
  models,
  defaultModel,
  onModel,
  onMode,
}: {
  model: string;
  mode: string;
  models: string[];
  defaultModel?: string;
  onModel: (v: string) => void;
  onMode: (v: string) => void;
}) {
  return (
    <div className="tmpl-sched">
      <label className="tmpl-field">
        <span>Model</span>
        <select
          className="tmpl-input tmpl-select"
          value={model}
          onChange={(e) => onModel(e.target.value)}
          data-testid="auto-model"
        >
          <option value="">Default{defaultModel ? ` (${defaultModel})` : ""}</option>
          {models.map((m) => (
            <option value={m} key={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label className="tmpl-field">
        <span>Permission</span>
        <select
          className="tmpl-input tmpl-select"
          value={mode}
          onChange={(e) => onMode(e.target.value)}
          data-testid="auto-mode"
        >
          {MODES.map((m) => (
            <option value={m.value} key={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <span className="text-[11.5px] text-faint self-center">
        {MODES.find((m) => m.value === mode)?.hint}
      </span>
    </div>
  );
}

