/** Apps — small HTML tools Mimi writes and the user runs inside MimiWork.
 *
 * Mirrors Automations: an overview (cards + starters + "build one"), and a detail page
 * that is mostly the app itself, full-width, with the comment loop the flow diagram got
 * on 2026-09-02: say what should change, Mimi rewrites the file, the frame reloads.
 * Spec: docs/superpowers/specs/2026-09-03-apps-section-design.md.
 */
import { useEffect, useState } from "react";
import {
  announceAppsChanged,
  deleteApp,
  exportApp,
  getApp,
  getApps,
  getSettings,
  importApp,
  listAppStarters,
  revertApp,
  updateApp,
  type AppStarter,
  type MimiApp,
} from "../api";
import { AppFrame, AskLog, type AskEntry } from "./AppFrame";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icon";
import { PanelHead } from "./IntegrationsView";
import { RunSettings } from "./ScheduledView";

/** What the build conversation should run with, and what the app should be pinned to. */
export interface BuildOptions {
  builderSession?: string;
  model?: string;
  mode?: string;
}

/** The short display name for a model id ("Mimi Hound", not "qualitati:mimi-hound"). */
function shortLabel(labels: Record<string, string>, id: string): string {
  const raw = labels[id]?.split(" · ")[0];
  if (raw) return raw;
  return id.includes(":") ? id.slice(id.indexOf(":") + 1) : id;
}

const CARD = "rounded-xl2 border border-line bg-panel";

interface Props {
  // Open a conversation with Mimi and send `prompt` under the mimi-apps skill. When the
  // app remembers the session that built it, that one is reopened so Mimi has context.
  onBuild: (prompt: string, opts?: BuildOptions) => void;
  initialOpenId?: string | null;
}

