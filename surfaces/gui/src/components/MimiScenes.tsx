/** Mimi's playful scenes — a butterfly lands on her nose, a bubble drifts by and pops.
 *
 * Ported from QualiTaTi (mimiPlayfulScenes.js + MimiPlayfulScene.js, 2026-09-17). One
 * clock drives both the sprite's frame (an expression played once across its window,
 * neutral cell 0 before and after) and the vector visitor drawn over it. The visitor's
 * coordinates are percent of the sprite box. */
import { useEffect, useRef, useState } from "react";
import { SHEETS, SIZE, frameTransform, type Sheet } from "../mimiSheets";

export type SceneName = "butterfly" | "bubble";
export const SCENES: Record<SceneName, { duration: number; sheets: Sheet[] }> = {
  butterfly: { duration: 6.4, sheets: ["thinking", "sniff", "happy"] },
  bubble: { duration: 4.8, sheets: ["wink"] },
};

const clamp = (v: number) => Math.max(0, Math.min(1, v));
const ease = (v: number) => {
  const t = clamp(v);
  return t * t * (3 - 2 * t);
};
const phase = (time: number, start: number, end: number) => clamp((time - start) / (end - start));
const envelope = (time: number, start: number, peak: number, end: number) =>
  time <= peak ? ease(phase(time, start, peak)) : 1 - ease(phase(time, peak, end));
function bezier(points: [number, number][], progress: number): [number, number] {
  const t = clamp(progress);
  const u = 1 - t;
  return [0, 1].map(
    (axis) =>
      u ** 3 * points[0][axis] + 3 * u * u * t * points[1][axis] + 3 * u * t * t * points[2][axis] + t ** 3 * points[3][axis],
  ) as [number, number];
}

export type SceneSample = {
  time: number;
  sheet: Sheet;
  frame: number;
  lean: number;
  visitor: Record<string, number>;
};

export function sampleScene(name: SceneName, elapsed: number): SceneSample {
  const scene = SCENES[name];
  const time = Math.max(0, Math.min(scene.duration, Number.isFinite(elapsed) ? elapsed : 0));
  let expressionStart = 2.25;
  let expressionEnd = 4.25;
  let sheet: Sheet = scene.sheets[0];
  let lean = 0;
  let visitor: Record<string, number>;

  if (name === "bubble") {
    expressionStart = 1.55;
    expressionEnd = 3.55;
    const arrival = ease(phase(time, 0.35, 2.35));
    const [x, y] = bezier([[13, 72], [8, 39], [35, 29], [46, 43]], arrival);
    const pop = phase(time, 2.35, 2.9);
    visitor = {
      x,
      y,
      pop,
      radius: 6.5 - 1.6 * ease(phase(time, 2.08, 2.35)),
      opacity: ease(phase(time, 0.15, 0.5)) * (1 - ease(phase(time, 2.35, 2.43))),
      burstOpacity: envelope(time, 2.35, 2.43, 2.9),
    };
  } else {
    // Notice → investigate → delight. Each complete expression returns to its
    // neutral endpoints before the next sheet takes over.
    if (time < 2.25) {
      sheet = "thinking";
      expressionStart = 0.25;
      expressionEnd = 2.2;
    } else if (time < 4.3) {
      sheet = "sniff";
    } else {
      sheet = "happy";
      expressionStart = 4.3;
      expressionEnd = 6.3;
    }
    lean = -2.5 * envelope(time, 0.3, 1.25, 2.3) + 1.8 * envelope(time, 4.4, 5.2, 6.3);
    const leaving = time > 4.4;
    const progress = ease(phase(time, leaving ? 4.4 : 0.3, leaving ? 6.15 : 2.4));
    const [x, y] = leaving
      ? bezier([[49, 40], [80, 53], [90, 18], [72, 5]], progress)
      : bezier([[12, 35], [12, 8], [65, 16], [49, 40]], progress);
    visitor = {
      x,
      y,
      opacity: ease(phase(time, 0.1, 0.5)) * (1 - ease(phase(time, 5.65, 6.2))),
      // Slower, smaller wing beats while perched on the nose.
      wing: 0.25 + 0.75 * Math.abs(Math.cos(time * (time > 2.4 && !leaving ? 8 : 17))),
      rotation: leaving ? -18 + progress * 40 : -22 * (1 - progress),
    };
  }
  const frames = SHEETS[sheet].frames;
  return {
    time,
    sheet,
    lean,
    visitor,
    frame:
      time <= expressionStart || time >= expressionEnd
        ? 0
        : Math.round(phase(time, expressionStart, expressionEnd) * (frames - 1)),
  };
}

