/** The side panel for one agent in a system: what it does, which model thinks how hard,
 *  which tools it may use — or, for a coding agent, which CLI works in which folder.
 *
 *  Its connections are listed here too, with their label and loop limit. Dragging is the
 *  quick way to connect; this list is the way that also works from the keyboard. */
import { AGENT_TOOLS, type AgentEdge, type AgentEffort, type AgentNode, type CodingAgent } from "../../api";
import { chooseFolder } from "../../tauri";
import { Icon } from "../Icon";
import { CODING_LABELS, KIND_LABELS, modelShort } from "./AgentCanvas";
import { FieldTip, KIND_HELP } from "./HelpTip";

const EFFORTS: { value: AgentEffort; label: string }[] = [
  { value: "", label: "Default" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

interface Props {
  node: AgentNode;
  nodes: AgentNode[];
  edges: AgentEdge[];
  isEntry: boolean;
  problems: string[];
  models: string[];
  modelLabels: Record<string, string>;
  defaultModel: string;
  codingAgents: CodingAgent[];
  onChange: (patch: Partial<AgentNode>) => void;
  onEdgeChange: (edge: AgentEdge, patch: Partial<AgentEdge>) => void;
  onConnect: (to: string) => void;
  onRemoveEdge: (edge: AgentEdge) => void;
  onMakeEntry: () => void;
  onDelete: () => void;
  onClose: () => void;
}

export function NodeInspector({
  node,
  nodes,
  edges,
  isEntry,
  problems,
  models,
  modelLabels,
  defaultModel,
  codingAgents,
  onChange,
  onEdgeChange,
  onConnect,
  onRemoveEdge,
  onMakeEntry,
  onDelete,
  onClose,
}: Props) {
  const name = (id: string) => nodes.find((n) => n.id === id)?.name || id;
  const out = edges.filter((e) => e.from === node.id);
  const into = edges.filter((e) => e.to === node.id);
  const free = nodes.filter((n) => n.id !== node.id && !out.some((e) => e.to === n.id));
  const coding = node.kind === "coding";
  const thinks = node.kind !== "review" && !coding;
  const cli = codingAgents.find((a) => a.key === node.agent);
  const cliOptions = codingAgents.length
    ? codingAgents.map((a) => ({ key: a.key, label: a.label }))
    : Object.entries(CODING_LABELS).map(([key, label]) => ({ key, label }));
  // A model saved earlier (or by Mimi) may not be in today's list; keep it choosable.
  const modelOptions = node.model && !models.includes(node.model) ? [node.model, ...models] : models;

  return (
    <aside className="ag-inspector" data-testid="node-inspector" aria-label={`Settings for ${node.name}`}>
      <div className="ag-inspector-head">
        <span className="ag-inspector-kind" title={KIND_HELP[node.kind]}>
          {KIND_LABELS[node.kind]}
        </span>
        <button className="artifact-icon-btn" onClick={onClose} aria-label="Close settings" title="Close">
          <Icon name="x" size={14} />
        </button>
      </div>

      {problems.length > 0 && (
        <ul className="ag-inspector-problems" data-testid="node-problems">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}

      <label className="ag-field">
        <span className="ag-field-head">
          Name <FieldTip field="name" />
        </span>
        <input
          className="tmpl-input"
          data-testid="node-name"
          value={node.name}
          maxLength={60}
          onChange={(e) => onChange({ name: e.target.value })}
        />
      </label>

      <label className="ag-field">
        <span className="ag-field-head">
          {node.kind === "review" ? "What should the person check?" : "What should it do?"}{" "}
          <FieldTip field={node.kind === "review" ? "review" : "instructions"} />
        </span>
        <textarea
          className="tmpl-input tmpl-textarea"
          data-testid="node-instructions"
          rows={5}
          value={node.instructions}
          placeholder={
            node.kind === "router"
              ? "e.g. Decide whether the email is a question, a late arrival or an exception."
              : node.kind === "orchestrator"
                ? "e.g. Split the request into parts, give each part to the right helper, then write one answer."
                : node.kind === "review"
                  ? "Optional. e.g. Check the refund amount before it is sent."
                  : "e.g. Draft a short, warm reply in the guest's language."
          }
          onChange={(e) => onChange({ instructions: e.target.value })}
        />
      </label>

      {thinks && (
        <>
          <label className="ag-field">
            <span className="ag-field-head">
              Model <FieldTip field="model" />
            </span>
            <select
              className="tmpl-input tmpl-select"
              data-testid="node-model"
              value={node.model}
              onChange={(e) => onChange({ model: e.target.value })}
            >
              <option value="">
                The model this chat uses{defaultModel ? ` (now ${modelShort(modelLabels, defaultModel)})` : ""}
              </option>
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {modelShort(modelLabels, m)}
                </option>
              ))}
            </select>
          </label>
          <EffortField value={node.effort} onChange={(effort) => onChange({ effort })} />
          <fieldset className="ag-field ag-tools" data-testid="node-tools">
            <legend className="ag-field-head">
              Tools it may use <FieldTip field="tools" />
            </legend>
            {AGENT_TOOLS.map((t) => (
              <label key={t.id} className="ag-tool">
                <input
                  type="checkbox"
                  checked={node.tools.includes(t.id)}
                  onChange={(e) =>
                    onChange({
                      tools: e.target.checked ? [...node.tools, t.id] : node.tools.filter((x) => x !== t.id),
                    })
                  }
                />
                {t.label}
              </label>
            ))}
          </fieldset>
        </>
      )}

      {coding && (
        <>
          <label className="ag-field">
            <span className="ag-field-head">
              Coding agent <FieldTip field="coding" />
            </span>
            <select
              className="tmpl-input tmpl-select"
              data-testid="node-agent"
              value={node.agent}
              // A model id belongs to one CLI, so changing the CLI clears it.
              onChange={(e) => onChange({ agent: e.target.value, model: "" })}
            >
              {!node.agent && <option value="">Choose one</option>}
              {cliOptions.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
          <label className="ag-field">
            <span className="ag-field-head">
              Its model <FieldTip field="codingModel" />
            </span>
            <select
              className="tmpl-input tmpl-select"
              data-testid="node-coding-model"
              value={node.model}
              onChange={(e) => onChange({ model: e.target.value })}
            >
              <option value="">{cli ? `${cli.label}'s own setting` : "The agent's own setting"}</option>
              {node.model && !cli?.models.some((m) => m.id === node.model) && <option value={node.model}>{node.model}</option>}
              {(cli?.models || []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <EffortField value={node.effort} onChange={(effort) => onChange({ effort })} />
          <div className="ag-field">
            <span className="ag-field-head">
              Project folder <FieldTip field="folder" />
            </span>
            <div className="ag-folder">
              <input
                className="tmpl-input"
                data-testid="node-folder"
                value={node.folder}
                placeholder="~/projects/my-app"
                onChange={(e) => onChange({ folder: e.target.value })}
              />
              <button
                className="btn sm"
                onClick={async () => {
                  const picked = await chooseFolder().catch(() => null);
                  if (picked) onChange({ folder: picked });
                }}
              >
                Choose…
              </button>
            </div>
          </div>
        </>
      )}

      <div className="ag-field" data-testid="node-connections">
        <span className="ag-field-head">
          {node.kind === "orchestrator" ? "Assigns work to" : node.kind === "router" ? "Choices" : "Sends its work to"}{" "}
          <FieldTip
            field={node.kind === "orchestrator" ? "helpers" : node.kind === "router" ? "routerConnections" : "connections"}
          />
        </span>
        {out.length === 0 && <div className="dim ag-small">Nothing yet. The last agent's answer is the result.</div>}
        {out.map((e) => (
          <div className="ag-conn" key={e.to} data-testid={`node-conn-${e.to}`}>
            <div className="ag-conn-row">
              <span className="ag-conn-name">{name(e.to)}</span>
              <button className="link" onClick={() => onRemoveEdge(e)} aria-label={`Remove the connection to ${name(e.to)}`}>
                remove
              </button>
            </div>
            {e.kind === "flow" && (
              <div className="ag-conn-row">
                <input
                  className="tmpl-input ag-conn-label"
                  value={e.label}
                  maxLength={40}
                  aria-label={`Label for the connection to ${name(e.to)}`}
                  placeholder={node.kind === "router" ? "When to choose this (required)" : "Label (optional)"}
                  onChange={(ev) => onEdgeChange(e, { label: ev.target.value })}
                />
                <select
                  className="tmpl-input tmpl-select ag-conn-rounds"
                  aria-label={`Loop limit for the connection to ${name(e.to)}`}
                  value={e.max_rounds ?? ""}
                  onChange={(ev) => onEdgeChange(e, { max_rounds: ev.target.value ? Number(ev.target.value) : null })}
                >
                  <option value="">Goes forward</option>
                  {[1, 2, 3, 4, 5].map((r) => (
                    <option key={r} value={r}>
                      Loops back, up to {r} {r === 1 ? "time" : "times"}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        ))}
        {free.length > 0 && (
          <select
            className="tmpl-input tmpl-select"
            data-testid="node-connect"
            value=""
            aria-label="Connect to another agent"
            onChange={(e) => e.target.value && onConnect(e.target.value)}
          >
            <option value="">Connect to…</option>
            {free.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>
        )}
        {into.length > 0 && (
          <div className="dim ag-small">Gets work from {into.map((e) => name(e.from)).join(", ")}.</div>
        )}
      </div>

      <div className="ag-inspector-foot">
        {isEntry ? (
          <span className="dim ag-small">This agent starts the work.</span>
        ) : (
          <button className="btn sm" data-testid="node-make-entry" onClick={onMakeEntry}>
            Start the work here
          </button>
        )}
        <button className="btn sm danger-btn" data-testid="node-delete" onClick={onDelete}>
          <Icon name="trash" size={13} /> Remove agent
        </button>
      </div>
    </aside>
  );
}

function EffortField({ value, onChange }: { value: AgentEffort; onChange: (v: AgentEffort) => void }) {
  return (
    <label className="ag-field">
      <span className="ag-field-head">
        Thinking effort <FieldTip field="effort" />
      </span>
      <select
        className="tmpl-input tmpl-select"
        data-testid="node-effort"
        value={value}
        onChange={(e) => onChange(e.target.value as AgentEffort)}
      >
        {EFFORTS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
