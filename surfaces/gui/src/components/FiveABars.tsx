import type { FiveAProfile } from "../timesaved";
import { useT } from "../i18n";

// The Five A's of Applied GenAI (Chapter 7), drawn as the chapter draws them: a
// continuum, left to right, along which "autonomy, blast radius, and governance
// requirements rise together" (Figure 7.1).
//
// Bars rather than a radar, and counts rather than minutes, because this answers a
// different question from the EDGE profile beside it. EDGE asks where the value
// landed — time is the honest unit for that. This asks which mode of working the
// person actually uses, and a mode is a choice made once per turn.
//
// The order is never sorted by size. The whole point of the figure is the ladder:
// seeing that your bars pile up on the left (heavy human involvement) or the right
// (light supervision) is the finding. Sorting would destroy it.

export function FiveABars({ five }: { five: FiveAProfile }) {
  const t = useT();
  const levels = five.levels || [];
  if (!levels.length) return null;
  const peak = Math.max(...levels.map((l) => l.percent), 1);

  return (
    <div data-testid="fivea-bars">
      <div className="flex items-end gap-2 h-[92px] mb-1">
        {levels.map((level) => (
          <div key={level.key} className="flex-1 flex flex-col justify-end items-center h-full">
            <div className="text-[11px] tabular-nums text-muted mb-1">{level.percent}%</div>
            <div
              className="w-full rounded-t"
              style={{
                height: `${Math.max((level.percent / peak) * 68, level.percent > 0 ? 3 : 1)}px`,
                background: level.percent > 0 ? "var(--accent)" : "var(--line)",
                opacity: level.percent > 0 ? 0.85 : 1,
              }}
              title={`${level.turns} ${level.turns === 1 ? "turn" : "turns"}`}
            />
          </div>
        ))}
      </div>
      {/* The axis the figure is built on — stated, not implied. */}
      <div className="flex gap-2" data-testid="fivea-labels">
        {levels.map((level) => (
          <div key={level.key} className="flex-1 text-center">
            <div className="text-[10.5px] text-ink leading-tight">{t(level.label)}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 mt-1.5 text-[10px] text-faint">
        <span>{t("more human involvement")}</span>
        <div className="flex-1 h-px bg-line" />
        <span>{t("more autonomy")}</span>
      </div>
      {five.leading && (
        <div className="text-[11.5px] text-muted mt-2">
          {t("Mostly")}{" "}
          <span className="text-ink font-medium">{t(five.leading)}</span>
          {" — "}
          {t(levels.find((l) => l.key === five.leading)?.blurb || "")}
        </div>
      )}
    </div>
  );
}
