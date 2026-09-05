import { useState } from "react";
import { revealRoot } from "../api";
import { useT } from "../i18n";
import { baseName } from "../paths";
import { useRoots } from "../useRoots";
import { AddFolderForm } from "./AddFolderForm";
import { Icon } from "./Icon";
import { RootRow } from "./RootRow";

// FoldersSection — the rail's first section: which folders Mimi can read and write in this
// conversation, and a plain "Add a folder" button. It was a sub-list inside the collapsed
// Access section, which nobody found (owner ask 2026-09-05: "make it really obvious"). Open
// by default; the header carries the folder fact so it reads even when folded.
export function FoldersSection({
  sessionId,
  projectScoped,
  workspace,
  branch,
  scratchPrimary,
}: {
  sessionId: string;
  // Project-scoped (code-family) sessions summarize the folder NAME, not a count.
  projectScoped?: boolean;
  workspace?: string;
  branch?: string | null;
  scratchPrimary?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(false);
  const { roots, busy, error, addRoot, toggleAccess, removeRoot } = useRoots(sessionId);

  // The scratch primary is Mimi's own temporary space, not a folder the user gave — it
  // does not count, and its presence alone means "no folder yet".
  const own = roots.filter((r) => !(r.primary && scratchPrimary));
  const summary = projectScoped
    ? baseName(workspace || roots.find((r) => r.primary)?.path || "")
    : own.length === 0
      ? t("No folder yet")
      : `${own.length} ${t(own.length === 1 ? "folder" : "folders")}`;

  return (
    <section className="rail-section" data-testid="folders-section">
      <div className="rail-section-head">
        <button className="rail-section-toggle" onClick={() => setOpen((v) => !v)} data-testid="folders-toggle">
          <Icon name={open ? "chevronDown" : "chevronRight"} size={14} className="rail-chev" />
          <span>{t("Folders")}</span>
          <span className="ml-auto min-w-0 truncate text-[11px] font-normal text-faint" data-testid="folders-summary" title={summary}>
            {summary}
          </span>
        </button>
      </div>
      {open && (
        <div className="rail-section-body" data-testid="drawer-directories">
          {own.length === 0 && !projectScoped && (
            <p className="rail-muted">{t("Mimi works in a temporary space. Add a folder to work on your own files.")}</p>
          )}
          <div className="-mx-1.5">
            {roots.map((r) => (
              <RootRow
                key={r.path}
                root={r}
                busy={busy}
                scratchPrimary={scratchPrimary}
                branch={r.primary ? branch : undefined}
                onToggle={toggleAccess}
                onRemove={removeRoot}
                onOpen={(r) => void revealRoot(sessionId, r.path)}
              />
            ))}
          </div>
          {adding ? (
            <div className="mt-1.5">
              <AddFolderForm onAdd={addRoot} busy={busy} startOpen onDismiss={() => setAdding(false)} />
            </div>
          ) : (
            <button className="rail-primary-btn" onClick={() => setAdding(true)} data-testid="folders-add">
              <Icon name="folder" size={14} />
              {t("Add a folder")}
            </button>
          )}
          {error && <div className="roots-err">{error}</div>}
        </div>
      )}
    </section>
  );
}
