import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
// Emits the asset URL only; the worker itself loads lazily with the pdfjs chunk.
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  getArtifacts,
  getRecoveryPoints,
  readArtifact,
  revealArtifact,
  restoreRecoveryPoint,
  type ArtifactContent,
  type ArtifactInfo,
  type RecoveryPoint,
} from "../api";
import type { TodoItem } from "../types";
import { clockTime } from "../time";
import { useT } from "../i18n";
import { AccessSection } from "./AccessSection";
import { Icon } from "./Icon";
import { AppFrame, AskLog, type AskEntry } from "./AppFrame";
import { APPS_CHANGED, commentArtifact, getApp, getApps, revertApp, type MimiApp } from "../api";
import { Markdown, OPEN_ARTIFACT_EVENT, REVEAL_ARTIFACT_EVENT } from "./Markdown";

type Panel = "progress" | "artifacts" | "recovery";

// Quiet file-type icons for the artifact list (the colored kind pills read as noisy).
function kindIcon(kind: string): "file" | "fileCode" | "image" | "table" {
  if (kind === "image") return "image";
  if (kind === "html" || kind === "code") return "fileCode";
  if (kind === "csv" || kind === "sheet") return "table";
  return "file"; // markdown, text, pdf, everything else
}

// Word/Excel/PowerPoint have no in-app renderer, so an artifact: link to one goes straight
// to the app that owns it — "open the file" should open the file (owner ask 2026-08-24).
// Word, PowerPoint and Excel preview in the app since 2026-09-02 (office_preview.py, SheetJS);
// only the legacy binary formats still go straight to the OS.
const OPENS_ELSEWHERE = new Set(["doc", "docm", "xls", "xlsm", "ppt", "pptm"]);

// Fallback kind for an artifact: link whose path isn't in the list (yet) — mirrors the
// server's extension mapping closely enough for the viewer to pick a renderer.
function kindFromPath(path: string): string {
  const ext = (path.split(".").pop() || "").toLowerCase();
  if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext)) return "image";
  if (["html", "htm"].includes(ext)) return "html";
  if (ext === "md") return "markdown";
  if (ext === "csv") return "csv";
  if (ext === "pdf") return "pdf";
  if (["py", "js", "ts", "tsx", "jsx", "json", "sh", "css"].includes(ext)) return "code";
  return "text";
}

interface Props {
  active: boolean;
  sessionId: string;
  refreshKey: number;
  toolNames: string[];
  todo: TodoItem[];
  running: boolean;
  // Fires when a full artifact preview opens/closes, so the app can auto-collapse the left nav
  // to give the preview (PDF/webpage/sheet) more room (#3).
  onPreviewChange?: (open: boolean) => void;
  // §32: the rail is the ONE session panel for every non-chat persona. Artifacts stays
  // cowork-only (deliverables; code-family gets "Files" later — slot reserved); the Access
  // section (the former Session-settings drawer) renders for all.
  showArtifacts?: boolean;
  personaId?: string;
  projectScoped?: boolean;
  workspace?: string;
  branch?: string | null;
  scratchPrimary?: boolean;
  openAccessKey?: number;
  onOpenIntegrations?: () => void;
  // Feedback on a produced file goes to the conversation as a message — Mimi already
  // knows the file, so "make the background white" is all it takes (owner ask 2026-09-02).
  onFeedback?: (text: string) => void;
  // Building an app in this conversation: the rail shows it running beside the chat,
  // Coze-style, and reloads whenever Mimi saves. Open the app's own page from here.
  onOpenApp?: (id: string) => void;
}

