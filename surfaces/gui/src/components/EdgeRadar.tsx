import type { EdgeProfile } from "../timesaved";
import { useT } from "../i18n";

// The EDGE profile as a four-axis radar: Efficiency, Decisions, Growth, Empowerment,
// shares summing to 100.
//
// Growth and Empowerment are the two a usage log cannot read off its categories, so
// they are given operating definitions (see coworker/edge.py): Growth is work that is
// new and very different — the first time you reach for something; Empowerment is
// when you learned something, taken in or made permanent. Both are measured, so all
// four axes can carry a real number and the radar is a radar rather than three
// numbers and an apology.
//
// Inline SVG rather than a charting library: four points do not justify a dependency.

const W = 300;
const H = 190;
const CX = W / 2;
const CY = H / 2;
const R = 62;

/** Axis angles, clockwise from the top: Efficiency → Decisions → Growth → Empowerment. */
const ANGLES = [-90, 0, 90, 180];
const RINGS = [0.33, 0.66, 1];

function point(index: number, fraction: number): [number, number] {
  const rad = (ANGLES[index] * Math.PI) / 180;
  const r = R * Math.max(0, Math.min(1, fraction));
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)];
}

function ring(fraction: number): string {
  return ANGLES.map((_, i) => point(i, fraction).join(",")).join(" ");
}

/** Labels sit outside the outer ring; anchor by side so none of them clip. */
function anchor(index: number): "start" | "middle" | "end" {
  if (index === 1) return "start";
  if (index === 3) return "end";
  return "middle";
}

export function EdgeRadar({ edge }: { edge: EdgeProfile }) {
  const t = useT();
  const pillars = (edge.pillars || []).slice(0, 4);
  if (pillars.length < 4) return null;
  // Scale to the largest share, not to 100: an even 25/25/25/25 would otherwise draw
  // a tiny diamond and read as "you barely use it".
  const peak = Math.max(...pillars.map((p) => p.percent), 1);
  const shape = pillars.map((p, i) => point(i, p.percent / peak).join(",")).join(" ");

  return (
    <div className="flex flex-wrap items-start gap-5" data-testid="edge-radar">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
        {RINGS.map((f) => (
          <polygon key={f} points={ring(f)} fill="none" stroke="var(--line)" strokeWidth={1} />
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
          const [x, y] = point(i, 1.26);
          return (
            <text
              key={p.key}
              x={x}
              y={y}
              textAnchor={anchor(i)}
              dominantBaseline="middle"
              fontSize="10"
              fill="var(--muted)"
            >
              {t(p.label)}
            </text>
          );
        })}
      </svg>

      <div className="min-w-[210px] flex-1">
        <div className="text-[10px] uppercase tracking-wide text-faint mb-1">
          {t("Where the value lands")}
        </div>
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
