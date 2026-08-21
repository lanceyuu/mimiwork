/** Project page (PROJECTS spec, 2026-08-21) — MimiWork's take on Claude Code's projects.
 *
 * A project IS a real folder. This page is where the folder's identity (emoji + name),
 * its standing instructions (the folder's AGENTS.md, injected into every NEW session as
 * "Project conventions"), what Mimi remembers about it (the workspace-scoped memory the
 * `remember` tool already writes to), and its conversations all live in one place.
 */
import { useEffect, useRef, useState } from "react";
import {
  addMemory,
  deleteMemory,
  getProjectDetail,
  setProjectInstructions,
  updateMemory,
  updateProject,
  type MemoryEntry,
  type ProjectDetail,
} from "../api";
import { openExternal } from "../tauri";
import { Icon } from "./Icon";

const EMOJIS = [
  "📁", "🎓", "📊", "📝", "🧪", "💼", "🎯", "📚",
  "🧠", "✍️", "🔬", "📈", "🗂️", "🎨", "🛠️", "🌱",
  "🏛️", "💡", "🧭", "🗣️", "📣", "🧾", "🗓️", "🚀",
];

function relTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  if (Number.isNaN(t)) return "";
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "yesterday" : `${d}d ago`;
}

export function ProjectView(props: {
  path: string;
  onNewSession: (path: string) => void;
  onSelectSession: (id: string, workspace: string, agent: string) => void;
  /** Metadata changed (name/emoji/pin/archive) — the sidebar band re-reads. */
  onChanged?: () => void;
}) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [text, setText] = useState("");
  const [savedText, setSavedText] = useState("");
  const [saving, setSaving] = useState(false);
  const [newFact, setNewFact] = useState("");
  const [editing, setEditing] = useState<{ id: number; content: string } | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  const load = () =>
    getProjectDetail(props.path)
      .then((d) => {
        if (!d.ok) {
          setError(d.error || "unknown project");
          return;
        }
        setDetail(d);
        setName(d.project.name);
        setText(d.instructions);
        setSavedText(d.instructions);
        setError(null);
      })
      .catch(() => setError("server unreachable"));
  useEffect(() => {
    setDetail(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.path]);

  const patch = async (fields: Parameters<typeof updateProject>[1]) => {
    const r = await updateProject(props.path, fields).catch(() => null);
    if (r?.ok && r.project) {
      setDetail((d) => (d ? { ...d, project: r.project! } : d));
      props.onChanged?.();
    }
  };
  const commitName = () => {
    const next = name.trim();
    if (!detail) return;
    if (!next) {
      setName(detail.project.name);
      return;
    }
    if (next !== detail.project.name) void patch({ name: next });
  };
  const saveInstructions = async () => {
    setSaving(true);
    const r = await setProjectInstructions(props.path, text).catch(() => ({ ok: false }));
    setSaving(false);
    if (r.ok) {
      setSavedText(text.trimEnd());
      setText(text.trimEnd());
      setDetail((d) =>
        d ? { ...d, project: { ...d.project, has_instructions: !!text.trim() } } : d,
      );
      props.onChanged?.();
    }
  };
  const dirty = text.trimEnd() !== savedText.trimEnd();

  const refreshMemory = () =>
    getProjectDetail(props.path).then((d) => d.ok && setDetail((cur) => (cur ? { ...cur, memory: d.memory } : d)));
  const addFact = async () => {
    const content = newFact.trim();
    if (!content) return;
    await addMemory(content, "workspace", props.path).catch(() => null);
    setNewFact("");
    void refreshMemory();
  };
  const saveEdit = async () => {
    if (!editing) return;
    await updateMemory(editing.id, editing.content.trim()).catch(() => null);
    setEditing(null);
    void refreshMemory();
  };
  const removeFact = async (m: MemoryEntry) => {
    await deleteMemory(m.id).catch(() => null);
    void refreshMemory();
  };

  if (error) {
    return (
      <main className="flex-1 min-w-0 flex flex-col bg-paper" data-testid="project-view">
        <div className="p-12 text-center text-faint text-[13px]">{error}</div>
      </main>
    );
  }
  if (!detail) {
    return (
      <main className="flex-1 min-w-0 flex flex-col bg-paper" data-testid="project-view">
        <div className="p-12 text-center text-faint text-[13px]">Loading…</div>
      </main>
    );
  }
  const proj = detail.project;

  return (
    <main className="flex-1 min-w-0 overflow-y-auto bg-paper" data-testid="project-view">
      <div className="max-w-[760px] mx-auto px-8 py-7">
        {/* Identity row: emoji · name · path, then the actions. */}
        <div className="flex items-start gap-3.5">
          <div className="relative shrink-0">
            <button
              className="project-emoji-btn"
              title="Change emoji"
              aria-label="Change emoji"
              data-testid="project-emoji"
              onClick={() => setEmojiOpen((v) => !v)}
            >
              {proj.emoji || <Icon name="folder" size={22} className="text-muted" />}
            </button>
            {emojiOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setEmojiOpen(false)} />
                <div className="project-emoji-pop" role="listbox" data-testid="project-emoji-pop">
                  {EMOJIS.map((e) => (
                    <button
                      key={e}
                      role="option"
                      aria-selected={proj.emoji === e}
                      onClick={() => {
                        setEmojiOpen(false);
                        void patch({ emoji: e });
                      }}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <input
              className="project-name-input"
              value={name}
              aria-label="Project name"
              data-testid="project-name"
              onChange={(e) => setName(e.target.value)}
              onBlur={commitName}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                if (e.key === "Escape") setName(proj.name);
              }}
            />
            <button
              className="mt-1 flex items-center gap-1.5 text-[12px] text-faint hover:text-ink max-w-full"
              title="Open in your file manager"
              onClick={() => openExternal(`file://${proj.path}`)}
              data-testid="project-path"
            >
              <Icon name="folder" size={12} className="shrink-0" />
              <span className="truncate">{proj.path}</span>
              {!proj.exists && <span className="text-danger shrink-0">· folder missing</span>}
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            className="btn btn-primary text-[12.5px] whitespace-nowrap"
            disabled={!proj.exists}
            onClick={() => props.onNewSession(proj.path)}
            data-testid="project-new-session"
          >
            <span className="inline-flex items-center gap-1.5">
              <Icon name="plus" size={13} /> New session here
            </span>
          </button>
          <button
            className="btn text-[12.5px]"
            onClick={() => void patch({ pinned: !proj.pinned })}
            data-testid="project-pin"
          >
            <span className="inline-flex items-center gap-1.5">
              <Icon name="pin" size={13} /> {proj.pinned ? "Unpin" : "Pin"}
            </span>
          </button>
          <button
            className="btn text-[12.5px]"
            onClick={() => void patch({ archived: !proj.archived })}
            data-testid="project-archive"
          >
            <span className="inline-flex items-center gap-1.5">
              <Icon name="archive" size={13} /> {proj.archived ? "Unarchive" : "Archive"}
            </span>
          </button>
          <span className="text-[12px] text-faint ml-auto">
            {proj.sessions} {proj.sessions === 1 ? "conversation" : "conversations"}
            {proj.last_activity ? ` · active ${relTime(proj.last_activity)}` : ""}
          </span>
        </div>

        {/* Instructions — the folder's AGENTS.md. */}
        <section className="mt-8" data-testid="project-instructions">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[14px] font-semibold">Instructions</h2>
            <span className="text-[11.5px] text-faint" title={detail.instructions_file}>
              AGENTS.md in this folder · applies to new conversations
            </span>
          </div>
          <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
            Standing rules for everything Mimi does in this project — tone, sources to trust, files
            never to touch, how to cite. Loaded at the start of every new conversation here.
          </p>
          <textarea
            ref={textRef}
            className="input w-full mt-2.5 min-h-[140px] font-mono text-[12.5px] leading-relaxed"
            placeholder={"e.g.\n- Cite in APA 7.\n- Never modify anything under data/raw/.\n- Drafts go in drafts/, final versions in out/."}
            value={text}
            onChange={(e) => setText(e.target.value)}
            data-testid="project-instructions-text"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              className="btn btn-primary text-[12.5px] whitespace-nowrap"
              disabled={!dirty || saving}
              onClick={saveInstructions}
              data-testid="project-instructions-save"
            >
              {saving ? "Saving…" : "Save instructions"}
            </button>
            {dirty && (
              <button className="btn text-[12.5px]" onClick={() => setText(savedText)}>
                Discard
              </button>
            )}
          </div>
        </section>

        {/* Memory — the workspace-scoped facts. */}
        <section className="mt-8" data-testid="project-memory">
          <h2 className="text-[14px] font-semibold">What Mimi remembers about this project</h2>
          <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
            Facts Mimi saved while working here, plus anything you add. Edits reach new
            conversations; the global memory screen in Settings shows everything across projects.
          </p>
          <div className="mt-2.5 rounded-xl border border-line bg-panel divide-y divide-line">
            {detail.memory.length === 0 && (
              <div className="px-3.5 py-3 text-[12.5px] text-faint">
                Nothing yet — Mimi remembers as she works, or add a fact below.
              </div>
            )}
            {detail.memory.map((m) => (
              <div key={m.id} className="group flex items-start gap-2 px-3.5 py-2.5" data-testid="project-memory-row">
                {editing?.id === m.id ? (
                  <>
                    <input
                      className="input flex-1 text-[12.5px]"
                      value={editing.content}
                      autoFocus
                      onChange={(e) => setEditing({ id: m.id, content: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void saveEdit();
                        if (e.key === "Escape") setEditing(null);
                      }}
                    />
                    <button className="btn text-[12px]" onClick={() => void saveEdit()}>
                      Save
                    </button>
                  </>
                ) : (
                  <>
                    <span className="flex-1 text-[12.5px] leading-relaxed">{m.content}</span>
                    <button
                      className="opacity-0 group-hover:opacity-100 text-faint hover:text-ink"
                      title="Edit"
                      aria-label="Edit memory"
                      onClick={() => setEditing({ id: m.id, content: m.content })}
                    >
                      <Icon name="pencil" size={13} />
                    </button>
                    <button
                      className="opacity-0 group-hover:opacity-100 text-faint hover:text-danger"
                      title="Forget"
                      aria-label="Forget memory"
                      onClick={() => void removeFact(m)}
                    >
                      <Icon name="trash" size={13} />
                    </button>
                  </>
                )}
              </div>
            ))}
            <div className="flex items-center gap-2 px-3.5 py-2.5">
              <input
                className="input flex-1 text-[12.5px]"
                placeholder="Add a fact about this project…"
                value={newFact}
                onChange={(e) => setNewFact(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void addFact()}
                data-testid="project-memory-add"
              />
              <button className="btn text-[12px]" disabled={!newFact.trim()} onClick={() => void addFact()}>
                Add
              </button>
            </div>
          </div>
        </section>

        {/* Conversations in this project. */}
        <section className="mt-8 mb-10" data-testid="project-sessions">
          <h2 className="text-[14px] font-semibold">Conversations</h2>
          <div className="mt-2.5 rounded-xl border border-line bg-panel divide-y divide-line">
            {detail.sessions.length === 0 && (
              <div className="px-3.5 py-3 text-[12.5px] text-faint">
                No conversations here yet — start one with “New session here”.
              </div>
            )}
            {detail.sessions.map((s) => (
              <button
                key={s.session_id}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-paper"
                onClick={() => props.onSelectSession(s.session_id, proj.path, s.agent || "cowork")}
                data-testid="project-session-row"
              >
                <Icon name="chat" size={13} className="shrink-0 text-muted" />
                <span className="flex-1 truncate text-[12.5px]">{s.title || "New session"}</span>
                <span className="text-[11px] text-faint shrink-0">{relTime(s.updated_at)}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
