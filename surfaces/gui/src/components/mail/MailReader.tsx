import { useEffect, useState } from "react";
import {
  getMailMessage,
  getMailThread,
  markMailMessageRead,
  markMailThread,
  saveMailAttachment,
  type MailEnvelope,
  type MailMessage,
  type MailThread,
} from "../../api";
import { useT } from "../../i18n";
import { Icon } from "../Icon";
import { MailFrame } from "./MailFrame";
import { formatMailDate, senderName } from "./MailList";

/** What the reader is showing: a conversation from the inbox, or one message from search. */
export type Opened =
  | { kind: "thread"; key: string }
  | { kind: "message"; folder: string; uid: number };

const OFFLINE = "Could not reach MimiWork. Try again.";
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
}: {
  folder: string;
  uid: number;
  summary?: MailEnvelope;
  open: boolean;
  onToggle?: () => void;
  /** A search result: shown by itself under its own subject, and marked read by itself.
   *  A conversation has one subject above all its messages and is marked as a whole. */
  alone?: boolean;
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
        if (alone) void markMailMessageRead(folder, uid).catch(() => undefined);
      })
      .catch(() => alive && setError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [open, message, error, folder, uid, alone]);

  const save = async (index: number) => {
    const reply = await saveMailAttachment(folder, uid, index).catch(() => ({ ok: false, error: OFFLINE, path: "" }));
    const note = reply.ok ? `${t("Saved to")} ${reply.path}` : t(reply.error || OFFLINE);
    setSaved((notes) => ({ ...notes, [index]: note }));
  };

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
      {open && message && <MailFrame html={message.html} text={message.text} />}
    </article>
  );
}

/** The middle pane. Give it a `key` that names what is open, so each opening starts fresh. */
export function MailReader({
  opened,
  canArchive,
  canBin,
  onArchive,
  onBin,
  onUnread,
  onChanged,
}: {
  opened: Opened;
  canArchive: boolean;
  canBin: boolean;
  onArchive: (key: string) => void;
  onBin: (key: string) => void;
  onUnread: (key: string) => void;
  /** The reader changed something the list shows (it marked the conversation read). */
  onChanged: () => void;
}) {
  const t = useT();
  const [thread, setThread] = useState<MailThread | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
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

  if (opened.kind === "message") {
    // A search result is shown alone. Archive and Bin are not offered: it may already be
    // archived, or sit in a folder Mail does not manage.
    return (
      <div className="mail-reader" data-testid="mail-reader">
        <MessageCard folder={opened.folder} uid={opened.uid} open alone />
      </div>
    );
  }
  if (error) return <div className="mail-error" role="alert">{t(error)}</div>;
  if (!thread) return <div className="mail-note">{t("Loading…")}</div>;

  const toggle = (id: string) =>
    setExpanded((now) => {
      const next = new Set(now);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <div className="mail-reader" data-testid="mail-reader">
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
      {thread.messages.map((m) => (
        <MessageCard
          key={messageId(m)}
          folder={m.folder}
          uid={m.uid}
          summary={m}
          open={expanded.has(messageId(m))}
          onToggle={() => toggle(messageId(m))}
        />
      ))}
    </div>
  );
}
