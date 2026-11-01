/** The editable diagram of one agent system (the Agents section).
 *
 *  React Flow owns the node objects because it writes each node's measured size onto
 *  them; rebuilding nodes from the saved shape on every render would drop that and leave
 *  them invisible. Connections are rebuilt freely — they carry no measurements.
 *
 *  Every change autosaves after a short pause, and a pending save is sent when the page
 *  closes, so leaving right after an edit loses nothing. The server answers each save
 *  with the problems that stop the design from running; they are pinned on their node.
 */
import "@xyflow/react/dist/style.css";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import type {
  AgentEdge,
  AgentNode,
  AgentNodeKind,
  AgentNodeState,
  AgentSystem,
  AgentSystemProblem,
  CodingAgent,
} from "../../api";
import { NodeInspector } from "./NodeInspector";

/** What each kind is called in the palette — plain words, no "orchestrator". */
export const KIND_LABELS: Record<AgentNodeKind, string> = {
  agent: "Mimi agent",
  coding: "Coding agent",
  router: "Router",
  orchestrator: "Lead agent (assigns work)",
  review: "Human review",
};
const KIND_SHORT: Record<AgentNodeKind, string> = { ...KIND_LABELS, orchestrator: "Lead agent" };
const KINDS = Object.keys(KIND_LABELS) as AgentNodeKind[];

export const CODING_LABELS: Record<string, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  opencode: "opencode",
  cursor: "Cursor",
  gemini: "Gemini CLI",
};

export const STATE_LABELS: Record<AgentNodeState, string> = {
  queued: "Waiting its turn",
  working: "Working",
  done: "Done",
  failed: "Failed",
  waiting_for_person: "Waiting for you",
  skipped: "Not needed",
};

/** Default round limit for a connection that loops back (the backend allows 1-5). */
const LOOP_ROUNDS = 3;
const COL = 260;

type FlowNode = Node<{ node: AgentNode }, "agent">;
type SystemParts = Pick<AgentSystem, "nodes" | "edges" | "entry">;

export const modelShort = (labels: Record<string, string>, id: string): string => {
  const raw = labels[id]?.split(" · ")[0];
  if (raw) return raw;
  return id.includes(":") ? id.slice(id.indexOf(":") + 1) : id;
};

interface View {
  problems: Record<string, string[]>;
  states: Record<string, AgentNodeState>;
  entry: string;
  labels: Record<string, string>;
  compact: boolean;
}
const ViewCtx = createContext<View>({ problems: {}, states: {}, entry: "", labels: {}, compact: false });

