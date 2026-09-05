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
import type { Attachment } from "../types";
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
  // Several pinned comments go together, with a screenshot of the preview and its
  // numbered markers, so a vision-capable model sees where each one points.
  onFeedback?: (text: string, attachments?: Attachment[]) => void;
  onRevise?: (path: string) => void;
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
  onRevise,
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
  // The builder's app preview is a preview too: it wants the width. Only TRANSITIONS
  // fire: the callback's identity changes whenever the nav collapses or expands, and
  // re-firing on that re-collapsed the nav the instant the user opened it beside a
  // preview (owner-hit 2026-09-03: "it shows and disappears immediately").
  const previewChangeRef = useRef(onPreviewChange);
  previewChangeRef.current = onPreviewChange;
  useEffect(() => {
    previewChangeRef.current?.(!!selected || builderVisible);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!selected, builderVisible]);

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
                {!running && <p className="rail-muted">{t("Your files are saved. Open one to review it, or ask for changes.")}</p>}
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
                      <span className="artifact-open">{t("Open")}</span>
                    </button>
                    <div className="artifact-file-actions">
                      <button className="rail-secondary-btn" onClick={() => void revealArtifact(sessionId, a.path, "reveal")} aria-label={`${t("Show in folder")}: ${a.name}`}>
                        {t("Show in folder")}
                      </button>
                      {onRevise && <button className="rail-secondary-btn" disabled={running} onClick={() => onRevise(a.path)} aria-label={`${t("Revise")}: ${a.name}`}>
                        {t("Revise")}
                      </button>}
                    </div>
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
  onFeedback?: (text: string, attachments?: Attachment[]) => void;
}) {
  const [reloadKey, setReloadKey] = useState(0);
  // Comments are PINS: a click drops a numbered marker where you pointed, the note is
  // written beside it, and they all go at once (owner ask 2026-09-02). Coordinates are
  // in the preview's content space (scroll included), so markers scroll with the page.
  // A Word paragraph pin also carries its index, so the comment can go INTO the file.
  const previewRef = useRef<HTMLDivElement | null>(null);
  // An HTML preview lives in an iframe, which swallows clicks: the pin listener goes
  // INSIDE its document (same origin — it is our own srcdoc), the markers are painted in
  // there too so they scroll with the page, and the screenshot is taken of that document.
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const [pins, setPins] = useState<Pin[]>([]);
  const [draft, setDraft] = useState<Omit<Pin, "n" | "text"> | null>(null);
  const [draftText, setDraftText] = useState("");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [sending, setSending] = useState(false);
  const clearPins = () => {
    setPins([]);
    setDraft(null);
    setDraftText("");
  };
  const addPin = () => {
    const text = draftText.trim();
    if (!text || !draft) return;
    setPins((cur) => [...cur, { ...draft, n: cur.length + 1, text }]);
    setDraft(null);
    setDraftText("");
  };
  const wireFrame = () => {
    const frame = frameRef.current;
    const doc = frame?.contentDocument;
    if (!frame || !doc || !onFeedback) return;
    doc.addEventListener("click", (e) => {
      const host = previewRef.current;
      const target = e.target as Element | null;
      if (!host || !target || target.closest("[data-mimi-pin]")) return;
      const fr = frame.getBoundingClientRect();
      const hr = host.getBoundingClientRect();
      const spot = pinFor(target, e.clientX, e.clientY) || { pin: "" };
      // The draft box is the host's: place it where the click shows on screen. The pin
      // itself is remembered in the page's own coordinates (scroll included).
      setDraft({
        ...spot,
        x: e.clientX + fr.left - hr.left + host.scrollLeft,
        y: e.clientY + fr.top - hr.top + host.scrollTop,
        fx: e.pageX,
        fy: e.pageY,
      });
      setDraftText("");
    });
    paintFramePins(doc, pins);
  };
  useEffect(() => {
    const doc = frameRef.current?.contentDocument;
    if (doc) paintFramePins(doc, pins);
  }, [pins]);
  const sendAll = async () => {
    if (!onFeedback || !pins.length) return;
    setSending(true);
    const frameDoc = content?.kind === "html" ? frameRef.current?.contentDocument : null;
    const shot = frameDoc
      ? await screenshotPreview(
          frameDoc.documentElement,
          pins.map((p) => ({ n: p.n, x: p.fx ?? -1, y: p.fy ?? -1 })),
        )
      : await screenshotPreview(previewRef.current, pins);
    setSending(false);
    const lines = pins.map((p) => `${p.n}. ${p.pin ? `(${p.pin}) ` : ""}${p.text}`).join("\n");
    const head =
      pins.length === 1
        ? `Feedback on \`${artifact.path}\`${shot ? " (marker 1 in the attached screenshot)" : ""}:`
        : `Feedback on \`${artifact.path}\` — ${pins.length} comments${shot ? "; the numbers match the markers in the attached screenshot" : ""}:`;
    onFeedback(`${head}\n${lines}`, shot ? [{ kind: "image", name: "preview-with-comments.jpg", mime: "image/jpeg", data_url: shot }] : undefined);
    clearPins();
  };
  const addWordComments = async () => {
    const targets = pins.filter((p) => p.paragraph != null);
    if (!targets.length) return;
    setSending(true);
    let done = 0;
    let lastError = "";
    for (const p of targets) {
      const r = await commentArtifact(sessionId, artifact.path, p.paragraph!, p.text).catch(() => ({ ok: false as const }));
      if (r.ok) done += 1;
      else lastError = ("error" in r && r.error) || "could not write";
    }
    setSending(false);
    setFeedbackNote(
      done === targets.length
        ? `Added ${done} comment${done === 1 ? "" : "s"} to the Word file.`
        : `Added ${done} of ${targets.length} — ${lastError}.`,
    );
    if (done === targets.length) clearPins();
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
              onClick={() => setDraft((d) => (d ? null : { pin: "", x: -1, y: -1 }))}
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
      {(pins.length > 0 || (draft && draft.x < 0)) && (
        <div className="artifact-feedback" data-testid="artifact-feedback">
          {pins.length > 0 && (
            <div className="artifact-feedback-head">
              <span>Comments</span>
              <span className="artifact-feedback-count">{pins.length}</span>
            </div>
          )}
          {pins.length > 0 && (
            <ol className="artifact-pin-list">
              {pins.map((p) => (
                <li key={p.n} data-testid="artifact-pin-row">
                  <span className="artifact-pin-badge">{p.n}</span>
                  <span className="artifact-pin-text">
                    {p.pin && <span className="dim">{p.pin} · </span>}
                    {p.text}
                  </span>
                  <button
                    className="artifact-icon-btn artifact-pin-remove"
                    aria-label={`Remove comment ${p.n}`}
                    onClick={() => setPins((cur) => cur.filter((q) => q !== p).map((q, i) => ({ ...q, n: i + 1 })))}
                  >
                    <Icon name="x" size={13} />
                  </button>
                </li>
              ))}
            </ol>
          )}
          {draft && draft.x < 0 && (
            <div className="artifact-pin-draft-inline">
              <textarea
                autoFocus
                className="tmpl-input tmpl-textarea"
                data-testid="artifact-draft-text"
                placeholder="About the whole file, e.g. “make the background white”"
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) addPin();
                }}
              />
              <div className="artifact-feedback-actions">
                <button className="btn sm" data-testid="artifact-draft-add" disabled={!draftText.trim()} onClick={addPin}>
                  Add
                </button>
                <button className="link" onClick={() => setDraft(null)}>
                  cancel
                </button>
              </div>
            </div>
          )}
          {pins.length > 0 && (
            <div className="artifact-feedback-actions">
              <button className="btn-primary sm" data-testid="artifact-send-all" disabled={sending} onClick={() => void sendAll()}>
                {sending ? "Preparing…" : `Send ${pins.length === 1 ? "to Mimi" : `all ${pins.length} to Mimi`}`}
              </button>
              {content?.kind === "docx" && pins.some((p) => p.paragraph != null) && (
                <button
                  className="btn sm"
                  data-testid="artifact-word-comment"
                  disabled={sending}
                  title="Write them into the .docx as Word comments on their paragraphs"
                  onClick={() => void addWordComments()}
                >
                  Add {pins.filter((p) => p.paragraph != null).length === 1 ? "as a Word comment" : "all as Word comments"}
                </button>
              )}
              <span className="dim text-[12px]">click the preview to add another</span>
              <button className="link" onClick={clearPins}>
                clear
              </button>
            </div>
          )}
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
        ref={previewRef}
        onClick={(e) => {
          if (!onFeedback || !content || content.kind === "html" || content.kind === "office" || content.kind === "folder") return;
          const el = e.currentTarget;
          const r = el.getBoundingClientRect();
          const spot = pinFor(e.target as Element, e.clientX, e.clientY) || { pin: "" };
          setDraft({ ...spot, x: e.clientX - r.left + el.scrollLeft, y: e.clientY - r.top + el.scrollTop });
          setDraftText("");
        }}
      >
        {draft && draft.x >= 0 && (
          <>
            <div className="artifact-pin artifact-pin-new" style={{ left: draft.x, top: draft.y }}>
              {pins.length + 1}
            </div>
            <div
              className="artifact-pin-draft"
              data-html2canvas-ignore
              data-testid="artifact-draft"
              style={{ left: draft.x + 16, top: draft.y - 8 }}
              onClick={(e) => e.stopPropagation()}
            >
              {draft.pin && <div className="dim text-[11.5px] mb-1">{draft.pin}</div>}
              <textarea
                autoFocus
                className="tmpl-input tmpl-textarea"
                data-testid="artifact-draft-text"
                placeholder="What should change here?"
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) addPin();
                  if (e.key === "Escape") setDraft(null);
                }}
              />
              <div className="artifact-feedback-actions">
                <button className="btn-primary sm" data-testid="artifact-draft-add" disabled={!draftText.trim()} onClick={addPin}>
                  Add
                </button>
                <button className="link" onClick={() => setDraft(null)}>
                  cancel
                </button>
              </div>
            </div>
          </>
        )}
        {!content ? (
          <div className="rail-muted">Loading...</div>
        ) : content.error ? (
          <div className="rail-error">{content.error}</div>
        ) : content.kind === "html" ? (
          <iframe
            key={`${artifact.path}-${reloadKey}`}
            ref={frameRef}
            sandbox="allow-scripts allow-same-origin"
            className="artifact-frame"
            srcDoc={content.content || ""}
            onLoad={wireFrame}
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
        {/* Markers last, so they paint above the content in the browser AND in the
            html2canvas capture (which follows DOM order more than z-index). */}
        {pins.map((p) =>
          p.x >= 0 && p.fx == null ? (
            <div key={p.n} className="artifact-pin" style={{ left: p.x, top: p.y }} data-testid="artifact-pin" title={p.text} data-html2canvas-ignore>
              {p.n}
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}

const MAX_TABLE_ROWS = 500;

/** One pinned comment: where (content coordinates + the spot in words) and what. */
interface Pin {
  n: number;
  pin: string;
  paragraph?: number;
  x: number;
  y: number;
  // Set for a pin inside an HTML preview: the page's own coordinates, where the marker
  // is painted (see paintFramePins) and where the disc goes on the screenshot.
  fx?: number;
  fy?: number;
  text: string;
}

/** Numbered markers inside an HTML preview's document, redrawn from `pins` on every
 *  change and after every (re)load — they are DOM the page does not own, so they are
 *  replaced wholesale rather than reconciled. Ignored by the capture; the discs are
 *  drawn by hand there, like the host's. */
function paintFramePins(doc: Document, pins: Pin[]) {
  doc.querySelectorAll("[data-mimi-pin]").forEach((n) => n.remove());
  const body = doc.body;
  if (!body) return;
  for (const p of pins) {
    if (p.fx == null || p.fy == null) continue;
    const m = doc.createElement("div");
    m.setAttribute("data-mimi-pin", String(p.n));
    m.setAttribute("data-html2canvas-ignore", "");
    m.textContent = String(p.n);
    m.style.cssText =
      `position:absolute;left:${p.fx}px;top:${p.fy}px;margin:-11px 0 0 -11px;width:22px;height:22px;` +
      "border-radius:999px;background:#2563eb;color:#fff;font:700 11.5px/18px -apple-system,'Segoe UI',sans-serif;" +
      "text-align:center;border:2px solid #fff;box-sizing:border-box;pointer-events:none;z-index:2147483647";
    body.appendChild(m);
  }
}

/** The preview with its markers, as one JPEG for the model to look at. html2canvas is a
 *  lazy chunk (like pdfjs and SheetJS); the scroll container is opened up in the clone so
 *  the whole page is captured, then capped at a size the message channel accepts. The
 *  numbered discs are drawn by hand afterwards: html2canvas rendered the DOM markers as
 *  pale rings with no digit, and a marker the model cannot read is no marker. */
async function screenshotPreview(
  el: HTMLElement | null | undefined,
  pins: { n: number; x: number; y: number }[],
): Promise<string | null> {
  if (!el) return null;
  try {
    const { default: html2canvas } = await import("html2canvas");
    // Capture at the on-screen width: any other width reflows the text and the markers,
    // placed in content coordinates, land on the wrong lines.
    const height = Math.min(el.scrollHeight, 6000);
    const canvas = await html2canvas(el, {
      scale: 1,
      useCORS: true,
      backgroundColor: "#ffffff",
      width: el.clientWidth,
      height,
      scrollX: 0,
      scrollY: 0,
      onclone: (_doc, cloned) => {
        (cloned as HTMLElement).style.overflow = "visible";
        (cloned as HTMLElement).style.height = "auto";
        (cloned as HTMLElement).style.width = `${el.clientWidth}px`;
      },
    });
    // A fresh canvas: html2canvas hands back a context still carrying its last clip,
    // and anything drawn there outside that region silently vanishes.
    const maxW = 1400;
    const ratio = Math.min(1, maxW / Math.max(1, canvas.width));
    const out = document.createElement("canvas");
    out.width = Math.round(canvas.width * ratio);
    out.height = Math.round(canvas.height * ratio);
    const ctx = out.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(canvas, 0, 0, out.width, out.height);
    for (const p of pins) {
      if (p.x < 0 || p.y > canvas.height) continue;
      const x = p.x * ratio;
      const y = p.y * ratio;
      const r = 12 * Math.max(0.6, ratio);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = "#2563eb"; // the app accent, literal: canvas has no CSS variables
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.font = `bold ${Math.round(13 * Math.max(0.6, ratio))}px -apple-system, 'Segoe UI', sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(p.n), x, y + 0.5);
    }
    const url = out.toDataURL("image/jpeg", 0.85);
    return url && url.startsWith("data:image") ? url : null;
  } catch {
    return null;
  }
}

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
  const pin = pinRegion(target, clientX, clientY) || nearText(target);
  return pin ? { pin } : null;
}

/** Prose and pages: the block the click landed in, quoted by its first words — enough
 *  for Mimi to find the spot in the source without the screenshot. */
function nearText(target: Element): string {
  const block = target.closest("h1,h2,h3,h4,h5,h6,p,li,td,th,button,a,label,figcaption,blockquote,pre,summary,dt,dd");
  if (!block) return "";
  const words = (block.textContent || "").trim().split(/\s+/);
  if (!words[0]) return "";
  return `${block.tagName.toLowerCase()} “${words.slice(0, 8).join(" ")}${words.length > 8 ? "…" : ""}”`;
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
