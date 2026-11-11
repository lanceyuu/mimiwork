import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  archiveMailThread,
  binMailThread,
  createMailDraft,
  getMailDrafts,
  getMailStatus,
  getMailThreads,
  markMailThread,
  putMailSettings,
  searchMail,
  syncMail,
  type MailDraft,
  type MailEnvelope,
  type MailReply,
  type MailStatus,
  type MailThreadRow,
} from "../../api";
import { useT } from "../../i18n";
import { Icon } from "../Icon";
import { MailDraftPane } from "./MailComposer";
import { formatMailDate, MailList, type MailRow } from "./MailList";
import { MailReader, type Opened } from "./MailReader";
import { MailSortingOffer, MailSortingSettings } from "./MailSorting";

const POLL_MS = 2000;
const SYNC_EVERY_MS = 120_000;
const OFFLINE = "Could not reach MimiWork. Try again.";

type Tab = "all" | "needs_reply" | "fyi" | "newsletters" | "drafts";
const SORTED: Tab[] = ["needs_reply", "fyi", "newsletters"];
const TAB_NAMES: Record<Tab, string> = {
  all: "All",
  needs_reply: "Needs reply",
  fyi: "FYI",
  newsletters: "Newsletters",
  drafts: "Drafts",
};
const draftRow = (id: string) => `draft/${id}`;
const openedId = (opened: Opened | null): string =>
  !opened
    ? ""
    : opened.kind === "thread"
      ? opened.key
      : opened.kind === "draft"
        ? draftRow(opened.id)
        : `${opened.folder}/${opened.uid}`;

