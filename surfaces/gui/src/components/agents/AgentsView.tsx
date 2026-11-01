/** Agents — teams of agents the user designs once and runs again (backend: agent systems).
 *
 *  Mirrors Apps: an overview (saved systems, "describe what you need", and the nine
 *  patterns from the owner's Agentic AI deck), and a detail page that is mostly the
 *  diagram. Runs happen in a chat, where Mimi can ask the user at a review step; this page
 *  polls the newest run and lights up each agent as it works.
 */
import { useEffect, useState } from "react";
import {
  announceAgentSystemsChanged,
  createAgentSystem,
  deleteAgentSystem,
  exportAgentSystem,
  getAgentSystem,
  getAgentSystemPatterns,
  getAgentSystemRuns,
  getAgentSystems,
  getCodingAgents,
  getSettings,
  updateAgentSystem,
  type AgentSystem,
  type AgentSystemPattern,
  type AgentSystemProblem,
  type AgentSystemRun,
  type CodingAgent,
} from "../../api";
import { ConfirmDialog } from "../ConfirmDialog";
import { Icon } from "../Icon";
import { InlineNotice } from "../InlineNotice";
import { PanelHead } from "../IntegrationsView";
import { AgentCanvas } from "./AgentCanvas";

const CARD = "rounded-xl2 border border-line bg-panel";
const GROUPS = ["Flow", "Loops", "Capabilities", "Collaboration"];

const RUN_LABELS: Record<string, string> = {
  working: "Running",
  done: "Finished",
  failed: "Stopped with an error",
  stopped: "Stopped",
};

interface Props {
  /** Open a conversation with Mimi and send `prompt` under the mimi-agents skill. */
  onBuild: (prompt: string) => void;
  initialOpenId?: string | null;
}

