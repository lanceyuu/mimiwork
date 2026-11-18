import { useState, type KeyboardEvent } from "react";
import { getMailMessage, getMailThread } from "../../api";
import { useT } from "../../i18n";
import type { Attachment } from "../../types";
import type { Opened } from "./MailReader";
import { OFFLINE } from "./mailWork";

/** What a question can be about: the conversation, or the one search result, that is open. */
export type MailAbout = Exclude<Opened, { kind: "draft" }>;

// ponytail: the newest twenty messages and 150,000 characters, which fits in the one text
// file a chat accepts (200,000). If long conversations are seen to be cut short, leave the
// older messages for Mimi to fetch with her own mail tools.
const MAX_MESSAGES = 20;
const MAX_CHARS = 150_000;
const RULE = "\n\n----------\n\n";

/** The open conversation as one text file for the chat: each message with who wrote it, to
 *  whom and when, oldest first. Read through the same calls the reader makes, so nothing
 *  reaches the chat that is not already on screen. Throws with a reason fit to show. */
async function conversation(about: MailAbout): Promise<Attachment> {
  let subject = "";
  let places: { folder: string; uid: number }[] = [about as { folder: string; uid: number }];
  if (about.kind === "thread") {
    const thread = await getMailThread(about.key);
    if (!thread.ok) throw new Error(thread.error || OFFLINE);
    subject = thread.subject;
    places = thread.messages.slice(-MAX_MESSAGES);
  }
  const parts: string[] = [];
  for (const place of places) {
    const message = await getMailMessage(place.folder, place.uid);
    if (!message.ok) throw new Error(message.error || OFFLINE);
    subject ||= message.subject;
    const head = [
      `From: ${message.from}`,
      `To: ${message.to}`,
      message.cc ? `Cc: ${message.cc}` : "",
      `Date: ${new Date(message.date * 1000).toISOString()}`,
      message.attachments.length ? `Attached: ${message.attachments.map((file) => file.filename).join(", ")}` : "",
    ].filter(Boolean);
    parts.push(`${head.join("\n")}\n\n${message.text.trim()}`);
  }
  // Too long to hand over whole: the oldest messages go first, the newest is kept.
  while (parts.length > 1 && parts.join(RULE).length > MAX_CHARS) parts.shift();
  const name = subject.replace(/[\\/:*?"<>|\u0000-\u001f]/g, " ").trim().slice(0, 80) || "Email";
  return {
    kind: "text",
    name: `${name}.txt`,
    mime: "text/plain",
    text: `Email conversation: ${subject}\n\n${parts.join(RULE)}`.slice(0, MAX_CHARS),
  };
}

/** Ask Mimi a question from Mail. The answer comes in a new chat: with a conversation open
 *  the chat is handed that conversation; with none open Mimi is told to look in the mailbox,
 *  which she does with the mail tools a chat already has. Nothing is sent or changed. */
export function MailAsk({
  about,
  onAsk,
  onClose,
}: {
  about: MailAbout | null;
  onAsk: (text: string, attachments?: Attachment[]) => void;
  onClose: () => void;
}) {
  const t = useT();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ask = async () => {
    const words = question.trim();
    if (!words || busy) return;
    if (!about) return onAsk(`${words}\n\n${t("Look in my mailbox to answer this.")}`);
    setBusy(true);
    setError("");
    try {
      onAsk(words, [await conversation(about)]);
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  const key = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter while a word is still being composed (Chinese, Japanese) picks the word.
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void ask();
  };

  return (
    <section className="mail-settings mail-ask" data-testid="mail-ask-panel" aria-label={t("Ask Mimi")}>
      <div className="mail-settings-head">
        <strong>{t("Ask Mimi")}</strong>
        <button className="mail-inline-link" data-testid="mail-ask-close" onClick={onClose}>{t("Close")}</button>
      </div>
      <textarea
        className="tmpl-input mail-comment-note"
        data-testid="mail-ask-question"
        rows={2}
        autoFocus
        aria-label={t("Your question")}
        placeholder={t(about ? "What do you want to know about this conversation?" : "What do you want to know about your mail?")}
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={key}
      />
      <div className="mail-composer-actions">
        <button className="btn-primary" data-testid="mail-ask-send" disabled={!question.trim() || busy} onClick={() => void ask()}>
          {t(busy ? "Opening…" : "Ask")}
        </button>
        <span className="mail-side-hint" data-testid="mail-ask-scope">
          {t(
            about
              ? "Mimi will read the conversation you have open and answer in a new chat."
              : "Mimi will look in your mailbox and answer in a new chat. Open a conversation first to ask about that one.",
          )}
        </span>
      </div>
      {error && <div className="mail-error" role="alert" data-testid="mail-ask-error">{t(error)}</div>}
    </section>
  );
}