export function RightRail({
  active,
  sessionId,
  refreshKey,
  toolNames,
  todo,
  running,
  onPreviewChange,
  showArtifacts = true,
  personaId,
  projectScoped,
  workspace,
  branch,
  scratchPrimary,
  openAccessKey = 0,
  onOpenIntegrations,
  onFeedback,
  onOpenApp,
}: Props) {
  const t = useT();
  const [open, setOpen] = useState<Record<Panel, boolean>>({
    progress: true,
    artifacts: true,
    recovery: true,
  });
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
  const [recoveryPoints, setRecoveryPoints] = useState<RecoveryPoint[]>([]);
  const [recoveryError, setRecoveryError] = useState("");
  const [restoring, setRestoring] = useState(false);
  const [selected, setSelected] = useState<ArtifactInfo | null>(null);

  // The app this conversation is building, if any: the one whose builder_session is us.
  // Polled like the artifacts list (Mimi saves from a tool call the GUI never sees) and
  // nudged by APPS_CHANGED; the frame reloads when the file's updated_at moves.
  const [builderApp, setBuilderApp] = useState<MimiApp | null>(null);
  const [builderHtml, setBuilderHtml] = useState("");
  const [showBuilder, setShowBuilder] = useState(true);
  const [builderAsks, setBuilderAsks] = useState<AskEntry[]>([]);
  useEffect(() => {
    if (!active || !sessionId) return;
    let dead = false;
    const load = () =>
      getApps()
        .then((list) => {
          if (dead) return;
          const mine = list.find((a) => a.builder_session === sessionId) || null;
          setBuilderApp((cur) => (cur && mine && cur.updated_at === mine.updated_at && cur.id === mine.id ? cur : mine));
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 4000);
    window.addEventListener(APPS_CHANGED, load);
    return () => {
      dead = true;
      clearInterval(t);
      window.removeEventListener(APPS_CHANGED, load);
    };
  }, [active, sessionId, refreshKey]);
  useEffect(() => {
    if (!builderApp) {
      setBuilderHtml("");
      return;
    }
    getApp(builderApp.id)
      .then((d) => setBuilderHtml(d.ok ? d.html ?? "" : ""))
      .catch(() => {});
  }, [builderApp?.id, builderApp?.updated_at]);
  useEffect(() => {
    setShowBuilder(true);
    setBuilderAsks([]);
  }, [sessionId]);
  const builderVisible = !!builderApp && showBuilder && !selected;

  // Opening an artifact is ONE decision, made here: a legacy Office binary has no in-app
  // preview, so it goes to the OS; everything else opens the viewer. This used to
  // be decided in two places — the artifact: chip in the transcript knew the rule, the
  // Artifacts list did not — so clicking a .docx Mimi had just written selected a file
  // the viewer could not render and the click looked dead (owner report 2026-08-30).
  const openArtifact = useCallback(
    (a: ArtifactInfo) => {
      const ext = (a.path.split(".").pop() || "").toLowerCase();
      if (OPENS_ELSEWHERE.has(ext)) {
        void revealArtifact(sessionId, a.path, "open");
        return;
      }
      setSelected(a);
    },
    [sessionId],
  );
  const [content, setContent] = useState<ArtifactContent | null>(null);

  const refreshArtifacts = () => getArtifacts(sessionId).then(setArtifacts).catch(() => setArtifacts([]));
  const refreshRecovery = () => getRecoveryPoints(sessionId).then(setRecoveryPoints).catch(() => setRecoveryPoints([]));

  useEffect(() => {
    if (!active) return;
    if (showArtifacts) {
      refreshArtifacts();
      refreshRecovery();
    }
  }, [active, sessionId, refreshKey, showArtifacts]);

  // Switching conversations closes any open artifact — it belongs to the previous session's
  // workspace, which the new session can't (and shouldn't) read.
  useEffect(() => {
    setSelected(null);
    setContent(null);
    setRecoveryError("");
  }, [sessionId]);

  const latestRecovery = recoveryPoints.find((point) => !point.restored_at);

  const undoLatestTurn = async () => {
    if (!latestRecovery || restoring || running) return;
    const names = latestRecovery.files.map((file) => file.name).join(", ");
    if (!window.confirm(`${t("Undo Mimi's latest file changes?")}\n\n${names}`)) return;
    setRestoring(true);
    setRecoveryError("");
    try {
      const result = await restoreRecoveryPoint(sessionId, latestRecovery.id);
      if (!result.ok) {
        setRecoveryError(result.error || t("Files could not be restored."));
        return;
      }
      await Promise.all([refreshArtifacts(), refreshRecovery()]);
    } catch {
      setRecoveryError(t("Files could not be restored."));
    } finally {
      setRestoring(false);
    }
  };

  useEffect(() => {
    setContent(null);
    if (!selected) return;
    readArtifact(sessionId, selected.path).then(setContent).catch(() => setContent(null));
  }, [selected?.path, sessionId]);

  // Notify the app when a preview opens/closes (drives the left-nav auto-collapse).
  // The builder's app preview is a preview too: it wants the width.
  useEffect(() => {
    onPreviewChange?.(!!selected || builderVisible);
  }, [!!selected, builderVisible, onPreviewChange]);

  const reloadSelected = () => {
    if (!selected) return Promise.resolve();
    setContent(null);
    return readArtifact(sessionId, selected.path).then(setContent).catch(() => setContent(null));
  };

  // §34 (UX-016): [Title](artifact:path) chips in the transcript open the viewer directly.
  // Resolve against the loaded list first; on a miss, refresh once (the file may be
  // seconds old), then fall back to a minimal record — readArtifact validates the path.
  useEffect(() => {
    if (!active) return;
    const minimal = (path: string): ArtifactInfo => ({
      path,
      name: path.split("/").pop() || path,
      kind: kindFromPath(path),
      size: 0,
      modified_at: 0,
    });
    const match = (list: ArtifactInfo[], path: string) =>
      list.find((a) => a.path === path || a.path.endsWith("/" + path) || a.name === path);
    const onOpen = (e: Event) => {
      const path = String((e as CustomEvent).detail?.path || "");
      if (!path) return;
      const found = match(artifacts, path);
      if (found) {
        openArtifact(found);
        return;
      }
      getArtifacts(sessionId)
        .then((list) => {
          setArtifacts(list);
          openArtifact(match(list, path) ?? minimal(path));
        })
        .catch(() => openArtifact(minimal(path)));
    };
    window.addEventListener(OPEN_ARTIFACT_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_ARTIFACT_EVENT, onOpen);
  }, [active, sessionId, artifacts, openArtifact]);

  // Right-click on a produced file: open it in the program that owns it, or show it where
  // it lives. Its OWN effect, deliberately not gated on `active` — the effect above bails
  // when the rail is closed, and right-clicking a file in the transcript has to work
  // whether or not the panel happens to be open (owner ask 2026-08-31).
  useEffect(() => {
    const onReveal = (e: Event) => {
      const detail = (e as CustomEvent).detail || {};
      const path = String(detail.path || "");
      const mode = detail.mode === "open" ? "open" : "reveal";
      if (!path || !sessionId) return;
      void revealArtifact(sessionId, path, mode).catch(() => undefined);
    };
    window.addEventListener(REVEAL_ARTIFACT_EVENT, onReveal);
    return () => window.removeEventListener(REVEAL_ARTIFACT_EVENT, onReveal);
  }, [sessionId]);

  if (!active) return null;

  return (
    <aside className={"right-rail" + (selected ? " artifact-mode" : builderVisible ? " app-mode" : "")}>
      {builderVisible && builderApp ? (
        <div className="app-builder" data-testid="app-builder">
          <div className="app-builder-head">
            <span className="app-icon" aria-hidden>
              {builderApp.icon}
            </span>
            <div className="app-head-text">
              <div className="app-builder-title">{builderApp.title}</div>
              <div className="app-desc">Running here as you build it — it reloads each time Mimi saves.</div>
            </div>
            {builderApp.has_previous && (
              <button
                className="btn sm"
                data-testid="app-builder-undo"
                title="Swap back to the version before the last change (press again to redo)"
                onClick={async () => {
                  const r = await revertApp(builderApp.id).catch(() => ({ ok: false as const }));
                  if (r.ok && r.app) {
                    setBuilderApp(r.app);
                    setBuilderHtml(r.html ?? "");
                  }
                }}
              >
                Undo last change
              </button>
            )}
            {onOpenApp && (
              <button className="btn sm" data-testid="app-builder-open" onClick={() => onOpenApp(builderApp.id)}>
                Open page
              </button>
            )}
            <button
              className="artifact-icon-btn"
              aria-label="Show the side panels instead"
              title="Show the side panels instead"
              onClick={() => setShowBuilder(false)}
            >
              <Icon name="panelClose" size={16} />
            </button>
          </div>
          <div className="app-builder-stage">
            <AppFrame
              key={builderApp.updated_at}
              app={{ id: builderApp.id, title: builderApp.title }}
              html={builderHtml}
              onAsk={(e) => setBuilderAsks((cur) => [...cur.slice(-49), e])}
            />
          </div>
          <AskLog entries={builderAsks} />
        </div>
      ) : selected ? (
        <ArtifactViewer
          sessionId={sessionId}
          artifact={selected}
          content={content}
          onReload={reloadSelected}
          onBack={() => setSelected(null)}
          onFeedback={onFeedback}
          onOpenEntry={(path) =>
            setSelected({
              path,
              name: path.split("/").pop() || path,
              kind: kindFromPath(path),
              size: 0,
              modified_at: 0,
            })
          }
        />
      ) : (
        <>
          {builderApp && !showBuilder && (
            <button className="app-builder-return" data-testid="app-builder-return" onClick={() => setShowBuilder(true)}>
              <span aria-hidden>{builderApp.icon}</span> Show {builderApp.title} here
            </button>
          )}
          <RailSection title="Progress" open={open.progress} onToggle={() => setOpen({ ...open, progress: !open.progress })}>
            <ProgressSummary running={running} toolNames={toolNames} todo={todo} />
          </RailSection>

          {showArtifacts && (
          <RailSection
            title={`Artifacts${artifacts.length ? ` (${artifacts.length})` : ""}`}
            open={open.artifacts}
            onToggle={() => setOpen({ ...open, artifacts: !open.artifacts })}
            action={
              <>
                {artifacts.length > 0 && (
                  <button
                    className="rail-mini-btn"
                    onClick={(e) => { e.stopPropagation(); revealArtifact(sessionId, artifacts[0].path, "reveal"); }}
                    title="Show the folder where these files are saved"
                  >
                    <Icon name="folder" size={13} />
                  </button>
                )}
                <button className="rail-mini-btn" onClick={(e) => { e.stopPropagation(); refreshArtifacts(); }} title="Refresh artifacts"><Icon name="refresh" size={13} /></button>
              </>
            }
          >
            {artifacts.length === 0 ? (
              // The list is what THIS conversation wrote, so "yet" is the honest word:
              // an empty panel means nothing has been produced, not nothing exists.
              <div className="rail-muted">Nothing produced yet — files Mimi writes appear here.</div>
            ) : (
              <div className="artifact-list">
                {artifacts.slice(0, 16).map((a, i, list) => (
                  <div key={a.path}>
                    {/* The server ranks deliverables above working files; the first
                        working file gets a quiet label so the split is legible rather
                        than mysterious. */}
                    {(a.tier ?? 3) >= 3 && (i === 0 || (list[i - 1].tier ?? 3) < 3) && (
                      <div className="rail-muted" style={{ padding: "6px 2px 2px" }}>
                        Working files
                      </div>
                    )}
                    <button className="artifact-row" onClick={() => openArtifact(a)}>
                    <span className="artifact-ico" title={a.kind}>
                      <Icon name={kindIcon(a.kind)} size={17} />
                    </span>
                    <span className="artifact-name">
                      {a.name}
                      <span className="artifact-row-meta">{formatBytes(a.size)} · {clockTime(a.modified_at)}</span>
                    </span>
                      <span className="artifact-open">Open</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </RailSection>
          )}

          {showArtifacts && recoveryPoints.length > 0 && (
            <RailSection
              title={t("File recovery")}
              open={open.recovery}
              onToggle={() => setOpen({ ...open, recovery: !open.recovery })}
            >
              {latestRecovery ? (
                <div className="recovery-card">
                  <div className="rail-muted">
                    {latestRecovery.files.length} {t(latestRecovery.files.length === 1
                      ? "file changed in Mimi's latest recoverable turn."
                      : "files changed in Mimi's latest recoverable turn.")}
                  </div>
                  <div className="recovery-files" title={latestRecovery.files.map((file) => file.path).join("\n")}>
                    {latestRecovery.files.slice(0, 3).map((file) => file.name).join(", ")}
                    {latestRecovery.files.length > 3 ? ` +${latestRecovery.files.length - 3}` : ""}
                  </div>
                  <button
                    className="rail-secondary-btn"
                    onClick={() => void undoLatestTurn()}
                    disabled={running || restoring}
                    title={running ? t("Wait for Mimi to finish before restoring files") : t("Restore modified files and remove files created in that turn")}
                  >
                    {restoring ? t("Restoring…") : t("Undo latest file changes")}
                  </button>
                  {recoveryError && <div className="recovery-error">{recoveryError}</div>}
                </div>
              ) : (
                <div className="rail-muted">{t("The available file changes have already been restored.")}</div>
              )}
            </RailSection>
          )}

          {/* §32: Access — the former Session-settings drawer, one section among peers.
              key: its data ownership resets with the conversation, like the old row did. */}
          <AccessSection
            key={sessionId}
            sessionId={sessionId}
            personaId={personaId}
            projectScoped={projectScoped}
            workspace={workspace}
            branch={branch}
            scratchPrimary={scratchPrimary}
            openKey={openAccessKey}
            onOpenIntegrations={onOpenIntegrations}
          />
        </>
      )}
    </aside>
  );
}

function ProgressSummary({ running, toolNames, todo }: { running: boolean; toolNames: string[]; todo: TodoItem[] }) {
  if (todo.length) {
    return (
      <div className="rail-todo-list">
        {todo.map((item, index) => (
          <div className={"rail-todo " + item.status} key={index}>
            <span className="rail-todo-mark" />
            <span>{item.content}</span>
          </div>
        ))}
        {running && (
          <div className="rail-muted">
            {toolNames.length ? `${toolNames.length} tool call${toolNames.length === 1 ? "" : "s"} so far.` : "Working..."}
          </div>
        )}
      </div>
    );
  }
  if (running) {
    return (
      <div className="rail-muted">
        Working on this task{toolNames.length ? ` with ${toolNames.length} tool call${toolNames.length === 1 ? "" : "s"} so far.` : "."}
      </div>
    );
  }
  return (
    <div className="rail-muted">
      For longer multi-step tasks, progress will appear here while MimiWork plans, uses tools, waits for approval, and produces artifacts.
    </div>
  );
}

function RailSection({
  title,
  open,
  onToggle,
  children,
  action,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rail-section">
      <div className="rail-section-head">
        <button className="rail-section-toggle" onClick={onToggle}>
          <Icon name={open ? "chevronDown" : "chevronRight"} size={14} className="rail-chev" />
          <span>{title}</span>
        </button>
        {action}
      </div>
      {open && <div className="rail-section-body">{children}</div>}
    </section>
  );
}

function ArtifactViewer({
  sessionId,
  artifact,
  content,
  onReload,
  onBack,
  onOpenEntry,
  onFeedback,
}: {
  sessionId: string;
  artifact: ArtifactInfo;
  content: ArtifactContent | null;
  onReload: () => Promise<void>;
  onBack: () => void;
  // Folder listings: open a child entry in the viewer (files and subfolders alike).
  onOpenEntry?: (path: string) => void;
  onFeedback?: (text: string) => void;
}) {
  const [reloadKey, setReloadKey] = useState(0);
  // A comment in progress, and the spot it is about ("page 2, top left"). Clicking the
  // preview sets the spot; the button in the header opens a comment about the whole file.
  // A Word paragraph pin also carries its index, so the comment can go INTO the file.
  const [feedback, setFeedback] = useState<{ pin: string; paragraph?: number } | null>(null);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackNote, setFeedbackNote] = useState("");
  const sendFeedback = () => {
    const text = feedbackText.trim();
    if (!text || !onFeedback) return;
    const where = feedback?.pin ? ` (${feedback.pin})` : "";
    onFeedback(`Feedback on \`${artifact.path}\`${where}: ${text}`);
    setFeedback(null);
    setFeedbackText("");
  };
  const addWordComment = async () => {
    const text = feedbackText.trim();
    if (!text || feedback?.paragraph == null) return;
    const r = await commentArtifact(sessionId, artifact.path, feedback.paragraph, text).catch(() => ({ ok: false as const }));
    if (r.ok) {
      setFeedbackNote(`Added to the Word file (${feedback.pin}).`);
      setFeedback(null);
      setFeedbackText("");
    } else setFeedbackNote(("error" in r && r.error) || "Could not write the comment.");
  };
  const isHtml = content?.kind === "html" && !content.error;
  // Also at home in a real app: spreadsheets, PDFs and Office files (the preview is reading
  // quality, not page layout — Word/PowerPoint stay one click away).
  const isApp = ["sheet", "pdf", "office", "docx", "slides"].includes(content?.kind || "");

  return (
    <div className="artifact-viewer">
      <div className="artifact-head">
        <button className="artifact-icon-btn" onClick={onBack} aria-label="Back to artifacts" title="Back">
          <Icon name="arrowLeft" size={16} />
        </button>
        <div className="artifact-heading">
          <div className="artifact-title"><span>Artifacts</span><span className="artifact-sep">/</span><span>{artifact.name}</span></div>
          <div className="artifact-path">{artifact.path}</div>
        </div>
        <div className="rail-actions">
          {isHtml && (
            <button
              className="artifact-icon-btn"
              onClick={async () => {
                await onReload();
                setReloadKey((k) => k + 1);
              }}
              aria-label="Reload preview"
              title="Reload"
            >
              <Icon name="refresh" size={16} />
            </button>
          )}
          {onFeedback && (
            <button
              className="artifact-icon-btn"
              data-testid="artifact-comment"
              onClick={() => setFeedback((f) => (f ? null : { pin: "" }))}
              aria-label="Comment on this file"
              title="Comment on this file"
            >
              <Icon name="chat" size={16} />
            </button>
          )}
          {isApp && (
            <button
              className="artifact-icon-btn"
              onClick={() => revealArtifact(sessionId, artifact.path, "open")}
              aria-label="Open in default app"
              title="Open in default app"
            >
              <Icon name="panelOpen" size={16} />
            </button>
          )}
          {/* Copy the ABSOLUTE path — the workspace-relative one is useless outside the app
              (tester catch 2026-07-12: it copied just "slack-connector-debug.md"). */}
          <button
            className="artifact-icon-btn"
            onClick={() => navigator.clipboard?.writeText(artifact.abs_path || artifact.path)}
            aria-label="Copy path"
            title="Copy full path"
          >
            <Icon name="copy" size={16} />
          </button>
          <button
            className="artifact-icon-btn"
            onClick={() => revealArtifact(sessionId, artifact.path, "reveal")}
            aria-label="Show in folder"
            title="Show in folder"
          >
            <Icon name="folder" size={16} />
          </button>
        </div>
      </div>
      {feedback && (
        <div className="artifact-feedback" data-testid="artifact-feedback">
          <div className="artifact-feedback-pin">
            {feedback.pin ? `About ${feedback.pin}` : "About this file"}
            {content && content.kind !== "office" && content.kind !== "html" && (
              <span className="dim"> · click the preview to point at a spot</span>
            )}
          </div>
          <textarea
            autoFocus
            className="tmpl-input tmpl-textarea"
            placeholder="What should change? e.g. “make the background white”"
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) sendFeedback();
            }}
          />
          <div className="artifact-feedback-actions">
            <button className="btn-primary sm" disabled={!feedbackText.trim()} onClick={sendFeedback}>
              Send to Mimi
            </button>
            {content?.kind === "docx" && feedback.paragraph != null && (
              <button
                className="btn sm"
                data-testid="artifact-word-comment"
                disabled={!feedbackText.trim()}
                title="Write it into the .docx as a Word comment on this paragraph"
                onClick={() => void addWordComment()}
              >
                Add as Word comment
              </button>
            )}
            <button className="link" onClick={() => setFeedback(null)}>
              cancel
            </button>
          </div>
        </div>
      )}
      {feedbackNote && (
        <div className="artifact-feedback-note" data-testid="artifact-feedback-note">
          {feedbackNote}
          <button className="link" onClick={() => setFeedbackNote("")}>
            dismiss
          </button>
        </div>
      )}
      <div
        className="artifact-preview"
        onClick={(e) => {
          if (!onFeedback) return;
          const spot = pinFor(e.target as Element, e.clientX, e.clientY);
          if (spot) setFeedback(spot);
        }}
      >
        {!content ? (
          <div className="rail-muted">Loading...</div>
        ) : content.error ? (
          <div className="rail-error">{content.error}</div>
        ) : content.kind === "html" ? (
          <iframe
            key={`${artifact.path}-${reloadKey}`}
            sandbox="allow-scripts allow-same-origin"
            className="artifact-frame"
            srcDoc={content.content || ""}
          />
        ) : content.kind === "markdown" ? (
          <div className="artifact-md">
            <Markdown text={content.content || ""} />
          </div>
        ) : content.kind === "docx" || content.kind === "slides" ? (
          // Reading-quality HTML the sidecar built from the file (office_preview.py) —
          // its own escaping, no scripts. Paragraphs and slides are click-to-pin targets.
          <div
            className={"artifact-doc" + (content.kind === "slides" ? " artifact-slides" : "") + (onFeedback ? " pinnable" : "")}
            data-testid={`artifact-${content.kind}`}
            dangerouslySetInnerHTML={{ __html: content.content || "" }}
          />
        ) : content.kind === "image" ? (
          <img className="artifact-image" src={content.data_url} />
        ) : content.kind === "pdf" ? (
          <PdfViewer dataUrl={content.data_url || ""} />
        ) : content.kind === "csv" ? (
          <CsvTable text={content.content || ""} />
        ) : content.kind === "sheet" ? (
          <SheetViewer dataUrl={content.data_url || ""} />
        ) : content.kind === "folder" ? (
          // A linked directory (e.g. a skill package): render the listing, click through.
          <div className="artifact-folderlist" data-testid="artifact-folder">
            {(content.entries || []).map((e) => (
              <button
                key={e.name}
                className="artifact-folder-row"
                onClick={() => onOpenEntry?.(`${artifact.path.replace(/\/+$/, "")}/${e.name}`)}
              >
                <Icon name={e.dir ? "folder" : "file"} size={14} />
                <span className="artifact-folder-name">{e.name}</span>
                {!e.dir && <span className="artifact-folder-size">{formatBytes(e.size)}</span>}
              </button>
            ))}
            {!content.entries?.length && <div className="rail-muted">This folder is empty.</div>}
          </div>
        ) : content.kind === "office" ? (
          <div className="artifact-open-prompt">
            <Icon name="panelOpen" size={28} />
            <p>This {/\.pptm?$/i.test(artifact.name) ? "PowerPoint" : "Word"} file can’t be previewed here.</p>
            <button className="btn sm" onClick={() => revealArtifact(sessionId, artifact.path, "open")}>
              Open in default app
            </button>
          </div>
        ) : (
          <pre className="artifact-code">{content.content}</pre>
        )}
      </div>
    </div>
  );
}

const MAX_TABLE_ROWS = 500;

/** Where in the preview a click landed, in words Mimi can act on: "page 2, top left",
 *  "row 4, column 2", "paragraph 12, starting …". Null when the click is nowhere in
 *  particular (prose, code). A Word paragraph also carries its index for the file comment. */
function pinFor(target: Element, clientX: number, clientY: number): { pin: string; paragraph?: number } | null {
  const para = target.closest("[data-p]");
  if (para) {
    const index = parseInt(para.getAttribute("data-p") || "", 10);
    const words = (para.textContent || "").trim().split(/\s+/).slice(0, 8).join(" ");
    return { pin: `paragraph ${index + 1}, starting “${words}”`, paragraph: index };
  }
  const slide = target.closest("[data-slide]");
  if (slide) return { pin: `slide ${slide.getAttribute("data-slide")}` };
  const pin = pinRegion(target, clientX, clientY);
  return pin ? { pin } : null;
}

function pinRegion(target: Element, clientX: number, clientY: number): string {
  const region = (el: Element) => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return "";
    const rx = (clientX - r.left) / r.width;
    const ry = (clientY - r.top) / r.height;
    const v = ry < 0.33 ? "top" : ry > 0.66 ? "bottom" : "middle";
    const h = rx < 0.33 ? "left" : rx > 0.66 ? "right" : "centre";
    return `${v} ${h}`;
  };
  const page = target.closest("canvas.artifact-pdf-page");
  if (page) {
    const n = Array.from(page.parentElement?.children ?? []).indexOf(page) + 1;
    return `page ${n}, ${region(page)}`;
  }
  const img = target.closest("img.artifact-image");
  if (img) return `${region(img)} of the image`;
  const cell = target.closest("td, th");
  const row = cell?.closest("tr");
  if (cell && row) {
    const table = row.closest("table");
    const rows = Array.from(table?.querySelectorAll("tr") ?? []);
    return `row ${rows.indexOf(row) + 1}, column ${Array.from(row.children).indexOf(cell) + 1}`;
  }
  return "";
}

function GridTable({ rows, note }: { rows: unknown[][]; note?: string }) {
  const [head, ...body] = rows;
  return (
    <div className="artifact-tablewrap">
      <table className="artifact-table">
        {head && (
          <thead>
            <tr>{head.map((c, i) => <th key={i}>{String(c ?? "")}</th>)}</tr>
          </thead>
        )}
        <tbody>
          {body.slice(0, MAX_TABLE_ROWS).map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j}>{String(c ?? "")}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {(note || body.length > MAX_TABLE_ROWS) && (
        <div className="rail-muted artifact-table-note">
          {note}
          {body.length > MAX_TABLE_ROWS ? ` Showing first ${MAX_TABLE_ROWS} of ${body.length} rows.` : ""}
        </div>
      )}
    </div>
  );
}

// Minimal RFC-4180-ish CSV parsing: quoted fields, escaped quotes, CRLF. TSV via tab sniffing.
function parseCsv(text: string): string[][] {
  const delim = text.includes("\t") && !text.split("\n")[0]?.includes(",") ? "\t" : ",";
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else quoted = false;
      } else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delim) {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      cell = "";
      rows.push(row);
      row = [];
    } else cell += ch;
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((c) => c !== ""));
}

