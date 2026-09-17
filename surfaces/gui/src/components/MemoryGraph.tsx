/** The memory graph (Settings → Memory → Graph), drawn the way Obsidian draws its vault.
 *
 * A hand-rolled force simulation on <canvas> — ~150 lines beats a graph library for a
 * few hundred nodes. Memories are dots (coloured by scope), #tags and folders are hubs;
 * [[wiki-links]] draw direct memory↔memory edges. The layout settles before the first
 * paint and fits the view; hovering a dot lights its neighbourhood and dims the rest;
 * clicking a memory opens its note beside the canvas (rendered markdown, Edit, Forget),
 * the same note that lives as a file in ~/MimiWork/Memory. Drag a node, pan the
 * background, wheel to zoom, right-click a memory to forget it.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  MemoryEntry,
  MemoryGraphData,
  deleteMemory,
  getMemory,
  getMemoryGraph,
  getMemoryVault,
  revealMemoryVault,
  updateMemory,
} from "../api";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";

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
  /** 0→1 as the hover/selection highlight eases in — the growth you can see. */
  glow: number;
};

const COLORS: Record<string, string> = {
  // Obsidian-ish: neutral notes, accent hubs. Scope tints the memory dots.
  global: "#0d9488", // teal — user-wide facts
  workspace: "#7c8590", // gray — project facts
  session: "#b9bec7",
  tag: "#a78bfa", // purple hubs, like Obsidian's tag nodes
  workspaceHub: "#f59e0b",
};

function nodeColor(n: SimNode): string {
  if (n.kind === "tag") return COLORS.tag;
  // Folder hubs and project-group hubs are the same idea to the reader: "where this
  // was learned" — one colour, one legend entry.
  if (n.kind === "workspace" || n.kind === "project") return COLORS.workspaceHub;
  return COLORS[n.scope || "workspace"] || COLORS.workspace;
}

function nodeRadius(n: SimNode): number {
  const base = n.kind === "memory" ? 4.5 : 6;
  return base + Math.min(7, Math.sqrt(n.degree) * 1.7);
}

const HEIGHT = 520;

