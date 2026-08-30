import type { EdgeProfile } from "../timesaved";
import { useT } from "../i18n";

// The EDGE profile, drawn the way Chapter 9 draws it (Figure 9.1): three outcome
// pillars resting on one enabling pillar.
//
// The first version of this component was a four-axis radar with the shares summing
// to 100 — which contradicted the framework it claimed to show. Empowerment is not a
// fourth slice competing with the others; it is "the human capability that
// determines whether the other three materialize at all", and the book draws it as
// the foundation the three sit on. So: a triangle for the outcomes, a foundation bar
// underneath for the enabler.
//
// Inline SVG rather than a charting library: three points and a bar do not justify a
// dependency, and this way the shape is exactly the book's.

const W = 300;
const H = 172;
const CX = W / 2;
const CY = 84;
const R = 58;

/** Axis angles, clockwise from the top: Efficiency → Decisions → Growth. */
const ANGLES = [-90, 30, 150];
const RINGS = [0.33, 0.66, 1];

function point(index: number, fraction: number): [number, number] {
  const rad = (ANGLES[index] * Math.PI) / 180;
  const r = R * Math.max(0, Math.min(1, fraction));
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)];
}

function ring(fraction: number): string {
  return ANGLES.map((_, i) => point(i, fraction).join(",")).join(" ");
}

export function EdgeRadar({ edge }: { edge: EdgeProfile }) {
  const t = useT();
  const pillars = (edge.pillars || []).slice(0, 3);
  if (pillars.length < 3) return null;
  // Scale to the largest share, not to 100: an even 33/33/33 would otherwise draw a
  // tiny triangle and read as "you barely use it".
  const peak = Math.max(...pillars.map((p) => p.percent), 1);
  const shape = pillars.map((p, i) => point(i, p.percent / peak).join(",")).join(" ");
  const enabling = edge.enabling;

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
          const [x, y] = point(i, 1.3);
          return (
            <text
              key={p.key}
              x={x}
              y={y}
              textAnchor={i === 1 ? "start" : i === 2 ? "end" : "middle"}
              dominantBaseline="middle"
              fontSize="10"
              fill="var(--muted)"
            >
              {t(p.label)}
            </text>
          );
        })}
        {/* The enabling pillar, drawn as what it is: the base the three rest on. */}
        {enabling && (
          <>
            <rect
              x={40}
              y={H - 26}
              width={W - 80}
              height={18}
              rx={5}
              fill="var(--accent)"
              fillOpacity={0.14}
              stroke="var(--accent)"
              strokeOpacity={0.35}
            />
            <text
              x={CX}
              y={H - 17}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize="9.5"
              fill="var(--muted)"
            >
              {t(enabling.label)} · {enabling.percent}%
            </text>
          </>
        )}
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
        {enabling && (
          <div className="mt-2 pt-2 border-t border-line">
            <div className="text-[10px] uppercase tracking-wide text-faint mb-1">
              {t("What makes them possible")}
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-[13px] tabular-nums text-ink w-9 text-right font-medium">
                {enabling.percent}%
              </span>
              <span className="text-[12.5px] text-ink">{t(enabling.label)}</span>
            </div>
            <div className="text-[11px] text-faint mt-0.5">{t(enabling.blurb)}</div>
          </div>
        )}
      </div>
    </div>
  );
}
