/** n8n-style flow diagram for one automation (Automations → task detail).
 *
 * An automation is a pipeline even if it's authored as prose, and the diagram borrows
 * n8n's vocabulary because that is the one this audience already reads:
 *
 *   ⏰ trigger ──▶ 🐶 agent ──▶ ⑂ result ──▶ where it lands / what happens if it fails
 *                    ┊
 *              model · folder · each tool it may use, hanging below on dashed wires
 *
 * The split matters. The MAIN chain is what happens; the SUB-NODES are what the agent
 * is made of — the model answering, the folder it works in, the standing grants it may
 * exercise. n8n draws that distinction with solid versus dashed connectors, and it is
 * the reason its graphs read at a glance while a flat left-to-right row of four boxes
 * looks the same for every automation (owner ask 2026-08-31).
 *
 * Everything drawn comes from the task's own data — the permission level, the model, the
 * grants, the delivery target. Nothing is a placeholder: a diagram that says the same
 * thing about every automation is decoration.
 */
import { Automation } from "../api";

const NODE_W = 170;
const NODE_H = 58;
const GAP_X = 66;
const SUB_R = 20;
const SUB_GAP = 96;
// How far the two outcomes sit above and below the main line.
const BRANCH_RISE = 46;

type FlowNode = {
  id: string;
  icon: string;
  title: string;
  sub: string;
  tone: "trigger" | "agent" | "action" | "output" | "muted" | "danger";
};

const TONES: Record<FlowNode["tone"], { border: string; chip: string }> = {
  trigger: { border: "#0d9488", chip: "rgba(13,148,136,0.12)" },
  agent: { border: "#6366f1", chip: "rgba(99,102,241,0.12)" },
  action: { border: "#f59e0b", chip: "rgba(245,158,11,0.14)" },
  output: { border: "#10b981", chip: "rgba(16,185,129,0.12)" },
  danger: { border: "#ef4444", chip: "rgba(239,68,68,0.12)" },
  muted: { border: "var(--line)", chip: "var(--paper)" },
};

/** The model's short name — "qualitati:mimi-wolf" is a routing address, "mimi-wolf" is
 *  what the user picked it under. */
function shortModel(model?: string | null): string {
  const raw = (model || "").trim();
  if (!raw) return "";
  return raw.includes(":") ? raw.slice(raw.indexOf(":") + 1) : raw;
}

function basename(path: string): string {
  const parts = (path || "").split("/").filter(Boolean);
  let name = parts[parts.length - 1] || path || "";
  // A task's own workspace folder is internal plumbing ("__task__task-…"):
  // the human-meaningful location is its parent.
  if (name.startsWith("__task__")) name = parts[parts.length - 2] || "workspace";
  return name;
}

function toolIcon(tool: string): string {
  if (tool.includes("send") || tool.includes("mail")) return "📨";
  if (tool.includes("shell") || tool.includes("bash")) return "⌘";
  if (tool.includes("file") || tool.includes("write")) return "📄";
  if (tool.includes("search") || tool.includes("browser")) return "🔎";
  return "🔧";
}

export type FlowModel = {
  trigger: FlowNode;
  agent: FlowNode;
  /** What the agent is MADE of — model, folder, standing grants. Dashed, below. */
  subs: FlowNode[];
  /** The two ways a run ends. Both are always drawn: an automation that can only be
   *  shown succeeding is a diagram that has never met one. */
  success: FlowNode;
  failure: FlowNode;
};

export function flowNodes(task: Automation): FlowModel {
  const trigger: FlowNode = {
    id: "trigger",
    icon: "⏰",
    title: task.enabled ? "Schedule" : "Schedule · paused",
    sub: task.schedule || "manual",
    tone: task.enabled ? "trigger" : "muted",
  };

  const agent: FlowNode = {
    id: "agent",
    icon: "🐶",
    title: task.agent === "cowork" ? "MimiWork" : task.agent,
    sub:
      task.mode === "auto"
        ? "runs unattended"
        : task.mode === "plan"
          ? "proposes only"
          : "asks before acting",
    tone: "agent",
  };

  // What the agent is made of. The model and the folder are always true of a run; the
  // grants are whatever this automation was actually given.
  const subs: FlowNode[] = [
    {
      id: "model",
      icon: "🧠",
      title: shortModel(task.model) || "App default",
      sub: "model",
      tone: "muted",
    },
    {
      id: "folder",
      icon: "📁",
      title: basename(task.workspace) || "workspace",
      sub: "works in",
      tone: "muted",
    },
    ...(task.always_allowed || []).map((g, i) => ({
      id: `grant-${i}`,
      icon: toolIcon(g.tool),
      title: g.tool,
      sub: g.target ? g.target : "any target",
      tone: "action" as const,
    })),
  ];

  // Where a finished run goes. A standing send grant means it is DELIVERED somewhere,
  // and naming that is the difference between a diagram and a decoration.
  const delivery = (task.always_allowed || []).find((g) => g.tool.includes("send"));
  const success: FlowNode = {
    id: "output",
    icon: "📬",
    title: delivery?.target ? "Delivered" : "Saved",
    sub: delivery?.target
      ? `${delivery.target}${task.notify_on_completion ? " + note" : ""}`
      : task.notify_on_completion
        ? "transcript + a note"
        : "kept in Automations",
    tone: "output",
  };

  const failure: FlowNode = {
    id: "failure",
    icon: "⚠️",
    title: "If it fails",
    // Deliberately concrete: this is what the app actually does, and it is the half of
    // the picture every generic flow diagram leaves out.
    sub: "recorded and badged",
    tone: task.last_status === "error" ? "danger" : "muted",
  };

  return { trigger, agent, subs, success, failure };
}

