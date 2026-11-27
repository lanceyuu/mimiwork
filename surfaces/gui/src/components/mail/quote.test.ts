/** Reading the reader's selection in an email, and marking what they commented on. */
import { describe, expect, it } from "vitest";
import { clearSelection, markQuotes, pickedText, selectedText, selectionSpot } from "./quote";

const parse = (html: string) => new DOMParser().parseFromString(html, "text/html");
// A selection exists only in a document that is shown, as the email's is in its frame.
const shown = (html: string): Document => {
  const frame = document.createElement("iframe");
  document.body.append(frame);
  const doc = frame.contentDocument!;
  Document.prototype.write.call(doc, html);
  return doc;
};
const marks = (doc: Document) => Array.from(doc.querySelectorAll("mark[data-mail-comment]")).map((m) => m.textContent);

describe("selectedText", () => {
  it("gives the selection as one line, and nothing when nothing is selected", () => {
    const doc = shown("<p id='a'>Shall we meet\n   on Friday?</p><p>Yes.</p>");
    expect(selectedText(doc)).toBe("");
    const range = doc.createRange();
    range.selectNodeContents(doc.getElementById("a")!);
    Document.prototype.getSelection.call(doc)!.addRange(range);
    expect(selectedText(doc)).toBe("Shall we meet on Friday?");
  });

  it("is not fooled by an element named after what it reads", () => {
    const doc = shown('<form id="f"></form><img id="i"><p id="a">Hello there</p>');
    const range = doc.createRange();
    range.selectNodeContents(doc.getElementById("a")!);
    Document.prototype.getSelection.call(doc)!.addRange(range);
    // What a webview does for <form name="getSelection"> and <img name="body">: the element
    // answers in place of the document's own property. (The test browser does not do this
    // by itself, so it is done by hand.)
    Object.defineProperty(doc, "getSelection", { value: doc.getElementById("f") });
    Object.defineProperty(doc, "body", { value: doc.getElementById("i") });
    Object.defineProperty(doc, "createTreeWalker", { value: doc.getElementById("f") });
    expect(selectedText(doc)).toBe("Hello there");
    expect(markQuotes(doc, ["Hello"])).toEqual([true]);
  });
});

describe("markQuotes", () => {
  it("marks a passage that runs across a link and across lines, and leaves the text as it was", () => {
    const doc = parse('<p>Shall we meet on <a data-mail-href="x">Friday\n at ten</a>? The plan is attached.</p>');
    const before = doc.body.textContent;
    expect(markQuotes(doc, ["meet on Friday at ten?"])).toEqual([true]);
    expect(marks(doc)).toEqual(["meet on ", "Friday\n at ten", "?"]);
    expect(doc.body.textContent).toBe(before);
    expect(doc.querySelector("mark")!.getAttribute("style")).toContain("background");
  });

  it("marks several passages whatever order they are given in, two of them in one sentence", () => {
    const doc = parse("<p>The budget is due on the 14th and the plan on the 20th.</p><p>See you.</p>");
    expect(markQuotes(doc, ["See you", "the plan", "The budget"])).toEqual([true, true, true]);
    expect(marks(doc)).toEqual(["The budget", "the plan", "See you"]);
  });

  it("marking again replaces the marks, and a quote that is gone is just not marked", () => {
    const doc = parse("<p>The budget is due on the 14th.</p>");
    markQuotes(doc, ["The budget", "due on"]);
    expect(markQuotes(doc, ["due on the 14th", "not in this email", ""])).toEqual([true, false, false]);
    expect(marks(doc)).toEqual(["due on the 14th"]);
    expect(markQuotes(doc, [])).toEqual([]);
    expect(doc.body.innerHTML).toBe("<p>The budget is due on the 14th.</p>");
  });

  it("gives a passage that overlaps one already marked no highlight", () => {
    const doc = parse("<p>The budget is due on the 14th.</p>");
    expect(markQuotes(doc, ["budget is due", "is due on the 14th"])).toEqual([false, true]);
    expect(marks(doc)).toEqual(["is due on the 14th"]);
  });

  it("looks only at text that is on the page", () => {
    const doc = parse("<style>p { color: red }</style><p>color is the word</p>");
    expect(markQuotes(doc, ["color"])).toEqual([true]);
    expect(doc.querySelector("style")!.textContent).toBe("p { color: red }");
    expect(marks(doc)).toEqual(["color"]);
  });
});

