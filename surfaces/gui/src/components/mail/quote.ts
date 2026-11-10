// Comments are tied to passages of an email. The email sits in a frame where nothing can
// run, so the app reads what the reader selected, and marks the passages they commented
// on, from outside. As in disarm.ts, nothing is read off the email's document or its
// elements by name: an email can plant an element that answers to that name.
import { own } from "./disarm";

export const QUOTE_LIMIT = 1000;
const MARK = "data-mail-comment";
// The CSP in the frame allows inline styles and nothing else, so the colours travel here.
// The text colour is set too: an email styled light-on-dark would otherwise be pale on pale.
const MARK_STYLE = "background: #fde68a; color: #1f2937;";
// Text that is never on the page.
const UNSEEN = new Set(["style", "script", "title", "textarea", "noframes", "noembed", "desc"]);
const SVG = "http://www.w3.org/2000/svg";

const bodyOf = own<HTMLElement | null>(Document.prototype, "body");
const parentOf = own<Element | null>(Node.prototype, "parentElement");
const tagOf = own<string>(Element.prototype, "localName");
const spaceOf = own<string | null>(Element.prototype, "namespaceURI");
// Not in every webview (it arrived in Safari 17.4). Where it is missing, hidden text is
// treated as shown, which costs a highlight landing on a hidden copy of the passage.
const isShown: ((this: Element) => boolean) | undefined = (Element.prototype as { checkVisibility?: () => boolean })
  .checkVisibility;

/** Whether text directly inside `parent` is something a reader could have selected. A mark
 *  inside SVG text is not drawn at all, so SVG is left alone. */
function selectable(parent: Element | null): boolean {
  if (!parent) return true;
  if (UNSEEN.has(tagOf(parent)) || spaceOf(parent) === SVG) return false;
  return isShown ? isShown.call(parent) : true;
}

/** One character as it is compared: lower case, so text the email shows in capitals with
 *  a style still matches what the reader selected. Kept to one character, because the
 *  place of every character is counted. */
function folded(ch: string): string {
  const low = ch.toLowerCase();
  return low.length === 1 ? low : ch;
}

function squeezed(text: string): string {
  return text.replace(/\s+/g, "").split("").map(folded).join("");
}
const within = (root: Element, selector: string): Element[] =>
  Array.from(Element.prototype.querySelectorAll.call(root, selector));

/** What the reader has selected in a shown email, as one line of text, or "". */
export function selectedText(doc: Document): string {
  const selection = Document.prototype.getSelection.call(doc);
  const text = String(selection ?? "").replace(/\s+/g, " ").trim().slice(0, QUOTE_LIMIT);
  // The cut can fall in the middle of an emoji, which is two units long. Half of one is
  // not a character.
  const last = text.charCodeAt(text.length - 1);
  return last >= 0xd800 && last <= 0xdbff ? text.slice(0, -1) : text;
}

/** Let go of whatever is selected in a shown email. */
export function clearSelection(doc: Document): void {
  Document.prototype.getSelection.call(doc)?.removeAllRanges();
}

function wrap(doc: Document, spots: Array<[Text, number]>, start: number, end: number): void {
  // A passage can run across several pieces of text (a link in the middle of a sentence).
  // Each piece gets its own mark, last piece first.
  let last = end - 1;
  while (last >= start) {
    const node = spots[last][0];
    let first = last;
    while (first > start && spots[first - 1][0] === node) first -= 1;
    // A piece in the middle of the passage takes the white space at its edges with it,
    // so the highlight has no gaps where one piece of text meets the next.
    const from = first === start ? spots[first][1] : 0;
    const to = last === end - 1 ? spots[last][1] + 1 : node.data.length;
    const piece = node.splitText(from);
    piece.splitText(to - from);
    const mark = Document.prototype.createElement.call(doc, "mark");
    mark.setAttribute(MARK, "");
    mark.setAttribute("style", MARK_STYLE);
    piece.replaceWith(mark);
    mark.append(piece);
    last = first - 1;
  }
}

/** Highlight each quote where it first appears in a shown email, and say which were found.
 *  Marking again replaces the marks, so it can be called whenever the comments change.
 *  A quote that is no longer in the email is simply not highlighted. */
export function markQuotes(doc: Document, quotes: string[]): boolean[] {
  const marked = quotes.map(() => false);
  const body = bodyOf(doc);
  if (!body) return marked;
  for (const old of within(body, `mark[${MARK}]`)) {
    // Moved out as one piece. Handing a mark's children over one by one fails outright
    // when there are very many of them.
    const inside = Document.prototype.createRange.call(doc);
    inside.selectNodeContents(old);
    old.replaceWith(inside.extractContents());
  }
  Node.prototype.normalize.call(body);

  // Every character of the email's text with where it sits, white space left out. What
  // was selected on screen and the same words in the email differ in their line breaks
  // and spacing, and in nothing else.
  const spots: Array<[Text, number]> = [];
  let flat = "";
  const walker = Document.prototype.createTreeWalker.call(doc, body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    if (!selectable(parentOf(node))) continue;
    for (let i = 0; i < node.data.length; i += 1) {
      if (/\s/.test(node.data[i])) continue;
      flat += folded(node.data[i]);
      spots.push([node, i]);
    }
  }

  const found = quotes
    .map((quote, index) => {
      const wanted = squeezed(quote);
      const start = wanted ? flat.indexOf(wanted) : -1;
      return { index, start, end: start + wanted.length };
    })
    .filter((range) => range.start >= 0)
    // From the end of the email backwards: marking splits the text it touches, and only
    // what comes before a split keeps its place.
    .sort((a, b) => b.start - a.start);
  // ponytail: a quote is marked where it first appears, and one that overlaps a passage
  // already marked gets no highlight. Keep each comment's own range if that is ever missed.
  let floor = Infinity;
  for (const { index, start, end } of found) {
    if (end > floor) continue;
    floor = start;
    wrap(doc, spots, start, end);
    marked[index] = true;
  }
  return marked;
}
