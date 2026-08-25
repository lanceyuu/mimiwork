import { useEffect, useState } from "react";
import { AutomationFlow } from "./AutomationFlow";
import {
  createAutomation,
  getSettings,
  deleteAutomation,
  exportBlueprint,
  listBuiltinBlueprints,
  getAutomation,
  getAutomations,
  markAutomationSeen,
  announceAutomationsChanged,
  updateAutomation,
  type Automation,
  type AutomationRun,
  type Blueprint,
} from "../api";
import { Icon } from "./Icon";
import { PanelHead } from "./IntegrationsView";
import { SelectMenu } from "./SelectMenu";
import { AutomationQuickstart } from "./AutomationQuickstart";

// Shared utility strings (the §28 page shell — mirrors IntegrationsView's constants).
const CARD = "rounded-xl2 border border-line bg-panel";

// Parse a simple "min hour * * dow" cron back into the time + frequency the editor uses.
// Falls back to 09:00 / daily for anything it doesn't recognize (e.g. agent-written crons).
function fromCron(cron?: string | null): { time: string; freq: string } {
  const parts = (cron || "").trim().split(/\s+/);
  if (parts.length !== 5) return { time: "09:00", freq: "daily" };
  const [m, h, , , dow] = parts;
  const hh = String(Math.min(23, Math.max(0, parseInt(h, 10) || 9))).padStart(2, "0");
  const mm = String(Math.min(59, Math.max(0, parseInt(m, 10) || 0))).padStart(2, "0");
  const freq = dow === "1-5" ? "weekdays" : dow === "0,6" || dow === "6,0" ? "weekends" : "daily";
  return { time: `${hh}:${mm}`, freq };
}

