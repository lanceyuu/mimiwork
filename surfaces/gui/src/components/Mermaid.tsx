import { useEffect, useState } from "react";

// A ```mermaid fence in an assistant reply, drawn inline (the show-me skill answers
// "Show me how" with one). The library is ~2.5 MB and rarely needed, so it loads on
// first use, not at startup. While the diagram is still streaming in — or if the model
// wrote something Mermaid cannot parse — the raw fence shows instead, so a bad diagram
// is never worse than a code block.
let seq = 0;
export function Mermaid({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    // ponytail: 250 ms settle — streaming re-renders on every delta, and a render is not cheap.
    const t = setTimeout(async () => {
      try {
        const m = (await import("mermaid")).default;
        m.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: document.documentElement.dataset.theme === "dark" ? "dark" : "neutral",
          fontFamily: "inherit",
        });
        const out = await m.render(`mmd-${++seq}`, chart);
        if (live) setSvg(out.svg);
      } catch {
        if (live) setSvg(null);
      }
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [chart]);
  if (!svg)
    return (
      <pre>
        <code>{chart}</code>
      </pre>
    );
  return <div className="md-mermaid" data-testid="mermaid" dangerouslySetInnerHTML={{ __html: svg }} />;
}
