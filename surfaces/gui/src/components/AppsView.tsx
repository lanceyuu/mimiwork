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
  updateApp,
  type AppStarter,
  type MimiApp,
} from "../api";
import { AppFrame } from "./AppFrame";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icon";
import { PanelHead } from "./IntegrationsView";

const CARD = "rounded-xl2 border border-line bg-panel";

interface Props {
  // Open a conversation with Mimi and send `prompt` under the mimi-apps skill. When the
  // app remembers the session that built it, that one is reopened so Mimi has context.
  onBuild: (prompt: string, builderSession?: string) => void;
  initialOpenId?: string | null;
}

export function AppsView({ onBuild, initialOpenId }: Props) {
  const [apps, setApps] = useState<MimiApp[]>([]);
  const [openId, setOpenId] = useState<string | null>(initialOpenId ?? null);
  const [starters, setStarters] = useState<AppStarter[]>([]);
  const [wish, setWish] = useState("");
  const [confirmDel, setConfirmDel] = useState<MimiApp | null>(null);

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
    onBuild(`Build me an app: ${text}`);
    setWish("");
  };

  return (
    <Shell>
      <PanelHead
        title="Apps"
        sub="Small tools Mimi builds for you — a form, a button, a result. They run right here and ask Mimi when they need to."
      />

      <div className={CARD + " p-4 mb-5"} data-testid="apps-build">
        <div className="text-[13px] font-medium mb-2">What should the app do?</div>
        <div className="flex gap-2">
          <input
            className="tmpl-input flex-1"
            data-testid="apps-wish"
            placeholder="e.g. translate what I paste into Norwegian and keep the last five"
            value={wish}
            onChange={(e) => setWish(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") build();
            }}
          />
          <button className="btn-primary sm" data-testid="apps-build-go" disabled={!wish.trim()} onClick={build}>
            Build with Mimi
          </button>
        </div>
        <div className="text-[12px] text-faint mt-2">
          Mimi writes one small page and it appears below. Everything stays on this computer.
        </div>
      </div>

      {starters.length > 0 && (
        <>
          <div className="sa-sub">Starters</div>
          <div className="grid gap-2.5 mb-5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
            {starters.map((s) => (
              <div className={CARD + " p-3.5 flex flex-col gap-1.5"} key={s.name} data-testid={`app-starter-${s.name}`}>
                <div className="flex items-center gap-2 text-[13.5px] font-medium">
                  <span aria-hidden>{s.icon}</span>
                  {s.title}
                </div>
                <div className="text-[12.5px] text-muted flex-1">{s.description}</div>
                <button
                  className="btn sm self-start"
                  onClick={async () => {
                    const r = await importApp({ title: s.title, icon: s.icon, description: s.description, html: s.html });
                    if (r.ok && r.app) {
                      announceAppsChanged();
                      await refresh();
                      setOpenId(r.app.id);
                    } else alert(r.error || "Could not add the starter.");
                  }}
                >
                  Add
                </button>
              </div>
            ))}
          </div>
        </>
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
  onBuild: (prompt: string, builderSession?: string) => void;
}) {
  const [app, setApp] = useState<MimiApp | null>(null);
  const [html, setHtml] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [note, setNote] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);

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
      app.builder_session || undefined,
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
        <span className="text-[18px]" aria-hidden>
          {app.icon}
        </span>
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
        <span className="text-[12px] text-faint truncate">{app.description}</span>
        <span className="flex-1" />
        <select
          className="tmpl-input tmpl-select app-model"
          value={app.model || ""}
          title="Which model answers this app"
          data-testid="app-model"
          onChange={async (e) => {
            const r = await updateApp(app.id, { model: e.target.value });
            if (r.ok && r.app) setApp(r.app);
          }}
        >
          <option value="">Default{defaultModel ? ` (${defaultModel})` : ""}</option>
          {models.map((m) => (
            <option value={m} key={m}>
              {m}
            </option>
          ))}
        </select>
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
      <div className="app-stage">
        <AppFrame key={app.updated_at} app={{ id: app.id, title: app.title }} html={html} />
      </div>
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