function Card({
  n,
  x,
  y,
  onClick,
  noted,
}: {
  n: FlowNode;
  x: number;
  y: number;
  onClick?: (id: string) => void;
  noted?: boolean;
}) {
  const tone = TONES[n.tone];
  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={onClick ? () => onClick(n.id) : undefined}
      style={onClick ? { cursor: "pointer" } : undefined}
      data-testid={`flow-node-${n.id}`}
    >
      <rect
        width={NODE_W}
        height={NODE_H}
        rx={12}
        fill="var(--panel)"
        stroke={tone.border}
        strokeWidth={1.4}
      />
      {noted ? <circle cx={NODE_W - 10} cy={10} r={4} fill="#f59e0b" /> : null}
      <rect x={10} y={13} width={32} height={32} rx={9} fill={tone.chip} />
      <text x={26} y={34} textAnchor="middle" fontSize={15}>
        {n.icon}
      </text>
      <text x={50} y={26} fontSize={12} fontWeight={600} fill="var(--ink)">
        {n.title.length > 17 ? n.title.slice(0, 16) + "…" : n.title}
      </text>
      <text x={50} y={42} fontSize={10.5} fill="var(--muted)">
        {n.sub.length > 21 ? n.sub.slice(0, 20) + "…" : n.sub}
      </text>
      {/* n8n-style ports: square in, round out. */}
      <rect x={-3.5} y={NODE_H / 2 - 5} width={7} height={10} rx={1.5} fill={tone.border} />
      <circle cx={NODE_W} cy={NODE_H / 2} r={4} fill="var(--panel)" stroke={tone.border} strokeWidth={1.4} />
    </g>
  );
}

/** A capability the agent is built from: a circle with its name beneath, exactly the
 *  shape n8n gives a sub-node so it never reads as a step in the chain. */
function SubNode({
  n,
  cx,
  cy,
  onClick,
  noted,
}: {
  n: FlowNode;
  cx: number;
  cy: number;
  onClick?: (id: string) => void;
  noted?: boolean;
}) {
  const tone = TONES[n.tone];
  const label = n.title.length > 15 ? n.title.slice(0, 14) + "…" : n.title;
  return (
    <g
      transform={`translate(${cx}, ${cy})`}
      onClick={onClick ? () => onClick(n.id) : undefined}
      style={onClick ? { cursor: "pointer" } : undefined}
      data-testid={`flow-sub-${n.id}`}
    >
      <circle r={SUB_R} fill="var(--panel)" stroke={tone.border} strokeWidth={1.4} />
      <circle r={SUB_R - 4} fill={tone.chip} />
      <text y={5} textAnchor="middle" fontSize={15}>
        {n.icon}
      </text>
      {noted ? <circle cx={SUB_R - 3} cy={-SUB_R + 3} r={4} fill="#f59e0b" /> : null}
      {/* The diamond port n8n puts on top of a sub-node. */}
      <path d={`M 0 ${-SUB_R - 5} l 4.5 4.5 l -4.5 4.5 l -4.5 -4.5 z`} fill={tone.border} />
      <text y={SUB_R + 15} textAnchor="middle" fontSize={10.5} fontWeight={600} fill="var(--ink)">
        {label}
      </text>
      <text y={SUB_R + 28} textAnchor="middle" fontSize={9.5} fill="var(--muted)">
        {n.sub.length > 18 ? n.sub.slice(0, 17) + "…" : n.sub}
      </text>
    </g>
  );
}

