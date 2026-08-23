import { useRef, useState } from "react";
import { useEffect } from "react";
import {
  importSkill,
  importableSkills,
  type ImportableSkill,
  createSkill,
  deleteSkill,
  installStoreSkill,
  listSkills,
  revealSkill,
  searchSkillStore,
  stageSkillUpload,
  confirmSkillUpload,
  updateSkill,
  type SkillRow,
  type SkillStoreEntry,
  type SkillUploadPreview,
} from "../api";
import { Icon } from "./Icon";

// Settings ▸ Skills (SKILLS-SPEC §5/§6) — the management home: the LIST is the page; every
// add-surface appears only when summoned from the single "Add skill" menu (the three doors:
// write form / import / start-a-conversation). Everything a user creates here is GLOBAL —
// "skills are things your worker knows everywhere". Creation-by-AI is a CONVERSATION (the
// menu's third door starts one; the worker proposes via save_skill) — there is no
// in-Settings drafting and no description box: the composer is where you describe it.
// Persona-bundled skills arrive with personas (§10), managed on the persona page, not here.

const CARD = "rounded-xl2 border border-line bg-panel";
const FIELD_LABEL = "text-[12.5px] font-medium text-ink";
const INPUT =
  "w-full min-w-0 px-3 py-2 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";
const BTN_ACCENT =
  "text-[12.5px] px-3 py-2 rounded-lg bg-accent text-white shrink-0 disabled:opacity-40";
const BTN_BORDERED =
  "text-[12.5px] px-3 py-2 rounded-lg border border-line bg-paper hover:border-lineStrong shrink-0";
const BADGE =
  "text-[11px] px-2 py-0.5 rounded-full border border-line bg-paper text-muted shrink-0";

type Editor = {
  mode: "new" | "edit";
  name: string;
  description: string;
  instructions: string;
};

const emptyEditor = (): Editor => ({
  mode: "new",
  name: "",
  description: "",
  instructions: "",
});

