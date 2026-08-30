import { useCallback, useEffect, useState } from "react";
// The sidecar's address and launch token come from api.ts — the shell injects the
// real port at runtime. A local resolver that only read the Vite env var returned ""
// in the packaged app, so every fetch went to tauri://localhost and WebKit threw
// "The string did not match the expected pattern" (owner report 2026-08-30).
import { apiToken, httpBase } from "../api";
import { PanelHead } from "./IntegrationsView";
import { Icon } from "./Icon";

// Files — a read-only browser of the session's granted folders (the same roots
// the @-picker and the file tools see). Breadcrumb + one-level tree + a
// line-numbered viewer; mutating stays with the agent (approval-gated tools),
// this pane is for the human to see what's there.

export interface TreeEntry {
  name: string;
  type: "dir" | "file";
  size: number;
  modified_at: number;
  path: string;
  truncated?: boolean;
}
export interface TreeResult {
  root?: string;
  root_label?: string;
  roots?: Array<{ index: number; path: string; label: string }>;
  path?: string;
  entries?: TreeEntry[];
  error?: string;
}
export interface ReadResult {
  path?: string;
  full_path?: string;
  start_line?: number;
  end_line?: number;
  total_lines?: number;
  content?: string;
  note?: string;
  error?: string;
}

const INPUT =
  "px-3 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";
const BTN =
  "text-[12.5px] px-3 py-1.5 rounded-lg border border-line bg-paper text-ink hover:bg-panel shrink-0";


function jsonPost(body: unknown): RequestInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const t = apiToken();
  if (t) headers["X-OpenWorker-Token"] = t;
  return { method: "POST", headers, body: JSON.stringify(body) };
}