function CsvTable({ text }: { text: string }) {
  const rows = parseCsv(text);
  if (!rows.length) return <div className="rail-muted artifact-table-note">Empty file.</div>;
  return <GridTable rows={rows} />;
}

// xlsx/xls preview via SheetJS (loaded on demand — it's a heavy module): sheet tabs + a capped
// grid. Real spreadsheet work belongs in Numbers/Excel via "Open in default app".
// WKWebView has no inline PDF plugin (<embed> shows a gray pane in the Tauri shell), so we
// rasterize pages with pdf.js onto stacked canvases — same lazy-chunk pattern as SheetViewer.
function PdfViewer({ dataUrl }: { dataUrl: string }) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const holder = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setLoading(true);
    const base64 = dataUrl.split(",")[1] || "";
    import("pdfjs-dist")
      .then(async (pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
        const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
        const doc = await pdfjs.getDocument({ data: bytes }).promise;
        const el = holder.current;
        if (cancelled || !el) return;
        el.innerHTML = "";
        const width = el.clientWidth || 640;
        const dpr = window.devicePixelRatio || 1;
        for (let i = 1; i <= doc.numPages; i++) {
          const page = await doc.getPage(i);
          const base = page.getViewport({ scale: 1 });
          const viewport = page.getViewport({ scale: (width / base.width) * dpr });
          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.className = "artifact-pdf-page";
          await page.render({ canvasContext: canvas.getContext("2d")!, viewport }).promise;
          if (cancelled) return;
          el.appendChild(canvas);
        }
        setLoading(false);
      })
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => {
      cancelled = true;
    };
  }, [dataUrl]);

  if (error) return <div className="rail-error artifact-table-note">Could not render PDF: {error}</div>;
  return (
    <div className="artifact-pdfjs">
      {loading && <div className="rail-muted artifact-table-note">Rendering PDF…</div>}
      <div ref={holder} />
    </div>
  );
}