const TEAL = "#0d9488";

function SceneDetails({ name, sample }: { name: SceneName; sample: SceneSample }) {
  const v = sample.visitor;
  return (
    <svg aria-hidden="true" viewBox="0 0 100 100" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
      {name === "butterfly" && (
        <g transform={`translate(${v.x} ${v.y}) rotate(${v.rotation})`} opacity={v.opacity}>
          <g transform={`scale(${v.wing} 1)`}>
            <path d="M0 0 C-9 -12 -12 -3 -6 1 C-12 7 -3 9 0 1" fill={TEAL} />
            <path d="M0 0 C9 -12 12 -3 6 1 C12 7 3 9 0 1" fill={TEAL} />
            <path d="M-2 -1 Q-7 -7 -7 -3 M2 -1 Q7 -7 7 -3" fill="none" stroke="white" strokeWidth=".65" opacity=".75" />
          </g>
          <path d="M0 -2V3 M0 -1Q-1 -5 -2 -5 M0 -1Q1 -5 2 -5" fill="none" stroke="#184B45" strokeWidth=".8" strokeLinecap="round" />
        </g>
      )}
      {name === "bubble" && (
        <>
          <g transform={`translate(${v.x} ${v.y})`} opacity={v.opacity}>
            <circle r={v.radius} fill={TEAL} fillOpacity=".08" stroke={TEAL} strokeOpacity=".65" strokeWidth=".65" />
            <path d={`M${-v.radius * 0.65} -1 Q${-v.radius * 0.6} ${-v.radius * 0.7} 0 ${-v.radius * 0.72}`} fill="none" stroke="white" strokeWidth="1.3" strokeLinecap="round" />
            <path d={`M1 ${v.radius * 0.76} Q${v.radius * 0.6} ${v.radius * 0.7} ${v.radius * 0.76} 1`} fill="none" stroke="#C6BAE8" strokeWidth=".8" strokeLinecap="round" />
          </g>
          <g transform={`translate(${v.x} ${v.y})`} opacity={v.burstOpacity} fill="none" stroke={TEAL} strokeWidth=".85" strokeLinecap="round">
            {[0, 60, 120, 180, 240, 300].map((angle) => (
              <path key={angle} transform={`rotate(${angle})`} d={`M${5 + v.pop * 8} 0h${2 * (1 - v.pop)}`} />
            ))}
          </g>
        </>
      )}
    </svg>
  );
}

/** One scene, played once; `onDone` when its clock runs out. The clock pauses while the
 *  window is hidden (a floating pet behind another app should not burn frames). */
