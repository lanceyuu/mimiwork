/** Project page — a project GROUPS conversations (2026-08-31).
 *
 * It used to be a real folder, and this page was that folder's home: a file browser, the
 * folder's AGENTS.md, the workspace-scoped memory. A group has no folder, so what is left
 * is what a group actually is — a name, an emoji, standing instructions, and the
 * conversations filed under it.
 *
 * The instructions live on the group row in the database rather than in a file: a group
 * has nowhere on disk to put one, and a temp directory would be worse than nowhere
 * because the OS empties it under text somebody typed.
 */
import { useEffect, useState } from "react";
import {
  deleteProject,
  getProjectDetail,
  setProjectInstructions,
  updateProject,
  type ProjectDetail,
} from "../api";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icon";
import { useT } from "../i18n";

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
  projectId: string;
  onSelectSession: (id: string, workspace: string, agent: string) => void;
  /** Name/emoji/pin changed — the sidebar band re-reads. */
  onChanged?: () => void;
  /** The group is gone — the page must close. */
  onDeleted?: (id: string) => void;
}) {
  const t = useT();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [text, setText] = useState("");
  const [savedText, setSavedText] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [alsoSessions, setAlsoSessions] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refresh = () =>
    getProjectDetail(props.projectId)
      .then((d) => {
        if (!d.ok) {
          setError(d.error || "This project no longer exists.");
          return;
        }
        setDetail(d);
        setName(d.project.name);
        setText(d.instructions || "");
        setSavedText(d.instructions || "");
        setError(null);
      })
      .catch(() => setError("Could not load this project."));

  useEffect(() => {
    setDetail(null);
    setError(null);
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.projectId]);

  const patch = async (fields: Parameters<typeof updateProject>[1]) => {
    await updateProject(props.projectId, fields).catch(() => undefined);
    props.onChanged?.();
    void refresh();
  };

  const saveInstructions = async () => {
    setSaving(true);
    try {
      await setProjectInstructions(props.projectId, text);
      setSavedText(text);
      props.onChanged?.();
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <main className="flex-1 min-w-0 overflow-y-auto bg-paper">
        <div className="mx-auto max-w-[760px] px-6 py-8 text-[13px] text-muted">{error}</div>
      </main>
    );
  }
  if (!detail) {
    return (
      <main className="flex-1 min-w-0 overflow-y-auto bg-paper">
        <div className="mx-auto max-w-[760px] px-6 py-8 text-[13px] text-muted">Loading…</div>
      </main>
    );
  }

  const proj = detail.project;
  const dirty = text !== savedText;

  return (
    <main className="flex-1 min-w-0 overflow-y-auto bg-paper">
      <div className="mx-auto max-w-[760px] px-6 py-8">
        {/* Identity */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <button
              className="w-11 h-11 rounded-xl2 border border-line bg-panel text-[20px] leading-none flex items-center justify-center hover:border-lineStrong"
              data-testid="project-emoji"
              title="Choose an icon"
              onClick={() => setEmojiOpen((v) => !v)}
            >
              {proj.emoji || "📁"}
            </button>
            {emojiOpen && (
              <div className="absolute z-20 mt-1.5 p-2 rounded-xl2 border border-line bg-panel shadow-xl grid grid-cols-8 gap-1 w-[280px]">
                {EMOJIS.map((e) => (
                  <button
                    key={e}
                    className="w-8 h-8 rounded-lg hover:bg-paper text-[17px]"
                    onClick={() => {
                      setEmojiOpen(false);
                      void patch({ emoji: e });
                    }}
                  >
                    {e}
                  </button>
                ))}
              </div>
            )}
          </div>
          <input
            className="flex-1 min-w-0 bg-transparent outline-none text-[19px] font-semibold text-ink border-b border-transparent focus:border-line py-0.5"
            value={name}
            data-testid="project-name"
            onChange={(e) => setName(e.target.value)}
            onBlur={() => name.trim() && name !== proj.name && void patch({ name: name.trim() })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
          <button
            className="btn sm"
            title={proj.pinned ? "Unpin" : "Pin to the top"}
            onClick={() => void patch({ pinned: !proj.pinned })}
          >
            <Icon name="pin" size={14} className={proj.pinned ? "text-accent" : "text-faint"} />
          </button>
        </div>

        <div className="mt-1.5 text-[12px] text-faint">
          {proj.sessions} {proj.sessions === 1 ? "conversation" : "conversations"}
          {proj.last_activity ? ` · active ${relTime(proj.last_activity)}` : ""}
        </div>

        {/* Standing instructions */}
        <section className="mt-7">
          <h2 className="text-[13px] font-semibold text-ink">{t("Instructions")}</h2>
          <p className="text-[12px] text-muted mt-1 leading-relaxed">
            {t("Added to every new conversation in this project. Say how you want the work done — the conventions you would otherwise repeat each time.")}
          </p>
          <textarea
            className="mt-2.5 w-full h-[150px] rounded-xl2 border border-line bg-panel p-3 text-[13px] text-ink outline-none focus:border-lineStrong resize-y leading-relaxed"
            value={text}
            data-testid="project-instructions"
            placeholder={t("e.g. Always cite the transcript line number. Write in British English.")}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              className="btn sm accent-btn"
              disabled={!dirty || saving}
              data-testid="project-instructions-save"
              onClick={() => void saveInstructions()}
            >
              {saving ? t("Saving…") : t("Save")}
            </button>
            {dirty && <span className="text-[12px] text-faint">{t("Unsaved changes")}</span>}
          </div>
        </section>

        {/* Its conversations */}
        <section className="mt-8">
          <h2 className="text-[13px] font-semibold text-ink mb-2">{t("Conversations")}</h2>
          {detail.sessions.length === 0 ? (
            <p className="text-[12.5px] text-muted">
              {t("Nothing filed here yet — drag a conversation onto this project in the sidebar.")}
            </p>
          ) : (
            <div className="rounded-xl2 border border-line bg-panel overflow-hidden">
              {detail.sessions.map((s) => (
                <button
                  key={s.session_id}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-paper border-b border-line last:border-b-0"
                  data-testid="project-session"
                  onClick={() => props.onSelectSession(s.session_id, s.workspace, s.agent)}
                >
                  <Icon name="chat" size={14} className="text-faint shrink-0" />
                  <span className="flex-1 min-w-0 truncate text-[13px] text-ink">
                    {s.title || "New session"}
                  </span>
                  <span className="text-[11.5px] text-faint shrink-0">{relTime(s.updated_at)}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Delete */}
        <section className="mt-9 pt-5 border-t border-line">
          <button
            className="btn sm danger-btn"
            data-testid="project-delete"
            onClick={() => {
              setAlsoSessions(false);
              setDeleteError(null);
              setConfirmDelete(true);
            }}
          >
            <Icon name="trash" size={13} /> {t("Delete project")}
          </button>
          {deleteError && (
            <div className="mt-2 text-[12px] text-danger" data-testid="project-delete-error">
              {deleteError}
            </div>
          )}
        </section>

        {confirmDelete && (
          <ConfirmDialog
            title={`${t("Delete")} “${proj.name}”?`}
            body={
              proj.sessions === 0
                ? t("This project is empty, so nothing else goes with it.")
                : alsoSessions
                  ? `${t("Its")} ${proj.sessions} ${proj.sessions === 1 ? t("conversation is deleted too.") : t("conversations are deleted too.")} ${t("Files they wrote to your folders stay where they are.")}`
                  : `${t("Its")} ${proj.sessions} ${proj.sessions === 1 ? t("conversation returns") : t("conversations return")} ${t("to the main list — nothing is deleted.")}`
            }
            confirmLabel={alsoSessions ? t("Delete project and conversations") : t("Delete project")}
            onCancel={() => setConfirmDelete(false)}
            onConfirm={async () => {
              const out = await deleteProject(props.projectId, {
                deleteSessions: alsoSessions,
              }).catch(() => ({ ok: false, error: "Delete failed." }));
              setConfirmDelete(false);
              if (!out.ok) {
                setDeleteError(out.error || "Delete failed.");
                return;
              }
              props.onDeleted?.(props.projectId);
            }}
          >
            {proj.sessions > 0 && (
              <label className="mt-2.5 flex items-center gap-2 text-[12.5px] text-ink">
                <input
                  type="checkbox"
                  checked={alsoSessions}
                  data-testid="project-delete-sessions"
                  onChange={(e) => setAlsoSessions(e.target.checked)}
                />
                {t("Also delete its conversations")}
              </label>
            )}
          </ConfirmDialog>
        )}
      </div>
    </main>
  );
}