function wire(x1: number, y1: number, x2: number, y2: number): string {
  const dx = Math.max(28, (x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

/** Agent bottom → sub-node top. Vertical bezier, so it reads as "hangs off" rather
 *  than "comes after" — the whole point of the dashed sub-connector. */
function drop(x1: number, y1: number, x2: number, y2: number): string {
  const dy = Math.max(24, (y2 - y1) / 2);
  return `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
}

export function AutomationFlow({
  task,
  running,
  onNodeClick,
  notedNodes,
}: {
  task: Automation;
  running?: boolean;
  onNodeClick?: (id: string) => void;
  notedNodes?: Set<string>;
}) {
  const { trigger, agent, subs, success, failure } = flowNodes(task);

  const colX = [14, 14 + NODE_W + GAP_X, 14 + (NODE_W + GAP_X) * 2];
  // The main line sits low enough that the branch rising above it is not clipped —
  // the success node lives at mainY - BRANCH_RISE.
  const mainY = 14 + BRANCH_RISE;
  const midY = mainY + NODE_H / 2;
  // The branch splits above and below the main line, the way an n8n If node does.
  const successY = mainY - BRANCH_RISE;
  const failureY = mainY + BRANCH_RISE;
  const subY = mainY + NODE_H + 96;

  // Sub-nodes hang under the agent, centred on it and spreading out as they multiply.
  const subCentre = colX[1] + NODE_W / 2;
  const subStart = subCentre - ((subs.length - 1) * SUB_GAP) / 2;
  const subX = (i: number) => subStart + i * SUB_GAP;

  const W = Math.max(
    colX[2] + NODE_W + 14,
    subX(subs.length - 1) + SUB_R + 40,
  );
  const leftPad = Math.min(0, subX(0) - SUB_R - 14);
  const height = subY + SUB_R + 46;

  const errored = task.last_status === "error";
  const wireStyle = {
    fill: "none",
    stroke: errored ? "rgba(220,80,80,0.5)" : "rgba(120,128,140,0.45)",
    strokeWidth: 1.6,
    strokeDasharray: running ? "6 5" : undefined,
  } as const;
  // Sub-connectors are ALWAYS dashed: they are not a step, and n8n's readers know that
  // shape means "provides", not "then".
  const subWire = {
    fill: "none",
    stroke: "rgba(120,128,140,0.4)",
    strokeWidth: 1.4,
    strokeDasharray: "4 4",
  } as const;

  return (
    <div className="autoflow" data-testid="automation-flow">
      <svg
        viewBox={`${leftPad} 0 ${W - leftPad} ${height}`}
        width="100%"
        style={{ maxWidth: W - leftPad, display: "block" }}
      >
        <defs>
          <pattern id="flow-dots" width={16} height={16} patternUnits="userSpaceOnUse">
            <circle cx={1.2} cy={1.2} r={1.2} fill="var(--line)" />
          </pattern>
          {running && (
            <style>{`.autoflow-wire { animation: autoflow-dash 0.9s linear infinite; } @keyframes autoflow-dash { to { stroke-dashoffset: -11; } }`}</style>
          )}
        </defs>
        <rect x={leftPad} width={W - leftPad} height={height} rx={14} fill="url(#flow-dots)" opacity={0.55} />

        {/* Main chain */}
        <path className="autoflow-wire" d={wire(colX[0] + NODE_W, midY, colX[1], midY)} {...wireStyle} />
        <path
          className="autoflow-wire"
          d={wire(colX[1] + NODE_W, midY, colX[2], successY + NODE_H / 2)}
          {...wireStyle}
        />
        <path
          className="autoflow-wire"
          d={wire(colX[1] + NODE_W, midY, colX[2], failureY + NODE_H / 2)}
          {...wireStyle}
        />
        {/* Branch labels, as n8n puts true/false on the wire. */}
        <text
          x={colX[1] + NODE_W + GAP_X / 2}
          y={successY + NODE_H / 2 - 6}
          textAnchor="middle"
          fontSize={9.5}
          fill="var(--faint)"
        >
          done
        </text>
        <text
          x={colX[1] + NODE_W + GAP_X / 2}
          y={failureY + NODE_H / 2 + 16}
          textAnchor="middle"
          fontSize={9.5}
          fill="var(--faint)"
        >
          error
        </text>

        {/* What the agent is made of */}
        {subs.map((n, i) => (
          <path
            key={`sub-${n.id}`}
            d={drop(subCentre, mainY + NODE_H, subX(i), subY - SUB_R - 6)}
            {...subWire}
          />
        ))}

        <Card n={trigger} x={colX[0]} y={mainY} onClick={onNodeClick} noted={notedNodes?.has(trigger.id)} />
        <Card n={agent} x={colX[1]} y={mainY} onClick={onNodeClick} noted={notedNodes?.has(agent.id)} />
        <Card n={success} x={colX[2]} y={successY} onClick={onNodeClick} noted={notedNodes?.has(success.id)} />
        <Card n={failure} x={colX[2]} y={failureY} onClick={onNodeClick} noted={notedNodes?.has(failure.id)} />
        {subs.map((n, i) => (
          <SubNode
            key={n.id}
            n={n}
            cx={subX(i)}
            cy={subY}
            onClick={onNodeClick}
            noted={notedNodes?.has(n.id)}
          />
        ))}
      </svg>
    </div>
  );
}
