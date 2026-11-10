import { useState } from "react";
import type { MailComment } from "../../api";
import { useT } from "../../i18n";
import { Icon } from "../Icon";
import type { MailNotes } from "./mailWork";

/** The passage selected in the reader right now, and the message it is in. */
export interface Picked {
  messageId: string;
  quote: string;
}

/** The column beside the email: a comment on each passage that needs an answer, one note
 *  for anything else, and the button that has Mimi write the reply from them. */
export function MailComments({
  comments,
  note,
  picked,
  ready,
  writing,
  locked,
  error,
  onChange,
  onWrite,
}: {
  comments: MailComment[];
  note: string;
  picked: Picked | null;
  /** The saved comments have loaded, so adding to them cannot replace them. */
  ready: boolean;
  writing: boolean;
  /** A reply is being written or sent. Nothing here can change until that has ended: a
   *  note typed during a send would be saved after the send had cleared the comments. */
  locked: boolean;
  error: string;
  onChange: (next: MailNotes) => void;
  onWrite: () => void;
}) {
  const t = useT();
  // Pressing a button can clear the selection in the email before the click arrives. What
  // was selected when the press began is held until the press ends, and is what gets
  // commented on.
  const [held, setHeld] = useState<Picked | null>(null);
  const [fresh, setFresh] = useState(-1);
  const from = held ?? picked;
  const taken = !!from && comments.some((c) => c.message_id === from.messageId && c.quote === from.quote);
  const canWrite = !!note.trim() || comments.some((c) => c.note.trim());

  const add = () => {
    setHeld(null);
    if (!from || taken) return;
    setFresh(comments.length);
    onChange({ comments: [...comments, { message_id: from.messageId, quote: from.quote, note: "" }], note });
  };
  const setNote = (index: number, value: string) =>
    onChange({ comments: comments.map((c, i) => (i === index ? { ...c, note: value } : c)), note });
  const remove = (index: number) => {
    setFresh(-1);
    onChange({ comments: comments.filter((_, i) => i !== index), note });
  };

  return (
    <aside className="mail-side" data-testid="mail-comments" aria-label={t("Comments")}>
      <h3 className="mail-side-title">{t("Comments")}</h3>
      <p className="mail-side-hint">{t("Select text in the email, then press Comment.")}</p>
      <button
        className="btn sm"
        data-testid="mail-comment-add"
        disabled={!ready || locked || !from || taken}
        onPointerDown={() => setHeld(picked)}
        onPointerLeave={() => setHeld(null)}
        onPointerCancel={() => setHeld(null)}
        onClick={add}
      >
        {t("Comment")}
      </button>
      {comments.map((comment, index) => (
        <div className="mail-comment" key={index} data-testid="mail-comment">
          {/* The sender's words, not the app's: never run through the translator. */}
          <blockquote className="mail-comment-quote" data-no-translate>{comment.quote}</blockquote>
          <textarea
            className="tmpl-input mail-comment-note"
            data-testid="mail-comment-note"
            rows={2}
            autoFocus={index === fresh}
            disabled={locked}
            maxLength={4000}
            placeholder={t("What should the reply say about this?")}
            aria-label={t("What should the reply say about this?")}
            value={comment.note}
            onChange={(event) => setNote(index, event.target.value)}
          />
          <button
            className="mail-comment-remove"
            data-testid="mail-comment-remove"
            aria-label={`${t("Remove comment")}: ${comment.quote.slice(0, 60)}`}
            title={t("Remove comment")}
            disabled={locked}
            onClick={() => remove(index)}
          >
            <Icon name="trash" size={13} />
          </button>
        </div>
      ))}
      <label className="mail-side-label">
        {t("Anything else the reply should say")}
        <textarea
          className="tmpl-input mail-comment-note"
          data-testid="mail-free-note"
          rows={2}
          disabled={!ready || locked}
          maxLength={4000}
          value={note}
          onChange={(event) => onChange({ comments, note: event.target.value })}
        />
      </label>
      {error && <div className="mail-error" role="alert" data-testid="mail-comments-error">{t(error)}</div>}
      <button className="btn-primary" data-testid="mail-write-reply" disabled={!canWrite || locked} onClick={onWrite}>
        {writing ? t("Writing the reply…") : t("Write reply")}
      </button>
      {!canWrite && (
        <p className="mail-side-hint" data-testid="mail-write-hint">
          {t("Add a note to a comment, or write one here, and Mimi can write the reply.")}
        </p>
      )}
    </aside>
  );
}
