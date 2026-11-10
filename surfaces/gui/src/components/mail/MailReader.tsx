import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getMailMessage,
  getMailThread,
  markMailMessageRead,
  markMailThread,
  saveMailAttachment,
  type MailComment,
  type MailEnvelope,
  type MailMessage,
  type MailThread,
} from "../../api";
import { useT } from "../../i18n";
import { Icon } from "../Icon";
import { MailComments, type Picked } from "./MailComments";
import { MailComposer, MailDraftError } from "./MailComposer";
import { MailFrame } from "./MailFrame";
import { formatMailDate, senderName } from "./MailList";
import { OFFLINE, useMailComments, useMailDraft } from "./mailWork";

/** What the reader is showing: a conversation from the inbox, one message from search, or
 *  a draft by itself. */
export type Opened =
  | { kind: "thread"; key: string }
  | { kind: "message"; folder: string; uid: number }
  | { kind: "draft"; id: string };

const messageId = (m: { folder: string; uid: number }) => `${m.folder}/${m.uid}`;

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** One message. Its body is fetched the first time it is opened, not before. */
function MessageCard({
  folder,
  uid,
  summary,
  open,
  onToggle,
  alone = false,
  comments,
  onSelect,
  chosen,
  onLoaded,
}: {
  folder: string;
  uid: number;
  summary?: MailEnvelope;
  open: boolean;
  onToggle?: () => void;
  /** A search result: shown by itself under its own subject, and marked read by itself.
   *  A conversation has one subject above all its messages and is marked as a whole. */
  alone?: boolean;
  /** The conversation's comments; the ones on this message are highlighted in it. */
  comments: MailComment[];
  /** Told what is selected in this message whenever that changes. */
  onSelect: (messageId: string, quote: string) => void;
  /** The Message-ID of the message holding the selection to comment on, or null. */
  chosen: string | null;
  onLoaded?: (message: MailMessage) => void;
}) {
  const t = useT();
  const [message, setMessage] = useState<MailMessage | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!open || message || error) return;
    let alive = true;
    getMailMessage(folder, uid)
      .then((reply) => {
        if (!alive) return;
        if (!reply.ok) return setError(reply.error || OFFLINE);
        setMessage(reply);
        onLoaded?.(reply);
        if (alone) void markMailMessageRead(folder, uid).catch(() => undefined);
      })
      .catch(() => alive && setError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [open, message, error, folder, uid, alone, onLoaded]);

  const save = async (index: number) => {
    const reply = await saveMailAttachment(folder, uid, index).catch(() => ({ ok: false, error: OFFLINE, path: "" }));
    const note = reply.ok ? `${t("Saved to")} ${reply.path}` : t(reply.error || OFFLINE);
    setSaved((notes) => ({ ...notes, [index]: note }));
  };

  const id = message?.message_id ?? "";
  const quotes = useMemo(() => comments.filter((c) => c.message_id === id).map((c) => c.quote), [comments, id]);
  const select = useCallback((quote: string) => onSelect(id, quote), [onSelect, id]);

  const shown = message ?? summary;
  return (
    <article className={"mail-message" + (open ? " open" : "")} data-testid="mail-message">
      {alone && message && (
        <h2 className="mail-subject mail-subject-alone" data-testid="mail-subject">{message.subject || "—"}</h2>
      )}
      <button className="mail-message-head" onClick={onToggle} disabled={!onToggle} aria-expanded={open}>
        <span className="mail-message-from">{shown ? senderName(shown.from) : ""}</span>
        <span className="mail-message-date">{shown ? formatMailDate(shown.date, true) : ""}</span>
      </button>
      {open && shown && (
        <div className="mail-message-to">
          {t("To")}: {[shown.to, shown.cc].filter(Boolean).join(", ")}
        </div>
      )}
      {open && error && <div className="mail-error" role="alert">{t(error)}</div>}
      {open && !message && !error && <div className="mail-note">{t("Loading…")}</div>}
      {open && message && message.attachments.length > 0 && (
        <ul className="mail-attachments" data-testid="mail-attachments">
          {message.attachments.map((file, index) => (
            <li key={index}>
              <Icon name="file" size={13} />
              <span className="mail-attachment-name">{file.filename}</span>
              <span className="mail-attachment-size">{fileSize(file.size)}</span>
              <button className="btn sm" data-testid="mail-attachment-save" onClick={() => save(index)}>
                {t("Save")}
              </button>
              {saved[index] && (
                <span className="mail-attachment-note" role="status">{saved[index]}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {open && message && <MailFrame html={message.html} text={message.text} quotes={quotes} onSelect={select} chosen={chosen === id} />}
    </article>
  );
}

/** The middle pane and the comments beside it. Give it a `key` that names what is open,
 *  so each opening starts fresh. */
export function MailReader({
  opened,
  canArchive,
  canBin,
  onArchive,
  onBin,
  onUnread,
  onChanged,
  onDrafts,
  onSent,
  onSendFailed,
}: {
  opened: Exclude<Opened, { kind: "draft" }>;
  canArchive: boolean;
  canBin: boolean;
  onArchive: (key: string) => void;
  onBin: (key: string) => void;
  onUnread: (key: string) => void;
  /** The reader changed something the list shows (it marked the conversation read). */
  onChanged: () => void;
  /** A draft was started or discarded, so the Drafts tab is out of date. */
  onDrafts: () => void;
  /** The reply went. `note` is "" unless there is something to add ("no copy in Sent"). */
  onSent: (note: string) => void;
  /** A send failed after this reader was left; here is why. */
  onSendFailed: (reason: string) => void;
}) {
  const t = useT();
  const [thread, setThread] = useState<MailThread | null>(null);
  const [alone, setAlone] = useState<MailMessage | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [picked, setPicked] = useState<Picked | null>(null);
  const key = opened.kind === "thread" ? opened.key : "";

  useEffect(() => {
    if (!key) return;
    let alive = true;
    getMailThread(key)
      .then((reply) => {
        if (!alive) return;
        if (!reply.ok) return setError(reply.error || OFFLINE);
        setThread(reply);
        // Open what has not been read, and always the newest.
        const last = reply.messages.length - 1;
        setExpanded(new Set(reply.messages.filter((m, i) => m.unread || i === last).map(messageId)));
        if (reply.messages.some((m) => m.unread)) {
          void markMailThread(key, true).then(onChanged).catch(() => undefined);
        }
      })
      .catch(() => alive && setError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [key, onChanged]);

  // A search result is one message; its conversation, and the reply to it, are known
  // once it has loaded.
  const conversation = thread?.key ?? alone?.thread_key ?? "";
  const answer =
    thread?.answer ?? (alone ? { folder: alone.folder, uid: alone.uid, message_id: alone.message_id } : null);
  const notes = useMailComments(conversation);
  const work = useMailDraft(thread?.draft ?? alone?.draft ?? "", notes.flush, onSent, onSendFailed);
  // The conversation has moved on since this reply was started.
  const older =
    !!work.draft && !!answer?.message_id && !!work.draft.answers_id && work.draft.answers_id !== answer.message_id;

  const select = useCallback((id: string, quote: string) => {
    // Each message has its own frame and its own selection. The newest selection wins,
    // and a frame that stops having one only clears what was its own.
    setPicked((now) => (quote ? { messageId: id, quote } : now?.messageId === id ? null : now));
  }, []);

  const toggle = (id: string) =>
    setExpanded((now) => {
      const next = new Set(now);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  if (opened.kind === "thread") {
    if (error) return <div className="mail-error" role="alert">{t(error)}</div>;
    if (!thread) return <div className="mail-note">{t("Loading…")}</div>;
  }

  const start = (all: boolean) => answer && void work.start(answer, all).then((made) => made && onDrafts());
  const write = (guidance: string) => answer && void work.write(answer, guidance).then(onDrafts);

  return (
    <div className="mail-work">
      <div className="mail-reader" data-testid="mail-reader">
        {thread && (
          <div className="mail-reader-head">
            <h2 className="mail-subject" data-testid="mail-subject">{thread.subject || "—"}</h2>
            {thread.in_inbox && (
              <div className="mail-actions">
                {canArchive && (
                  <button className="btn sm" data-testid="mail-archive" onClick={() => onArchive(key)}>
                    <Icon name="archive" size={14} /> {t("Archive")}
                  </button>
                )}
                {canBin && (
                  <button className="btn sm" data-testid="mail-bin" onClick={() => onBin(key)}>
                    <Icon name="trash" size={14} /> {t("Move to bin")}
                  </button>
                )}
                <button className="btn sm" data-testid="mail-unread" onClick={() => onUnread(key)}>
                  {t("Mark unread")}
                </button>
              </div>
            )}
          </div>
        )}
        {thread ? (
          thread.messages.map((m) => (
            <MessageCard
              key={messageId(m)}
              folder={m.folder}
              uid={m.uid}
              summary={m}
              open={expanded.has(messageId(m))}
              onToggle={() => toggle(messageId(m))}
              comments={notes.comments}
              onSelect={select}
              chosen={picked?.messageId ?? null}
            />
          ))
        ) : opened.kind === "message" ? (
          // A search result is shown alone. Archive and Bin are not offered: it may already
          // be archived, or sit in a folder Mail does not manage.
          <MessageCard
            folder={opened.folder}
            uid={opened.uid}
            open
            alone
            comments={notes.comments}
            onSelect={select}
            chosen={picked?.messageId ?? null}
            onLoaded={setAlone}
          />
        ) : null}
        <MailDraftError error={work.error} report={work.modelFailed} />
        {work.draft ? (
          <MailComposer
            draft={work.draft}
            busy={work.busy}
            onEdit={work.edit}
            onSend={() => void work.send()}
            onDiscard={() => void work.discard().then((gone) => gone && onDrafts())}
            onRewrite={write}
            older={older}
            onRestore={work.canRestore ? work.restore : undefined}
          />
        ) : (
          answer && (
            <div className="mail-reply-bar">
              <button className="btn sm" data-testid="mail-reply" disabled={work.busy !== ""} onClick={() => start(false)}>
                {t("Reply")}
              </button>
              <button className="btn sm" data-testid="mail-reply-all" disabled={work.busy !== ""} onClick={() => start(true)}>
                {t("Reply all")}
              </button>
            </div>
          )
        )}
      </div>
      {answer && (
        <MailComments
          comments={notes.comments}
          note={notes.note}
          picked={picked}
          ready={notes.loaded}
          writing={work.busy === "writing" || work.busy === "starting"}
          locked={work.busy !== ""}
          error={notes.error}
          onChange={notes.change}
          onWrite={() => write("")}
        />
      )}
    </div>
  );
}