export function AgentsView({ onBuild, initialOpenId }: Props) {
  const [systems, setSystems] = useState<AgentSystem[]>([]);
  const [patterns, setPatterns] = useState<AgentSystemPattern[]>([]);
  const [openId, setOpenId] = useState<string | null>(initialOpenId ?? null);
  const [wish, setWish] = useState("");
  const [problem, setProblem] = useState("");
  const [confirmDel, setConfirmDel] = useState<AgentSystem | null>(null);

  const refresh = () => getAgentSystems().then(setSystems).catch(() => setSystems([]));
  useEffect(() => {
    refresh();
    getAgentSystemPatterns().then(setPatterns).catch(() => setPatterns([]));
    // Mimi saves systems from a chat; the overview must notice without a click.
    const h = setInterval(refresh, 5000);
    return () => clearInterval(h);
  }, []);
  useEffect(() => {
    if (initialOpenId) setOpenId(initialOpenId);
  }, [initialOpenId]);

  if (openId) {
    return (
      <AgentSystemDetail
        key={openId}
        id={openId}
        onOpen={setOpenId}
        onBack={() => {
          setOpenId(null);
          refresh();
        }}
        onBuild={onBuild}
      />
    );
  }

  const describe = () => {
    const text = wish.trim();
    if (!text) return;
    onBuild(`Design an agent system for me: ${text}`);
    setWish("");
  };

  const addPattern = async (p: AgentSystemPattern) => {
    setProblem("");
    const r = await createAgentSystem(p.system).catch(() => ({ ok: false as const, system: undefined }));
    if (r.ok && r.system) {
      announceAgentSystemsChanged();
      setOpenId(r.system.id);
    } else setProblem(`"${p.title}" could not be added. Try again in a moment.`);
  };

  return (
    <Shell>
      <PanelHead
        title="Agents"
        sub="Teams of agents that share a job you do again and again. Start from a pattern or describe what you need, then choose each agent's model, effort and tools."
      />

      <div className={CARD + " p-4 mb-5"} data-testid="agents-describe">
        <div className="text-[13px] font-medium mb-1">Describe what you need</div>
        <div className="text-[12px] text-faint mb-2">
          Say what comes in, what should come out, what has to be checked, and where a person should decide. Mimi
          asks a few questions, picks a pattern and draws the team below.
        </div>
        <textarea
          className="tmpl-input tmpl-textarea w-full"
          data-testid="agents-wish"
          rows={3}
          placeholder="e.g. Answer guest emails: sort them, draft a reply, check it against our policies, and let me approve refunds."
          value={wish}
          onChange={(e) => setWish(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) describe();
          }}
        />
        <div className="mt-2">
          <button className="btn-primary sm" data-testid="agents-describe-go" disabled={!wish.trim()} onClick={describe}>
            Design it with Mimi
          </button>
        </div>
      </div>

      {systems.length > 0 && (
        <>
          <div className="sa-sub">Your agent systems</div>
          <div className="grid gap-2.5 mb-5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
            {systems.map((s) => (
              <button
                key={s.id}
                className={CARD + " p-3.5 text-left hover:border-accent flex flex-col gap-1.5"}
                data-testid={`agent-system-card-${s.id}`}
                onClick={() => setOpenId(s.id)}
              >
                <div className="flex items-center gap-2 text-[13.5px] font-medium">
                  <span className="truncate flex-1">{s.title}</span>
                  <span
                    className="text-faint hover:text-danger"
                    role="button"
                    aria-label={`Delete ${s.title}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmDel(s);
                    }}
                  >
                    <Icon name="trash" size={14} />
                  </span>
                </div>
                {s.description && <div className="text-[12.5px] text-muted">{s.description}</div>}
                <div className="text-[11.5px] text-faint">
                  {s.nodes.length} {s.nodes.length === 1 ? "agent" : "agents"}
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      {patterns.length > 0 && (
        <div className="ag-gallery" data-testid="agents-gallery">
          <div className="sa-sub">Start from a pattern</div>
          <div className="dim" style={{ marginBottom: 10, fontSize: 12.5 }}>
            Each one is a working example built on a hotel front desk. Pick one, then change it to fit your work.
          </div>
          {problem && <InlineNotice text={problem} onDismiss={() => setProblem("")} />}
          {[...GROUPS, ...new Set(patterns.map((p) => p.group).filter((g) => !GROUPS.includes(g)))].map((g) => {
            const items = patterns.filter((p) => p.group === g);
            if (!items.length) return null;
            return (
              <div key={g} className="ag-gallery-group">
                <div className="apps-gallery-cat">{g}</div>
                <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
                  {items.map((p) => (
                    <button
                      key={p.pattern}
                      className={CARD + " ag-pattern text-left hover:border-accent"}
                      data-testid={`agent-pattern-${p.pattern}`}
                      onClick={() => void addPattern(p)}
                    >
                      <AgentCanvas system={p.system} readOnly />
                      <div className="p-3 pt-2 flex flex-col gap-1">
                        <div className="text-[13.5px] font-medium">{p.title}</div>
                        <div className="text-[12.5px] text-muted">{p.summary}</div>
                        <div className="text-[11.5px] text-faint">Use when: {p.when}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {confirmDel && (
        <ConfirmDialog
          title="Delete this agent system?"
          body={`${confirmDel.title} is removed from Agents. Chats that ran it keep their results.`}
          confirmLabel="Delete"
          onCancel={() => setConfirmDel(null)}
          onConfirm={async () => {
            const target = confirmDel;
            setConfirmDel(null);
            await deleteAgentSystem(target.id).catch(() => {});
            announceAgentSystemsChanged();
            refresh();
          }}
        />
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1 min-w-0 flex bg-paper">
      <div className="flex-1 min-w-0 overflow-y-auto hairline-scroll">
        <div className="max-w-4xl mx-auto px-7 py-6">{children}</div>
      </div>
    </main>
  );
}

/** Save system.json. The sidecar writes it to Downloads when it can (the desktop webview
 *  does not reliably download); otherwise the browser saves it. */
async function exportSystem(system: AgentSystem): Promise<string> {
  const saved = await exportAgentSystem(system.id).catch(() => null);
  if (saved?.path) return `Saved to ${saved.path}.`;
  const url = URL.createObjectURL(new Blob([JSON.stringify(system, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "system.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return "Saved system.json to your downloads.";
}

function AgentSystemDetail({
  id,
  onOpen,
  onBack,
  onBuild,
}: {
  id: string;
  onOpen: (id: string) => void;
  onBack: () => void;
  onBuild: (prompt: string) => void;
}) {
  const [system, setSystem] = useState<AgentSystem | null>(null);
  const [problems, setProblems] = useState<AgentSystemProblem[]>([]);
  const [run, setRun] = useState<AgentSystemRun | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [defaultModel, setDefaultModel] = useState("");
  const [codingAgents, setCodingAgents] = useState<CodingAgent[]>([]);
  const [runOpen, setRunOpen] = useState(false);
  const [input, setInput] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);
  const [notice, setNotice] = useState<{ text: string; tone: "error" | "info" } | null>(null);
  const [saving, setSaving] = useState<"" | "saving" | "saved" | "failed">("");

  useEffect(() => {
    getAgentSystem(id)
      .then((r) => {
        if (!r.ok || !r.system) return onBack();
        setSystem(r.system);
        setProblems(r.problems || []);
      })
      .catch(() => onBack());
    getSettings()
      .then((s) => {
        setModels(s.models || []);
        setLabels(s.model_labels || {});
        setDefaultModel(s.model || "");
      })
      .catch(() => {});
    getCodingAgents().then(setCodingAgents).catch(() => {});
    // ponytail: edits Mimi makes from a chat while this page is open show on reopening;
    // merging them live would need conflict handling with the user's own unsaved edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // The newest run, polled: it starts in a chat, so this page only learns of it here.
  useEffect(() => {
    let stop = false;
    const poll = async () => {
      // Each listed run is the full saved run, newest first.
      const runs = await getAgentSystemRuns(id).catch(() => []);
      if (!stop) setRun(runs[0] ?? null);
    };
    void poll();
    const h = setInterval(poll, 3000);
    return () => {
      stop = true;
      clearInterval(h);
    };
  }, [id]);

  if (!system) {
    return (
      <Shell>
        <div className="dim">Loading…</div>
      </Shell>
    );
  }

  const save = async (parts: Partial<AgentSystem>) => {
    setSaving("saving");
    const r = await updateAgentSystem(id, parts).catch(() => null);
    if (r?.ok && r.system) {
      setProblems(r.problems || []);
      setSystem((cur) => (cur ? { ...cur, ...parts, updated_at: r.system!.updated_at } : cur));
      setSaving("saved");
      announceAgentSystemsChanged();
    } else setSaving("failed");
  };

  const startRun = () => {
    const text = input.trim();
    if (!text) return;
    onBuild(
      `Run the agent system "${system.title}" (id ${system.id}) with run_agent_system on this input:\n\n${text}`,
    );
    setRunOpen(false);
    setInput("");
  };

  const runnable = problems.length === 0;

  return (
    <div className="app-page ag-page" data-testid="agent-system-page">
      <div className="app-head">
        <button className="artifact-icon-btn" onClick={onBack} aria-label="Back to agents" title="Back">
          <Icon name="arrowLeft" size={16} />
        </button>
        <div className="app-head-text">
          {renaming ? (
            <input
              className="tmpl-input app-title-input"
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={async (e) => {
                if (e.key === "Escape") setRenaming(false);
                if (e.key === "Enter" && title.trim()) {
                  await save({ title: title.trim() });
                  setRenaming(false);
                }
              }}
              onBlur={() => setRenaming(false)}
            />
          ) : (
            <button
              className="app-title"
              title="Rename"
              data-testid="agent-system-title"
              onClick={() => {
                setTitle(system.title);
                setRenaming(true);
              }}
            >
              {system.title}
            </button>
          )}
          <div className="app-desc" title={system.description}>
            {system.description || "No description yet."}
          </div>
        </div>
        <span className="ag-save-state" data-testid="agent-save-state" aria-live="polite">
          {saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : saving === "failed" ? "Not saved. Your next change retries." : ""}
        </span>
        <div className="app-head-actions">
          <button className="btn-primary sm" data-testid="agent-system-run" onClick={() => setRunOpen((v) => !v)}>
            Run
          </button>
          <button
            className="btn sm"
            data-testid="agent-system-duplicate"
            onClick={async () => {
              const { id: _id, created_at: _c, updated_at: _u, builder_session: _b, card: _card, ...rest } = system;
              const r = await createAgentSystem({ ...rest, title: `${system.title} (copy)` }).catch(() => null);
              if (r?.ok && r.system) {
                announceAgentSystemsChanged();
                onOpen(r.system.id);
              } else setNotice({ tone: "error", text: "The copy could not be made. Try again in a moment." });
            }}
          >
            Duplicate
          </button>
          <button
            className="btn sm"
            data-testid="agent-system-export"
            title="Save the design as a file to share or keep"
            onClick={async () => setNotice({ tone: "info", text: await exportSystem(system) })}
          >
            Export
          </button>
          <button className="btn sm danger-btn" data-testid="agent-system-delete" onClick={() => setConfirmDel(true)}>
            <Icon name="trash" size={14} /> Delete
          </button>
        </div>
      </div>
      {notice && <InlineNotice text={notice.text} tone={notice.tone} onDismiss={() => setNotice(null)} />}
      {runOpen && (
        <div className="flow-note app-note" data-testid="agent-run-box">
          <div className="flow-note-head">
            <span>
              What should the agents work on?
              <span className="dim"> · Mimi runs the system in a chat and asks you at any review step.</span>
            </span>
            <button className="link" onClick={() => setRunOpen(false)}>
              close
            </button>
          </div>
          <textarea
            autoFocus
            className="tmpl-input tmpl-textarea flow-note-text"
            data-testid="agent-run-input"
            placeholder="e.g. paste the guest's email here"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && runnable) startRun();
            }}
          />
          <div className="flow-note-actions">
            <button
              className="btn-primary sm"
              data-testid="agent-run-go"
              disabled={!input.trim() || !runnable}
              onClick={startRun}
            >
              Run in a chat
            </button>
            {!runnable && <span className="text-[12px] text-faint">Fix what is marked on the diagram first.</span>}
          </div>
        </div>
      )}
      {run && (
        <div className={`ag-run-status run-${run.status}`} data-testid="agent-run-status">
          Last run: {RUN_LABELS[run.status] || run.status.replace(/_/g, " ")}
          {Object.values(run.node_states || {}).includes("waiting_for_person") && " · waiting for your answer in the chat"}
        </div>
      )}
      <div className="ag-stage">
        <AgentCanvas
          system={system}
          problems={problems}
          nodeStates={run?.node_states}
          onSave={(parts) => void save(parts)}
          models={models}
          modelLabels={labels}
          defaultModel={defaultModel}
          codingAgents={codingAgents}
        />
      </div>
      {confirmDel && (
        <ConfirmDialog
          title="Delete this agent system?"
          body={`${system.title} is removed from Agents. Chats that ran it keep their results.`}
          confirmLabel="Delete"
          onCancel={() => setConfirmDel(false)}
          onConfirm={async () => {
            setConfirmDel(false);
            await deleteAgentSystem(system.id).catch(() => {});
            announceAgentSystemsChanged();
            onBack();
          }}
        />
      )}
    </div>
  );
}