export function AppsView({ onBuild, initialOpenId }: Props) {
  const [apps, setApps] = useState<MimiApp[]>([]);
  const [openId, setOpenId] = useState<string | null>(initialOpenId ?? null);
  const [starters, setStarters] = useState<AppStarter[]>([]);
  const [wish, setWish] = useState("");
  const [confirmDel, setConfirmDel] = useState<MimiApp | null>(null);
  // The build conversation's model and permission level, and the model the app is pinned
  // to — the same two controls an automation has (owner ask 2026-09-02).
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("interactive");
  const [models, setModels] = useState<string[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  useEffect(() => {
    getSettings()
      .then((s) => {
        setModels(s.models || []);
        setDefaultModel(s.model || "");
      })
      .catch(() => setModels([]));
  }, []);

  const refresh = () => getApps().then(setApps).catch(() => setApps([]));
  useEffect(() => {
    refresh();
    listAppStarters().then(setStarters).catch(() => {});
    // Mimi creates apps from a chat; the overview must notice without a click.
    const h = setInterval(refresh, 5000);
    return () => clearInterval(h);
  }, []);
  useEffect(() => {
    if (initialOpenId) setOpenId(initialOpenId);
  }, [initialOpenId]);

  if (openId) {
    return (
      <AppDetail
        id={openId}
        onBack={() => {
          setOpenId(null);
          refresh();
        }}
        onBuild={onBuild}
      />
    );
  }

  const build = () => {
    const text = wish.trim();
    if (!text) return;
    const pin = model ? `\n\nWhen you save it with create_app, pass model="${model}" so the app asks that model.` : "";
    onBuild(`Build me an app: ${text}${pin}`, { model: model || undefined, mode });
    setWish("");
  };

  return (
    <Shell>
      <PanelHead
        title="Apps"
        sub="Small tools Mimi builds for you — a form, a button, a result. They run right here and ask Mimi when they need to."
      />

      <div className={CARD + " p-4 mb-5 apps-build"} data-testid="apps-build">
        <div className="text-[13px] font-medium mb-1">What should the app do?</div>
        <div className="text-[12px] text-faint mb-2">
          Describe it the way you would to a colleague: what goes in, what comes out, what it
          should remember. Mimi writes one small page and it appears below.
        </div>
        <textarea
          className="tmpl-input tmpl-textarea apps-wish"
          data-testid="apps-wish"
          rows={4}
          placeholder={
            "e.g. A translator: I paste text or drop a .txt/.md file, pick a language, and get the " +
            "translation with a copy button. Keep my last five."
          }
          value={wish}
          onChange={(e) => setWish(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) build();
          }}
        />
        <div className="apps-build-settings">
          <RunSettings
            model={model}
            mode={mode}
            models={models}
            defaultModel={defaultModel}
            onModel={setModel}
            onMode={setMode}
          />
        </div>
        <div className="apps-build-actions">
          <button className="btn-primary sm" data-testid="apps-build-go" disabled={!wish.trim()} onClick={build}>
            Build with Mimi
          </button>
          <span className="text-[12px] text-faint">
            The model answers the app's questions too. Everything stays on this computer.
          </span>
        </div>
      </div>

      {starters.length > 0 && (
        <div className="apps-gallery" data-testid="apps-gallery">
          <div className="sa-sub">Templates</div>
          <div className="dim" style={{ marginBottom: 10, fontSize: 12.5 }}>
            Ready-made apps to add as your own, then change however you like.
          </div>
          {Array.from(new Set(starters.map((s) => s.category))).map((cat) => (
            <div key={cat} className="apps-gallery-group">
              <div className="apps-gallery-cat">{cat}</div>
              <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
                {starters
                  .filter((s) => s.category === cat)
                  .map((s) => (
                    <div className={CARD + " p-3.5 flex flex-col gap-1.5"} key={s.name} data-testid={`app-starter-${s.name}`}>
                      <div className="flex items-center gap-2 text-[13.5px] font-medium">
                        <span aria-hidden>{s.icon}</span>
                        {s.title}
                      </div>
                      <div className="text-[12.5px] text-muted flex-1">{s.description}</div>
                      <button
                        className="btn sm self-start"
                        onClick={async () => {
                          const r = await importApp({
                            title: s.title,
                            icon: s.icon,
                            description: s.description,
                            intro: s.intro,
                            suggestions: s.suggestions,
                            html: s.html,
                          });
                          if (r.ok && r.app) {
                            announceAppsChanged();
                            await refresh();
                            setOpenId(r.app.id);
                          } else alert(r.error || "Could not add the template.");
                        }}
                      >
                        Add
                      </button>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="sa-sub">Your apps</div>
      {apps.length === 0 ? (
        <div className={CARD + " p-4 text-[12.5px] text-muted"} data-testid="apps-empty">
          Nothing yet — describe one above, add a starter, or ask Mimi in any conversation.
        </div>
      ) : (
        <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
          {apps.map((a) => (
            <button
              key={a.id}
              className={CARD + " p-3.5 text-left hover:border-accent flex flex-col gap-1.5"}
              data-testid={`app-card-${a.id}`}
              onClick={() => setOpenId(a.id)}
            >
              <div className="flex items-center gap-2 text-[13.5px] font-medium">
                <span aria-hidden>{a.icon}</span>
                <span className="truncate flex-1">{a.title}</span>
                <span
                  className="text-faint hover:text-danger"
                  role="button"
                  aria-label={`Delete ${a.title}`}
                  data-testid="app-card-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmDel(a);
                  }}
                >
                  <Icon name="trash" size={14} />
                </span>
              </div>
              {a.description && <div className="text-[12.5px] text-muted">{a.description}</div>}
              <div className="text-[11.5px] text-faint">
                {a.asks > 0 ? `asked Mimi ${a.asks} time${a.asks === 1 ? "" : "s"}` : "not used yet"}
              </div>
            </button>
          ))}
        </div>
      )}

      {confirmDel && (
        <ConfirmDialog
          title="Delete this app?"
          body={`${confirmDel.title} — it is removed from Apps. Nothing else changes.`}
          confirmLabel="Delete app"
          onCancel={() => setConfirmDel(null)}
          onConfirm={async () => {
            const target = confirmDel;
            setConfirmDel(null);
            await deleteApp(target.id);
            announceAppsChanged();
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

function AppDetail({
  id,
  onBack,
  onBuild,
}: {
  id: string;
  onBack: () => void;
  onBuild: (prompt: string, opts?: BuildOptions) => void;
}) {
  const [app, setApp] = useState<MimiApp | null>(null);
  const [html, setHtml] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [defaultModel, setDefaultModel] = useState("");
  const [note, setNote] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);
  const [asks, setAsks] = useState<AskEntry[]>([]);
  const [suggestion, setSuggestion] = useState<{ text: string; nonce: number } | null>(null);
  const [undoing, setUndoing] = useState(false);

  const load = () =>
    getApp(id)
      .then((d) => {
        if (!d.ok || !d.app) {
          onBack();
          return;
        }
        setApp(d.app);
        // Only a real change reloads the frame — the app would lose its inputs otherwise.
        setHtml((cur) => (cur === (d.html ?? "") ? cur : d.html ?? ""));
      })
      .catch(() => {});
  useEffect(() => {
    load();
    // Mimi rewrites the file from a chat; the frame reloads when the text changes.
    const h = setInterval(load, 4000);
    return () => clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  useEffect(() => {
    getSettings()
      .then((s) => {
        setModels(s.models || []);
        setLabels(s.model_labels || {});
        setDefaultModel(s.model || "");
      })
      .catch(() => setModels([]));
  }, []);

  if (!app) {
    return (
      <Shell>
        <div className="dim">Loading…</div>
      </Shell>
    );
  }

  const improve = () => {
    const text = noteText.trim();
    if (!text) return;
    onBuild(
      `Change the app ${app.title} (id ${app.id}): ${text}\n\nHere is its current index.html — make exactly that change, keep the rest, and save it with update_app:\n\n\`\`\`html\n${html}\n\`\`\``,
      { builderSession: app.builder_session || undefined, model: app.model || undefined },
    );
    setNote(false);
    setNoteText("");
  };

  return (
    <div className="app-page" data-testid="app-page">
      <div className="app-head">
        <button className="artifact-icon-btn" onClick={onBack} aria-label="Back to apps" title="Back">
          <Icon name="arrowLeft" size={16} />
        </button>
        <span className="app-icon" aria-hidden>
          {app.icon}
        </span>
        <div className="app-head-text">
          {renaming ? (
            <input
              className="tmpl-input app-title-input"
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={async (e) => {
                if (e.key === "Escape") setRenaming(false);
                if (e.key === "Enter") {
                  const r = await updateApp(app.id, { title: title.trim() });
                  if (r.ok && r.app) setApp(r.app);
                  announceAppsChanged();
                  setRenaming(false);
                }
              }}
              onBlur={() => setRenaming(false)}
            />
          ) : (
            <button
              className="app-title"
              title="Rename"
              data-testid="app-title"
              onClick={() => {
                setTitle(app.title);
                setRenaming(true);
              }}
            >
              {app.title}
            </button>
          )}
          <div className="app-desc" title={app.description}>
            {app.description || "No description yet — Improve can add one."}
          </div>
        </div>
        <label className="app-model-field" title="Which model answers this app's questions">
          <span>Model</span>
          <select
            className="tmpl-input tmpl-select app-model"
            value={app.model || ""}
            data-testid="app-model"
            onChange={async (e) => {
              const r = await updateApp(app.id, { model: e.target.value });
              if (r.ok && r.app) setApp(r.app);
            }}
          >
            <option value="">Default{defaultModel ? ` · ${shortLabel(labels, defaultModel)}` : ""}</option>
            {models.map((m) => (
              <option value={m} key={m}>
                {shortLabel(labels, m)}
              </option>
            ))}
          </select>
        </label>
        <div className="app-head-actions">
          {app.has_previous && (
            <button
              className="btn sm"
              data-testid="app-undo"
              title="Swap back to the version before the last change (press again to redo)"
              disabled={undoing}
              onClick={async () => {
                setUndoing(true);
                const r = await revertApp(app.id).catch(() => ({ ok: false as const }));
                setUndoing(false);
                if (r.ok && r.app) {
                  setApp(r.app);
                  setHtml(r.html ?? "");
                  announceAppsChanged();
                } else alert(("error" in r && r.error) || "Could not undo.");
              }}
            >
              Undo last change
            </button>
          )}
          <button className="btn-primary sm" data-testid="app-improve" onClick={() => setNote((v) => !v)}>
            Improve
          </button>
          <button
            className="btn sm"
            title="Save a shareable .mimiapp.html file"
            onClick={async () => {
              const r = await exportApp(app.id);
              alert(r.ok ? `Saved to ${r.path}\n\nSend the file — anyone can import it from Apps.` : r.error || "Export failed.");
            }}
          >
            Export
          </button>
          <button className="btn sm danger-btn" data-testid="app-delete" onClick={() => setConfirmDel(true)}>
            <Icon name="trash" size={14} /> Delete
          </button>
        </div>
      </div>
      {note && (
        <div className="flow-note app-note" data-testid="app-note">
          <div className="flow-note-head">
            <span>
              What should be different?
              <span className="dim"> · Mimi rewrites the app; it reloads here when she is done.</span>
            </span>
            <button className="link" onClick={() => setNote(false)}>
              close
            </button>
          </div>
          <textarea
            autoFocus
            className="tmpl-input tmpl-textarea flow-note-text"
            data-testid="app-note-text"
            placeholder="e.g. “add a copy button under the result” or “remember the last language I picked”"
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) improve();
            }}
          />
          <div className="flow-note-actions">
            <button className="btn-primary sm" data-testid="app-note-submit" disabled={!noteText.trim()} onClick={improve}>
              Ask Mimi to change it
            </button>
          </div>
        </div>
      )}
      {(app.intro || (app.suggestions && app.suggestions.length > 0)) && (
        <div className="app-intro" data-testid="app-intro">
          {app.intro && <span className="app-intro-text">{app.intro}</span>}
          {(app.suggestions || []).map((s) => (
            <button
              key={s}
              type="button"
              className="app-chip"
              data-testid="app-chip"
              onClick={() => setSuggestion({ text: s, nonce: Date.now() })}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="app-stage">
        <AppFrame
          key={app.updated_at}
          app={{ id: app.id, title: app.title }}
          html={html}
          suggestion={suggestion}
          onAsk={(e) => setAsks((cur) => [...cur.slice(-49), e])}
        />
      </div>
      <AskLog entries={asks} />
      {confirmDel && (
        <ConfirmDialog
          title="Delete this app?"
          body={`${app.title} — it is removed from Apps. Nothing else changes.`}
          confirmLabel="Delete app"
          onCancel={() => setConfirmDel(false)}
          onConfirm={async () => {
            setConfirmDel(false);
            await deleteApp(app.id);
            announceAppsChanged();
            onBack();
          }}
        />
      )}
    </div>
  );
}
