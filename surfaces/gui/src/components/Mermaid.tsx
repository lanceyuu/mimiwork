import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";

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

// Zoom (owner ask 2026-09-29): a long flowchart is shrunk to the column's width and its
// labels become unreadable. The picture is made wider inside a frame that scrolls, so
// panning is ordinary scrolling and the text stays sharp at any size.
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 4;

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
  const [k, setK] = useState(1);
  const frame = useRef<HTMLDivElement | null>(null);
  // Where the middle of the frame sat in the picture before a zoom, so the same spot is
  // in the middle after it; without this every zoom jumps back to the top-left corner.
  const keep = useRef<{ x: number; y: number } | null>(null);
  const zoomBy = (factor: number) => {
    const f = frame.current;
    if (f)
      keep.current = {
        x: (f.scrollLeft + f.clientWidth / 2) / (f.scrollWidth || 1),
        y: (f.scrollTop + f.clientHeight / 2) / (f.scrollHeight || 1),
      };
    setK((v) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, v * factor)));
  };
  useLayoutEffect(() => {
    const f = frame.current;
    const c = keep.current;
    if (!f || !c) return;
    f.scrollLeft = c.x * f.scrollWidth - f.clientWidth / 2;
    f.scrollTop = c.y * f.scrollHeight - f.clientHeight / 2;
    keep.current = null;
  }, [k]);
  // Only a pinch or Ctrl/Cmd+scroll zooms: the diagram sits in the conversation, and a
  // plain scroll over it must keep scrolling the page. React attaches onWheel passively,
  // so the listener that has to stop the browser's own zoom is wired by hand.
  useEffect(() => {
    const f = frame.current;
    if (!f) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      zoomBy(Math.exp(-e.deltaY * 0.0015));
    };
    f.addEventListener("wheel", onWheel, { passive: false });
    return () => f.removeEventListener("wheel", onWheel);
  }, [shown]);

  if (!shown)
    return (
      <pre>
        <code>{chart}</code>
      </pre>
    );
  // Mermaid caps the picture at its drawn width with an inline max-width; the stylesheet
  // lifts that cap and sizes the picture from these two values instead.
  const natural = /max-width:\s*([\d.]+)px/.exec(shown)?.[1];
  const size = { "--zoom": k, "--natural": natural ? `${natural}px` : "100%" } as CSSProperties;
  return (
    <div className="md-mermaid">
      <div className="md-mermaid-tools">
        {k !== 1 && (
          <button type="button" onClick={() => setK(1)} aria-label="Reset view" title="Reset view">
            ⟲
          </button>
        )}
        <button type="button" onClick={() => zoomBy(0.8)} aria-label="Zoom out" title="Zoom out">
          −
        </button>
        <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in" title="Zoom in">
          +
        </button>
      </div>
      <div className="md-mermaid-frame" ref={frame} data-zoomed={k > 1 || undefined}>
        <div className="md-mermaid-canvas" data-testid="mermaid" style={size} dangerouslySetInnerHTML={{ __html: shown }} />
      </div>
    </div>
  );
}
