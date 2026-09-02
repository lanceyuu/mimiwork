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
import { useEffect, useMemo, useRef } from "react";
import { askApp, getAppState, setAppState } from "../api";

const CSP =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'";

const KINDS = new Set(["ask", "state.get", "state.set"]);
const MAX_PROMPT = 32 * 1024;

/** What the app sees. Kept tiny and dependency-free on purpose: it is source text that
 *  ships inside every app's frame. */
export function bridgeScript(app: { id: string; title: string }): string {
  return `<script>(function(){var seq=0,pend={};
window.addEventListener("message",function(e){var d=e.data;if(!d||d.mimi!==1||!pend[d.id])return;var p=pend[d.id];delete pend[d.id];if(d.error)p.reject(new Error(d.error));else p.resolve(d.result);});
function call(kind,payload){return new Promise(function(res,rej){var id=++seq;pend[id]={resolve:res,reject:rej};parent.postMessage({mimi:1,id:id,kind:kind,payload:payload},"*");});}
window.Mimi={app:${JSON.stringify({ id: app.id, title: app.title })},
ask:function(prompt,o){o=o||{};return call("ask",{prompt:String(prompt),system:o.system?String(o.system):""}).then(function(t){if(!o.json)return t;return JSON.parse(String(t).replace(/^\\s*\`\`\`(?:json)?\\s*|\\s*\`\`\`\\s*$/g,""));});},
state:{get:function(){return call("state.get",{});},set:function(v){return call("state.set",{value:v});}}};})();</script>`;
}

export function frameDocument(app: { id: string; title: string }, html: string): string {
  const head = `<meta http-equiv="Content-Security-Policy" content="${CSP}">` + bridgeScript(app);
  const m = /<head[^>]*>/i.exec(html);
  if (m) return html.slice(0, m.index + m[0].length) + head + html.slice(m.index + m[0].length);
  return head + html;
}

export function AppFrame({ app, html }: { app: { id: string; title: string }; html: string }) {
  const ref = useRef<HTMLIFrameElement | null>(null);
  const doc = useMemo(() => frameDocument(app, html), [app.id, app.title, html]);

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
          const r = await askApp(app.id, prompt, String(payload.system ?? ""));
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
