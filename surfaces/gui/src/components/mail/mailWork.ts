// What the reader keeps for a conversation besides its mail: the comments, and the draft
// of the reply. Both are saved as they are typed.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createMailDraft,
  deleteMailDraft,
  getMailComments,
  getMailDraft,
  putMailComments,
  sendMailDraft,
  updateMailDraft,
  writeMailReply,
  type MailComment,
  type MailDraft,
  type MailDraftFields,
  type MailReply,
} from "../../api";

export const OFFLINE = "Could not reach MimiWork. Try again.";
const SAVE_AFTER_MS = 600;
// What a call that never reached the sidecar is taken to have answered.
const offline = (): MailReply & { draft?: undefined; text?: undefined; note?: undefined } => ({
  ok: false,
  error: OFFLINE,
});

/** Save a value a moment after it last changed. `flush` saves at once and answers only
 *  when nothing is on its way or waiting any more, saying whether everything is saved.
 *  Leaving the screen flushes.
 *
 *  Saves go out one at a time, in the order they were made, so an older one can never
 *  land on top of a newer one. One that fails is kept and tried again with the next save,
 *  unless something newer has been typed since, or `drop` was called, or what is being
 *  saved has changed (a different draft): then it is let go, because writing it later
 *  would put old text over new, or into the wrong place. */
export function useAutosave<T>(save: (value: T) => Promise<MailReply>) {
  const waiting = useRef<{ value: T; turn: number } | null>(null);
  // Counts what has been handed over to be saved, so a failed save can tell whether
  // anything newer has been handed over since.
  const turns = useRef(0);
  const timer = useRef(0);
  const last = useRef<Promise<boolean>>(Promise.resolve(true));
  // Moves whenever what is waiting, or on its way, stops belonging here.
  const era = useRef(0);
  const [error, setError] = useState("");

  const flush = useCallback((): Promise<boolean> => {
    window.clearTimeout(timer.current);
    const taken = waiting.current;
    waiting.current = null;
    const born = era.current;
    last.current = last.current.then(async () => {
      // Nothing new to save, but an earlier save may have failed and been put back.
      const next = taken ?? (born === era.current ? waiting.current : null);
      if (!next) return true;
      if (next === waiting.current) waiting.current = null;
      const reply = await save(next.value).catch(offline);
      if (born !== era.current) return reply.ok;
      if (!reply.ok && next.turn === turns.current) waiting.current = next;
      setError(reply.ok ? "" : reply.error || OFFLINE);
      return reply.ok;
    });
    return last.current;
  }, [save]);

  const queue = useCallback(
    (value: T) => {
      turns.current += 1;
      waiting.current = { value, turn: turns.current };
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush(), SAVE_AFTER_MS);
    },
    [flush],
  );

  /** Forget what is waiting or on its way: what it belonged to was sent or discarded. */
  const drop = useCallback(() => {
    window.clearTimeout(timer.current);
    waiting.current = null;
    era.current += 1;
    setError("");
  }, []);

  // When the screen is left, or what is being saved changes, what is waiting is saved to
  // where it belongs, and anything that fails after that is let go.
  useEffect(
    () => () => {
      void flush();
      era.current += 1;
    },
    [flush],
  );
  return { queue, flush, drop, error };
}

export interface MailNotes {
  comments: MailComment[];
  note: string;
}

/** A conversation's comments and free note. Until they have loaded nothing can be added,
 *  because saving is always the whole list and would replace what is stored. */
