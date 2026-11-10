import { useEffect, useRef, useState } from "react";
import type { MailDraft, MailDraftFields } from "../../api";
import { useT } from "../../i18n";
import { ConfirmDialog } from "../ConfirmDialog";
import { ReportProblem } from "../ReportProblem";
import { senderName } from "./MailList";
import { useMailDraft, type MailBusy } from "./mailWork";

/** Why the last thing asked of a draft did not happen. */
export function MailDraftError({ error, report }: { error: string; report: boolean }) {
  const t = useT();
  if (!error) return null;
  return (
    <div className="mail-error" role="alert" data-testid="mail-draft-error">
      {t(error)}
      {report && <ReportProblem error={error} context="mail reply" />}
    </div>
  );
}

/** The draft editor, for a reply and for a new message. It holds nothing itself: every
 *  keystroke goes to `onEdit`, which saves it. */
export function MailComposer({
  draft,
  busy,
  onEdit,
  onSend,
  onDiscard,
  onRewrite,
  older = false,
  onRestore,
}: {
  draft: MailDraft;
  busy: MailBusy;
  onEdit: (fields: MailDraftFields) => void;
  onSend: () => void;
  onDiscard: () => void;
  /** Have Mimi write the reply again, with one line on how. A reply only. */
  onRewrite?: (guidance: string) => void;
  /** The conversation has a newer message than the one this reply answers. */
  older?: boolean;
  /** Put back what was in the editor before Mimi wrote over it; absent when there is nothing to put back. */
  onRestore?: () => void;
}) {
  const t = useT();
  const [guidance, setGuidance] = useState("");
  const [asking, setAsking] = useState(false);
  const box = useRef<HTMLElement>(null);
  // It opens beneath the conversation, which can be below the bottom of the window.
  useEffect(() => box.current?.scrollIntoView?.({ block: "nearest" }), []);
  const locked = busy !== "";
  const field = (name: "to" | "cc" | "subject", label: string) => (
    <label className="mail-field">
      <span>{label}</span>
      <input
        className="tmpl-input"
        data-testid={`mail-draft-${name}`}
        disabled={locked}
        value={draft[name]}
        onChange={(event) => onEdit({ [name]: event.target.value })}
      />
    </label>
  );

  return (
    <section ref={box} className="mail-composer" data-testid="mail-composer" aria-label={draft.reply ? t("Reply") : t("New message")}>
      {draft.interrupted && (
        <div className="mail-error" role="alert" data-testid="mail-draft-interrupted">
          {t("A send was interrupted. Check Sent before sending again.")}
        </div>
      )}
      {draft.reply && draft.answers && (
        <div className="mail-composer-answers">
          {t("In reply to")} <span data-no-translate>{senderName(draft.answers)}</span>
        </div>
      )}
      {older && (
        <div className="mail-note mail-composer-older" role="status" data-testid="mail-draft-older">
          {t("This reply answers an earlier message in the conversation. To answer the newest one, discard it and start again.")}
        </div>
      )}
      {field("to", t("To"))}
      {field("cc", t("Cc"))}
      {field("subject", t("Subject"))}
      <textarea
        className="tmpl-input mail-draft-body"
        data-testid="mail-draft-body"
        rows={10}
        disabled={locked}
        aria-label={t("Message")}
        value={draft.body}
        onChange={(event) => onEdit({ body: event.target.value })}
      />
      {draft.reply && (
        <p className="mail-side-hint">{t("The original message will be quoted beneath your reply.")}</p>
      )}
      <div className="mail-composer-actions">
        <button className="btn-primary" data-testid="mail-send" disabled={locked || !draft.to.trim()} onClick={onSend}>
          {busy === "sending" ? t("Sending…") : t("Send")}
        </button>
        <button className="btn sm" data-testid="mail-discard" disabled={locked} onClick={() => setAsking(true)}>
          {t("Discard")}
        </button>
        {onRewrite && (
          <form
            className="mail-rewrite"
            onSubmit={(event) => {
              event.preventDefault();
              onRewrite(guidance);
            }}
          >
            <input
              className="tmpl-input"
              data-testid="mail-rewrite-guidance"
              disabled={locked}
              maxLength={200}
              placeholder={t("How should it change? Shorter, warmer…")}
              aria-label={t("How should it change? Shorter, warmer…")}
              value={guidance}
              onChange={(event) => setGuidance(event.target.value)}
            />
            <button className="btn sm" data-testid="mail-rewrite" disabled={locked}>
              {busy === "writing" ? t("Writing the reply…") : t("Rewrite")}
            </button>
          </form>
        )}
        {onRestore && (
          <button className="mail-inline-link" data-testid="mail-restore" disabled={locked} onClick={onRestore}>
            {t("Put back what I had written")}
          </button>
        )}
      </div>
      {asking && (
        <ConfirmDialog
          title={t("Discard this draft?")}
          body={t("It will be deleted from MimiWork. Nothing has been sent.")}
          confirmLabel={t("Discard")}
          onConfirm={() => {
            setAsking(false);
            onDiscard();
          }}
          onCancel={() => setAsking(false)}
        />
      )}
    </section>
  );
}

// A draft opened by itself has no comments column, so no comments waiting to be saved.
const nothingToSave = async () => true;

/** A draft opened by itself from the Drafts tab: a new message, or a reply whose
 *  conversation is no longer in the inbox. */
export function MailDraftPane({
  id,
  onSent,
  onSendFailed,
  onClosed,
}: {
  id: string;
  onSent: (note: string) => void;
  onSendFailed: (reason: string) => void;
  /** The draft was discarded. */
  onClosed: () => void;
}) {
  const t = useT();
  const work = useMailDraft(id, nothingToSave, onSent, onSendFailed);
  const answer = { folder: "", uid: 0, message_id: "" };
  return (
    <div className="mail-reader" data-testid="mail-draft-pane">
      <MailDraftError error={work.error} report={work.modelFailed} />
      {work.draft ? (
        <MailComposer
          draft={work.draft}
          busy={work.busy}
          onEdit={work.edit}
          onSend={() => void work.send()}
          onDiscard={() => void work.discard().then((gone) => gone && onClosed())}
          // The comments made on the conversation are still kept, so the reply can be rewritten.
          onRewrite={work.draft.reply ? (guidance) => void work.write(answer, guidance) : undefined}
          onRestore={work.canRestore ? work.restore : undefined}
        />
      ) : (
        !work.error && <div className="mail-note">{t("Loading…")}</div>
      )}
    </div>
  );
}
