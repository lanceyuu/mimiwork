/** Obsidian-style memory graph (Settings → Memory → Graph).
 *
 * A hand-rolled force simulation on <canvas> — ~120 lines beats a graph
 * library dependency for a few hundred nodes. Memories are dots (colored by
 * scope), #tags and workspaces are hub nodes; [[wiki-links]] draw direct
 * memory↔memory edges. Drag a node, pan the background, wheel to zoom, hover
 * for the label, click a memory to hand it to the list view.
 */
import { useEffect, useRef, useState } from "react";
import { MemoryGraphData, getMemoryGraph } from "../api";

type SimNode = {
  id: string;
  kind: string;
  label: string;
  scope?: string;
  memory_id?: number;
  degree: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
};

const COLORS: Record<string, string> = {
  // Obsidian-ish: neutral notes, accent hubs. Scope tints the memory dots.
  global: "#0d9488", // teal — user-wide facts
  workspace: "#6b7280", // gray — project facts
  session: "#b9bec7",
  tag: "#c084fc", // purple hubs, like Obsidian's tag nodes
  workspaceHub: "#f59e0b",
};

function nodeColor(n: SimNode): string {
  if (n.kind === "tag") return COLORS.tag;
  if (n.kind === "workspace") return COLORS.workspaceHub;
  return COLORS[n.scope || "workspace"] || COLORS.workspace;
}

function nodeRadius(n: SimNode): number {
  const base = n.kind === "memory" ? 4 : 5;
  return base + Math.min(6, Math.sqrt(n.degree) * 1.6);
}