describe("what a reader could not have selected", () => {
  it("is not matched: a copy of the passage inside a drawing is passed over for the one in the text", () => {
    const doc = parse('<svg><text>Revenue went up</text><desc>Revenue went up</desc></svg><p>Revenue went up</p>');
    expect(markQuotes(doc, ["Revenue went up"])).toEqual([true]);
    expect(doc.querySelector("svg mark")).toBeNull();
    expect(doc.querySelector("p mark")!.textContent).toBe("Revenue went up");
  });

  it("finds a passage the email shows in capitals with a style", () => {
    // The webview hands the selection back as it is shown: "QUARTERLY REPORT".
    const doc = parse('<p style="text-transform: uppercase">Quarterly report</p>');
    expect(markQuotes(doc, ["QUARTERLY REPORT"])).toEqual([true]);
    expect(marks(doc)).toEqual(["Quarterly report"]);
  });

  it("does not cut a selection in the middle of an emoji", () => {
    const doc = shown(`<p id="a">${"x".repeat(999)}\u{1F600} and more</p>`);
    const range = doc.createRange();
    range.selectNodeContents(doc.getElementById("a")!);
    Document.prototype.getSelection.call(doc)!.addRange(range);
    expect(selectedText(doc)).toBe("x".repeat(999));
  });
});

describe("an email built to break the marking", () => {
  it("is unmarked in one piece however many children a mark holds", () => {
    // Handing a very large number of children over one by one overflows the stack in
    // Chromium (seen at 140,000). The test browser is too slow for that many, so this
    // checks the unwrapping is right; the browser test has the size.
    const doc = parse("<p>Hi</p>");
    const mark = doc.createElement("mark");
    mark.setAttribute("data-mail-comment", "");
    for (let i = 0; i < 2_000; i += 1) mark.appendChild(doc.createElement("br"));
    doc.body.appendChild(mark);
    expect(markQuotes(doc, ["Hi"])).toEqual([true]);
    expect(doc.querySelectorAll("br").length).toBe(2_000);
    expect(marks(doc)).toEqual(["Hi"]);
  });
});

describe("where the reader clicked", () => {
  // The test browser lays nothing out and cannot widen a selection, so both are stood in
  // for here. The browser tests click in a real email, in both of the app's engines.
  const caretIn = (doc: Document, id: string) => {
    const selection = Document.prototype.getSelection.call(doc)!;
    selection.collapse(doc.getElementById(id)!.firstChild, 3);
    return selection;
  };

  it("is nowhere until they click or select, and nowhere when the click fell on no text", () => {
    const doc = shown("<p id='a'>Shall we meet on Friday?</p>");
    expect(selectionSpot(doc)).toBeNull();
    const range = caretIn(doc, "a").getRangeAt(0);
    range.getClientRects = () => [] as unknown as DOMRectList;
    range.getBoundingClientRect = () => ({ right: 0, top: 0, bottom: 0, height: 0 }) as DOMRect;
    expect(selectionSpot(doc)).toBeNull();
  });

  it("is the end of the last line of what is selected, and says when it is only a click", () => {
    const doc = shown("<p id='a'>Shall we meet on Friday?</p>");
    const range = caretIn(doc, "a").getRangeAt(0);
    const lines = [{ right: 300, top: 2, bottom: 20, height: 18 }, { right: 90, top: 22, bottom: 40, height: 18 }];
    range.getClientRects = () => lines as unknown as DOMRectList;
    expect(selectionSpot(doc)).toEqual({ x: 90, top: 22, bottom: 40, caret: true });
  });

  it("takes the whole paragraph after a plain click, and only the selection when there is one", () => {
    const doc = shown("<p id='a'>Shall we meet on Friday?</p><p id='b'>The plan is attached.</p>");
    const selection = caretIn(doc, "b");
    // What the webview does when asked to widen a caret to its paragraph.
    const asked: string[][] = [];
    (selection as unknown as { modify: (...how: string[]) => void }).modify = (...how) => {
      asked.push(how);
      if (how[0] === "extend") selection.selectAllChildren(doc.getElementById("b")!);
    };
    expect(pickedText(doc)).toBe("The plan is attached.");
    expect(asked).toEqual([["move", "backward", "paragraphboundary"], ["extend", "forward", "paragraphboundary"]]);
    // Now that something is selected, it is taken as it is.
    asked.length = 0;
    selection.selectAllChildren(doc.getElementById("a")!);
    expect(pickedText(doc)).toBe("Shall we meet on Friday?");
    expect(asked).toEqual([]);
  });

  it("takes nothing where a caret cannot be widened", () => {
    const doc = shown("<p id='a'>Shall we meet on Friday?</p>");
    const selection = caretIn(doc, "a");
    (selection as unknown as { modify?: unknown }).modify = undefined;
    expect(pickedText(doc)).toBe("");
  });
});

describe("clearSelection", () => {
  it("lets go of the selection", () => {
    const doc = shown("<p id='a'>Hello there</p>");
    const range = doc.createRange();
    range.selectNodeContents(doc.getElementById("a")!);
    Document.prototype.getSelection.call(doc)!.addRange(range);
    clearSelection(doc);
    expect(selectedText(doc)).toBe("");
  });
});
