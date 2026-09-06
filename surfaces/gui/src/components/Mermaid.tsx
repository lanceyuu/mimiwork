import { useEffect, useState } from "react";

// A ```mermaid fence in an assistant reply, drawn inline (the show-me skill answers
// "Visualize this task" with one). The library is ~2.5 MB and rarely needed, so it loads
// on first use, not at startup. While the diagram is still streaming in — or if the model
// wrote something Mermaid cannot parse — the raw fence shows instead, so a bad diagram is
// never worse than a code block.
//
// Two lessons from the first release (owner report 2026-09-06): Mermaid draws its own
// "Syntax error in text" bomb into document.body on every failed render unless told not
// to, and a streamed fence fails dozens of times before it is complete — so parse first,
// render only what parses, and never let the library touch the page on failure. And the
// answer bubble remounts when the stream is finalized, which showed the raw fence again
// for a beat before the SVG came back — the cache below makes a remount instant.
const drawn = new Map<string, string>();
let seq = 0;

export function Mermaid({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const shown = drawn.get(chart) ?? svg;
  useEffect(() => {
    if (drawn.has(chart)) return;
    let live = true;
    // ponytail: 250 ms settle — streaming re-renders on every delta, and a render is not cheap.
    const t = setTimeout(async () => {
      try {
        const m = (await import("mermaid")).default;
        m.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: document.documentElement.dataset.theme === "dark" ? "dark" : "neutral",
          fontFamily: "inherit",
        });
        if (!(await m.parse(chart, { suppressErrors: true }))) return;
        const out = await m.render(`mmd-${++seq}`, chart);
        drawn.set(chart, out.svg);
        if (live) setSvg(out.svg);
      } catch {
        /* unparseable or mid-stream: keep showing the fence */
      }
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [chart]);
  if (!shown)
    return (
      <pre>
        <code>{chart}</code>
      </pre>
    );
  return <div className="md-mermaid" data-testid="mermaid" dangerouslySetInnerHTML={{ __html: shown }} />;
}