export function useMailComments(key: string) {
  const [notes, setNotes] = useState<MailNotes | null>(null);
  const [loadError, setLoadError] = useState("");
  const save = useCallback((value: MailNotes) => putMailComments(key, value.comments, value.note), [key]);
  const { queue, flush, error } = useAutosave(save);

  useEffect(() => {
    if (!key) return;
    let alive = true;
    getMailComments(key)
      .then((reply) => {
        if (!alive) return;
        if (!reply.ok) return setLoadError(reply.error || OFFLINE);
        setNotes({ comments: reply.comments ?? [], note: reply.note ?? "" });
      })
      .catch(() => alive && setLoadError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [key]);

  const change = useCallback(
    (next: MailNotes) => {
      setNotes(next);
      queue(next);
    },
    [queue],
  );

  return {
    comments: notes?.comments ?? [],
    note: notes?.note ?? "",
    loaded: notes !== null,
    error: loadError || error,
    change,
    flush,
  };
}

export type MailBusy = "" | "starting" | "writing" | "sending";
/** The message a reply answers. */
export interface MailAnswer {
  folder: string;
  uid: number;
  message_id: string;
}

/** The draft being written: a reply to a conversation, or a new message. `id` is the
 *  draft to open, or "" when there is none yet. `saveNotes` saves the conversation's
 *  comments at once and says whether it could: before Mimi reads them, and before a send
 *  clears them. `onSent` is told when the message has gone. `onSendFailed` is told why a
 *  send failed only when the screen that asked for it has been left, since nothing there
 *  can show the reason any more. */
export function useMailDraft(
  id: string,
  saveNotes: () => Promise<boolean>,
  onSent: (note: string) => void,
  onSendFailed: (reason: string) => void,
) {
  const [draft, setDraft] = useState<MailDraft | null>(null);
  const [busy, setBusy] = useState<MailBusy>("");
  const [error, setError] = useState("");
  // The last failure was Mimi not writing, which is worth reporting; a bad address is not.
  const [modelFailed, setModelFailed] = useState(false);
  // What the editor held before Mimi last wrote over it, so it can be put back.
  const [before, setBefore] = useState<string | null>(null);
  const here = useRef(true);
  const draftId = draft?.id ?? "";
  const save = useCallback((fields: MailDraftFields) => updateMailDraft(draftId, fields), [draftId]);
  const saver = useAutosave(save);

  useEffect(() => {
    here.current = true;
    return () => {
      here.current = false;
    };
  }, []);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    getMailDraft(id)
      .then((reply) => {
        if (!alive) return;
        if (reply.ok && reply.draft) setDraft(reply.draft);
        else setError(reply.error || OFFLINE);
      })
      .catch(() => alive && setError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [id]);

  const fail = (reason: string | undefined, model = false) => {
    setBusy("");
    setError(reason || OFFLINE);
    setModelFailed(model);
  };

  const edit = (fields: MailDraftFields) => {
    if (!draft) return;
    const next = { ...draft, ...fields };
    setDraft(next);
    saver.queue({ to: next.to, cc: next.cc, subject: next.subject, body: next.body });
  };

  /** Start the reply to a message. Gives back the draft, or null with `error` set. */
  const start = async (answer: MailAnswer, replyAll = false): Promise<MailDraft | null> => {
    setBusy("starting");
    setError("");
    const reply = await createMailDraft({ folder: answer.folder, uid: answer.uid, reply_all: replyAll }).catch(offline);
    if (!reply.ok || !reply.draft) {
      fail(reply.error);
      return null;
    }
    setBusy("");
    setDraft(reply.draft);
    return reply.draft;
  };

  /** Have Mimi write the reply from the comments. With no draft yet, or with one left
   *  empty on an earlier message of the conversation, the reply is started for `answer`. */
  const write = async (answer: MailAnswer, guidance = "") => {
    const stale = !!draft && !draft.body.trim() && !!answer.message_id && draft.answers_id !== answer.message_id;
    const started = !draft || stale;
    const target = started ? await start(answer) : draft;
    if (!target) return;
    setBusy("writing");
    setError("");
    // What was just typed must be saved first: the comments, because Mimi reads the saved
    // ones, and the draft, because a save still waiting would put the old text back over
    // hers. If either cannot be saved, she is not asked.
    const saved = await Promise.all([saveNotes(), saver.flush()]);
    if (!saved.every(Boolean)) return fail(OFFLINE);
    const reply = await writeMailReply(target.id, guidance).catch(offline);
    if (!reply.ok || !reply.text) {
      if (started) {
        // A reply started only to be written, and not written, is not left under Drafts.
        await deleteMailDraft(target.id).catch(offline);
        setDraft(null);
      }
      return fail(reply.error, true);
    }
    const body = reply.text;
    setBefore(target.body.trim() ? target.body : null);
    setDraft((now) => (now ? { ...now, body } : now));
    const kept = await updateMailDraft(target.id, { body }).catch(offline);
    if (!kept.ok) return fail(kept.error);
    setBusy("");
  };

  /** Put back what the editor held before Mimi wrote over it. */
  const restore = () => {
    if (before === null) return;
    edit({ body: before });
    setBefore(null);
  };

  const send = async () => {
    if (!draft) return;
    setBusy("sending");
    setError("");
    // Never send text older than what is on screen. The comments are saved too: sending
    // clears them, and one still waiting to be saved would come back afterwards.
    const saved = await Promise.all([saveNotes(), saver.flush()]);
    if (!saved.every(Boolean)) return fail(OFFLINE);
    const reply = await sendMailDraft(draft.id).catch(offline);
    if (!reply.ok) {
      if (!here.current) onSendFailed(reply.error || OFFLINE);
      return fail(reply.error);
    }
    saver.drop();
    setBusy("");
    onSent(reply.note || "");
  };

  /** Delete the draft. Says whether it is gone. */
  const discard = async (): Promise<boolean> => {
    if (!draft) return false;
    saver.drop();
    const reply = await deleteMailDraft(draft.id).catch(offline);
    if (!reply.ok) {
      fail(reply.error);
      return false;
    }
    setDraft(null);
    setBefore(null);
    return true;
  };

  return {
    draft,
    busy,
    error: error || saver.error,
    modelFailed: modelFailed && !!error,
    canRestore: before !== null,
    edit,
    start,
    write,
    restore,
    send,
    discard,
  };
}
