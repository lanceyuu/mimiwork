import type { EdgeProfile } from "../timesaved";
import { useT } from "../i18n";

// The EDGE radar: what KIND of help this account gets from Mimi.
//
// Four axes, drawn as inline SVG rather than pulled from a charting library — the
// shape is four points on two crossed axes, and a dependency for that would cost
// more to ship than it saves to write. The geometry is deliberately plain: a
// polygon over concentric rings, so the eye reads the SHAPE (lopsided vs even)
// before it reads any number.

// The canvas is WIDER than it is tall on purpose: "Empowerment" and "Decisions" sit
// on the horizontal axis and run outward from it, so a square viewBox clips them —
// which is exactly what the first render did.
const W = 300;
const H = 190;
const CX = W / 2;
const CY = H / 2;
const R = 66; // outer ring radius; labels live in the margin beyond it
const RINGS = [0.25, 0.5, 0.75, 1];

/** Axis angles, clockwise from the top: E → D → G → E. */
const ANGLES = [-90, 0, 90, 180];

function point(index: number, fraction: number): [number, number] {
  const rad = (ANGLES[index] * Math.PI) / 180;
  const r = R * Math.max(0, Math.min(1, fraction));
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)];
}

function ringPath(fraction: number): string {
  return ANGLES.map((_, i) => point(i, fraction).join(",")).join(" ");
}

export function EdgeRadar({ edge }: { edge: EdgeProfile }) {
  const t = useT();
  const pillars = edge.pillars.slice(0, 4);
  // Scale to the largest share, not to 100: a balanced profile of 25/25/25/25 would
  // otherwise draw as a tiny diamond and read as "you barely use it".
  const peak = Math.max(...pillars.map((p) => p.percent), 1);
  const shape = pillars.map((p, i) => point(i, p.percent / peak).join(",")).join(" ");

  return (
    <div className="flex flex-wrap items-center gap-5" data-testid="edge-radar">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
        {RINGS.map((f) => (
          <polygon
            key={f}
            points={ringPath(f)}
            fill="none"
            stroke="var(--line)"
            strokeWidth={1}
          />
        ))}
        {ANGLES.map((_, i) => {
          const [x, y] = point(i, 1);
          return <line key={i} x1={CX} y1={CY} x2={x} y2={y} stroke="var(--line)" strokeWidth={1} />;
        })}
        <polygon
          points={shape}
          fill="var(--accent)"
          fillOpacity={0.16}
          stroke="var(--accent)"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {pillars.map((p, i) => {
          const [x, y] = point(i, p.percent / peak);
          return <circle key={p.key} cx={x} cy={y} r={3.5} fill="var(--accent)" />;
        })}
        {pillars.map((p, i) => {
          const [x, y] = point(i, i % 2 === 1 ? 1.14 : 1.3);
          return (
            <text
              key={p.key}
              x={x}
              y={y}
              // i=1 is the RIGHT axis, so its text runs rightward ("start"); i=3 is the
              // LEFT axis and runs leftward ("end"). Reversed, the labels lie across
              // the chart — which is exactly how the first render looked.
              textAnchor={i === 1 ? "start" : i === 3 ? "end" : "middle"}
              dominantBaseline="middle"
              fontSize="10"
              fill="var(--muted)"
            >
              {t(p.label)}
            </text>
          );
        })}
      </svg>
      <div className="min-w-[200px] flex-1">
        {pillars.map((p) => (
          <div key={p.key} className="flex items-baseline gap-2 py-[3px]">
            <span className="text-[13px] tabular-nums text-ink w-9 text-right font-medium">
              {p.percent}%
            </span>
            <span className="text-[12.5px] text-ink">{t(p.label)}</span>
            <span className="text-[11px] text-faint truncate">{t(p.blurb)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