async function fileToB64(file: File): Promise<string> {
  // FileReader fallback: File.arrayBuffer is missing in some webviews (and jsdom).
  const buf =
    typeof file.arrayBuffer === "function"
      ? await file.arrayBuffer()
      : await new Promise<ArrayBuffer>((resolve, reject) => {
          const r = new FileReader();
          r.onload = () => resolve(r.result as ArrayBuffer);
          r.onerror = () => reject(r.error);
          r.readAsArrayBuffer(file);
        });
  const bytes = new Uint8Array(buf);
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

export function SkillsTab({
  onCreateSkill,
}: {
  // The doorway (SKILLS-SPEC §5.2): starts a new conversation with the description
  // prefilled in the composer — the worker builds the skill and proposes it via save_skill.
  onCreateSkill?: (description: string) => void;
}) {
  const [rows, setRows] = useState<SkillRow[]>([]);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [upload, setUpload] = useState<SkillUploadPreview | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [armedDelete, setArmedDelete] = useState<string | null>(null);
  const [error, setError] = useState("");
  // The state-change callout (SKILLS-SPEC §4.1 #2): name-first so the user knows WHICH
  // skill, and visually distinct so it can't be skimmed past (tester ask 2026-07-27).
  const [notice, setNotice] = useState<{ name: string; text: string; tone: "ok" | "warn" } | null>(
    null,
  );
  const fileInput = useRef<HTMLInputElement>(null);
  // The skill store: search the bundled community index, install on demand.
  const [storeOpen, setStoreOpen] = useState(false);
  const [storeQuery, setStoreQuery] = useState("");
  const [storeResults, setStoreResults] = useState<SkillStoreEntry[]>([]);
  const [storeBusy, setStoreBusy] = useState<string | null>(null); // name mid-install
  const [storeFlag, setStoreFlag] = useState<{ entry: SkillStoreEntry; text: string; url?: string } | null>(null);
  // Skills this machine already has for Claude Code / Cowork (including plugin bundles):
  // the folder layout is identical, so importing is a copy, not a rewrite.
  const [importOpen, setImportOpen] = useState(false);
  const [importRows, setImportRows] = useState<ImportableSkill[] | null>(null);
  const [importBusy, setImportBusy] = useState<string | null>(null);
  const loadImportable = () => {
    setImportRows(null);
    importableSkills()
      .then(setImportRows)
      .catch(() => setImportRows([]));
  };

  // Confirmation copy (SKILLS-SPEC §4.1 #2): name-first, outcome + remedy only, in words a
  // person already owns — now / everywhere / off / start a new one. Never mechanism ("the
  // model will be told…") or engineering timing ("from the next message") — owner-driver
  // review rounds, 2026-07-27. The engine countermands disabled-but-loaded skills silently;
  // the copy promises only the guaranteed part.
  const CONFIRMATION = "— the worker can now use it in every conversation.";
  const OFF_NOTE =
    "turned off everywhere. If a conversation already used it, start a new one for a completely clean slate.";
  const DELETE_NOTE =
    "removed. If a conversation already used it, start a new one for a completely clean slate.";

  const refresh = () => listSkills().then(setRows);
  useEffect(() => {
    refresh();
  }, []);

  const fail = (res: { ok?: boolean; error?: string }) => {
    setNotice(null);
    if (res.ok === false) {
      setError(res.error || "Something went wrong.");
      return true;
    }
    setError("");
    return false;
  };

  const save = async () => {
    if (!editor) return;
    const res =
      editor.mode === "new"
        ? await createSkill({
            name: editor.name.trim(),
            description: editor.description.trim(),
            instructions: editor.instructions,
          })
        : await updateSkill(editor.name, {
            description: editor.description.trim(),
            instructions: editor.instructions,
          });
    if (fail(res)) return;
    setEditor(null);
    if (editor.mode === "new")
      setNotice({ name: editor.name.trim(), text: CONFIRMATION, tone: "ok" });
    refresh();
  };

  const onPickFile = async (file: File | undefined) => {
    if (!file) return;
    const res = await stageSkillUpload(await fileToB64(file), file.name);
    if (fail(res)) return;
    setUpload(res);
  };

  const confirmUpload = async () => {
    if (!upload?.token) return;
    const res = await confirmSkillUpload(upload.token);
    if (fail(res)) return;
    setUpload(null);
    setNotice({ name: upload.name || "Skill", text: CONFIRMATION, tone: "ok" });
    refresh();
  };

  const remove = async (row: SkillRow) => {
    if (armedDelete !== row.name) {
      setArmedDelete(row.name);
      return;
    }
    setArmedDelete(null);
    const res = await deleteSkill(row.name);
    if (fail(res)) return;
    setNotice({ name: row.name, text: DELETE_NOTE, tone: "warn" });
    refresh();
  };

  return (
    <section>
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-[16px] font-semibold">Skills</h2>
          <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
            Reusable instructions the worker can follow in every conversation. Off here means
            off everywhere.
          </p>
        </div>
        {/* One add-action, three doors behind it (SKILLS-SPEC §5): the list is the page. */}
        <div className="relative shrink-0">
          <button
            className={BTN_ACCENT}
            aria-haspopup="menu"
            aria-expanded={addOpen}
            onClick={() => setAddOpen((v) => !v)}
          >
            <span className="inline-flex items-center gap-1.5">
              <Icon name="plus" size={13} /> Add skill
            </span>
          </button>
          {addOpen ? (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setAddOpen(false)} />
              <div
                role="menu"
                className="absolute right-0 top-full mt-1.5 w-80 rounded-xl2 border border-line bg-panel shadow-xl z-20 p-1.5"
                onKeyDown={(e) => e.key === "Escape" && setAddOpen(false)}
              >
                <button
                  role="menuitem"
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-paper"
                  onClick={() => {
                    setAddOpen(false);
                    setEditor(emptyEditor());
                  }}
                >
                  <div className="text-[13px] font-medium">Write it myself</div>
                  <div className="text-[11.5px] text-muted">
                    A name, a description, and the instructions
                  </div>
                </button>
                <button
                  role="menuitem"
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-paper"
                  onClick={() => {
                    setAddOpen(false);
                    fileInput.current?.click();
                  }}
                >
                  <div className="text-[13px] font-medium">Import a file</div>
                  <div className="text-[11.5px] text-muted">
                    A .zip or SKILL.md someone shared — you review before it installs
                  </div>
                </button>
                <button
                  role="menuitem"
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-paper disabled:opacity-40"
                  disabled={!onCreateSkill}
                  onClick={() => {
                    setAddOpen(false);
                    onCreateSkill?.("");
                  }}
                >
                  <div className="text-[13px] font-medium">Create with MimiWork</div>
                  <div className="text-[11.5px] text-muted">
                    Starts a conversation — the worker builds it and asks before adding it to
                    your skills
                  </div>
                </button>
                <button
                  role="menuitem"
                  data-testid="skill-import-claude"
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-paper"
                  onClick={() => {
                    setAddOpen(false);
                    setImportOpen(true);
                    loadImportable();
                  }}
                >
                  <div className="text-[13px] font-medium">Import from Claude Code</div>
                  <div className="text-[11.5px] text-muted">
                    Skills and plugin bundles already on this Mac — same SKILL.md format
                  </div>
                </button>
                <button
                  role="menuitem"
                  data-testid="skill-store-open"
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-paper"
                  onClick={() => {
                    setAddOpen(false);
                    setStoreOpen(true);
                  }}
                >
                  <div className="text-[13px] font-medium">Browse the skill store</div>
                  <div className="text-[11.5px] text-muted">
                    ~7,200 community skills — search and install in one click
                  </div>
                </button>
              </div>
            </>
          ) : null}
        </div>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept=".zip,.md"
        className="hidden"
        aria-label="Upload a skill archive"
        onChange={(e) => {
          onPickFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {importOpen ? (
        <div className={`${CARD} p-4 mb-4`} data-testid="skill-import">
          <div className="flex items-center justify-between mb-2.5">
            <div>
              <div className="text-[13.5px] font-semibold">Import from Claude Code</div>
              <div className="text-[11.5px] text-muted">
                Skills in <code>~/.claude/skills</code> and installed plugins. A skill is a
                folder with a SKILL.md — the same thing here, so nothing is rewritten.
              </div>
            </div>
            <button className={BTN_BORDERED} onClick={() => setImportOpen(false)}>
              Close
            </button>
          </div>
          {importRows === null ? (
            <div className="text-[12px] text-muted py-2">Looking…</div>
          ) : importRows.length === 0 ? (
            <div className="text-[12px] text-muted py-2">
              Nothing found. Claude Code keeps skills in <code>~/.claude/skills</code>.
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {importRows.map((row) => (
                <div
                  key={row.path}
                  className="flex items-center gap-3 px-2.5 py-2 rounded-lg hover:bg-paper"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-medium truncate">{row.name}</div>
                    <div className="text-[11.5px] text-muted truncate">{row.description}</div>
                  </div>
                  <span className="text-[10.5px] px-1.5 py-0.5 rounded-full border border-line text-faint shrink-0">
                    {row.source}
                  </span>
                  <button
                    className={BTN_BORDERED}
                    disabled={row.installed || importBusy === row.path}
                    onClick={async () => {
                      setImportBusy(row.path);
                      const out = await importSkill(row.path);
                      setImportBusy(null);
                      if (!out.ok) {
                        setError(out.error || "Could not import that skill.");
                        return;
                      }
                      setError("");
                      setNotice({ name: row.name, text: CONFIRMATION, tone: "ok" });
                      await refresh();
                      loadImportable();
                    }}
                  >
                    {row.installed ? "Installed" : importBusy === row.path ? "Importing…" : "Import"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {storeOpen ? (
        <div className={`${CARD} p-4 mb-4`} data-testid="skill-store">
          <div className="flex items-center justify-between mb-2.5">
            <div>
              <div className="text-[13.5px] font-semibold">Skill store</div>
              <div className="text-[11.5px] text-muted">
                ~7,200 community skills from three curated GitHub collections — installs are
                pinned to the reviewed version.
              </div>
            </div>
            <button
              className={BTN_BORDERED}
              onClick={() => {
                setStoreOpen(false);
                setStoreFlag(null);
              }}
            >
              Close
            </button>
          </div>
          <input
            className={INPUT}
            placeholder="Search skills… (e.g. seo audit, meeting notes, resume)"
            value={storeQuery}
            autoFocus
            data-testid="skill-store-search"
            onChange={async (e) => {
              const q = e.target.value;
              setStoreQuery(q);
              setStoreFlag(null);
              setStoreResults(q.trim() ? await searchSkillStore(q) : []);
            }}
          />
          {storeFlag ? (
            <div
              className="mt-2.5 rounded-lg border border-amber-400/60 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-[12px]"
              role="alert"
              data-testid="skill-store-flag"
            >
              <div className="font-medium mb-1">“{storeFlag.entry.name}” needs a look first</div>
              <div className="text-muted">{storeFlag.text}</div>
              <div className="mt-1.5 flex gap-2">
                {storeFlag.url ? (
                  <a
                    className="underline underline-offset-2"
                    href={storeFlag.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Review on GitHub
                  </a>
                ) : null}
                <button
                  className="underline underline-offset-2"
                  onClick={async () => {
                    const res = await installStoreSkill(
                      storeFlag.entry.name,
                      storeFlag.entry.repo,
                      true,
                    );
                    setStoreFlag(null);
                    if (!fail(res)) {
                      setNotice({ name: storeFlag.entry.name, text: CONFIRMATION, tone: "ok" });
                      setStoreResults(await searchSkillStore(storeQuery));
                      refresh();
                    }
                  }}
                >
                  Install anyway
                </button>
              </div>
            </div>
          ) : null}
          <div className="mt-2 max-h-80 overflow-y-auto divide-y divide-line">
            {storeResults.map((r) => (
              <div key={`${r.repo}/${r.path}`} className="py-2.5 flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium truncate">{r.name}</span>
                    <span className={BADGE}>{r.repo.split("/")[0]}</span>
                  </div>
                  <div className="text-[11.5px] text-muted line-clamp-2">{r.description}</div>
                </div>
                <button
                  className={`${BTN_BORDERED} disabled:opacity-40`}
                  disabled={r.installed || storeBusy === r.name}
                  data-testid={`skill-store-install-${r.name}`}
                  onClick={async () => {
                    setStoreBusy(r.name);
                    const res = await installStoreSkill(r.name, r.repo);
                    setStoreBusy(null);
                    if (res.flagged) {
                      setStoreFlag({ entry: r, text: res.error || "", url: res.url });
                      return;
                    }
                    if (!fail(res)) {
                      setNotice({ name: r.name, text: CONFIRMATION, tone: "ok" });
                      setStoreResults(await searchSkillStore(storeQuery));
                      refresh();
                    }
                  }}
                >
                  {r.installed ? "Installed" : storeBusy === r.name ? "Installing…" : "Install"}
                </button>
              </div>
            ))}
            {storeQuery.trim() && storeResults.length === 0 ? (
              <div className="py-3 text-[12px] text-muted">No skills match that search.</div>
            ) : null}
          </div>
        </div>
      ) : null}
      {error ? (
        <div className="text-[12.5px] text-red-500 mb-3" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div
          role="status"
          className={
            "mb-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-[12.5px] " +
            (notice.tone === "ok"
              ? "bg-tealSoft/70 text-tealInk border-tealInk/20"
              : "bg-warnSoft/70 text-warnInk border-warnInk/20")
          }
        >
          <span className="min-w-0">
            <b>{notice.name}</b> {notice.text}
          </span>
          <button
            className="ml-auto shrink-0 opacity-60 hover:opacity-100"
            aria-label="Dismiss"
            onClick={() => setNotice(null)}
          >
            ✕
          </button>
        </div>
      ) : null}

      {upload ? (
        <div className={`${CARD} p-4 mb-4`}>
          <div className="text-[13px] font-medium mb-1">Review before installing</div>
          <p className="text-[12.5px] text-muted mb-3">
            Read the instructions — installing a skill means the worker will follow them.
          </p>
          <div className="text-[13px] mb-1">
            <span className="font-medium">{upload.name}</span>
            <span className="text-muted"> — {upload.description || "no description"}</span>
          </div>
          <pre className="text-[12px] bg-paper border border-line rounded-lg p-3 whitespace-pre-wrap max-h-64 overflow-y-auto mb-2">
            {upload.instructions}
          </pre>
          {upload.files?.length ? (
            <div className="text-[12px] text-muted mb-2">
              Bundled files: {upload.files.join(", ")}
            </div>
          ) : null}
          <div className="flex gap-2 mt-3">
            <button className={BTN_ACCENT} onClick={confirmUpload}>
              Install skill
            </button>
            <button className={BTN_BORDERED} onClick={() => setUpload(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {editor ? (
        <div className={`${CARD} p-4 mb-4`}>
          <div className="text-[13px] font-medium mb-3">
            {editor.mode === "new" ? "New skill" : `Edit ${editor.name}`}
          </div>
          <label className={FIELD_LABEL} htmlFor="skill-name">
            Name
          </label>
          <input
            id="skill-name"
            className={`${INPUT} mt-1 mb-3`}
            value={editor.name}
            disabled={editor.mode === "edit"}
            placeholder="weekly-report"
            onChange={(e) => setEditor({ ...editor, name: e.target.value })}
          />
          <label className={FIELD_LABEL} htmlFor="skill-desc">
            Description
          </label>
          <input
            id="skill-desc"
            className={`${INPUT} mt-1 mb-3`}
            value={editor.description}
            placeholder="One line the worker uses to decide when this applies"
            onChange={(e) => setEditor({ ...editor, description: e.target.value })}
          />
          <label className={FIELD_LABEL} htmlFor="skill-instructions">
            Instructions
          </label>
          <textarea
            id="skill-instructions"
            className={`${INPUT} mt-1 mb-3 min-h-[140px] font-mono`}
            value={editor.instructions}
            placeholder={"1. Gather last week's updates\n2. Write the report, under 300 words"}
            onChange={(e) => setEditor({ ...editor, instructions: e.target.value })}
          />
          <div className="flex gap-2 mt-3">
            <button
              className={BTN_ACCENT}
              disabled={!editor.name.trim() || !editor.instructions.trim()}
              onClick={save}
            >
              Save skill
            </button>
            <button className={BTN_BORDERED} onClick={() => setEditor(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <div className={`${CARD} divide-y divide-line`}>
        {rows.length === 0 && !editor ? (
          <div className="p-5 text-[13px] text-muted">
            No skills yet — <b>Add skill</b> teaches your worker its first one, like
            “prepare my Monday status report”.
          </div>
        ) : null}
        {rows.map((row) => (
          <div key={row.name} className="flex items-center gap-3 px-4 py-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-[13px] font-medium ${row.enabled ? "" : "text-muted"}`}>
                  {row.name}
                </span>
                {row.source !== "local" ? <span className={BADGE}>{row.source}</span> : null}
                {/* §6: a rich skill must not look identical to a one-file one. Styled as a
                    chip with a folder icon so it READS as clickable (live drive: plain
                    text hid the affordance). */}
                {row.files ? (
                  <button
                    className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-md border border-line bg-paper text-muted hover:text-ink hover:border-lineStrong shrink-0"
                    title="Show folder"
                    onClick={() => revealSkill(row.name)}
                  >
                    <Icon name="folder" size={11} /> {row.files} file{row.files === 1 ? "" : "s"}
                  </button>
                ) : null}
              </div>
              {/* Full description, wrapping — a skill's one-liner is its menu entry; cutting
                  it mid-word hid what the skill does (live drive). */}
              <div className="text-[12px] text-muted leading-relaxed">{row.description}</div>
            </div>
            <button
              className={BTN_BORDERED}
              title="Edit"
              onClick={() =>
                setEditor({
                  mode: "edit",
                  name: row.name,
                  description: row.description,
                  instructions: row.instructions,
                })
              }
            >
              <Icon name="pencil" size={13} />
            </button>
            <button
              className={BTN_BORDERED}
              aria-label={`Delete ${row.name}`}
              onClick={() => remove(row)}
              onBlur={() => setArmedDelete(null)}
            >
              {armedDelete === row.name ? "Confirm delete" : <Icon name="trash" size={13} />}
            </button>
            <label className="inline-flex items-center gap-1.5 text-[12px] text-muted">
              <input
                type="checkbox"
                role="switch"
                aria-label={`${row.name} enabled`}
                checked={row.enabled}
                onChange={(e) => {
                  const on = e.target.checked;
                  updateSkill(row.name, { enabled: on }).then((res) => {
                    if (!fail(res))
                      setNotice({
                        name: row.name,
                        text: on ? CONFIRMATION : OFF_NOTE,
                        tone: on ? "ok" : "warn",
                      });
                    refresh();
                  });
                }}
              />
              On
            </label>
          </div>
        ))}
      </div>

    </section>
  );
}