function SheetViewer({ dataUrl }: { dataUrl: string }) {
  const [sheets, setSheets] = useState<{ name: string; rows: unknown[][] }[] | null>(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setSheets(null);
    setError("");
    setActive(0);
    const base64 = dataUrl.split(",")[1] || "";
    import("xlsx")
      .then((XLSX) => {
        if (cancelled) return;
        const wb = XLSX.read(base64, { type: "base64" });
        setSheets(
          wb.SheetNames.map((name) => ({
            name,
            rows: XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, defval: "" }) as unknown[][],
          })),
        );
      })
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => {
      cancelled = true;
    };
  }, [dataUrl]);

  if (error) return <div className="rail-error artifact-table-note">Could not parse spreadsheet: {error}</div>;
  if (!sheets) return <div className="rail-muted artifact-table-note">Parsing spreadsheet…</div>;
  const sheet = sheets[active];
  return (
    <div className="sheet-viewer">
      {sheets.length > 1 && (
        <div className="sheet-tabs">
          {sheets.map((s, i) => (
            <button key={s.name} className={"sheet-tab" + (i === active ? " active" : "")} onClick={() => setActive(i)}>
              {s.name}
            </button>
          ))}
        </div>
      )}
      {sheet.rows.length ? <GridTable rows={sheet.rows} /> : <div className="rail-muted artifact-table-note">Empty sheet.</div>}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
