// A hand-run check of the real app window, kept so it can be repeated on Windows. Served
// by the dev server only; the production build has one entry, index.html.
import { disarmEmail, focusedAddress, stillArmed } from "../src/components/mail/disarm";

const hostile = (tag: string): string => {
  const at = (path: string) => `http://127.0.0.1:8799/${tag}-${path}`;
  return `<html><head>
<meta http-equiv="refresh" content="3;url=${at("refresh")}">
<link rel="stylesheet" href="${at("stylesheet")}">
<style>@import url(${at("import")}); body { background: url(${at("background")}); font: 14px system-ui; }</style>
<script>window.__ran = "script"; parent.__probeRan = "${tag} script"; fetch("${at("script")}");</script>
</head><body>
<p>Hostile test email (${tag}).</p>
<img src="${at("pixel")}" onerror="window.__ran = 'onerror'">
<img name="head" src="${at("named-head")}">
<img name="documentElement" src="${at("named-root")}">
<form name="querySelectorAll"><input name="getAttribute"></form>
<noscript><style></noscript><a href="${at("noscript")}">Noscript link</a></style></noscript>
<p><a href="${at("plain")}">Plain link</a></p>
<p><a target="_self" href="${at("self")}">Same-frame link</a></p>
<div><template shadowrootmode="closed"><p><a href="${at("shadow")}">Shadow link</a></p></template></div>
<svg width="220" height="28"><a xlink:href="${at("svg")}"><text x="0" y="20">SVG link</text></a></svg>
<svg width="220" height="28"><a><animate attributeName="href" to="${at("smil")}" fill="freeze"/><text x="0" y="20">Animated link</text></a></svg>
</body></html>`;
};

const safe = document.getElementById("safe") as HTMLIFrameElement;
const raw = document.getElementById("raw") as HTMLIFrameElement;
const report = document.getElementById("report") as HTMLPreElement;
safe.srcdoc = disarmEmail(hostile("hit")) ?? "<p>refused: could not be made inert</p>";
raw.srcdoc = hostile("raw");

let heard = 0;
safe.addEventListener("load", () => {
  // Expected never to fire: a frame without allow-scripts silences listeners added inside it.
  safe.contentDocument?.addEventListener("click", () => (heard += 1));
});

setInterval(() => {
  const doc = safe.contentDocument;
  const win = safe.contentWindow as (Window & { __ran?: string; __TAURI__?: unknown }) | null;
  if (!doc) return;
  report.textContent = [
    `disarmed frame still armed:        ${stillArmed(doc)}   (want false)`,
    `a script ran in the disarmed frame: ${win?.__ran ?? "no"}   (want no)`,
    `a frame reached the app window:     ${(window as { __probeRan?: string }).__probeRan ?? "no"}   (want no)`,
    `the frame has the Tauri API:        ${win?.__TAURI__ ? "yes" : "no"}   (unusable either way: no script runs)`,
    `clicks heard by a listener inside:  ${heard}   (want 0, which is why Mail asks on a timer)`,
    `focused element's address:          ${focusedAddress(doc) || "(none)"}`,
    `text selected in the frame:         ${JSON.stringify(Document.prototype.getSelection.call(doc)?.toString() ?? "")}`,
  ].join("\n");
}, 250);
