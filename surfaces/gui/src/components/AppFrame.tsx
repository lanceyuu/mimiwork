/** The frame a Mimi-written app runs in, and the bridge it talks through.
 *
 * The app is code that runs on the user's behalf, so it gets LESS than a document the
 * user wrote: `sandbox="allow-scripts"` and nothing else (no same-origin — it cannot
 * read the launch token or call the sidecar), plus a content security policy that
 * leaves it no network at all. The only way out is `window.Mimi`, injected here, whose
 * calls arrive as postMessage and are answered one by one after validation. The same
 * file runs unchanged wherever a host page supplies this bridge — which is what keeps
 * hosting on QualiTaTi possible later without touching the apps themselves.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { askApp, getAppState, setAppState } from "../api";

/** One model call the app made, for the creator's log (Coze shows each call in its
 *  preview; "why did it answer that" is otherwise unanswerable). */
export interface AskEntry {
  ts: number;
  prompt: string;
  system: string;
  reply?: string;
  error?: string;
  ms: number;
}

const CSP =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'";

const KINDS = new Set(["ask", "state.get", "state.set"]);
const MAX_PROMPT = 32 * 1024;

/** What the app sees. Kept tiny and dependency-free on purpose: it is source text that
 *  ships inside every app's frame. */
export function bridgeScript(app: { id: string; title: string }): string {
  return `<script>(function(){var seq=0,pend={},onSug=null;
window.addEventListener("message",function(e){var d=e.data;if(!d||d.mimi!==1)return;
if(d.kind==="suggestion"){if(onSug)try{onSug(String(d.text||""));}catch(err){}return;}
if(!pend[d.id])return;var p=pend[d.id];delete pend[d.id];if(d.error)p.reject(new Error(d.error));else p.resolve(d.result);});
function call(kind,payload){return new Promise(function(res,rej){var id=++seq;pend[id]={resolve:res,reject:rej};parent.postMessage({mimi:1,id:id,kind:kind,payload:payload},"*");});}
window.Mimi={app:${JSON.stringify({ id: app.id, title: app.title })},
ask:function(prompt,o){o=o||{};return call("ask",{prompt:String(prompt),system:o.system?String(o.system):""}).then(function(t){if(!o.json)return t;return JSON.parse(String(t).replace(/^\\s*\`\`\`(?:json)?\\s*|\\s*\`\`\`\\s*$/g,""));});},
state:{get:function(){return call("state.get",{});},set:function(v){return call("state.set",{value:v});}},
onSuggestion:function(fn){onSug=typeof fn==="function"?fn:null;}};})();</script>`;
}

export function frameDocument(app: { id: string; title: string }, html: string): string {
  const head = `<meta http-equiv="Content-Security-Policy" content="${CSP}">` + bridgeScript(app);
  const m = /<head[^>]*>/i.exec(html);
  if (m) return html.slice(0, m.index + m[0].length) + head + html.slice(m.index + m[0].length);
  return head + html;
}

export function AppFrame({
  app,
  html,
  onAsk,
  suggestion,
}: {
  app: { id: string; title: string };
  html: string;
  /** Every model call the app makes, as it completes — feeds the creator's log. */
  onAsk?: (entry: AskEntry) => void;
  /** A chip the user clicked: delivered into the page (Mimi.onSuggestion). The nonce
   *  lets the same text be sent twice. */
  suggestion?: { text: string; nonce: number } | null;
}) {
  const ref = useRef<HTMLIFrameElement | null>(null);
  const doc = useMemo(() => frameDocument(app, html), [app.id, app.title, html]);

  useEffect(() => {
    if (!suggestion) return;
    ref.current?.contentWindow?.postMessage({ mimi: 1, kind: "suggestion", text: suggestion.text }, "*");
  }, [suggestion]);

  useEffect(() => {
    const onMessage = async (e: MessageEvent) => {
      const win = ref.current?.contentWindow;
      if (!win || e.source !== win) return;
      const d = e.data;
      if (!d || d.mimi !== 1 || typeof d.id !== "number" || !KINDS.has(d.kind)) return;
      const reply = (body: { result?: unknown; error?: string }) =>
        win.postMessage({ mimi: 1, id: d.id, ...body }, "*");
      const payload = d.payload && typeof d.payload === "object" ? d.payload : {};
      try {
        if (d.kind === "ask") {
          const prompt = String(payload.prompt ?? "");
          if (!prompt.trim()) return reply({ error: "empty prompt" });
          if (prompt.length > MAX_PROMPT) return reply({ error: "the prompt is too long (32 KB max)" });
          const system = String(payload.system ?? "");
          const started = Date.now();
          const r = await askApp(app.id, prompt, system);
          onAsk?.({
            ts: started,
            prompt,
            system,
            reply: r.ok ? r.text ?? "" : undefined,
            error: r.ok ? undefined : r.error || "Mimi could not answer",
            ms: Date.now() - started,
          });
          return reply(r.ok ? { result: r.text ?? "" } : { error: r.error || "Mimi could not answer" });
        }
        if (d.kind === "state.get") return reply({ result: await getAppState(app.id) });
        const value = payload.value;
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          return reply({ error: "state must be an object" });
        }
        const r = await setAppState(app.id, value as Record<string, unknown>);
        return reply(r.ok ? { result: null } : { error: r.error || "could not save" });
      } catch (err) {
        return reply({ error: (err as Error)?.message || "bridge error" });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.id]);

  return (
    <iframe
      ref={ref}
      className="app-frame"
      title={app.title}
      sandbox="allow-scripts"
      srcDoc={doc}
      data-testid="app-frame"
    />
  );
}


/** The creator's log of the app's model calls, newest first, folded by default. */
export function AskLog({ entries }: { entries: AskEntry[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ask-log" data-testid="ask-log">
      <button type="button" className="ask-log-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span>{open ? "▾" : "▸"}</span>
        <span>
          Model calls{entries.length ? ` (${entries.length})` : ""}
        </span>
        <span className="dim">what the app asked Mimi, and what came back</span>
      </button>
      {open && (
        <div className="ask-log-body">
          {entries.length === 0 && <div className="dim">None yet — use the app and its questions appear here.</div>}
          {[...entries].reverse().map((e) => (
            <div className="ask-entry" key={e.ts}>
              <div className="ask-entry-meta">
                {new Date(e.ts).toLocaleTimeString()} · {(e.ms / 1000).toFixed(1)} s{e.error ? " · failed" : ""}
              </div>
              {e.system && <pre className="ask-entry-text ask-entry-system">{e.system}</pre>}
              <pre className="ask-entry-text">{e.prompt}</pre>
              <pre className={"ask-entry-text ask-entry-reply" + (e.error ? " ask-entry-error" : "")}>{e.error ?? e.reply}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
