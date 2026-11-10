/** An email is made inert before any frame loads it. */
import { describe, expect, it } from "vitest";
import { disarmEmail, focusedAddress, linkAddresses, MAIL_CSP, releaseFocus, stillArmed } from "./disarm";

const parse = (html: string) => new DOMParser().parseFromString(html, "text/html");
const disarmed = (html: string, images = false) => {
  const out = disarmEmail(html, { images });
  if (out === null) throw new Error("expected a safe document");
  return parse(out);
};

describe("disarmEmail", () => {
  it("takes the address off a link and keeps it where the app can read it", () => {
    const doc = disarmed('<p><a href="https://example.com/a">Read</a></p>');
    const link = doc.querySelector("a")!;
    expect(link.hasAttribute("href")).toBe(false);
    expect(link.getAttribute("data-mail-href")).toBe("https://example.com/a");
    expect(link.getAttribute("tabindex")).toBe("0");
    expect(link.textContent).toBe("Read");
  });

  it("takes the address off an SVG link written with xlink:href", () => {
    const doc = disarmed('<svg><a xlink:href="https://example.com/s"><text>Go</text></a></svg>');
    const link = doc.querySelector("svg a")!;
    expect(link.getAttributeNames()).not.toContain("xlink:href");
    expect(link.getAttributeNames()).not.toContain("href");
    expect(link.getAttribute("data-mail-href")).toBe("https://example.com/s");
  });

  it("keeps an address only on what a person clicks", () => {
    const doc = disarmed(
      '<link rel="stylesheet" href="https://x.example/a.css">' +
        '<svg><image href="https://x.example/i.png"/><use xlink:href="https://x.example/u.svg#a"/></svg>',
    );
    expect(doc.documentElement.outerHTML).not.toContain("x.example");
    expect(doc.querySelector("[tabindex]")).toBeNull();
  });

  it("removes what could run, load a page or give a link an address later", () => {
    const doc = disarmed(
      '<head><base href="https://x.example/"><meta http-equiv="refresh" content="0;url=https://x.example"></head>' +
        '<body><script>1</script><noscript><p>off</p></noscript>' +
        '<div><template shadowrootmode="closed"><a href="https://x.example/t">t</a></template></div>' +
        '<iframe src="https://x.example/f"></iframe><object data="https://x.example/o"></object>' +
        '<svg><a><animate attributeName="href" to="https://x.example/smil"/><text>x</text></a></svg></body>',
    );
    for (const gone of ["base", "script", "noscript", "template", "iframe", "object", "animate"]) {
      expect(doc.querySelector(gone), gone).toBeNull();
    }
    expect(doc.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(doc.documentElement.outerHTML).not.toContain("x.example");
  });

  it("takes away the names that would let an element stand in for part of the document", () => {
    const doc = disarmed(
      '<img name="head" src="data:image/png;base64,AAAA"><img name="documentElement">' +
        '<form name="querySelectorAll"><input name="q"></form>',
    );
    expect(doc.querySelector("img[name], form[name]")).toBeNull();
    expect(doc.querySelectorAll("img").length).toBe(2);
    expect(doc.head.firstElementChild!.getAttribute("http-equiv")).toBe("Content-Security-Policy");
  });

  it("does not let an email plant the address the app will offer", () => {
    const doc = disarmed('<p tabindex="0" data-mail-href="https://evil.example">Click</p>');
    expect(doc.querySelector("[data-mail-href]")).toBeNull();
  });

  it("puts the policy first in the head, without remote images unless asked", () => {
    const first = (doc: Document) => doc.head.firstElementChild!;
    const closed = first(disarmed('<head><meta http-equiv="Content-Security-Policy" content="img-src *"></head><p>hi</p>'));
    expect(closed.getAttribute("http-equiv")).toBe("Content-Security-Policy");
    expect(closed.getAttribute("content")).toBe("default-src 'none'; img-src data:; style-src 'unsafe-inline'; form-action 'none'");
    expect(first(disarmed("<p>hi</p>", true)).getAttribute("content")).toBe(MAIL_CSP(true));
    expect(MAIL_CSP(true)).toContain("img-src data: https:");
  });

  it("leaves an email's own images, text and styles alone", () => {
    const doc = disarmed('<p style="color:red">Hello <img src="data:image/png;base64,AAAA" alt="logo"></p>');
    expect(doc.querySelector("p")!.getAttribute("style")).toBe("color:red");
    expect(doc.querySelector("img")!.getAttribute("src")).toBe("data:image/png;base64,AAAA");
  });

  it("gives back a document that is still inert when parsed again", () => {
    const out = disarmEmail('<a href="https://example.com">x</a><svg><a xlink:href="https://e.example">y</a></svg>')!;
    expect(stillArmed(parse(out))).toBe(false);
  });
});

describe("stillArmed", () => {
  const policy = `<meta http-equiv="Content-Security-Policy" content="${MAIL_CSP(false)}">`;

  it("accepts only a document with the policy first and nothing armed", () => {
    expect(stillArmed(parse(`<head>${policy}</head><p>plain</p>`))).toBe(false);
    expect(stillArmed(parse("<p>no policy at all</p>"))).toBe(true);
    expect(stillArmed(parse(`<head><title>x</title>${policy}</head>`))).toBe(true);
    expect(stillArmed(parse(`<head>${policy}${policy}</head>`))).toBe(true);
  });

  it("is true for a link address, a template, a second meta or a name that hides the document", () => {
    for (const body of [
      '<a href="https://example.com">x</a>',
      "<div><template><b>x</b></template></div>",
      '<meta http-equiv="refresh" content="1">',
      '<img name="head">',
    ]) {
      expect(stillArmed(parse(`<head>${policy}</head>${body}`)), body).toBe(true);
    }
  });
});

describe("focusedAddress", () => {
  it("is the address of the link that has focus, and empty otherwise", () => {
    document.body.innerHTML = '<a tabindex="0" data-mail-href="https://example.com/a">Read</a><p>text</p>';
    expect(focusedAddress(document)).toBe("");
    document.querySelector("a")!.focus();
    expect(focusedAddress(document)).toBe("https://example.com/a");
    releaseFocus(document);
    expect(focusedAddress(document)).toBe("");
  });
});

describe("linkAddresses", () => {
  it("lists each link address once, in the order they appear", () => {
    const doc = parse(
      disarmEmail('<a href="https://a.example/">a</a><a href="https://b.example/">b</a><a href="https://a.example/">again</a>')!,
    );
    expect(linkAddresses(doc)).toEqual(["https://a.example/", "https://b.example/"]);
  });
});