const fmt = (t: number | null) =>
  t ? new Date(t * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

// Map a simple time-of-day + frequency selection to a 5-field cron string.
function toCron(time: string, freq: string): string {
  const [h, m] = (time || "09:00").split(":").map((x) => parseInt(x, 10) || 0);
  const dow = freq === "weekdays" ? "1-5" : freq === "weekends" ? "0,6" : "*";
  return `${m} ${h} * * ${dow}`;
}

// The §28 page shell: full-bleed main, centered ≤4xl column — same as Connectors/Activity/Inbox.
// The three permission levels, in the composer's own words — what you learned in
// a session is what an automation means. The difference: nobody is watching at
// 7am, so "ask" parks its question in the Inbox and the run waits there.
const MODES: { value: string; label: string; hint: string }[] = [
  { value: "interactive", label: "Ask for approval", hint: "Parks the question in your Inbox and waits." },
  { value: "auto", label: "Full access", hint: "Runs everything without asking." },
  { value: "plan", label: "Plan only", hint: "Proposes what it would do; never acts." },
];

export function modeLabel(mode?: string): string {
  return MODES.find((m) => m.value === (mode || "interactive"))?.label ?? "Ask for approval";
}

/** The model + permission pair, as two selects. Shared by the create form and the
 * detail's edit mode so an automation reads the same way in both. */
function RunSettings({
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

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1 min-w-0 flex bg-paper">
      <div className="flex-1 min-w-0 overflow-y-auto hairline-scroll">
        <div className="max-w-4xl mx-auto px-7 py-6">{children}</div>
      </div>
    </main>
  );
}

interface Props {
  // `task` gives the opened run session its context (banner + "Back to runs"; owner ask 2026-07-04).
  onOpenRun: (
    sessionId: string,
    workspace: string,
    agent: string,
    task?: { id: string; title: string },
  ) => void;
  onRunNow: (taskId: string, title?: string) => void;
  // Open directly on a task's detail (set by the run banner's "Back to runs").
  initialOpenId?: string | null;
}

export function ScheduledView({ onOpenRun, onRunNow, initialOpenId }: Props) {
  const [tasks, setTasks] = useState<Automation[]>([]);
  const [openId, setOpenId] = useState<string | null>(initialOpenId ?? null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  // A parsed .mimiflow.json waiting in the creation form (import flow).
  const [prefill, setPrefill] = useState<Blueprint | null>(null);
  // Starter blueprints bundled with the app — one click prefills the review form.
  const [starters, setStarters] = useState<{ name: string; blueprint: Blueprint }[]>([]);
  // The model menu an automation can pin, from the same settings the composer reads.
  const [models, setModels] = useState<string[]>([]);
  const [defaultModel, setDefaultModel] = useState<string>("");
  useEffect(() => {
    listBuiltinBlueprints().then((l) => setStarters(Array.isArray(l) ? l : [])).catch(() => {});
  }, []);

  // The sidebar's Scheduled band can retarget an ALREADY-open Automations surface —
  // initial state alone would ignore the change (UX-023).
  useEffect(() => {
    if (initialOpenId) setOpenId(initialOpenId);
  }, [initialOpenId]);

  const refresh = () => getAutomations().then(setTasks).catch(() => setTasks([]));
  useEffect(() => {
    refresh();
    const h = setInterval(refresh, 5000);
    return () => clearInterval(h);
  }, []);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setModels(s.models || []);
        setDefaultModel(s.model || "");
      })
      .catch(() => setModels([]));
  }, []);

  // Create from a payload, refresh the list, and open the new task's detail. `permissions`
  // rides through for quickstart recipes (§25 write grants).
  const create = async (payload: {
    title: string;
    instructions: string;
    cron?: string;
    permissions?: { tool: string; target: string; access: "read" | "write" }[];
    workspace?: string;
    files?: { name: string; data_b64: string }[];
    model?: string;
    mode?: string;
  }) => {
    setBusy(payload.title);
    try {
      const res = await createAutomation(payload);
      announceAutomationsChanged(); // new entry shows in the sidebar band right away
      await refresh();
      if (res.ok && res.task) {
        setShowForm(false);
        setOpenId(res.task.id);
      } else if (res.error) {
        alert(res.error);
      }
    } finally {
      setBusy(null);
    }
  };

  if (openId) {
    return (
      <TaskDetail
        id={openId}
        onBack={() => { setOpenId(null); refresh(); }}
        onOpenRun={onOpenRun}
        onRunNow={onRunNow}
        models={models}
        defaultModel={defaultModel}
      />
    );
  }

  const empty = tasks.length === 0;

  return (
    <Shell>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <PanelHead title="Automations" sub="Recurring tasks MimiWork runs on a schedule." />
        </div>
        <label
          className="text-[12.5px] px-3 py-1.5 rounded-lg border border-line bg-panel hover:border-lineStrong shrink-0 cursor-pointer"
          title="Import a shared .mimiflow.json blueprint — you review everything before it's created"
        >
          Import blueprint
          <input
            type="file"
            accept=".json,.mimiflow.json,application/json"
            className="hidden"
            data-testid="import-blueprint"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              try {
                const bp = JSON.parse(await file.text()) as Blueprint;
                if (!bp || bp.mimiwork_blueprint !== 1 || !bp.title || !bp.instructions) {
                  alert("That file isn't a MimiWork blueprint.");
                  return;
                }
                setPrefill(bp);
                setShowForm(true);
              } catch {
                alert("Could not read that file as JSON.");
              }
            }}
          />
        </label>
        {starters.length > 0 && (
          <div className="relative shrink-0" data-testid="starter-blueprints">
            <SelectMenu
              ariaLabel="Starter blueprints"
              value="__starters"
              options={[
                { value: "__starters", label: "Starter blueprints" },
                ...starters.map((s) => ({
                  value: s.name,
                  label: s.blueprint.title,
                  sub: "Prefills the form — review, then create",
                })),
              ]}
              onChange={(v) => {
                const hit = starters.find((s) => s.name === v);
                if (!hit) return;
                setPrefill(hit.blueprint);
                setShowForm(true);
              }}
            />
          </div>
        )}
        <button
          className="text-[12.5px] px-3 py-1.5 rounded-lg border border-lineStrong bg-panel hover:border-accent hover:text-accent shrink-0"
          onClick={() => setShowForm((v) => !v)}
        >
          + New automation
        </button>
      </div>

      <div className="text-[12px] text-faint flex gap-1.5 mb-4">
        <span aria-hidden>ⓘ</span>
        <span>
          Runs only while openworker-server is up — a missed schedule catches up once when it next
          starts.
        </span>
      </div>

      {showForm && (
        <NewAutomationForm
          key={prefill ? `bp-${prefill.title}` : "blank"}
          busy={busy !== null}
          initial={prefill}
          models={models}
          defaultModel={defaultModel}
          onCancel={() => {
            setShowForm(false);
            setPrefill(null);
          }}
          onCreate={async (p) => {
            await create(p);
            setPrefill(null);
          }}
        />
      )}

      {/* The quickstart (§29): ONE template system — role recipes + generic templates, each
          card with §27 connector dots; picking one expands the configure card. */}
      {(empty || showForm) && <AutomationQuickstart busy={busy !== null} onCreate={create} />}

      {empty ? (
        !showForm && (
          <div className={CARD + " p-4 text-[12.5px] text-muted"}>
            No scheduled tasks yet — use a template above, click <strong>+ New automation</strong>,
            or just ask MimiWork in a session.
          </div>
        )
      ) : (
        <div className="flex flex-col gap-2.5">
          {tasks.map((t) => (
            <div
              className={CARD + " sched-card px-4 py-3 cursor-pointer hover:border-lineStrong transition-colors"}
              key={t.id}
              onClick={() => setOpenId(t.id)}
            >
              <div className="flex items-center justify-between gap-2.5 mb-1">
                <span className="text-[13.5px] font-semibold truncate">{t.title}</span>
                <button
                  className="sched-card-del"
                  title="Delete automation"
                  aria-label={`Delete ${t.title}`}
                  onClick={async (e) => {
                    e.stopPropagation();
                    await deleteAutomation(t.id);
                    refresh();
                  }}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
              <div className="flex items-center gap-1.5 text-[12px] text-muted">
                <Icon name="clock" size={13} className="text-faint shrink-0" />
                {t.enabled ? t.schedule : "Paused"} · next {fmt(t.next_run)} · {t.run_count} run{t.run_count === 1 ? "" : "s"}
                {t.last_status ? ` · last ${t.last_status}` : ""}
              </div>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}

async function fileToB64(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

// Node id → which part of the form it edits, for the click-to-edit flow preview.
const NODE_HINTS: Record<string, string> = {
  trigger: "Schedule — when this runs",
  agent: "Where it works — the folder and files it can use",
  ask: "Approvals — it asks before consequential steps",
  output: "Where the result lands",
};

function NewAutomationForm({
  busy,
  onCancel,
  onCreate,
  initial,
  models,
  defaultModel,
}: {
  busy: boolean;
  models: string[];
  defaultModel?: string;
  onCancel: () => void;
  onCreate: (p: {
    title: string;
    instructions: string;
    cron?: string;
    workspace?: string;
    files?: { name: string; data_b64: string }[];
    permissions?: { tool: string; target: string; access: "read" | "write" }[];
    model?: string;
    mode?: string;
  }) => void;
  // A blueprint being imported: prefills every field; the user reviews (grants
  // shown below) and the Create click IS the consent (§25).
  initial?: Blueprint | null;
}) {
  const initialSched = fromCron(initial?.schedule?.cron);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [instructions, setInstructions] = useState(initial?.instructions ?? "");
  const [time, setTime] = useState(initial ? initialSched.time : "09:00");
  const [freq, setFreq] = useState(initial ? initialSched.freq : "daily");
  const grants = initial?.permissions ?? [];
  const [folder, setFolder] = useState<string>("");
  const [files, setFiles] = useState<File[]>([]);
  const [model, setModel] = useState<string>("");
  // Default to asking: an unattended task that can do anything is a decision, not
  // a default.
  const [mode, setMode] = useState<string>("interactive");
  // Revision notes attached to flow nodes — folded into the instructions on create,
  // so "check the flowchart, annotate what to change" is part of the request itself.
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [activeNode, setActiveNode] = useState<string | null>(null);

  const valid = title.trim() && instructions.trim();

  // A draft task so the live flowchart mirrors the form as it's filled in.
  const draft = {
    id: "draft",
    title: title || "New automation",
    enabled: true,
    schedule: `${freq} at ${time}`,
    agent: "cowork",
    workspace: folder,
    always_allowed: [],
    notify_on_completion: true,
    last_status: null,
  } as unknown as Automation;

  const notedNodes = new Set(Object.keys(notes).filter((k) => notes[k]?.trim()));

  const submit = async () => {
    const noteLines = Object.entries(notes)
      .filter(([, v]) => v.trim())
      .map(([k, v]) => `- ${NODE_HINTS[k] ?? k}: ${v.trim()}`);
    onCreate({
      title: title.trim(),
      instructions:
        instructions.trim() +
        (noteLines.length ? `\n\nRevision notes from the flow review:\n${noteLines.join("\n")}` : ""),
      cron: toCron(time, freq),
      ...(model ? { model } : {}),
      mode,
      ...(grants.length ? { permissions: grants } : {}),
      ...(folder ? { workspace: folder } : {}),
      ...(files.length
        ? {
            files: await Promise.all(
              files.map(async (f) => ({ name: f.name, data_b64: await fileToB64(f) })),
            ),
          }
        : {}),
    });
  };

  return (
    <div className={CARD + " tmpl-form p-4 mb-4"} data-testid="new-automation-form">
      <div className="text-[11px] uppercase tracking-[0.05em] text-faint mb-2.5">
        {initial ? "Import blueprint — review, then create" : "New automation"}
      </div>
      {grants.length > 0 && (
        <div
          className="mb-2.5 rounded-lg border border-line bg-paper px-3 py-2 text-[12px]"
          data-testid="blueprint-grants"
        >
          <span className="font-medium">This blueprint asks for standing permissions: </span>
          {grants.map((g, i) => (
            <span key={i} className="text-muted">
              {g.tool} → {g.target}
              {i < grants.length - 1 ? ", " : ""}
            </span>
          ))}
          <span className="text-muted"> — creating the automation grants them.</span>
        </div>
      )}
      <input
        className="tmpl-input"
        placeholder="Title (e.g. Daily standup notes)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="tmpl-input tmpl-textarea"
        placeholder="What should it do each run? (e.g. Summarize today's calendar and open tasks.)"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
      />
      <div className="tmpl-sched">
        <label className="tmpl-field">
          <span>At</span>
          <input
            type="time"
            className="tmpl-input tmpl-time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            data-testid="auto-time"
          />
        </label>
        <label className="tmpl-field">
          <span>Repeat</span>
          <select
            className="tmpl-input tmpl-select"
            value={freq}
            onChange={(e) => setFreq(e.target.value)}
          >
            <option value="daily">Every day</option>
            <option value="weekdays">Weekdays</option>
            <option value="weekends">Weekends</option>
          </select>
        </label>
      </div>

      <RunSettings
        model={model}
        mode={mode}
        models={models}
        defaultModel={defaultModel}
        onModel={setModel}
        onMode={setMode}
      />

      {/* Folder + files: run against real material, not an empty scratch dir. */}
      <div className="flex flex-wrap items-center gap-2 mt-2.5 text-[12.5px]">
        <span className="text-muted">Works in:</span>
        <button
          className="px-2.5 py-1 rounded-lg border border-line bg-paper hover:border-lineStrong"
          data-testid="auto-pick-folder"
          onClick={async () => {
            const { chooseFolder } = await import("../tauri");
            const picked = await chooseFolder();
            if (picked) setFolder(picked);
          }}
        >
          {folder ? folder.split("/").filter(Boolean).slice(-1)[0] : "Choose folder…"}
        </button>
        {folder ? (
          <button className="link" onClick={() => setFolder("")}>
            use a fresh folder instead
          </button>
        ) : (
          <span className="text-faint">(otherwise it gets its own fresh folder)</span>
        )}
        <label className="px-2.5 py-1 rounded-lg border border-line bg-paper hover:border-lineStrong cursor-pointer">
          + Attach files
          <input
            type="file"
            multiple
            className="hidden"
            data-testid="auto-files"
            onChange={(e) => {
              setFiles((prev) => [...prev, ...Array.from(e.target.files ?? [])].slice(0, 10));
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {files.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {files.map((f, i) => (
            <span
              key={`${f.name}-${i}`}
              className="text-[11.5px] px-2 py-0.5 rounded-full border border-line bg-paper text-muted"
            >
              {f.name}{" "}
              <button className="link" onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Live flow preview: what will actually happen, as a pipeline. Click a node to
          see what it means and leave a revision note — notes travel with the request. */}
      <div className="mt-3">
        <div className="text-[11px] uppercase tracking-[0.05em] text-faint mb-1.5">
          Flow preview — click a step to annotate it
        </div>
        <AutomationFlow
          task={draft}
          onNodeClick={(id) => setActiveNode(activeNode === id ? null : id)}
          notedNodes={notedNodes}
        />
        {activeNode && (
          <div className="mt-1.5 flex items-start gap-2" data-testid="auto-node-note">
            <div className="text-[12px] text-muted pt-1.5 shrink-0">
              {NODE_HINTS[activeNode] ?? activeNode}:
            </div>
            <input
              className="tmpl-input flex-1"
              placeholder="Revision note (e.g. skip weekends when I'm traveling; keep reports under one page)"
              value={notes[activeNode] ?? ""}
              autoFocus
              onChange={(e) => setNotes({ ...notes, [activeNode]: e.target.value })}
            />
          </div>
        )}
      </div>

      <div className="tmpl-form-actions">
        <button className="btn-primary sm" disabled={!valid || busy} onClick={submit}>
          {busy ? "Creating…" : "Create automation"}
        </button>
        <button className="link" onClick={onCancel}>cancel</button>
      </div>
    </div>
  );
}

function TaskDetail({
  id,
  onBack,
  onOpenRun,
  onRunNow,
  models,
  defaultModel,
}: {
  id: string;
  models: string[];
  defaultModel?: string;
  onBack: () => void;
  onOpenRun: (
    sessionId: string,
    workspace: string,
    agent: string,
    task?: { id: string; title: string },
  ) => void;
  onRunNow: (taskId: string, title?: string) => void;
}) {
  const [task, setTask] = useState<Automation | null>(null);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [time, setTime] = useState("09:00");
  const [freq, setFreq] = useState("daily");
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("interactive");
  const [saving, setSaving] = useState(false);

  // The seen mark AS OF opening — the "new" pills compare against this frozen value
  // while mark-seen advances the stored one (badge clears; highlights survive).
  const [seenMark, setSeenMark] = useState<number | null>(null);

  const refresh = () =>
    getAutomation(id)
      .then((d) => {
        if (!d.task) {
          // Deleted (or a stale reopen target): "Loading…" forever is a trap —
          // fall back to the overview (owner-hit 2026-07-20).
          onBack();
          return;
        }
        setTask(d.task);
        setRuns(d.runs || []);
        setSeenMark((cur) => (cur === null ? d.task?.seen_runs_at ?? 0 : cur));
      })
      .catch(() => {});
  useEffect(() => {
    setSeenMark(null);
    refresh();
    // Opening the detail IS reading it: advance the seen mark and nudge the
    // sidebar so the badge clears immediately (UX-023).
    markAutomationSeen(id)
      .then(() => announceAutomationsChanged())
      .catch(() => {});
  }, [id]);

  if (!task)
    return (
      <Shell>
        <div className="text-[13px] text-muted">Loading…</div>
      </Shell>
    );

  const startEdit = () => {
    setTitle(task.title);
    setInstructions(task.instructions);
    const { time: t, freq: f } = fromCron(task.schedule_raw?.cron);
    setTime(t);
    setFreq(f);
    setModel(task.model ?? "");
    setMode(task.mode ?? "interactive");
    setEditing(true);
  };
  const saveEdit = async () => {
    setSaving(true);
    try {
      await updateAutomation(id, {
        title: title.trim(),
        instructions: instructions.trim(),
        cron: toCron(time, freq),
        // "" clears the pin and puts the automation back on the app default.
        model,
        mode,
      });
      await refresh();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };
  const toggle = async () => {
    await updateAutomation(id, { enabled: !task.enabled });
    refresh();
  };
  const remove = async () => {
    await deleteAutomation(id);
    announceAutomationsChanged(); // the sidebar band must not wait out its poll
    onBack();
  };

  return (
    <Shell>
      <button className="text-[13px] text-muted hover:text-ink mb-3" onClick={onBack}>
        ← Automations
      </button>
      <div className="sched-detail">
        <div className="sched-detail-head">
          {editing ? (
            <input
              className="tmpl-input sched-edit-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title"
            />
          ) : (
            <h2 className="text-[18px] font-semibold tracking-tight">{task.title}</h2>
          )}
          <div className="sched-actions">
            {editing ? (
              <>
                <button className="btn-primary sm" disabled={saving || !title.trim() || !instructions.trim()} onClick={saveEdit}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="link" onClick={() => setEditing(false)}>cancel</button>
              </>
            ) : (
              <>
                <button className="btn-primary sm" onClick={() => onRunNow(id, task.title)}>
                  ▶ Run now
                </button>
                <button
                  className="btn sm"
                  data-testid="share-blueprint"
                  title="Save this automation's design as a shareable .mimiflow.json file"
                  onClick={async () => {
                    const res = await exportBlueprint(id);
                    alert(
                      res.ok
                        ? `Blueprint saved to ${res.path}\n\nShare the file — anyone can import it from Automations → Import blueprint.`
                        : res.error || "Export failed.",
                    );
                  }}
                >
                  Share blueprint
                </button>
                <button className="btn sm" onClick={startEdit}>Edit</button>
                <button className="btn sm danger-btn" onClick={remove}>
                  <Icon name="trash" size={14} /> Delete
                </button>
              </>
            )}
          </div>
        </div>

        {editing ? (
          <div className="tmpl-sched sched-edit-sched">
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
            <RunSettings
              model={model}
              mode={mode}
              models={models}
              defaultModel={defaultModel}
              onModel={setModel}
              onMode={setMode}
            />
          </div>
        ) : (
          <div className="conn-meta">
            <label className="switch">
              <input type="checkbox" checked={task.enabled} onChange={toggle} />
              <span className="slider" />
            </label>{" "}
            {task.enabled ? `Active · next ${fmt(task.next_run)}` : "Paused"} · {task.schedule}
            <span data-testid="task-run-settings">
              {" · "}
              {task.model || "default model"} · {modeLabel(task.mode)}
            </span>
          </div>
        )}

        {!editing && <AutomationFlow task={task} running={task.last_status === "running"} />}

        <div className="sa-sub">Instructions</div>
        {editing ? (
          <textarea
            className="tmpl-input tmpl-textarea sched-edit-instr"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        ) : (
          <div className="sched-instructions">{task.instructions}</div>
        )}

        {(task.always_allowed || []).length > 0 && (
          <>
            <div className="sa-sub">Allowed without asking</div>
            <div className="dim" style={{ marginBottom: 8, fontSize: 12.5 }}>
              Standing approvals this automation may use — everything else still asks first.
            </div>
            <div className="sched-grants" data-testid="task-grants">
              {(task.always_allowed || []).map((rule) => (
                <div className="sched-grant" key={rule.entry}>
                  <span className="sched-grant-rule">
                    <code>{rule.tool}</code>
                    {rule.target && <span className="sched-grant-target"> → {rule.target}</span>}
                  </span>
                  <button
                    className="link"
                    title="This automation will ask for approval again"
                    onClick={async () => {
                      await updateAutomation(id, { revoke: rule.entry });
                      refresh();
                    }}
                  >
                    Revoke
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="sa-sub">Runs</div>
        <div className="dim" style={{ marginBottom: 8, fontSize: 12.5 }}>
          Each run is a live conversation — open one to see what the agent did and ask a follow-up.
        </div>
        {runs.length === 0 && <div className="dim">No runs yet.</div>}
        {runs.map((r) => (
          <div
            className="sched-run open"
            key={r.run_id}
            onClick={() =>
              r.session_id &&
              onOpenRun(r.session_id, task.workspace, task.agent, {
                id: task.id,
                title: task.title,
              })
            }
            title="Open this run's conversation"
          >
            <div className="sched-run-row">
              <span>
                {seenMark !== null && r.started_at > seenMark && (
                  <span className="run-new-pill" data-testid="run-new">new</span>
                )}
                {fmt(r.started_at)} · <span className={"run-" + r.status}>{r.status}</span> · {r.trigger}
                {r.artifacts.length > 0 && <span className="dim"> · {r.artifacts.length} file(s)</span>}
              </span>
              <span className="sched-run-go" aria-hidden>
                Open ›
              </span>
            </div>
            {r.result_text && <div className="sched-run-peek">{r.result_text}</div>}
            {r.error && <div className="mcp-error">{r.error}</div>}
          </div>
        ))}
      </div>
    </Shell>
  );
}