export function MemoryGraph({
  onOpenMemory,
  onForgotten,
}: {
  /** Also told when a memory is opened from the graph (the list can highlight it). */
  onOpenMemory?: (id: number) => void;
  /** A memory changed or was forgotten from the graph — the list view re-reads. */
  onForgotten?: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [data, setData] = useState<MemoryGraphData | null>(null);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [vaultPath, setVaultPath] = useState("");
  const [empty, setEmpty] = useState(false);
  // Right-click a dot to forget it. The menu carries the memory's own words, because
  // "delete this node" means nothing when the dot is one of two hundred (owner ask
  // 2026-08-31).
  const [menu, setMenu] = useState<{ x: number; y: number; id: number; label: string } | null>(null);
  const [confirming, setConfirming] = useState<{ id: number; label: string } | null>(null);
  // The note panel: which memory is open beside the canvas, and its draft while editing.
  const [selected, setSelected] = useState<number | null>(null);
  const selectedRef = useRef<number | null>(null);
  selectedRef.current = selected;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const reload = useCallback(
    () =>
      Promise.all([getMemoryGraph(), getMemory().catch(() => [] as MemoryEntry[])])
        .then(([g, list]) => {
          setData(g);
          setEntries(list);
          setEmpty(!g.nodes.length);
        })
        .catch(() => setEmpty(true)),
    [],
  );

  useEffect(() => {
    void reload();
    getMemoryVault()
      .then((v) => setVaultPath(v.path || ""))
      .catch(() => {});
  }, [reload]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data || !data.nodes.length) return;

    const parent = canvas.parentElement!;
    const dpr = window.devicePixelRatio || 1;
    const W = parent.clientWidth;
    const H = HEIGHT;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    // No 2D context (jsdom, headless): the graph cannot be DRAWN, but layout and the
    // pointer handlers below still work and are worth having. Bailing here meant the
    // right-click handler was never even attached, so the feature was untestable
    // outside a real browser.
    const ctx = canvas.getContext("2d");
    const dark = document.documentElement.dataset.theme === "dark";

    // Deterministic initial ring placement so reloads look familiar.
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
        glow: 0,
      };
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = data.edges
      .map((e) => ({ a: byId.get(e.source)!, b: byId.get(e.target)!, kind: e.kind }))
      .filter((l) => l.a && l.b);
    const neighbours = new Map<SimNode, Set<SimNode>>();
    for (const l of links) {
      if (!neighbours.has(l.a)) neighbours.set(l.a, new Set());
      if (!neighbours.has(l.b)) neighbours.set(l.b, new Set());
      neighbours.get(l.a)!.add(l.b);
      neighbours.get(l.b)!.add(l.a);
    }

    let zoom = 1;
    let panX = 0;
    let panY = 0;
    let hover: SimNode | null = null;
    let dragging: SimNode | null = null;
    let moved = false;
    let panning = false;
    let lastPointer = { x: 0, y: 0 };
    let alpha = 1; // simulation heat: cools to a standstill, reheats on drag
    let raf = 0;
    const t0 = performance.now();

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

    const relax = () => {
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
      alpha *= 0.96;
    };
    // Settle BEFORE the first paint: the user sees a finished map, not six seconds of
    // drift ("the brain always moves" — owner report 2026-09-17). A drag reheats to 0.3,
    // which cools in about two seconds.
    for (let i = 0; i < 400 && alpha > 0.003; i++) relax();

    // Fit the settled map to the canvas once, with a margin, capped so a three-dot
    // graph is not blown up to poster size.
    const fit = () => {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const n of nodes) {
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x);
        maxY = Math.max(maxY, n.y);
      }
      const bw = Math.max(maxX - minX, 1) + 160;
      const bh = Math.max(maxY - minY, 1) + 120;
      zoom = Math.min(1.6, Math.max(0.3, Math.min(W / bw, H / bh)));
      panX = (W / 2 - (minX + maxX) / 2) * zoom;
      panY = (H / 2 - (minY + maxY) / 2) * zoom;
    };
    // Fitting is for the drawn canvas; without a context (jsdom) the layout keeps its
    // raw coordinates, which is what the pointer tests address.
    if (ctx) fit();

    const draw = () => {
      if (!ctx) return;
      const now = performance.now();
      const selectedNode = nodes.find((n) => n.kind === "memory" && n.memory_id === selectedRef.current) || null;
      const focus = hover || selectedNode;
      const lit = focus ? new Set([focus, ...(neighbours.get(focus) || [])]) : null;
      for (const n of nodes) {
        const target = lit && lit.has(n) ? 1 : 0;
        n.glow += (target - n.glow) * 0.18;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      // A faint dot grid — the workbench feel, without competing with the dots.
      ctx.fillStyle = dark ? "rgba(255,255,255,0.05)" : "rgba(17,17,17,0.06)";
      const step = 22 * zoom;
      const ox = ((panX % step) + step) % step;
      const oy = ((panY % step) + step) % step;
      for (let x = ox; x < W; x += step)
        for (let y = oy; y < H; y += step) ctx.fillRect(x, y, 1, 1);

      ctx.save();
      ctx.translate(W / 2 + panX, H / 2 + panY);
      ctx.scale(zoom, zoom);
      ctx.translate(-W / 2, -H / 2);

      for (const l of links) {
        const on = lit ? lit.has(l.a) && lit.has(l.b) && (l.a === focus || l.b === focus) : false;
        const dim = lit && !on;
        ctx.lineWidth = (on ? 1.8 : 1) / zoom;
        ctx.strokeStyle = on
          ? "rgba(13,148,136,0.95)"
          : l.kind === "link"
            ? `rgba(13,148,136,${dim ? 0.12 : 0.5})`
            : dark
              ? `rgba(200,206,214,${dim ? 0.06 : 0.22})`
              : `rgba(120,126,138,${dim ? 0.07 : 0.28})`;
        ctx.beginPath();
        ctx.moveTo(l.a.x, l.a.y);
        ctx.lineTo(l.b.x, l.b.y);
        ctx.stroke();
      }

      for (const n of nodes) {
        const r = nodeRadius(n) * (1 + 0.35 * n.glow);
        const color = nodeColor(n);
        const dim = lit && !lit.has(n);
        ctx.globalAlpha = dim ? 0.18 : 1;
        // Hubs and lit dots wear a soft halo — the glow Obsidian's graph is known for.
        if (n.kind !== "memory" || n.glow > 0.05) {
          ctx.shadowColor = color;
          ctx.shadowBlur = (8 + 14 * n.glow) / zoom;
        }
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.shadowBlur = 0;
        // The open note breathes: a slow ring around it, so it is findable at a glance.
        if (n === selectedNode) {
          const pulse = 6 + 2.5 * Math.sin((now - t0) / 380);
          ctx.beginPath();
          ctx.arc(n.x, n.y, r + pulse / zoom, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(13,148,136,0.55)";
          ctx.lineWidth = 1.2 / zoom;
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        // Hubs always carry their label; memories when lit or zoomed in (Obsidian shows
        // labels on zoom — hover is simpler).
        if (n.kind !== "memory" || n.glow > 0.3 || zoom > 1.5) {
          ctx.font = `${n.kind === "memory" ? 11 : 11.5}px -apple-system, "Segoe UI", sans-serif`;
          ctx.fillStyle = dark ? "rgba(230,232,235,0.92)" : "rgba(60,66,76,0.95)";
          ctx.globalAlpha = dim ? 0.25 : n.kind === "memory" ? Math.min(1, n.glow + (zoom > 1.5 ? 1 : 0)) : 1;
          ctx.fillText(n.label, n.x + r + 4 / zoom, n.y + 3.5 / zoom);
          ctx.globalAlpha = 1;
        }
      }
      ctx.restore();
    };

    const step = () => {
      if (alpha > 0.003) relax();
      draw();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);

    const onDown = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      lastPointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      dragging = pick(lastPointer.x, lastPointer.y);
      moved = false;
      panning = !dragging;
      canvas.setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      if (dragging) {
        const w = toWorld(px, py);
        if (Math.hypot(w.x - dragging.x, w.y - dragging.y) > 1) moved = true;
        dragging.x = w.x;
        dragging.y = w.y;
        alpha = Math.max(alpha, 0.3); // reheat so neighbours follow
      } else if (panning) {
        panX += px - lastPointer.x;
        panY += py - lastPointer.y;
        if (Math.abs(px - lastPointer.x) + Math.abs(py - lastPointer.y) > 1) moved = true;
      } else {
        hover = pick(px, py);
        canvas.style.cursor = hover ? "pointer" : "grab";
      }
      lastPointer = { x: px, y: py };
    };
    const onUp = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const n = pick(e.clientX - rect.left, e.clientY - rect.top);
      if (dragging && n === dragging && !moved) {
        if (n.kind === "memory" && n.memory_id != null) {
          setSelected(n.memory_id);
          setEditing(false);
          onOpenMemory?.(n.memory_id);
        }
      } else if (panning && !moved) {
        setSelected(null); // a click on empty space closes the note
      }
      dragging = null;
      panning = false;
    };
    // Right-click a MEMORY dot. Hubs (#tags, projects) are not memories — they exist
    // because something references them, so there is nothing there to delete.
    const onContext = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const n = pick(e.clientX - rect.left, e.clientY - rect.top);
      if (!n || n.kind !== "memory" || n.memory_id == null) return;
      e.preventDefault();
      setMenu({ x: e.clientX, y: e.clientY, id: n.memory_id, label: n.label || "this memory" });
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * 0.0015);
      zoom = Math.min(4, Math.max(0.3, zoom * factor));
    };
    const onLeave = () => {
      hover = null;
    };

    canvas.addEventListener("contextmenu", onContext);
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointerleave", onLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener("contextmenu", onContext);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointerleave", onLeave);
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

  const forget = async () => {
    if (!confirming) return;
    const { id } = confirming;
    setConfirming(null);
    if (selected === id) setSelected(null);
    await deleteMemory(id).catch(() => undefined);
    await reload();
    onForgotten?.();
  };

  const note = selected != null ? entries.find((m) => m.id === selected) : undefined;
  const save = async () => {
    if (!note) return;
    const text = draft.trim();
    if (text && text !== note.content) await updateMemory(note.id, text);
    setEditing(false);
    await reload();
    onForgotten?.();
  };

  return (
    <div data-testid="memory-graph">
      <div className="flex items-center gap-2 mb-2 text-[11.5px] text-faint min-w-0">
        <span className="truncate" title={vaultPath}>
          {vaultPath ? `Every memory is also a note in ${vaultPath} — open the folder in Obsidian.` : ""}
        </span>
        <button
          className="ml-auto shrink-0 text-[11.5px] text-muted hover:text-ink inline-flex items-center gap-1"
          data-testid="memory-vault-open"
          onClick={() => void revealMemoryVault().catch(() => {})}
        >
          <Icon name="folder" size={12} /> Open folder
        </button>
      </div>
      <div className="relative rounded-xl border border-line bg-panel overflow-hidden">
        <canvas ref={canvasRef} data-testid="memory-graph-canvas" />
        {note && (
          <aside
            className="absolute top-0 right-0 bottom-0 w-[340px] max-w-[70%] border-l border-line bg-panel/95 backdrop-blur flex flex-col"
            data-testid="memory-note"
          >
            <div className="flex items-center gap-2 px-3.5 pt-3 pb-2 border-b border-line">
              <span
                className="text-[10.5px] px-1.5 py-0.5 rounded-full text-white"
                style={{ background: COLORS[note.scope] || COLORS.workspace }}
              >
                {note.scope === "global" ? "About you" : note.scope}
              </span>
              {note.created_at && (
                <span className="text-[11px] text-faint truncate">{note.created_at.slice(0, 10)}</span>
              )}
              <button
                className="ml-auto topbar-icon-btn"
                aria-label="Close note"
                title="Close"
                onClick={() => setSelected(null)}
              >
                <Icon name="x" size={14} />
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto px-3.5 py-3">
              <div className="text-[13.5px] font-semibold mb-2">{note.summary || note.content.split("\n")[0].slice(0, 80)}</div>
              {editing ? (
                <textarea
                  className="w-full min-h-[220px] text-[12.5px] leading-relaxed rounded-lg border border-line bg-paper p-2"
                  value={draft}
                  autoFocus
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setEditing(false);
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void save();
                  }}
                  data-testid="memory-note-editor"
                />
              ) : (
                <div className="md text-[12.5px] leading-relaxed" data-testid="memory-note-body">
                  <Markdown text={note.content} />
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-line text-[12.5px]">
              {editing ? (
                <>
                  <button className="btn primary sm" onClick={() => void save()}>Save</button>
                  <button className="btn sm" onClick={() => setEditing(false)}>Cancel</button>
                </>
              ) : (
                <>
                  <button
                    className="btn sm"
                    data-testid="memory-note-edit"
                    onClick={() => {
                      setDraft(note.content);
                      setEditing(true);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="ml-auto text-danger/80 hover:text-danger"
                    onClick={() => setConfirming({ id: note.id, label: note.summary || "this memory" })}
                  >
                    Forget…
                  </button>
                </>
              )}
            </div>
          </aside>
        )}
      </div>
      {menu && (
        <GraphMenu
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          onForget={() => {
            setConfirming({ id: menu.id, label: menu.label });
            setMenu(null);
          }}
        />
      )}
      {confirming && (
        <ConfirmDialog
          title="Forget this memory?"
          body={`“${confirming.label}” — Mimi stops using it in new conversations. Conversations that already referenced it keep what they said.`}
          confirmLabel="Forget it"
          onCancel={() => setConfirming(null)}
          onConfirm={() => void forget()}
        />
      )}
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
        <span className="ml-auto">drag · scroll to zoom · click to open · right-click to forget</span>
      </div>
    </div>
  );
}


/** The graph's right-click menu. One action, because there is only one thing you can
 *  usefully do to a dot that a click does not already do. */
function GraphMenu({
  x,
  y,
  onForget,
  onClose,
}: {
  x: number;
  y: number;
  onForget: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const away = (e: Event) => {
      if ((e.target as HTMLElement)?.closest?.("[data-testid='memory-graph-menu']")) return;
      onClose();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    // Next frame: the contextmenu that opened this is still unwinding, and a listener
    // added synchronously would catch it and close immediately. And presses INSIDE the
    // menu are ignored — mousedown precedes click, so a blanket handler unmounts the
    // menu before its own button can be clicked.
    const id = requestAnimationFrame(() => {
      window.addEventListener("mousedown", away, true);
      window.addEventListener("contextmenu", away, true);
      window.addEventListener("keydown", key, true);
    });
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("mousedown", away, true);
      window.removeEventListener("contextmenu", away, true);
      window.removeEventListener("keydown", key, true);
    };
  }, [onClose]);

  const W = 170;
  const left = Math.min(x, Math.max(8, window.innerWidth - W - 8));
  const top = Math.min(y, Math.max(8, window.innerHeight - 52));
  return createPortal(
    <div
      className="fixed z-[70] w-[170px] py-1 rounded-xl2 border border-line bg-panel shadow-xl"
      style={{ left, top }}
      role="menu"
      data-testid="memory-graph-menu"
    >
      <button
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-[12.5px] text-left text-danger hover:bg-paper"
        role="menuitem"
        data-testid="memory-graph-forget"
        onClick={onForget}
      >
        <Icon name="trash" size={13} /> Forget this memory
      </button>
    </div>,
    document.body,
  );
}
