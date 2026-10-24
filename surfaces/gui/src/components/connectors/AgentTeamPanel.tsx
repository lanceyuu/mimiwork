import { useEffect, useState } from "react";
import { getCodingAgents, setCodingAgent, type CodingAgent } from "../../api";
import { useT } from "../../i18n";
import { effortsFor, firstModelOption } from "./CodingAgentsSection";

// The model and effort of each connected coding agent, set from the conversation that is
// coordinating them (owner ask 2026-10-24) instead of a trip to Connectors. The same
// settings as the Coding agents page: every round reads them afresh, so a change applies
// from each agent's next round, including feedback to an agent already working.

const SELECT = "w-full min-w-0 rounded-md border border-line bg-paper px-1.5 py-1 text-[12px]";

export function AgentTeamPanel({ onOpenSettings }: { onOpenSettings?: () => void }) {
  const t = useT();
  const [agents, setAgents] = useState<CodingAgent[] | null>(null);
  useEffect(() => {
    getCodingAgents()
      .then(setAgents)
      .catch(() => setAgents([]));
  }, []);

  if (!agents) return <div className="rail-muted">{t("Loading…")}</div>;
  const ready = agents.filter((a) => a.installed && a.signed_in && !a.error);
  return (
    <div className="space-y-3" data-testid="agent-team">
      {ready.length === 0 ? (
        <div className="rail-muted">{t("No coding agent is connected yet.")}</div>
      ) : (
        ready.map((a) => <AgentRow key={a.key} a={a} />)
      )}
      <div className="rail-muted">{t("A change applies from each agent's next round.")}</div>
      {onOpenSettings && (
        <button className="rail-secondary-btn" onClick={onOpenSettings}>
          {t("All agent settings")}
        </button>
      )}
    </div>
  );
}

function AgentRow({ a }: { a: CodingAgent }) {
  const t = useT();
  const [model, setModel] = useState(a.model);
  const [effort, setEffort] = useState(a.effort);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const efforts = effortsFor({ ...a, model });

  const save = (next: { model: string; effort: string }) => {
    setNote(null);
    setCodingAgent(a.key, next)
      .then((r) => setNote(r.ok ? { ok: true, text: t("Saved") } : { ok: false, text: r.error || t("Could not save. Try again.") }))
      .catch(() => setNote({ ok: false, text: t("Could not save. Try again.") }));
  };

  return (
    <div data-testid={`agent-team-${a.key}`}>
      <div className="flex items-center gap-2 text-[12.5px] font-medium mb-1">
        {a.label}
        {note && <span className={"text-[11.5px] font-normal " + (note.ok ? "text-ok" : "text-danger")}>{note.text}</span>}
      </div>
      <div className="flex gap-1.5">
        <select
          className={SELECT}
          aria-label={`${a.label} ${t("Model")}`}
          value={model}
          onChange={(e) => {
            // A model the new pick does not take an effort level for falls back to the default.
            const m = e.target.value;
            const keep = effortsFor({ ...a, model: m }).includes(effort) ? effort : "";
            setModel(m);
            setEffort(keep);
            save({ model: m, effort: keep });
          }}
          data-testid="agent-team-model"
        >
          <option value="">{firstModelOption(a, t)}</option>
          {a.models.map((m) => (
            <option key={m.id} value={m.id} title={m.description}>
              {m.resolved ? `${t(m.label)} (${m.resolved})` : t(m.label)}
            </option>
          ))}
          {/* A name typed on the Coding agents page stays selectable here. */}
          {model && !a.models.some((m) => m.id === model) && <option value={model}>{model}</option>}
        </select>
        {efforts.length > 0 && (
          <select
            className={SELECT + " max-w-[7.5rem]"}
            aria-label={`${a.label} ${t("Effort")}`}
            value={effort}
            onChange={(e) => {
              setEffort(e.target.value);
              save({ model, effort: e.target.value });
            }}
            data-testid="agent-team-effort"
          >
            <option value="">{t("Default")}</option>
            {efforts.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}
