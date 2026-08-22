import { useEffect, useState } from "react";
import { getRecentWorkspaces, openWorkspace, type RecentWorkspace } from "../api";
import { chooseFolder } from "../tauri";

// The mandatory workspace picker for project-scoped personas. Deliberately no
// "switch persona" escape hatch: if a persona needs a folder, the choice here is
// pick one or cancel — offering Chat as an exit undermined the persona the user
// just chose (owner call, 2026-07-03).
interface Props {
  onChoose: (path: string, branch?: string | null) => void;
  onCancel?: () => void; // present when changing folder mid-session
  create?: boolean; // "New project" mode: create the folder if missing
  // "project": the Projects band's "+" — creating a PLACE, not a conversation. Same
  // picker, different words, and the caller lands on the Project page, not a session
  // (owner catch 2026-08-22: "create new folder is the same interface as new session").
  mode?: "session" | "project";
}

export function FolderGate({ onChoose, onCancel, create, mode = "session" }: Props) {
  const project = mode === "project";
  const [recents, setRecents] = useState<RecentWorkspace[]>([]);
  const [path, setPath] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getRecentWorkspaces().then(setRecents).catch(() => {});
  }, []);

  const open = async (p: string, doCreate = false) => {
    setError("");
    const res = await openWorkspace(p.trim(), doCreate);
    if (res.ok) onChoose(res.path, res.git_branch);
    else setError(res.error || "could not open that folder");
  };

  const browse = async () => {
    const picked = await chooseFolder();
    if (picked) {
      setPath(picked);
      open(picked, create); // a picked folder already exists; create flag is harmless
    }
  };

  return (
    <div className="gate-overlay">
      <div className="gate">
        <div className="gate-mark">✦</div>
        <h2 data-testid="gate-title">
          {project ? "New project" : create ? "New project folder" : "Choose a project folder"}
        </h2>
        <p className="gate-sub">
          {project
            ? "A project is a folder Mimi works in — its files, your instructions, and what she remembers about it. Pick an existing folder, or type a path to create one. You'll land on the project's page to set it up; conversations come after."
            : create
              ? "Pick a folder or enter a path. If the path doesn't exist, it will be created."
              : "This coworker needs a workspace to read, edit, and run in."}
        </p>

        <div className="gate-input">
          <input
            data-testid="gate-path"
            placeholder={project ? "/Users/you/Documents/My thesis" : "/path/to/your/project"}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && open(path, create)}
            autoFocus
          />
          <button className="btn" onClick={browse} title="Pick a folder">
            Browse…
          </button>
          <button
            className="btn primary"
            onClick={() => open(path, create)}
            disabled={!path.trim()}
            data-testid="gate-submit"
          >
            {project ? "Create project" : create ? "Create" : "Open"}
          </button>
        </div>
        {error && <div className="gate-error">{error}</div>}

        {recents.length > 0 && (
          <>
            <div className="gate-label">{project ? "Or turn a recent folder into a project" : "Recent"}</div>
            <div className="gate-recents">
              {recents.map((w) => (
                <div className="gate-recent" key={w.path} onClick={() => open(w.path)} title={w.path}>
                  <span className="folder">📁 {w.name}</span>
                  <span className="dim">{w.path}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {onCancel && (
          <div className="gate-foot">
            <button className="btn gate-cancel" onClick={onCancel}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
