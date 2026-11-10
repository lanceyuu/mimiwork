import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "../../i18n";
import { openExternal } from "../../tauri";
import { contentHeight, disarmEmail, focusedAddress, isParsed, releaseFocus, stillArmed } from "./disarm";
import { clearSelection, markQuotes, selectedText } from "./quote";

const MAX_HEIGHT = 20_000;
// How many times the frame may grow to fit its email. An email sized to its own window
// ("min-height: 100vh" plus padding) is a little taller every time the frame is made to
// fit it; after this many rounds the frame stops following and scrolls instead.
const MAX_GROWTHS = 12;
const REMOTE_IMAGE = /<img[^>]+src\s*=\s*["']?https?:|url\(\s*["']?https?:/i;
const HIDDEN_MARKS = /[\u0000-\u001f\u007f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

/** How a link's address is shown, and whether the app will hand it to the browser. An
 *  address is shown as the browser itself reads it, so characters that reorder text or
 *  look like other letters cannot make it pass for another site. Only web and mail
 *  addresses can be opened; anything else is shown, with no button. */
export function linkTarget(address: string): { shown: string; openable: boolean } {
  try {
    const url = new URL(address);
    if (["http:", "https:", "mailto:"].includes(url.protocol)) return { shown: url.href, openable: true };
  } catch {
    // Not a full address (a bare "#top", say): shown as written, never opened.
  }
  return { shown: address.replace(HIDDEN_MARKS, ""), openable: false };
}

/** One email, shown as it was sent, in a frame where nothing can run, load or navigate. */
export function MailFrame({
  html,
  text,
  quotes = [],
  onSelect,
  chosen = false,
}: {
  html: string;
  text: string;
  /** Passages to highlight: the ones the user has commented on. Each is one line of text. */
  quotes?: string[];
  /** Told what the reader has selected in the email whenever it changes; "" for nothing.
   *  Give it a function that stays the same between renders. */
  onSelect?: (text: string) => void;
  /** This email holds the selection the reader will comment on. When another email takes
   *  it over, this one lets go of its own. */
  chosen?: boolean;
}) {
  const t = useT();
  const frame = useRef<HTMLIFrameElement>(null);
  const growths = useRef(0);
  const tallest = useRef(80);
  const [images, setImages] = useState(false);
  const safe = useMemo(() => disarmEmail(html, { images }), [html, images]);
  // Which document passed, or failed, the look from outside. Held as the document itself,
  // so a new email, or Show images, starts unchecked again.
  const [checked, setChecked] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [height, setHeight] = useState(80);
  const [link, setLink] = useState("");
  const ready = safe !== null && checked === safe;

  useEffect(() => {
    if (safe === null) return;
    growths.current = 0;
    // Scripts are off inside the frame, so a listener added there never fires. The app
    // asks from outside instead, four times a second.
    const timer = window.setInterval(() => {
      const doc = frame.current?.contentDocument;
      if (!doc || !isParsed(doc)) return;
      // Looked at as soon as it has been read, not when its last image arrives: with Show
      // images on, one slow picture would otherwise keep the whole email hidden.
      if (stillArmed(doc)) return setRefused(safe);
      setChecked(safe);
      const wanted = Math.min(MAX_HEIGHT, Math.max(80, contentHeight(doc)));
      if (wanted > tallest.current && growths.current < MAX_GROWTHS) {
        growths.current += 1;
        tallest.current = wanted;
        setHeight(wanted);
      }
      setLink(focusedAddress(doc));
    }, 250);
    return () => window.clearInterval(timer);
  }, [safe]);

  // Each quote is one line, so the list can be compared, and kept, as text.
  const quoted = quotes.join("\n");
  // The quotes the shown email was last marked with; null until it has been marked once.
  const marked = useRef<string | null>(null);
  const wasChosen = useRef(false);
  useEffect(() => {
    if (!ready) return;
    const shown = () => {
      const doc = frame.current?.contentDocument;
      return doc && isParsed(doc) ? doc : null;
    };
    let pending = true;
    const mark = (doc: Document) => {
      pending = false;
      try {
        markQuotes(doc, quoted ? quoted.split("\n") : []);
      } catch {
        // An email built to break the marking costs its highlights, never the app.
        return;
      }
      // Marking rebuilds the text it touches, which leaves the selection stretched over
      // words the reader never chose. When the quotes have changed, a comment was just
      // added or removed and the selection has done its work, so it is let go. Not the
      // first time an email is marked: the reader may already be selecting in it.
      if (marked.current !== null && marked.current !== quoted) clearSelection(doc);
      marked.current = quoted;
    };
    // At once, so a new comment's passage lights up with the press, not a moment later.
    const now = shown();
    if (now) mark(now);
    // Each email has its own selection, and a webview may keep them all. Once the reader
    // has selected in another email, what is still selected here would look chosen and
    // not be, and selecting the same words here again would not count as a change.
    if (now && wasChosen.current && !chosen) clearSelection(now);
    wasChosen.current = chosen;
    // Unknown at first, so the first look always reports, even "nothing selected".
    let picked: string | null = null;
    // Asked from outside on a timer, like everything else about a shown email.
    const timer = window.setInterval(() => {
      const doc = shown();
      if (!doc) return;
      if (pending) mark(doc);
      const text = selectedText(doc);
      if (text !== picked) {
        picked = text;
        onSelect?.(text);
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, [ready, quoted, onSelect, chosen]);

  if (safe === null || refused === safe) {
    return (
      <div data-testid="mail-plain">
        <p className="mail-note">{t("This message could not be shown safely, so here is its text.")}</p>
        <pre className="mail-plain">{text}</pre>
      </div>
    );
  }

  const target = ready && link ? linkTarget(link) : null;
  return (
    <div className="mail-frame-wrap">
      {target && (
        <div className="mail-link-card" role="status" data-testid="mail-link-card">
          <span className="mail-link-label">{t("This link goes to")}</span>
          <span className="mail-link-address" data-testid="mail-link-address">{target.shown}</span>
          {target.openable && (
            <button className="btn sm" data-testid="mail-link-open" onClick={() => openExternal(target.shown)}>
              {t("Open in browser")}
            </button>
          )}
          <button
            className="btn sm"
            onClick={() => {
              // Letting go of the link is what closes the card, so clicking the same link
              // again shows it again.
              const doc = frame.current?.contentDocument;
              if (doc) releaseFocus(doc);
              setLink("");
            }}
          >
            {t("Close")}
          </button>
        </div>
      )}
      {!images && REMOTE_IMAGE.test(html) && (
        <button className="btn sm mail-show-images" data-testid="mail-show-images" onClick={() => setImages(true)}>
          {t("Show images")}
        </button>
      )}
      <iframe
        // A new frame for each document, so a check can never vouch for the wrong one.
        key={safe}
        ref={frame}
        className="mail-frame"
        data-testid="mail-frame"
        title={t("Message")}
        // These two go together and must never be changed apart. `allow-same-origin` is
        // what lets the app read the frame from outside; it is safe only because, with no
        // `allow-scripts`, nothing inside the frame can run to use it.
        sandbox="allow-same-origin"
        srcDoc={safe}
        // Hidden until it has been looked at from outside, so nothing can be clicked first.
        style={{ height, visibility: ready ? "visible" : "hidden" }}
      />
    </div>
  );
}