function AgentNodeCard({ data, selected }: NodeProps<FlowNode>) {
  const { problems, states, entry, labels, compact } = useContext(ViewCtx);
  const n = data.node;
  const issues = problems[n.id] || [];
  const state = states[n.id];
  const detail =
    n.kind === "coding"
      ? [CODING_LABELS[n.agent] || "Choose a coding agent", n.model].filter(Boolean).join(" · ")
      : n.kind === "review"
        ? "A person approves or sends it back"
        : n.model
          ? modelShort(labels, n.model)
          : "The chat's model";
  const tools = n.tools.length ? ` · ${n.tools.length} tool${n.tools.length === 1 ? "" : "s"}` : "";
  return (
    <div
      className={
        `ag-node kind-${n.kind}` +
        (selected ? " selected" : "") +
        (issues.length ? " has-problem" : "") +
        (state ? ` state-${state}` : "")
      }
      data-testid={`agent-node-${n.id}`}
      data-state={state || undefined}
      title={issues.join("\n") || undefined}
    >
      <Handle type="target" position={Position.Left} />
      <div className="ag-node-kind">
        <span>{KIND_SHORT[n.kind]}</span>
        {!compact && entry === n.id && <span className="ag-node-start">Starts here</span>}
      </div>
      <div className="ag-node-name" data-no-translate>{n.name}</div>
      {!compact && <div className="ag-node-detail">{detail + (n.kind === "review" ? "" : tools)}</div>}
      {!compact && state && <div className="ag-node-state">{STATE_LABELS[state]}</div>}
      {!compact && issues.length > 0 && (
        <div className="ag-node-problem" data-testid="agent-node-problem">
          {issues[0]}
          {issues.length > 1 ? ` (and ${issues.length - 1} more)` : ""}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { agent: AgentNodeCard };

const edgeId = (e: AgentEdge) => `${e.from}->${e.to}`;

function toFlowEdge(e: AgentEdge, selected: boolean): Edge {
  const loop = e.max_rounds != null;
  const text = [e.label, loop ? `up to ${e.max_rounds} times` : ""].filter(Boolean).join(" · ");
  return {
    id: edgeId(e),
    source: e.from,
    target: e.to,
    label: text || undefined,
    selected,
    className: loop ? "ag-edge-loop" : e.kind === "assign" ? "ag-edge-assign" : undefined,
    // Assign is drawn dashed: the worker runs only if the lead calls it, not every time.
    style: e.kind === "assign" ? { strokeDasharray: "6 4" } : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  };
}

const toFlowNode = (n: AgentNode): FlowNode => ({ id: n.id, type: "agent", position: n.position, data: { node: n } });

/** True when `to` already leads to `from` along non-loop flow connections — so a new
 *  from → to connection would close a circle and must be a loop with a round limit. */
function closesCircle(edges: AgentEdge[], from: string, to: string): boolean {
  const seen = new Set<string>();
  const stack = [to];
  while (stack.length) {
    const at = stack.pop()!;
    if (at === from) return true;
    if (seen.has(at)) continue;
    seen.add(at);
    for (const e of edges) if (e.from === at && e.kind === "flow" && e.max_rounds == null) stack.push(e.to);
  }
  return false;
}

/** The connection a drag from `src` to `dst` makes: a lead agent assigns work; a router's
 *  choices need a label, so the target's name stands in; a connection that closes a circle
 *  becomes a loop, and a review's way back is called "revise" as the runner expects. */
export function newEdge(nodes: AgentNode[], edges: AgentEdge[], from: string, to: string): AgentEdge | null {
  const src = nodes.find((n) => n.id === from);
  const dst = nodes.find((n) => n.id === to);
  if (!src || !dst || from === to || edges.some((e) => e.from === from && e.to === to)) return null;
  if (src.kind === "orchestrator") return { from, to, kind: "assign", label: "", max_rounds: null };
  const loop = closesCircle(edges, from, to);
  const label = src.kind === "router" ? dst.name.slice(0, 40) : loop && src.kind === "review" ? "revise" : "";
  return { from, to, kind: "flow", label, max_rounds: loop ? LOOP_ROUNDS : null };
}

function blankNode(kind: AgentNodeKind, nodes: AgentNode[]): AgentNode {
  let k = nodes.length + 1;
  while (nodes.some((n) => n.id === `n${k}`)) k++;
  const base = KIND_SHORT[kind];
  let name = base;
  for (let i = 2; nodes.some((n) => n.name === name); i++) name = `${base} ${i}`;
  const right = nodes.length ? Math.max(...nodes.map((n) => n.position.x)) + COL : 0;
  return {
    id: `n${k}`,
    kind,
    name,
    instructions: "",
    model: "",
    effort: "",
    tools: [],
    agent: kind === "coding" ? "claude_code" : "",
    folder: "",
    position: { x: right, y: 0 },
  };
}

interface Props {
  system: SystemParts;
  problems?: AgentSystemProblem[];
  nodeStates?: Record<string, AgentNodeState>;
  /** A small, still picture for the pattern gallery: no palette, no editing. */
  readOnly?: boolean;
  onSave?: (parts: SystemParts) => void;
  saveDelayMs?: number;
  models?: string[];
  modelLabels?: Record<string, string>;
  defaultModel?: string;
  codingAgents?: CodingAgent[];
}

export function AgentCanvas({
  system,
  problems = [],
  nodeStates = {},
  readOnly = false,
  onSave,
  saveDelayMs = 700,
  models = [],
  modelLabels = {},
  defaultModel = "",
  codingAgents = [],
}: Props) {
  const [flowNodes, setFlowNodes] = useState<FlowNode[]>(() => system.nodes.map(toFlowNode));
  const [edges, setEdges] = useState<AgentEdge[]>(system.edges);
  const [entry, setEntry] = useState(system.entry);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);

  const nodes = useMemo(() => flowNodes.map((f) => ({ ...f.data.node, position: f.position })), [flowNodes]);
  const flowEdges = useMemo(() => edges.map((e) => toFlowEdge(e, edgeId(e) === selectedEdge)), [edges, selectedEdge]);

  // Autosave. The timer reads the latest state from a ref the commit effect keeps current,
  // so a burst of edits (typing, dragging) becomes one PATCH.
  const latest = useRef<SystemParts>({ nodes, edges, entry });
  const save = useRef(onSave);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const instance = useRef<ReactFlowInstance<FlowNode> | null>(null);
  useEffect(() => {
    latest.current = { nodes, edges, entry };
    save.current = onSave;
  });
  const sendNow = () => {
    if (!timer.current) return;
    clearTimeout(timer.current);
    timer.current = null;
    save.current?.(latest.current);
  };
  const touch = () => {
    if (readOnly) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      save.current?.(latest.current);
    }, saveDelayMs);
  };
  useEffect(() => () => sendNow(), []);

  const byNode = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const p of problems) if (p.node) (out[p.node] ||= []).push(p.message);
    return out;
  }, [problems]);
  const whole = problems.filter((p) => !p.node || !nodes.some((n) => n.id === p.node));
  const view = useMemo<View>(
    () => ({ problems: byNode, states: nodeStates, entry, labels: modelLabels, compact: readOnly }),
    [byNode, nodeStates, entry, modelLabels, readOnly],
  );

  const removeNodes = (ids: string[]) => {
    if (!ids.length) return;
    const gone = new Set(ids);
    // Functional updates: React Flow can report a removal in the same tick as other changes.
    setFlowNodes((ns) => ns.filter((f) => !gone.has(f.id)));
    setEdges((es) => es.filter((e) => !gone.has(e.from) && !gone.has(e.to)));
    if (gone.has(entry)) setEntry(nodes.find((n) => !gone.has(n.id))?.id ?? "");
    if (selectedId && gone.has(selectedId)) setSelectedId(null);
    touch();
  };

  const onNodesChange = (changes: NodeChange<FlowNode>[]) => {
    const removed = changes.filter((c) => c.type === "remove").map((c) => c.id);
    const rest = changes.filter((c) => c.type !== "remove");
    if (rest.length) setFlowNodes((ns) => applyNodeChanges(rest, ns));
    if (rest.some((c) => c.type === "position" && c.position)) touch();
    removeNodes(removed);
  };

  const onEdgesChange = (changes: EdgeChange[]) => {
    for (const c of changes) if (c.type === "select") setSelectedEdge(c.selected ? c.id : null);
    const removed = new Set(changes.filter((c) => c.type === "remove").map((c) => c.id));
    if (removed.size) {
      setEdges((es) => es.filter((e) => !removed.has(edgeId(e))));
      touch();
    }
  };

  const connect = (from: string, to: string) => {
    const e = newEdge(nodes, edges, from, to);
    if (!e) return;
    setEdges([...edges, e]);
    touch();
  };

  const add = (kind: AgentNodeKind) => {
    const n = blankNode(kind, nodes);
    setFlowNodes([...flowNodes.map((f) => ({ ...f, selected: false })), { ...toFlowNode(n), selected: true }]);
    if (!entry) setEntry(n.id);
    setSelectedId(n.id);
    touch();
    // New agents go to the right of the rest, often past the edge of the view (and the
    // settings panel narrows it). Centre on the new one at a readable zoom: fitting the
    // whole team into the narrowed canvas shrank four agents' text to ~7px.
    const at = { x: n.position.x + 105, y: n.position.y + 40 };
    setTimeout(() => void instance.current?.setCenter(at.x, at.y, { zoom: 0.9, duration: 200 }), 60);
  };

  const patchNode = (id: string, patch: Partial<AgentNode>) => {
    // Spread the flow node so React Flow keeps its measured size.
    setFlowNodes((ns) => ns.map((f) => (f.id === id ? { ...f, data: { node: { ...f.data.node, ...patch } } } : f)));
    touch();
  };

  const patchEdge = (target: AgentEdge, patch: Partial<AgentEdge>) => {
    setEdges((es) => es.map((e) => (edgeId(e) === edgeId(target) ? { ...e, ...patch } : e)));
    touch();
  };

  const selected = nodes.find((n) => n.id === selectedId);

  const flow = (
    <ViewCtx.Provider value={view}>
      <ReactFlow<FlowNode>
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={(c: Connection) => connect(c.source, c.target)}
        onNodeClick={(_, n) => setSelectedId(n.id)}
        onEdgeClick={(_, e) => setSelectedId(e.source)}
        onPaneClick={() => setSelectedId(null)}
        onInit={(rf) => (instance.current = rf)}
        fitView
        fitViewOptions={{ padding: readOnly ? 0.08 : 0.25, maxZoom: readOnly ? 0.75 : 1 }}
        // The default floor (0.5) stops a five-agent pattern shrinking into its gallery card.
        minZoom={readOnly ? 0.05 : 0.2}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
        panOnDrag={!readOnly}
        zoomOnScroll={!readOnly}
        zoomOnPinch={!readOnly}
        zoomOnDoubleClick={!readOnly}
        preventScrolling={!readOnly}
        deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
        proOptions={{ hideAttribution: readOnly }}
      >
        {!readOnly && <Background gap={20} size={1} />}
        {!readOnly && <Controls showInteractive={false} />}
      </ReactFlow>
    </ViewCtx.Provider>
  );

  if (readOnly) return <div className="ag-mini">{flow}</div>;

  return (
    <div className="ag-canvas" data-testid="agent-canvas">
      <div className="ag-palette" data-testid="agent-palette">
        <span className="ag-palette-label">Add</span>
        {KINDS.map((k) => (
          <button key={k} className={`btn sm ag-palette-btn kind-${k}`} data-testid={`agent-add-${k}`} onClick={() => add(k)}>
            {KIND_LABELS[k]}
          </button>
        ))}
        <span className="ag-palette-hint">Drag from a node's right edge to another node to connect them.</span>
      </div>
      {whole.length > 0 && (
        <div className="ag-problems" data-testid="agent-problems" role="status">
          <strong>Before this can run:</strong>{" "}
          {whole.map((p) => p.message).join(" ")}
        </div>
      )}
      <div className="ag-canvas-body">
        <div className="ag-flow">{flow}</div>
        {selected && (
          <NodeInspector
            key={selected.id}
            node={selected}
            nodes={nodes}
            edges={edges}
            isEntry={entry === selected.id}
            problems={byNode[selected.id] || []}
            models={models}
            modelLabels={modelLabels}
            defaultModel={defaultModel}
            codingAgents={codingAgents}
            onChange={(patch) => patchNode(selected.id, patch)}
            onEdgeChange={patchEdge}
            onConnect={(to) => connect(selected.id, to)}
            onRemoveEdge={(e) => {
              setEdges(edges.filter((x) => edgeId(x) !== edgeId(e)));
              touch();
            }}
            onMakeEntry={() => {
              setEntry(selected.id);
              touch();
            }}
            onDelete={() => removeNodes([selected.id])}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </div>
  );
}