export function MimiScene({ name, onDone }: { name: SceneName; onDone: () => void }) {
  const scene = SCENES[name];
  const [time, setTime] = useState(0);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    let raf = 0;
    let cancelled = false;
    let finished = false;
    let previous: number | null = null;
    let elapsed = 0;
    const tick = (stamp: number) => {
      if (cancelled || finished || document.hidden) return;
      if (previous !== null) elapsed += (stamp - previous) / 1000;
      previous = stamp;
      setTime(Math.min(elapsed, scene.duration));
      if (elapsed >= scene.duration) {
        finished = true;
        done.current();
      } else {
        raf = requestAnimationFrame(tick);
      }
    };
    const visibility = () => {
      cancelAnimationFrame(raf);
      previous = null;
      if (!document.hidden && !finished) raf = requestAnimationFrame(tick);
    };
    visibility();
    document.addEventListener("visibilitychange", visibility);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [name, scene.duration]);

  const sample = sampleScene(name, time);
  const sheet = SHEETS[sample.sheet];
  return (
    <div
      data-testid="companion-sprite"
      data-phase="idle"
      data-sheet={sample.sheet}
      data-scene={name}
      data-style="classic"
      style={{ position: "relative", width: SIZE, height: SIZE, overflow: "hidden", filter: "drop-shadow(0 4px 10px rgba(0,0,0,0.25))" }}
    >
      <div style={{ position: "absolute", inset: 0, transformOrigin: "50% 94%", transform: `rotate(${sample.lean}deg)` }}>
        <div
          style={{
            width: SIZE,
            height: SIZE,
            backgroundImage: `url(${sheet.src})`,
            backgroundRepeat: "no-repeat",
            backgroundSize: `${sheet.frames * SIZE}px ${SIZE}px`,
            backgroundPosition: `-${sample.frame * SIZE}px 0`,
            transform: frameTransform(sample.sheet, sample.frame),
            transformOrigin: "0 0",
          }}
        />
      </div>
      <SceneDetails name={name} sample={sample} />
    </div>
  );
}

/** Every animation at once, looping — the browser dev build's `#companion-gallery`, so
 *  the owner can watch them without waiting for the idle rotation. */
export function MimiGallery() {
  const names = Object.keys(SHEETS) as Sheet[];
  return (
    <div style={{ padding: 24, fontFamily: "-apple-system, sans-serif", color: "#111", background: "#fafafa", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 16px" }}>Mimi's animations</h1>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 18 }}>
        {(Object.keys(SCENES) as SceneName[]).map((name) => (
          <GalleryTile key={name} label={`scene · ${name}`}>
            {(replay) => <MimiScene name={name} onDone={replay} />}
          </GalleryTile>
        ))}
        {names.map((name) => (
          <GalleryTile key={name} label={`${name} · ${SHEETS[name].frames}f`}>
            {(replay) => <LoopingSheet name={name} onDone={replay} />}
          </GalleryTile>
        ))}
      </div>
    </div>
  );
}

function GalleryTile({ label, children }: { label: string; children: (replay: () => void) => JSX.Element }) {
  const [round, setRound] = useState(0);
  return (
    <div style={{ width: 150, textAlign: "center" }}>
      <div style={{ display: "flex", justifyContent: "center", height: SIZE + 8, alignItems: "flex-end" }} key={round}>
        {children(() => setTimeout(() => setRound((r) => r + 1), 400))}
      </div>
      <div style={{ fontSize: 11.5, color: "#555", marginTop: 6 }}>{label}</div>
    </div>
  );
}

function LoopingSheet({ name, onDone }: { name: Sheet; onDone: () => void }) {
  const sheet = SHEETS[name];
  const [frame, setFrame] = useState(0);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    const id = window.setInterval(() => {
      setFrame((f) => {
        const next = f + 1;
        if (next >= sheet.frames) {
          if (sheet.loop) return 0;
          window.clearInterval(id);
          done.current();
          return f;
        }
        return next;
      });
    }, 1000 / sheet.fps);
    return () => window.clearInterval(id);
  }, [name, sheet.frames, sheet.fps, sheet.loop]);
  return (
    <div style={{ width: SIZE, height: SIZE, overflow: "hidden" }}>
      <div
        style={{
          width: SIZE,
          height: SIZE,
          backgroundImage: `url(${sheet.src})`,
          backgroundRepeat: "no-repeat",
          backgroundSize: `${sheet.frames * SIZE}px ${SIZE}px`,
          backgroundPosition: `-${frame * SIZE}px 0`,
          transform: frameTransform(name, frame),
          transformOrigin: "0 0",
        }}
      />
    </div>
  );
}