export function MemoryGraph({ onOpenMemory }: { onOpenMemory?: (id: number) => void }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [data, setData] = useState<MemoryGraphData | null>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    getMemoryGraph()
      .then((g) => {
        setData(g);
        setEmpty(!g.nodes.length);
      })
      .catch(() => setEmpty(true));
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data || !data.nodes.length) return;

    const parent = canvas.parentElement!;
    const dpr = window.devicePixelRatio || 1;
    const W = parent.clientWidth;
    const H = 420;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom / headless environments

    // Deterministic-ish initial ring placement so reloads look familiar.
    const nodes: SimNode[] = data.nodes.map((n, i) => {
      const angle = (i / data.nodes.length) * Math.PI * 2;
      const r = 90 + (i % 5) * 26;
      return {
        ...n,
        degree: n.degree || 0,
        x: W / 2 + Math.cos(angle) * r,
        y: H / 2 + Math.sin(angle) * r,
        vx: 0,
        vy: 0,
      };
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = data.edges
      .map((e) => ({ a: byId.get(e.source)!, b: byId.get(e.target)!, kind: e.kind }))
      .filter((l) => l.a && l.b);

    let zoom = 1;
    let panX = 0;
    let panY = 0;
    let hover: SimNode | null = null;
    let dragging: SimNode | null = null;
    let panning = false;
    let lastPointer = { x: 0, y: 0 };
    let alpha = 1; // simulation heat: cools to a standstill, reheats on drag
    let raf = 0;

    const toWorld = (px: number, py: number) => ({
      x: (px - W / 2 - panX) / zoom + W / 2,
      y: (py - H / 2 - panY) / zoom + H / 2,
    });

    const pick = (px: number, py: number): SimNode | null => {
      const { x, y } = toWorld(px, py);
      let best: SimNode | null = null;
      let bestD = 12 / zoom;
      for (const n of nodes) {
        const d = Math.hypot(n.x - x, n.y - y);
        if (d < bestD + nodeRadius(n)) {
          best = n;
          bestD = d;
        }
      }
      return best;
    };

    const step = () => {
      if (alpha > 0.003) {
        // Repulsion (O(n²) — fine for the few hundred memories a user has).
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i];
            const b = nodes[j];
            let dx = a.x - b.x;
            let dy = a.y - b.y;
            let d2 = dx * dx + dy * dy;
            if (d2 < 1) d2 = 1;
            const f = (900 * alpha) / d2;
            const d = Math.sqrt(d2);
            dx /= d;
            dy /= d;
            a.vx += dx * f;
            a.vy += dy * f;
            b.vx -= dx * f;
            b.vy -= dy * f;
          }
        }
        // Springs along edges.
        for (const l of links) {
          const rest = l.kind === "link" ? 70 : 90;
          const dx = l.b.x - l.a.x;
          const dy = l.b.y - l.a.y;
          const d = Math.hypot(dx, dy) || 1;
          const f = ((d - rest) / d) * 0.04 * alpha;
          l.a.vx += dx * f;
          l.a.vy += dy * f;
          l.b.vx -= dx * f;
          l.b.vy -= dy * f;
        }
        // Gentle centering + integrate.
        for (const n of nodes) {
          n.vx += (W / 2 - n.x) * 0.0015 * alpha;
          n.vy += (H / 2 - n.y) * 0.0015 * alpha;
          if (n !== dragging) {
            n.x += n.vx;
            n.y += n.vy;
          }
          n.vx *= 0.85;
          n.vy *= 0.85;
        }
        alpha *= 0.985;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(W / 2 + panX, H / 2 + panY);
      ctx.scale(zoom, zoom);
      ctx.translate(-W / 2, -H / 2);

      ctx.lineWidth = 1 / zoom;
      for (const l of links) {
        ctx.strokeStyle = l.kind === "link" ? "rgba(13,148,136,0.5)" : "rgba(140,146,158,0.28)";
        ctx.beginPath();
        ctx.moveTo(l.a.x, l.a.y);
        ctx.lineTo(l.b.x, l.b.y);
        ctx.stroke();
      }
      for (const n of nodes) {
        const r = nodeRadius(n);
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = nodeColor(n);
        ctx.globalAlpha = hover && hover !== n ? 0.45 : 1;
        ctx.fill();
        ctx.globalAlpha = 1;
        // Hubs and hovered nodes carry their label; plain memories stay quiet
        // until hovered (Obsidian shows labels on zoom — hover is simpler).
        if (n === hover || n.kind !== "memory" || zoom > 1.7) {
          ctx.font = `${11 / zoom}px -apple-system, sans-serif`;
          ctx.fillStyle = "rgba(75,82,94,0.95)";
          ctx.fillText(n.label, n.x + r + 3 / zoom, n.y + 3 / zoom);
        }
      }
      ctx.restore();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);

    const onDown = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      lastPointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      dragging = pick(lastPointer.x, lastPointer.y);
      panning = !dragging;
      canvas.setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      if (dragging) {
        const w = toWorld(px, py);
        dragging.x = w.x;
        dragging.y = w.y;
        alpha = Math.max(alpha, 0.3); // reheat so neighbors follow
      } else if (panning) {
        panX += px - lastPointer.x;
        panY += py - lastPointer.y;
      } else {
        hover = pick(px, py);
        canvas.style.cursor = hover ? "pointer" : "grab";
      }
      lastPointer = { x: px, y: py };
    };
    const onUp = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const n = pick(e.clientX - rect.left, e.clientY - rect.top);
      if (dragging && n === dragging && n.kind === "memory" && n.memory_id != null) {
        onOpenMemory?.(n.memory_id);
      }
      dragging = null;
      panning = false;
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * 0.0015);
      zoom = Math.min(4, Math.max(0.3, zoom * factor));
    };

    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, [data, onOpenMemory]);

  if (empty)
    return (
      <div className="text-[12.5px] text-muted py-6 text-center" data-testid="memory-graph-empty">
        No memories yet — the graph draws itself as the coworker remembers things.
        Memories can reference each other with <code>[[links]]</code> and <code>#tags</code>.
      </div>
    );

  return (
    <div data-testid="memory-graph">
      <div className="rounded-xl border border-line bg-panel overflow-hidden">
        <canvas ref={canvasRef} data-testid="memory-graph-canvas" />
      </div>
      <div className="flex items-center gap-4 mt-2 text-[11.5px] text-faint" data-testid="memory-graph-legend">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS.global }} /> Global
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS.workspace }} /> Workspace
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS.tag }} /> #tag
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS.workspaceHub }} /> Project
        </span>
        <span className="ml-auto">drag · scroll to zoom · click a dot to open it</span>
      </div>
    </div>
  );
}
