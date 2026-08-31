/** n8n-style flow diagram for one automation (Automations → task detail).
 *
 * An automation is a pipeline even if it's authored as prose:
 *
 *   ⏰ trigger → 🤖 agent (persona · model · workspace) → grants → 📬 output
 *
 * This renders that pipeline the way n8n/make.com would — rounded node cards
 * with ports, smooth bezier connectors, a dotted-grid canvas — from data the
 * task already carries. Pure SVG, no library: the layout is a fixed
 * left-to-right rank layout (trigger, agent, actions fan-out, output), which
 * is exactly right for a linear-agent pipeline and needs no solver.
 */
import { Automation } from "../api";

const NODE_W = 168;
const NODE_H = 58;
const GAP_X = 64;
const ROW_GAP = 14;

type FlowNode = {
  id: string;
  icon: string;
  title: string;
  sub: string;
  tone: "trigger" | "agent" | "action" | "output" | "muted";
};

const TONES: Record<FlowNode["tone"], { border: string; chip: string }> = {
  trigger: { border: "#0d9488", chip: "rgba(13,148,136,0.12)" },
  agent: { border: "#6366f1", chip: "rgba(99,102,241,0.12)" },
  action: { border: "#f59e0b", chip: "rgba(245,158,11,0.14)" },
  output: { border: "#10b981", chip: "rgba(16,185,129,0.12)" },
  muted: { border: "var(--line)", chip: "var(--paper)" },
};

/** The model's short name for the agent card — "qualitati:mimi-wolf" is a routing
 *  address, "mimi-wolf" is what the user picked. */
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

export function flowNodes(task: Automation): { agentCol: FlowNode[]; actions: FlowNode[]; output: FlowNode } {
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
    // The model actually answers the run, so name it. The folder is the second line
    // because it is where the work LANDS, not who does it.
    sub: [shortModel(task.model), basename(task.workspace)].filter(Boolean).join(" · ") || "workspace",
    tone: "agent",
  };
  const grants = task.always_allowed || [];
  // What the run may do without asking. This node used to say "Approval-gated" no
  // matter what — so an automation set to Full access was drawn as one that asks, which
  // is the diagram stating the opposite of the truth (owner-hit 2026-08-31).
  const permission: FlowNode =
    task.mode === "auto"
      ? {
          id: "ask",
          icon: "⚡",
          title: "Runs unattended",
          sub: "acts without asking",
          tone: "action",
        }
      : task.mode === "plan"
        ? {
            id: "ask",
            icon: "📋",
            title: "Proposes only",
            sub: "never acts on its own",
            tone: "muted",
          }
        : {
            id: "ask",
            icon: "✋",
            title: "Asks first",
            sub: "before consequential steps",
            tone: "muted",
          };
  const actions: FlowNode[] = grants.length
    ? [
        ...grants.map((g, i) => ({
          id: `grant-${i}`,
          icon: g.tool.includes("send") ? "📨" : g.tool.includes("shell") ? "⌘" : "🔧",
          title: g.tool,
          sub: g.target ? `→ ${g.target}` : "any target",
          tone: "action" as const,
        })),
        // Standing grants are exceptions to the permission level, not a replacement for
        // it: everything they do not cover still follows the mode.
        ...(task.mode === "auto" ? [] : [permission]),
      ]
    : [permission];
  // Where the result goes. A standing send grant means it is delivered somewhere, and
  // saying so is the difference between a diagram and a decoration.
  const delivery = (task.always_allowed || []).find((g) => g.tool.includes("send"));
  const output: FlowNode = {
    id: "output",
    icon: "📬",
    title: delivery?.target ? "Delivered" : "Run lands",
    sub: delivery?.target
      ? `${delivery.target}${task.notify_on_completion ? " + note" : ""}`
      : task.notify_on_completion
        ? "transcript + completion note"
        : "transcript in Automations",
    tone: "output",
  };
  return { agentCol: [trigger, agent], actions, output };
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
      transform={`translate(${x},${y})`}
      data-testid={`flow-node-${n.id}`}
      onClick={onClick ? () => onClick(n.id) : undefined}
      style={onClick ? { cursor: "pointer" } : undefined}
    >
      <rect
        width={NODE_W}
        height={NODE_H}
        rx={12}
        fill="var(--panel)"
        stroke={tone.border}
        strokeWidth={1.4}
      />
      {/* A small dot marks a node carrying a revision note (creation-form editing). */}
      {noted ? <circle cx={NODE_W - 10} cy={10} r={4} fill="#f59e0b" /> : null}
      <rect x={10} y={13} width={32} height={32} rx={9} fill={tone.chip} />
      <text x={26} y={34} textAnchor="middle" fontSize={15}>
        {n.icon}
      </text>
      <text x={50} y={26} fontSize={12} fontWeight={600} fill="var(--ink)">
        {n.title.length > 16 ? n.title.slice(0, 15) + "…" : n.title}
      </text>
      <text x={50} y={42} fontSize={10.5} fill="var(--muted)">
        {n.sub.length > 20 ? n.sub.slice(0, 19) + "…" : n.sub}
      </text>
      {/* n8n-style ports */}
      <circle cx={0} cy={NODE_H / 2} r={3.5} fill="var(--panel)" stroke={tone.border} strokeWidth={1.2} />
      <circle cx={NODE_W} cy={NODE_H / 2} r={3.5} fill="var(--panel)" stroke={tone.border} strokeWidth={1.2} />
    </g>
  );
}

