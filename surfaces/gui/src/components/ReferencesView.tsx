import { useEffect, useState } from "react";
import { applyReferenceFixes, checkReferences, type RefCheck, type RefCode, type RefEntry, type RefFix } from "../api";
import { getLang, useT } from "../i18n";
import { openExternal } from "../tauri";

// The References tab (spec 2026-11-07). Its rule: never call a real paper wrong and never
// make an entry worse. So nothing runs before a click, a fix Mimi cannot write safely is
// shown for the researcher to copy, and an entry no index lists is "not found", not fake.

type Tr = (s: string) => string;
const fill = (s: string, vars: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
const plural = (t: Tr, n: number, one: string, many: string) => fill(t(n === 1 ? one : many), { n });

const GROUPS: { key: RefEntry["group"]; label: string }[] = [
  { key: "retracted", label: "Retracted" },
  { key: "fix", label: "Needs a fix" },
  { key: "not_found", label: "Not found" },
  { key: "couldnt", label: "Couldn't check" },
  { key: "verified", label: "Verified" },
];

const ERRORS: Record<string, string> = {
  scan: "This PDF is a scan with no text Mimi can read.",
  no_list: "Mimi couldn't find a reference list in this file.",
  read_failed: "Couldn't read the reference list. Try again.",
  unreadable: "Mimi couldn't open this file.",
  no_folder: "This conversation has no folder.",
  busy: "Wait until Mimi has finished, then try again.",
  changed: "The file changed since the check. Check again.",
  open_in_word:
    "Close the file in Word first, or Word will overwrite the fixes when it saves. If Word is closed, open and close the file once to clear the leftover lock.",
  read_only: "This folder is read-only, so Mimi can't write to the file.",
  write_failed: "Mimi couldn't write the fixes. The file is unchanged.",
};
const SOMETHING = "Something went wrong. Try again.";

const LOCALE: Record<string, string> = { en: "en-GB", zh: "zh-CN", no: "nb-NO", fr: "fr-FR", es: "es-ES", ja: "ja-JP", ar: "ar", de: "de-DE", pt: "pt-PT" };

export function describeCode(c: RefCode, t: Tr): string {
  const p = c.params || {};
  const years = Array.isArray(p.years) ? (p.years as number[]).join(", ") : "";
  const year = typeof p.year === "number" ? p.year : 0;
  switch (c.code) {
    case "retracted":
      if (p.via === "openalex") return t("Retracted (OpenAlex)");
      return year ? fill(t("Retracted in {year}"), { year }) : t("Retracted");
    case "partly_retracted":
      return year ? fill(t("Partly retracted in {year}"), { year }) : t("Partly retracted");
    case "doi_other_paper":
      return fill(t("The DOI leads to a different paper: {title}"), { title: String(p.title ?? "") });
    case "doi_not_found":
      return t("The DOI does not exist.");
    case "doi_unfixable":
      return t("The DOI is wrong, and Mimi found no published record to take the right one from.");
    case "doi_missing":
      return t("No DOI. The Crossref record has one.");
    case "surname_differs":
      return fill(t("The first author is spelled {surname} in the record."), { surname: String(p.surname ?? "") });
    case "title_differs":
      return t("The title differs from the record.");
    case "edition":
      return p.book
        ? fill(t("The record is from {years}: possibly another edition."), { years })
        : fill(t("The year differs from the record ({years})."), { years });
    case "year_differs":
      return fill(t("The record's year is {years}, often a preprint or online-first year."), { years });
    case "concern":
      return t("The journal published an expression of concern.");
    case "outside_crossref":
      return p.agency ? fill(t("Found on {agency}."), { agency: String(p.agency) }) : t("Found in another DOI registry.");
    case "found_openalex":
      return t("Found on OpenAlex.");
    case "found_copy":
      return t("Found as a preprint or posted version; details not compared with a published record.");
    case "retracted_maybe":
      return t("OpenAlex lists a retracted paper with this title.");
    case "chapter_doi":
      return fill(t("The DOI is the book's. The chapter has its own: {doi}"), { doi: String(p.doi ?? "") });
    case "not_found":
      return t("Mimi couldn't find this in Crossref or OpenAlex. Books, reports and work in some languages are often not listed there.");
    case "lookup_failed":
      return t("The lookup failed. Check again later.");
    case "no_title":
      return t("No title to look up.");
    case "openalex_limit":
      return t("OpenAlex's free daily limit was reached before this entry.");
    default:
      return c.code;
  }
}

function fixLabel(f: RefFix, t: Tr): string {
  if (f.kind === "replace_doi") return fill(t("Replace the DOI with {doi}"), { doi: f.new });
  if (f.kind === "add_doi") return fill(t("Add the DOI {doi}"), { doi: f.new.trim() });
  return fill(t("Change the surname to {surname}"), { surname: f.new });
}

function Copy({ text }: { text: string }) {
  const t = useT();
  const [done, setDone] = useState(false);
  return (
    <button
      className="link refs-copy"
      onClick={() => {
        void navigator.clipboard?.writeText(text);
        setDone(true);
      }}
    >
      {done ? t("Copied") : t("Copy")}
    </button>
  );
}

function Suggestion({ label, text }: { label: string; text: string }) {
  return (
    <div className="refs-suggestion">
      <span className="refs-suggestion-label">{label}</span>
      <p className="refs-suggestion-text" data-no-translate>{text}</p>
      <Copy text={text} />
    </div>
  );
}

function Item({ entry, canWrite, ticks, onTick }: { entry: RefEntry; canWrite: boolean; ticks: Set<string>; onTick: (id: string) => void }) {
  const t = useT();
  const notice = entry.codes.find((c) => c.code === "retracted" || c.code === "partly_retracted")?.params.notice;
  return (
    <li className={`refs-item refs-${entry.group}`} data-testid="refs-item">
      {/* data-no-translate: the frame's DOM translation must never rewrite a reference. */}
      <p className="refs-entry" title={entry.text} data-no-translate>{entry.text}</p>
      {entry.codes.map((c, i) => (
        <p key={i} className="refs-note">{describeCode(c, t)}</p>
      ))}
      {entry.fixes.map((f) =>
        canWrite && f.writable ? (
          <label key={f.id} className="refs-fix">
            <input type="checkbox" checked={ticks.has(f.id)} onChange={() => onTick(f.id)} /> {fixLabel(f, t)}
          </label>
        ) : (
          <Suggestion key={f.id} label={fixLabel(f, t)} text={f.after} />
        ),
      )}
      {canWrite && entry.layout && (
        <p className="refs-note refs-dim">{t("This entry has a link or layout Mimi can't edit safely. Copy the fix into Word.")}</p>
      )}
      {entry.suggestions.map((s, i) => (
        <Suggestion key={`s${i}`} label={t("The record's reference")} text={s.text} />
      ))}
      <div className="refs-links">
        {entry.record?.link && (
          <button className="link" onClick={() => openExternal(entry.record!.link)}>{t("Open the record")}</button>
        )}
        {typeof notice === "string" && notice && (
          <button className="link" onClick={() => openExternal(`https://doi.org/${notice}`)}>{t("Open the notice")}</button>
        )}
        {entry.group === "not_found" && (
          <button
            className="link"
            onClick={() => openExternal(`https://scholar.google.com/scholar?q=${encodeURIComponent(entry.title || entry.text)}`)}
          >
            {t("Search Google Scholar")}
          </button>
        )}
      </div>
    </li>
  );
}

export function ReferencesView({
  sessionId,
  path,
  isWord,
  onWritten,
}: {
  sessionId: string;
  path: string;
  isWord: boolean;
  onWritten?: () => Promise<void> | void;
}) {
  const t = useT();
  const [result, setResult] = useState<RefCheck | null>(null);
  const [pending, setPending] = useState(false);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState("");
  const [written, setWritten] = useState<number | null>(null);
  const [ticks, setTicks] = useState<Set<string>>(new Set());
  const [showVerified, setShowVerified] = useState(false);

  const adopt = (r: RefCheck) => {
    setResult(r);
    setTicks(new Set((r.entries || []).flatMap((e) => e.fixes.filter((f) => f.writable && f.ticked).map((f) => f.id))));
  };

  // A saved result for this exact file shows at once; nothing is checked, or charged,
  // until the researcher asks. The caller keys this component by path.
  useEffect(() => {
    let live = true;
    checkReferences(sessionId, path, { cachedOnly: true })
      .then((r) => {
        if (live && r.ok) adopt(r);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [sessionId, path]);

  const run = async (fresh: boolean) => {
    setPending(true);
    setError("");
    try {
      const r = await checkReferences(sessionId, path, fresh ? { fresh: true } : {});
      if (r.ok) {
        adopt(r);
        setWritten(null);
      } else setError(ERRORS[r.error || ""] || SOMETHING);
    } catch {
      setError(SOMETHING);
    } finally {
      setPending(false);
    }
  };

  const managed = result?.managed || null;
  const canWrite = isWord && result?.kind !== "pdf" && !managed;

  const write = async () => {
    if (!result?.hash) return;
    setWriting(true);
    setError("");
    try {
      const r = await applyReferenceFixes(sessionId, path, result.hash, [...ticks]);
      if (r.ok) {
        setWritten(r.applied ?? ticks.size);
        setResult(null); // the file has a new version now; its old result no longer applies
        await onWritten?.();
      } else setError(ERRORS[r.error || ""] || SOMETHING);
    } catch {
      setError(SOMETHING);
    } finally {
      setWriting(false);
    }
  };

  const checkButton = (label: string, fresh: boolean) => (
    <button className="btn sm" disabled={pending} onClick={() => void run(fresh)}>
      {pending ? t("Checking references…") : t(label)}
    </button>
  );

  if (!result) {
    return (
      <div className="refs-view refs-empty" data-testid="refs-view">
        <p>
          {written != null
            ? plural(
                t,
                written,
                "1 fix written as tracked changes. Accept or reject it in Word (Review, Track Changes). Check again to confirm.",
                "{n} fixes written as tracked changes. Accept or reject them in Word (Review, Track Changes). Check again to confirm.",
              )
            : t("Mimi reads the reference list and looks up each entry in Crossref and OpenAlex.")}
        </p>
        {checkButton(written != null ? "Check again" : "Check references", false)}
        {error && <p className="rail-error">{t(error)}</p>}
      </div>
    );
  }

  const c = result.counts || { total: 0, verified: 0, fix: 0, not_found: 0, retracted: 0, couldnt: 0 };
  const entries = result.entries || [];
  const parts = [
    c.verified && fill(t("{n} verified"), { n: c.verified }),
    c.fix && plural(t, c.fix, "1 needs a fix", "{n} need a fix"),
    c.not_found && fill(t("{n} not found"), { n: c.not_found }),
    c.retracted && fill(t("{n} retracted"), { n: c.retracted }),
    c.couldnt && fill(t("{n} couldn't be checked"), { n: c.couldnt }),
  ].filter(Boolean);
  const date = new Date((result.checked_at || 0) * 1000).toLocaleDateString(LOCALE[getLang()] || "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const writableCount = canWrite ? entries.reduce((n, e) => n + e.fixes.filter((f) => f.writable).length, 0) : 0;

  return (
    <div className="refs-view" data-testid="refs-view">
      <div className="refs-head">
        <span className="refs-dim">{fill(t("Checked on {date}"), { date })}</span>
        {checkButton("Check again", true)}
      </div>
      <p className="refs-summary">
        {plural(t, c.total, "1 reference", "{n} references")}: {parts.join(", ")}.
      </p>
      {!!result.unread && <p className="refs-note">{plural(t, result.unread, "1 entry couldn't be read.", "{n} entries couldn't be read.")}</p>}
      {(!!result.not_checked || result.cut) && <p className="refs-note">{t("The list was too long to check whole; the end was not checked.")}</p>}
      {managed && isWord && (
        <p className="refs-banner">
          {managed === "Word's bibliography"
            ? t("This list is made by Word's bibliography tool. Fix the sources in Word (References, Manage Sources), then update the bibliography.")
            : fill(t("This list is made by {tool}. Fix the entries in {tool}, then refresh the bibliography in Word."), { tool: t(managed) })}
        </p>
      )}
      {!isWord && <p className="refs-banner">{t("PDFs can't be edited here. Fix the source file, then check again.")}</p>}
      {GROUPS.map((g) => {
        const items = entries.filter((e) => e.group === g.key);
        if (!items.length) return null;
        const folded = g.key === "verified" && !showVerified;
        return (
          <section key={g.key} className={`refs-group refs-group-${g.key}`} data-testid={`refs-group-${g.key}`}>
            {g.key === "verified" ? (
              <button className="refs-group-head refs-fold" aria-expanded={showVerified} onClick={() => setShowVerified((v) => !v)}>
                {t(g.label)} ({items.length})
              </button>
            ) : (
              <h4 className="refs-group-head">
                {t(g.label)} ({items.length})
              </h4>
            )}
            {!folded && (
              <ol className="refs-list">
                {items.map((e) => (
                  <Item
                    key={e.id}
                    entry={e}
                    canWrite={canWrite}
                    ticks={ticks}
                    onTick={(id) =>
                      setTicks((prev) => {
                        const next = new Set(prev);
                        if (next.has(id)) next.delete(id);
                        else next.add(id);
                        return next;
                      })
                    }
                  />
                ))}
              </ol>
            )}
          </section>
        );
      })}
      {canWrite && writableCount > 0 && (
        <div className="refs-actions">
          <button className="btn-primary sm" disabled={writing || ticks.size === 0} onClick={() => void write()}>
            {writing ? t("Writing…") : plural(t, ticks.size, "Write 1 fix into the Word file", "Write {n} fixes into the Word file")}
          </button>
        </div>
      )}
      {error && <p className="rail-error">{t(error)}</p>}
    </div>
  );
}
