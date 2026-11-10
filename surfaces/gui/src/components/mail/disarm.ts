// An email is untrusted HTML. The reader's rule is that nothing in it ever runs, loads or
// navigates, and the app acts on it only from outside. The sandboxed frame stops scripts
// and forms; this file stops the two things the sandbox does not: a clicked link, which
// would load a remote page inside the reader, and remote content, which tells the sender
// the email was opened. It works on a parsed copy that runs and loads nothing, so the
// frame only ever receives the inert result.

// The sandbox already refuses forms; `form-action` says so a second time, because it is
// the one fetch a `default-src` does not cover.
export const MAIL_CSP = (images: boolean): string =>
  `default-src 'none'; img-src data:${images ? " https:" : ""}; style-src 'unsafe-inline'; form-action 'none'`;

// Each of these can run, load a page, hand a link its address after the document has
// loaded, or be read differently by two parsers: a `template` can become a shadow root
// the app cannot look into, an SVG animation can set `href` on a link with no script at
// all, and `noscript` is markup to one parser and text to another.
const DROP =
  "script, noscript, base, template, iframe, frame, frameset, object, embed, " +
  "animate, set, animateMotion, animateTransform";
const POLICY = 'meta[http-equiv="Content-Security-Policy"]';
// An element carrying one of these names answers in place of the document's own property
// of that name: <img name="head"> becomes `document.head`.
const NAMED = "form[name], img[name]";
// What a person clicks. Anything else with an address (a stylesheet link, an SVG image)
// only loads, so its address is dropped, not kept.
const LINKS = new Set(["a", "area"]);

// Because of those names, nothing here reads a property off an email's document or its
// elements. It calls the real one, taken from the prototype, which an email cannot reach.
export const own = <T>(proto: object, name: string) => {
  const read = Object.getOwnPropertyDescriptor(proto, name)!.get!;
  return (target: unknown): T => read.call(target);
};
const rootOf = own<HTMLElement | null>(Document.prototype, "documentElement");
const headOf = own<HTMLHeadElement | null>(Document.prototype, "head");
const focusOf = own<Element | null>(Document.prototype, "activeElement");
const tagOf = own<string>(Element.prototype, "localName");
const markupOf = own<string>(Element.prototype, "outerHTML");
const heightOf = own<number>(Element.prototype, "scrollHeight");
const urlOf = own<string>(Document.prototype, "URL");
const stateOf = own<string>(Document.prototype, "readyState");
const all = (doc: Document, selector: string): Element[] =>
  Array.from(Document.prototype.querySelectorAll.call(doc, selector));
const names = (el: Element): string[] => Element.prototype.getAttributeNames.call(el);
const read = (el: Element, name: string): string | null => Element.prototype.getAttribute.call(el, name);
const write = (el: Element, name: string, value: string): void =>
  Element.prototype.setAttribute.call(el, name, value);
const strip = (el: Element, name: string): void => Element.prototype.removeAttribute.call(el, name);
// "href", and the SVG spelling "xlink:href".
const isAddress = (name: string): boolean => name === "href" || name.endsWith(":href");

/** True unless a document is exactly the inert shape `disarmEmail` gives back. */
export function stillArmed(doc: Document): boolean {
  if (all(doc, `${DROP}, ${NAMED}, meta[http-equiv]:not(${POLICY})`).length) return true;
  // The policy is what keeps remote content out, so it must be there, once, and first.
  if (all(doc, POLICY).length !== 1 || all(doc, `head > ${POLICY}:first-child`).length !== 1) return true;
  return all(doc, "*").some((el) => names(el).some(isAddress));
}

/** The email as an inert document for a frame's `srcdoc`, or null when it cannot be
 *  made inert, in which case the reader shows its plain text. */
export function disarmEmail(html: string, opts: { images?: boolean } = {}): string | null {
  const doc = new DOMParser().parseFromString(html, "text/html");
  all(doc, `${DROP}, meta[http-equiv]`).forEach((el) => Element.prototype.remove.call(el));
  all(doc, NAMED).forEach((el) => strip(el, "name"));
  for (const el of all(doc, "*")) {
    // An email may not plant an address where the app looks for one, or pass one of its
    // own elements off as a highlight the app made (see quote.ts).
    strip(el, "data-mail-href");
    strip(el, "data-mail-comment");
    for (const name of names(el)) {
      if (!isAddress(name)) continue;
      const address = read(el, name) ?? "";
      strip(el, name);
      if (!LINKS.has(tagOf(el))) continue;
      write(el, "data-mail-href", address);
      write(el, "tabindex", "0");
    }
  }
  const head = headOf(doc);
  const root = rootOf(doc);
  if (!head || !root) return null;
  const policy = Document.prototype.createElement.call(doc, "meta");
  write(policy, "http-equiv", "Content-Security-Policy");
  write(policy, "content", MAIL_CSP(!!opts.images));
  Element.prototype.prepend.call(head, policy);
  const out = "<!doctype html>" + markupOf(root);
  // Writing a document out and reading it back can rebuild it differently. Read it back
  // the way the frame will, and refuse the email if anything armed has reappeared.
  return stillArmed(new DOMParser().parseFromString(out, "text/html")) ? null : out;
}

// -- reading a shown email from outside ---------------------------------------------------
// Scripts are off inside the frame, so listeners the app adds there never fire. The app
// asks instead, on a timer, with these.

/** The address of the link that has focus in a shown email, or "". */
export function focusedAddress(doc: Document): string {
  const el = focusOf(doc);
  return (el && read(el, "data-mail-href")) || "";
}

/** How tall the email is, so the frame can be sized to it and the page scrolls, not the frame.
 *  The scroll height, because an email that sizes itself to its window ("height: 100%")
 *  reports only the frame's own height any other way. */
export function contentHeight(doc: Document): number {
  const root = rootOf(doc);
  return root ? heightOf(root) : 0;
}

/** True once the frame holds the email itself, read to the end. Its remote images may
 *  still be on their way: with Show images on, waiting for the last of them would keep
 *  the whole email hidden behind one slow picture. */
export function isParsed(doc: Document): boolean {
  return urlOf(doc) === "about:srcdoc" && stateOf(doc) !== "loading";
}

/** Take focus off the focused link, which is how the address card is closed. */
export function releaseFocus(doc: Document): void {
  const el = focusOf(doc);
  if (!el) return;
  // An HTML link and an SVG link each have their own `blur`, and each refuses the other's.
  for (const proto of [HTMLElement.prototype, SVGElement.prototype]) {
    try {
      return proto.blur.call(el);
    } catch {
      continue;
    }
  }
}

/** Every link address in a shown email, in order, each once. */
export function linkAddresses(doc: Document): string[] {
  const found = all(doc, "[data-mail-href]").map((el) => read(el, "data-mail-href") || "");
  return [...new Set(found)].filter(Boolean);
}
