import type { RootInfo } from "../api";
import { Icon } from "./Icon";
import { baseName } from "../paths";

// One directory row, shared by the composer popover and the session start panel. The primary is the
// session's bound workspace — the repo/folder for Code/Ops (shown by name), or a throwaway scratch
// for Cowork (shown as "Temporary space"). It's always read-write and can't be removed.
export function RootRow({
  root,
  busy,
  scratchPrimary,
  branch,
  onToggle,
  onRemove,
  onOpen,
}: {
  root: RootInfo;
  busy?: boolean;
  scratchPrimary?: boolean;
  // The workspace's git branch — shown on the primary row (drawer's Working directories, §23).
  branch?: string | null;
  onToggle: (r: RootInfo) => void;
  onRemove: (path: string) => void;
  /** Open the folder on the user's computer. Absent → the row stays plain text. */
  onOpen?: (r: RootInfo) => void;
}) {
  const label = root.primary
    ? scratchPrimary
      ? "Temporary space"
      : baseName(root.path)
    : root.label;
  return (
    <div className={"root-row" + (root.exists ? "" : " missing")}>
      <Icon name="folder" size={14} className="root-ico" />
      {/* The name IS the way in: clicking a folder you granted opens it on your computer
        * (owner ask 2026-08-24). Missing folders stay inert — there is nothing to open. */}
      {onOpen && root.exists ? (
        <button
          type="button"
          className="root-text root-open"
          data-testid={`root-open-${root.path}`}
          title={`Open ${root.path}`}
          onClick={() => onOpen(root)}
        >
          <span className="root-label">
            {label}
            {root.primary && !scratchPrimary && <span className="root-tag"> main</span>}
            {branch && (
              <span className="root-tag root-branch">
                {" "}
                <Icon name="branch" size={11} /> {branch}
              </span>
            )}
          </span>
          <span className="root-path">{root.path}</span>
        </button>
      ) : (
        <span className="root-text" title={root.path}>
          <span className="root-label">
            {label}
            {root.primary && !scratchPrimary && <span className="root-tag"> main</span>}
            {branch && (
              <span className="root-tag root-branch">
                {" "}
                <Icon name="branch" size={11} /> {branch}
              </span>
            )}
          </span>
          <span className="root-path">{root.path}</span>
        </span>
      )}
      {!root.exists && <span className="root-tag warn">missing</span>}
      <button
        className={"root-access" + (root.writable ? " rw" : " ro")}
        onClick={() => onToggle(root)}
        disabled={busy || root.primary}
        title={root.primary ? "The main workspace is always read-write" : "Toggle read-only / read-write"}
      >
        {root.writable ? "Read-write" : "Read-only"}
      </button>
      {!root.primary && (
        <button className="root-x" onClick={() => onRemove(root.path)} disabled={busy} title="Remove">
          ×
        </button>
      )}
    </div>
  );
}
