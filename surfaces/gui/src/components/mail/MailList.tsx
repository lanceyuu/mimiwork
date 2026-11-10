import { useT } from "../../i18n";
import { Icon } from "../Icon";

/** One row of the list: a conversation, or a search result. */
export interface MailRow {
  id: string;
  sender: string;
  subject: string;
  date: number;
  unread: boolean;
  count?: number;
  has_attachments?: boolean;
  /** Where a search result sits, shown because it may not be the inbox. */
  folder?: string;
  /** Why the last archive, bin or mark on this row did not go through. */
  error?: string;
}

/** "Ana Lopez <ana@example.com>" as "Ana Lopez"; a bare address stays as it is. */
export function senderName(from: string): string {
  const named = from.match(/^\s*"?([^"<]*?)"?\s*<[^>]*>\s*$/);
  return (named && named[1].trim()) || from.replace(/[<>]/g, "").trim();
}

/** Seconds since 1970 as a time today, a day this year, or a full date. */
export function formatMailDate(seconds: number, long = false): string {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  const now = new Date();
  if (long) return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString(
    undefined,
    sameYear ? { month: "short", day: "numeric" } : { year: "numeric", month: "short", day: "numeric" },
  );
}

export function MailList({
  rows,
  selected,
  onOpen,
  empty,
}: {
  rows: MailRow[];
  selected: string;
  onOpen: (id: string) => void;
  empty: string;
}) {
  const t = useT();
  if (!rows.length) {
    return <div className="mail-list-empty" data-testid="mail-list-empty">{empty}</div>;
  }
  return (
    <ul className="mail-list" data-testid="mail-list">
      {rows.map((row) => (
        <li key={row.id}>
          <button
            className={"mail-row" + (row.unread ? " unread" : "") + (row.id === selected ? " selected" : "")}
            data-testid="mail-row"
            aria-current={row.id === selected ? "true" : undefined}
            onClick={() => onOpen(row.id)}
          >
            <span className="mail-row-top">
              <span className="mail-row-dot" aria-hidden="true" />
              {row.unread ? <span className="sr-only">{t("Unread")}</span> : null}
              <span className="mail-row-sender">{senderName(row.sender)}</span>
              {row.count && row.count > 1 ? <span className="mail-row-count">{row.count}</span> : null}
              {row.has_attachments ? (
                <span className="mail-row-clip" title={t("Has an attachment")}>
                  <Icon name="file" size={12} />
                  <span className="sr-only">{t("Has an attachment")}</span>
                </span>
              ) : null}
              <span className="mail-row-date">{formatMailDate(row.date)}</span>
            </span>
            <span className="mail-row-subject">{row.subject || "—"}</span>
            {row.folder ? <span className="mail-row-folder">{row.folder}</span> : null}
            {row.error ? <span className="mail-row-error" role="alert">{row.error}</span> : null}
          </button>
        </li>
      ))}
    </ul>
  );
}