async function apiGet<T>(path: string, params: Record<string, string>): Promise<T> {
  const q = new URLSearchParams(params).toString();
  const url = `${httpBase()}${path}${q ? `?${q}` : ""}`;
  const headers: Record<string, string> = {};
  const t = apiToken();
  if (t) headers["X-OpenWorker-Token"] = t;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function WorkspaceView(props: {
  workspace: string | null;
  sessionId: string | null;
}) {
  const [tree, setTree] = useState<TreeResult | null>(null);
  const [file, setFile] = useState<{ path: string; data: ReadResult } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");

  // ── Editor (manuscript workbench lite) ──
  // Editable for text files; save snapshots the previous version; proofread
  // sends the text through the configured provider and offers a diff.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [savedDraft, setSavedDraft] = useState("");
  const [saveBusy, setSaveBusy] = useState(false);
  const [proofBusy, setProofBusy] = useState(false);
  const [proof, setProof] = useState<{
    revised: string | null;
    notes: Array<{ kind?: string; issue?: string; suggestion?: string }>;
    truncated?: boolean;
    model?: string;
  } | null>(null);
  const [versions, setVersions] = useState<
    Array<{ ts: string; label: string }>
  >([]);
  const [showVersions, setShowVersions] = useState(false);

  const loadTree = useCallback(
    (path: string) => {
      setBusy(true);
      setErr("");
      apiGet<TreeResult>("/v1/workspace/tree", {
        path,
        ...(props.workspace ? { workspace: props.workspace } : {}),
        ...(props.sessionId ? { session_id: props.sessionId } : {}),
      })
        .then((t) => {
          setTree(t);
          if (t.error) setErr(t.error);
        })
        .catch((e) => setErr(String(e)))
        .finally(() => setBusy(false));
    },
    [props.workspace, props.sessionId],
  );

  useEffect(() => {
    loadTree(".");
  }, [loadTree]);

  const openFile = (path: string, startLine = 1) => {
    setBusy(true);
    setErr("");
    apiGet<ReadResult>("/v1/workspace/read", {
      path,
      start_line: String(startLine),
      ...(props.workspace ? { workspace: props.workspace } : {}),
      ...(props.sessionId ? { session_id: props.sessionId } : {}),
    })
      .then((data) => {
        if (data.error) {
          setErr(data.error);
          return;
        }
        setFile({ path, data });
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false));
  };

  // ── editor helpers ──
  const base = (extra: Record<string, string> = {}): Record<string, string> => ({
    ...(props.workspace ? { workspace: props.workspace } : {}),
    ...(props.sessionId ? { session_id: props.sessionId } : {}),
    ...extra,
  });

  const startEditing = () => {
    if (!file) return;
    // Join the numbered lines back to raw text for the textarea.
    const raw = (file.data.content ?? "")
      .split("\n")
      .map((l) => l.replace(/^\d+\t/, ""))
      .join("\n");
    setDraft(raw);
    setSavedDraft(raw);
    setEditing(true);
    setProof(null);
  };

  const saveDraft = async () => {
    if (!file) return;
    setSaveBusy(true);
    setErr("");
    try {
      const r = await fetch(
        `${httpBase()}/v1/manuscript/save`,
        jsonPost({ path: file.path, content: draft, label: "manual", ...base() }),
      );
      const d = (await r.json()) as { ok?: boolean; error?: string; saved?: boolean };
      if (d.error) {
        setErr(d.error);
        return;
      }
      setSavedDraft(draft);
      // Refresh the viewer + version list from the server.
      openFile(file.path);
      void loadVersions();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaveBusy(false);
    }
  };

  const loadVersions = () => {
    if (!file) return;
    apiGet<{ versions?: Array<{ ts: string; label: string }>; error?: string }>(
      "/v1/manuscript/versions",
      base({ path: file.path }),
    )
      .then((d) => setVersions(d.versions ?? []))
      .catch(() => setVersions([]));
  };

  const runProofread = async () => {
    if (!file) return;
    setProofBusy(true);
    setErr("");
    setProof(null);
    try {
      const r = await fetch(
        `${httpBase()}/v1/manuscript/proofread`,
        jsonPost({ path: file.path, ...base() }),
      );
      const d = (await r.json()) as {
        revised?: string | null;
        notes?: Array<{ kind?: string; issue?: string; suggestion?: string }>;
        truncated?: boolean;
        model?: string;
        error?: string;
      };
      if (d.error) {
        setErr(d.error);
        return;
      }
      setProof({ revised: d.revised ?? null, notes: d.notes ?? [], truncated: d.truncated, model: d.model });
    } catch (e) {
      setErr(String(e));
    } finally {
      setProofBusy(false);
    }
  };

  const applyRevised = () => {
    if (!proof?.revised) return;
    setDraft(proof.revised);
  };

  const restoreVersion = async (ts: string) => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await fetch(
        `${httpBase()}/v1/manuscript/restore`,
        jsonPost({ path: file.path, ts, ...base() }),
      );
      const d = (await r.json()) as { content?: string; error?: string };
      if (d.error) {
        setErr(d.error);
        return;
      }
      setDraft(d.content ?? "");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const crumbs = (): Array<{ label: string; path: string }> => {
    const out: Array<{ label: string; path: string }> = [];
    const roots = tree?.roots ?? [];
    if (roots.length > 1 && tree?.root_label) {
      out.push({ label: tree.root_label, path: "." });
    }
    const rel = tree?.path && tree.path !== "." ? tree.path : "";
    if (rel) {
      let acc = "";
      for (const part of rel.split("/")) {
        acc = acc ? `${acc}/${part}` : part;
        out.push({ label: part, path: acc });
      }
    }
    return out;
  };

  const entries = (tree?.entries ?? []).filter((e) =>
    filter.trim() ? e.name.toLowerCase().includes(filter.trim().toLowerCase()) : true,
  );

  return (
    <main className="flex-1 min-w-0 flex bg-paper" data-testid="workspace-view">
      {/* Left: the tree */}
      <div className="w-[340px] shrink-0 border-r border-line overflow-y-auto hairline-scroll">
        <div className="px-4 pt-5 pb-3">
          <PanelHead
            title="Files"
            sub="Browse everything this conversation can see — your granted folders and the files Mimi made. Text files open in a light editor with saved versions; for bigger changes, just ask Mimi."
          />
        </div>

        <div className="px-4 pb-2 flex items-center gap-2">
          <input
            className={INPUT + " flex-1 min-w-0"}
            placeholder="filter…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            data-testid="workspace-filter"
          />
          <button className={BTN} onClick={() => loadTree(tree?.path ?? ".")} disabled={busy}>
            <Icon name="refresh" size={13} />
          </button>
        </div>

        {/* Breadcrumb */}
        <div className="px-4 pb-2 flex items-center gap-1 text-[12px] text-muted flex-wrap" data-testid="workspace-crumbs">
          {tree?.root_label && (
            <button
              className="hover:text-ink"
              onClick={() => loadTree(".")}
            >
              {tree.root_label}
            </button>
          )}
          {crumbs().map((c) => (
            <span key={c.path} className="flex items-center gap-1">
              <span className="text-faint">/</span>
              <button className="hover:text-ink" onClick={() => loadTree(c.path)}>
                {c.label}
              </button>
            </span>
          ))}
        </div>

        {/* Multiple roots */}
        {(tree?.roots?.length ?? 0) > 1 && (
          <div className="px-4 pb-2 flex flex-col gap-1">
            {(tree?.roots ?? []).map((r) => (
              <button
                key={r.index}
                className={
                  "text-left px-2 py-1 rounded-md text-[12px] " +
                  (tree?.root === r.path ? "bg-panel text-ink" : "text-muted hover:text-ink")
                }
                onClick={() => loadTree(`root:${r.index}`)}
              >
                <Icon name="folder" size={12} /> {r.label}
              </button>
            ))}
          </div>
        )}

        {err && (
          <div className="mx-4 mb-2 px-3 py-2 rounded-lg bg-danger/10 text-danger text-[12.5px]" data-testid="workspace-error">
            {err}
          </div>
        )}

        <div className="px-2 pb-6">
          {entries.length === 0 && !busy && (
            <div className="px-2 py-3 text-[12.5px] text-faint">No entries.</div>
          )}
          {entries.map((e) => (
            <button
              key={e.path}
              className={
                "w-full text-left px-2 py-1.5 rounded-md text-[13px] flex items-center gap-2 " +
                (e.type === "dir"
                  ? "text-ink hover:bg-panel"
                  : "text-muted hover:bg-panel hover:text-ink")
              }
              data-testid={`workspace-entry-${e.name}`}
              onClick={() => (e.type === "dir" ? loadTree(e.path) : openFile(e.path))}
            >
              <Icon name={e.type === "dir" ? "folder" : "file"} size={13} className="shrink-0" />
              <span className="truncate flex-1 min-w-0">{e.name}</span>
              {e.type === "file" && (
                <span className="text-[11px] text-faint shrink-0">{fmtSize(e.size)}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Right: the viewer / editor */}
      <div className="flex-1 min-w-0 flex flex-col">
        {file ? (
          <>
            <div className="px-5 py-3 border-b border-line flex items-center gap-3 flex-wrap">
              <span className="text-[13px] font-semibold text-ink truncate" data-testid="workspace-file-title">
                {file.path}
              </span>
              <span className="text-[11.5px] text-faint shrink-0">
                {file.data.total_lines ?? 0} lines
              </span>
              {editing && draft !== savedDraft && (
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-warning/15 text-warning shrink-0">
                  unsaved
                </span>
              )}
              <div className="ml-auto flex items-center gap-2">
                {!editing ? (
                  <>
                    <button
                      className={BTN}
                      onClick={() => openFile(file.path, (file.data.end_line ?? 0) + 1)}
                      disabled={busy || (file.data.end_line ?? 0) >= (file.data.total_lines ?? 0)}
                    >
                      Next page
                    </button>
                    <button className={BTN} data-testid="workspace-edit-btn" onClick={startEditing}>
                      <Icon name="fileCode" size={13} /> Edit
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className={BTN}
                      data-testid="workspace-save-btn"
                      onClick={() => void saveDraft()}
                      disabled={saveBusy || draft === savedDraft}
                    >
                      {saveBusy ? "Saving…" : "Save"}
                    </button>
                    <button
                      className={BTN}
                      data-testid="workspace-proofread-btn"
                      onClick={() => void runProofread()}
                      disabled={proofBusy}
                    >
                      {proofBusy ? "Proofreading…" : "Proofread"}
                    </button>
                    <button
                      className={BTN}
                      data-testid="workspace-versions-btn"
                      onClick={() => {
                        setShowVersions((v) => !v);
                        if (!showVersions) loadVersions();
                      }}
                    >
                      Versions
                    </button>
                    <button
                      className={BTN}
                      onClick={() => {
                        setEditing(false);
                        setProof(null);
                        openFile(file.path);
                      }}
                    >
                      Done
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Proofread result card */}
            {proof && (
              <div className="mx-5 my-3 rounded-xl2 border border-line bg-panel p-4" data-testid="workspace-proofread">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[12.5px] font-semibold text-ink">
                    Proofread {proof.revised ? "— revision ready" : "— no revision returned"}
                  </span>
                  {proof.model && <span className="text-[11px] text-faint">via {proof.model}</span>}
                  {proof.truncated && (
                    <span className="text-[11px] text-warning">file truncated for review</span>
                  )}
                  {proof.revised && (
                    <button className={BTN + " ml-auto"} data-testid="workspace-apply-btn" onClick={applyRevised}>
                      Load revision into editor
                    </button>
                  )}
                </div>
                {proof.notes.length > 0 && (
                  <ul className="space-y-1.5">
                    {proof.notes.map((n, i) => (
                      <li key={i} className="text-[12.5px] text-muted flex gap-2">
                        <span className="px-1.5 py-0.5 rounded bg-paper text-[10.5px] uppercase tracking-wide text-faint shrink-0">
                          {n.kind || "note"}
                        </span>
                        <span className="min-w-0">
                          {n.issue}
                          {n.suggestion && <span className="text-faint"> → {n.suggestion}</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Version history drawer */}
            {editing && showVersions && (
              <div className="mx-5 my-2 rounded-xl2 border border-line bg-panel p-3 max-h-56 overflow-y-auto" data-testid="workspace-versions">
                {versions.length === 0 ? (
                  <div className="text-[12px] text-faint">No versions yet — save an edit to start history.</div>
                ) : (
                  versions.map((v) => (
                    <div key={v.ts} className="flex items-center gap-2 py-1">
                      <span className="text-[12px] text-ink flex-1 truncate">{v.label}</span>
                      <span className="text-[11px] text-faint">{new Date(v.ts).toLocaleString()}</span>
                      <button
                        className={BTN}
                        data-testid="workspace-restore"
                        onClick={() => void restoreVersion(v.ts)}
                      >
                        Load
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}

            <div className="flex-1 overflow-auto hairline-scroll">
              {editing ? (
                <textarea
                  className="w-full h-full min-h-[60vh] bg-transparent text-[12.5px] leading-[1.6] font-mono px-5 py-4 text-ink outline-none resize-none"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  spellCheck={false}
                  data-testid="workspace-editor"
                />
              ) : (
                <>
                  <pre className="text-[12px] leading-[1.55] font-mono px-5 py-4 text-ink whitespace-pre" data-testid="workspace-file-content">
                    {file.data.content ?? ""}
                  </pre>
                  {file.data.note && (
                    <div className="px-5 pb-4 text-[11.5px] text-faint">{file.data.note}</div>
                  )}
                </>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 grid place-items-center text-[13px] text-faint">
            Select a file to view it.
          </div>
        )}
      </div>
    </main>
  );
}