/** The Mail section: the connected mailbox's inbox, a reader, and search. */
export function MailView({ onOpenConnectors }: { onOpenConnectors: () => void }) {
  const t = useT();
  const [status, setStatus] = useState<MailStatus | null>(null);
  const [threads, setThreads] = useState<MailThreadRow[]>([]);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MailEnvelope[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [picked, setTab] = useState<Tab>("all");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [drafts, setDrafts] = useState<MailDraft[]>([]);
  // One line above the reader: that a message went, or why something could not be done
  // when the place that would have said so is no longer on screen.
  const [notice, setNotice] = useState<{ text: string; bad: boolean } | null>(null);
  const draftsRun = useRef(0);
  const revision = useRef(-1);
  const lastSync = useRef(0);
  const searchRun = useRef(0);

  const refresh = useCallback(async (force = false): Promise<MailStatus | null> => {
    const next = await getMailStatus().catch(() => null);
    if (!next) return null;
    setStatus(next);
    if (next.connected && (force || next.revision !== revision.current)) {
      const rows = await getMailThreads().catch(() => null);
      // A list that failed to load is asked for again on the next tick.
      revision.current = rows ? next.revision : -1;
      if (rows) setThreads(rows);
    }
    return next;
  }, []);

  const startSync = useCallback(() => {
    lastSync.current = Date.now();
    void syncMail()
      .then(() => refresh())
      .catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    let alive = true;
    void refresh(true).then((now) => {
      if (alive && now?.connected) startSync();
    });
    // ponytail: asks for status every two seconds for as long as Mail is open, and syncs
    // every two minutes. Move to a pushed event if the polling is ever seen to cost anything.
    const timer = window.setInterval(() => {
      void refresh().then((now) => {
        const due = Date.now() - lastSync.current > SYNC_EVERY_MS;
        if (alive && now?.connected && !now.syncing && due) startSync();
      });
    }, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [refresh, startSync]);

  const reload = useCallback(() => void refresh(true), [refresh]);

  const loadDrafts = useCallback(() => {
    const run = (draftsRun.current += 1);
    void getMailDrafts()
      // An answer overtaken by a later request is dropped, or a draft just discarded
      // would come back into the list.
      .then((rows) => run === draftsRun.current && setDrafts(rows))
      .catch(() => undefined);
  }, []);
  useEffect(loadDrafts, [loadDrafts]);
  // While the Drafts tab is open its rows follow what is being typed in the editor.
  // ponytail: asked for again every two seconds. Have the editor say when it has saved
  // if this is ever seen to cost anything.
  useEffect(() => {
    if (picked !== "drafts") return;
    const timer = window.setInterval(loadDrafts, POLL_MS);
    return () => window.clearInterval(timer);
  }, [picked, loadDrafts]);

  // `from` names the reader that sent. If the user has moved on to something else by the
  // time the answer comes, what they are reading now is left open.
  const sent = useCallback(
    (from: string, note: string) => {
      setOpened((now) => (openedId(now) === from ? null : now));
      setNotice({ text: t(note || "Sent."), bad: false });
      loadDrafts();
      reload();
    },
    [loadDrafts, reload, t],
  );
  // Only reached when the reader that was sending has been left: say it here, and say
  // where the message is, because nothing else on screen will.
  const sendFailed = useCallback(
    (reason: string) => {
      setNotice({ text: `${t("Your message was not sent.")} ${t(reason)} ${t("It is under Drafts.")}`, bad: true });
      loadDrafts();
    },
    [loadDrafts, t],
  );

  const newMessage = async () => {
    const reply = await createMailDraft().catch(() => null);
    if (!reply?.ok || !reply.draft) return setNotice({ text: t(reply?.error || OFFLINE), bad: true });
    setNotice(null);
    setTab("drafts");
    setOpened({ kind: "draft", id: reply.draft.id });
    loadDrafts();
  };

  // The list changes first so it answers at once. If the server refuses, the reload
  // brings the row back and it carries the reason.
  const change = async (key: string, call: () => Promise<MailReply>, leavesList: boolean) => {
    setOpened(null);
    if (leavesList) setThreads((rows) => rows.filter((row) => row.key !== key));
    const reply = await call().catch((): MailReply => ({ ok: false, error: OFFLINE }));
    setRowErrors((errors) => {
      const next = { ...errors };
      if (reply.ok) delete next[key];
      else next[key] = t(reply.error || OFFLINE);
      return next;
    });
    // If this reload cannot reach the sidecar either, the next tick must still fetch the
    // list, or a row taken out a moment ago would stay missing.
    revision.current = -1;
    await refresh(true);
  };

  const clearSearch = () => {
    searchRun.current += 1;
    setSearching(false);
    setQuery("");
    setResults(null);
    setSearchError("");
    setOpened(null);
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const words = query.trim();
    if (!words) return clearSearch();
    const run = (searchRun.current += 1);
    setSearching(true);
    setSearchError("");
    setOpened(null);
    const reply = await searchMail(words).catch(() => ({ ok: false, error: OFFLINE, results: [] }));
    // An answer to a search that has since been replaced, or left, is dropped.
    if (run !== searchRun.current) return;
    setSearching(false);
    setResults(reply.ok ? (reply.results ?? []) : []);
    if (!reply.ok) setSearchError(t(reply.error || OFFLINE));
  };

  if (!status) return <main className="app-page mail-page" data-testid="mail-page" />;

  // The sorted tabs exist only while sorting is on. If it is turned off while one of them
  // is showing, the list falls back to the whole inbox.
  const tabs: Tab[] = status.sorting ? ["all", ...SORTED, "drafts"] : ["all", "drafts"];
  const tab: Tab = tabs.includes(picked) ? picked : "all";

  const answerOffer = async (on: boolean) => {
    const reply = await putMailSettings({ sorting: on }).catch(() => null);
    if (!reply?.ok) setNotice({ text: t(reply?.error || OFFLINE), bad: true });
    await refresh(true);
    if (reply?.ok && on) startSync();
  };

  if (!status.connected) {
    return (
      <main className="app-page mail-page" data-testid="mail-page">
        <div className="mail-welcome" data-testid="mail-not-connected">
          <h2>{t("Mail")}</h2>
          <p>{t("Mail reads the mailbox you connect under Connectors, Email.")}</p>
          <p>{t("Sign-in for Gmail and Outlook is on its way. A personal Gmail works today with an app password.")}</p>
          <button className="btn-primary" data-testid="mail-open-connectors" onClick={onOpenConnectors}>
            {t("Open Connectors")}
          </button>
        </div>
      </main>
    );
  }

  const rows: MailRow[] = results
    ? results.map((r) => ({
        id: `${r.folder}/${r.uid}`,
        sender: r.from,
        subject: r.subject,
        date: r.date,
        unread: r.unread,
        has_attachments: r.has_attachments,
        folder: r.folder,
      }))
    : tab === "drafts"
      ? drafts.map((d) => ({
          id: draftRow(d.id),
          sender: d.to || t("No recipient yet"),
          subject: d.subject,
          date: d.updated_at,
          unread: false,
        }))
      : threads
          .filter((row) => tab === "all" || row.category === tab)
          .map((row) => ({ ...row, id: row.key, error: rowErrors[row.key] }));

  const open = (id: string) => {
    setNotice(null);
    const draft = results ? undefined : drafts.find((d) => draftRow(d.id) === id);
    if (draft) {
      // A reply is shown with the conversation it answers while that is still in the
      // inbox; otherwise, and for a new message, the draft is shown by itself.
      const inInbox = draft.thread_key && threads.some((row) => row.key === draft.thread_key);
      return setOpened(inInbox ? { kind: "thread", key: draft.thread_key } : { kind: "draft", id: draft.id });
    }
    // Opening a row is the user having seen why its last change failed.
    setRowErrors((errors) => {
      if (!(id in errors)) return errors;
      const next = { ...errors };
      delete next[id];
      return next;
    });
    const result = results?.find((r) => `${r.folder}/${r.uid}` === id);
    setOpened(result ? { kind: "message", folder: result.folder, uid: result.uid } : { kind: "thread", key: id });
  };

  const syncLine = status.syncing
    ? t("Syncing…")
    : status.last_sync
      ? `${t("Last synced")} ${formatMailDate(status.last_sync)}`
      : "";
  const empty = searching
    ? t("Searching…")
    : results
      ? t("Nothing found.")
      : tab === "drafts"
        ? t("No drafts.")
        : t("No mail here yet.");

  return (
    <main className="app-page mail-page" data-testid="mail-page">
      <div className="app-head">
        <div className="app-head-text">
          <span className="app-title">{t("Mail")}</span>
          <span className="app-desc" data-testid="mail-sync-line">
            {[status.address, syncLine].filter(Boolean).join(" · ")}
          </span>
        </div>
        <form className="mail-search" role="search" onSubmit={search}>
          <input
            className="tmpl-input"
            type="search"
            data-testid="mail-search"
            placeholder={t("Search mail")}
            aria-label={t("Search mail")}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              if (!event.target.value && results) clearSearch();
            }}
          />
        </form>
        <div className="app-head-actions">
          <button className="btn sm" data-testid="mail-new" onClick={() => void newMessage()}>
            <Icon name="pencil" size={14} /> {t("New message")}
          </button>
          <button className="btn sm" data-testid="mail-sorting" aria-expanded={settingsOpen} onClick={() => setSettingsOpen((now) => !now)}>
            {t("Sorting")}
          </button>
          <button className="btn sm" data-testid="mail-refresh" disabled={status.syncing} onClick={startSync}>
            <Icon name="refresh" size={14} /> {t("Refresh")}
          </button>
        </div>
      </div>
      {status.last_error && (
        <div className="mail-error mail-banner" role="alert" data-testid="mail-error">
          {status.last_error}{" "}
          <button className="mail-inline-link" onClick={onOpenConnectors}>{t("Open Connectors")}</button>
        </div>
      )}
      <div className="mail-body">
        <div className="mail-list-pane">
          {results ? (
            <div className="mail-search-head">
              <span>{t("Search results")}</span>
              <button className="mail-inline-link" data-testid="mail-search-clear" onClick={clearSearch}>
                {t("Back to inbox")}
              </button>
            </div>
          ) : (
            <div className="mail-tabs">
              {tabs.map((name) => (
                <button
                  key={name}
                  aria-pressed={tab === name}
                  className={"mail-tab" + (tab === name ? " active" : "")}
                  data-testid={`mail-tab-${name}`}
                  onClick={() => {
                    setTab(name);
                    setOpened(null);
                    if (name === "drafts") loadDrafts();
                  }}
                >
                  {t(TAB_NAMES[name])}
                  {name === "drafts" && drafts.length > 0 ? <span className="mail-tab-count">{drafts.length}</span> : null}
                </button>
              ))}
            </div>
          )}
          {!results && !status.sorting_asked && <MailSortingOffer onAnswer={(on) => void answerOffer(on)} />}
          {/* A search that failed shows why in place of results, not "Nothing found." */}
          {searchError ? (
            <div className="mail-error" role="alert" data-testid="mail-search-error">{searchError}</div>
          ) : (
            <MailList rows={searching ? [] : rows} selected={openedId(opened)} onOpen={open} empty={empty} />
          )}
        </div>
        <div className="mail-reader-pane">
          {settingsOpen && (
            // Opened afresh when sorting changes elsewhere (the offer above the list), so
            // its switch never shows a state that is no longer true.
            <MailSortingSettings
              key={String(status.sorting)}
              onChanged={() => void refresh(true)}
              onClose={() => setSettingsOpen(false)}
            />
          )}
          {notice && (
            <div
              className={notice.bad ? "mail-error mail-notice" : "mail-note mail-notice"}
              role={notice.bad ? "alert" : "status"}
              data-testid="mail-notice"
            >
              {notice.text}
            </div>
          )}
          {opened?.kind === "draft" ? (
            <MailDraftPane
              key={openedId(opened)}
              id={opened.id}
              onSent={(note) => sent(draftRow(opened.id), note)}
              onSendFailed={sendFailed}
              onClosed={() => {
                setOpened(null);
                loadDrafts();
              }}
            />
          ) : opened ? (
            <MailReader
              key={openedId(opened)}
              opened={opened}
              canArchive={status.can_archive}
              canBin={status.can_bin}
              onArchive={(key) => change(key, () => archiveMailThread(key), true)}
              onBin={(key) => change(key, () => binMailThread(key), true)}
              onUnread={(key) => change(key, () => markMailThread(key, false), false)}
              onChanged={reload}
              onDrafts={loadDrafts}
              onSent={(note) => sent(openedId(opened), note)}
              onSendFailed={sendFailed}
            />
          ) : notice ? null : (
            <div className="mail-placeholder">{t("Select a conversation to read it.")}</div>
          )}
        </div>
      </div>
    </main>
  );
}