function wire(x1: number, y1: number, x2: number, y2: number): string {
  const dx = Math.max(28, (x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

export function AutomationFlow({
  task,
  running,
  onNodeClick,
  notedNodes,
}: {
  task: Automation;
  running?: boolean;
  // Creation-form editing: nodes become clickable (focus the matching field /
  // attach a revision note); notedNodes marks which ones carry a note.
  onNodeClick?: (id: string) => void;
  notedNodes?: Set<string>;
}) {
  const { agentCol, actions, output } = flowNodes(task);
  const [trigger, agent] = agentCol;

  const colX = [12, 12 + NODE_W + GAP_X, 12 + (NODE_W + GAP_X) * 2, 12 + (NODE_W + GAP_X) * 3];
  const height = Math.max(actions.length, 1) * (NODE_H + ROW_GAP) - ROW_GAP + 24;
  const midY = height / 2;
  const rowY = (i: number) =>
    midY - ((actions.length - 1) * (NODE_H + ROW_GAP)) / 2 + i * (NODE_H + ROW_GAP) - NODE_H / 2;

  const wireStyle = {
    fill: "none",
    stroke: task.last_status === "error" ? "rgba(220,80,80,0.55)" : "rgba(120,128,140,0.45)",
    strokeWidth: 1.6,
    strokeDasharray: running ? "6 5" : undefined,
  } as const;

  const W = colX[3] + NODE_W + 12;
  return (
    <div className="autoflow" data-testid="automation-flow">
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" style={{ maxWidth: W, display: "block" }}>
        <defs>
          <pattern id="flow-dots" width={16} height={16} patternUnits="userSpaceOnUse">
            <circle cx={1.2} cy={1.2} r={1.2} fill="var(--line)" />
          </pattern>
          {running && (
            <style>{`.autoflow-wire { animation: autoflow-dash 0.9s linear infinite; } @keyframes autoflow-dash { to { stroke-dashoffset: -11; } }`}</style>
          )}
        </defs>
        <rect width={W} height={height} rx={14} fill="url(#flow-dots)" opacity={0.55} />

        <path className="autoflow-wire" d={wire(colX[0] + NODE_W, midY, colX[1], midY)} {...wireStyle} />
        {actions.map((_, i) => (
          <path
            key={`w1-${i}`}
            className="autoflow-wire"
            d={wire(colX[1] + NODE_W, midY, colX[2], rowY(i) + NODE_H / 2)}
            {...wireStyle}
          />
        ))}
        {actions.map((_, i) => (
          <path
            key={`w2-${i}`}
            className="autoflow-wire"
            d={wire(colX[2] + NODE_W, rowY(i) + NODE_H / 2, colX[3], midY)}
            {...wireStyle}
          />
        ))}

        <Card n={trigger} x={colX[0]} y={midY - NODE_H / 2} onClick={onNodeClick} noted={notedNodes?.has(trigger.id)} />
        <Card n={agent} x={colX[1]} y={midY - NODE_H / 2} onClick={onNodeClick} noted={notedNodes?.has(agent.id)} />
        {actions.map((n, i) => (
          <Card key={n.id} n={n} x={colX[2]} y={rowY(i)} onClick={onNodeClick} noted={notedNodes?.has(n.id)} />
        ))}
        <Card n={output} x={colX[3]} y={midY - NODE_H / 2} onClick={onNodeClick} noted={notedNodes?.has(output.id)} />
      </svg>
    </div>
  );
}
