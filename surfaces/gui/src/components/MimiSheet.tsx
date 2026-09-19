import { useEffect, useRef, useState, type CSSProperties } from "react";
import { SHEETS, SIZE, frameTransform, type Sheet } from "../mimiSheets";
import { useReducedMotion } from "../useReducedMotion";

type Step = { frame: number; duration: number; rest?: number };
const SCRATCH: Step[] = [
  { frame: 0, duration: 220, rest: 1 },
  { frame: 0, duration: 160, rest: 0.5 },
  ...[0, 1, 2, 3, 4, 5, 6].map((frame) => ({ frame, duration: 110 })),
  // Short strokes around the ear, with a breath between the two bouts.
  ...[7, 8, 9, 8, 7, 8, 9, 8, 7].map((frame) => ({ frame, duration: 75 })),
  { frame: 7, duration: 260 },
  ...[8, 9, 8, 7, 8, 9, 8, 7].map((frame) => ({ frame, duration: 85 })),
  ...[6, 5, 4, 3, 2, 1, 0].map((frame) => ({ frame, duration: 110 })),
  { frame: 0, duration: 160, rest: 0.5 },
  { frame: 0, duration: 300, rest: 1 },
];
const PLAYBACK = Object.fromEntries(Object.entries(SHEETS).map(([name, sheet]) => [
  name,
  name === "scratch" ? SCRATCH : Array.from({ length: sheet.frames }, (_, frame) => ({ frame, duration: 1000 / sheet.fps })),
])) as Record<Sheet, Step[]>;

export function sheetPlayback(name: Sheet): readonly Step[] { return PLAYBACK[name]; }

const ease = (value: number) => {
  const t = Math.max(0, Math.min(1, value));
  return t * t * (3 - 2 * t);
};
const pulse = (t: number, start: number, peak: number, end: number) =>
  t <= peak ? ease((t - start) / (peak - start)) : 1 - ease((t - peak) / (end - peak));

export function headMotion(name: Sheet, frame: number) {
  const t = frame / (SHEETS[name].frames - 1);
  if (name === "thinking") {
    const ponder = pulse(t, 0.08, 0.34, 0.69);
    return { x: -1.4 * ponder, y: -0.8 * ponder, angle: -6 * ponder + 3 * pulse(t, 0.62, 0.78, 0.98), scale: 1 };
  }
  if (name === "sniff") {
    const lean = pulse(t, 0.05, 0.27, 0.93);
    const breaths = pulse(t, 0.27, 0.35, 0.43) + pulse(t, 0.48, 0.56, 0.64);
    return { x: 1.5 * lean, y: 1.8 * lean + 2.2 * breaths, angle: 3 * lean, scale: 1 + 0.035 * lean };
  }
  return { x: 0, y: 0, angle: 0, scale: 1 };
}

/** Keep the paws planted while the head investigates. Both masks meet in the
 *  white neck fur, so the movement doesn't drag the entire dog around. */
export function MimiSheetFrame({ name, frame, rest = 0, still = false }: { name: Sheet; frame: number; rest?: number; still?: boolean }) {
  const sheet = SHEETS[name];
  const motion = headMotion(name, still ? 0 : frame);
  const imageStyle: CSSProperties = {
    width: SIZE, height: SIZE,
    backgroundImage: `url(${sheet.src})`,
    backgroundRepeat: "no-repeat",
    backgroundSize: `${sheet.frames * SIZE}px ${SIZE}px`,
    backgroundPosition: `-${frame * SIZE}px 0`,
    transform: frameTransform(name, frame), transformOrigin: "0 0",
  };
  const articulated = name === "thinking" || name === "sniff";
  return (
    <div style={{ position: "relative", width: SIZE, height: SIZE }}>
      {name === "scratch" && (
        <div style={{ position: "absolute", inset: 0, opacity: rest, transition: still ? undefined : "opacity 160ms linear" }}>
          <MimiSheetFrame name="idle" frame={0} still />
        </div>
      )}
      <div style={{ opacity: 1 - rest, transition: still ? undefined : "opacity 160ms linear" }}>
        <div style={articulated ? { maskImage: "linear-gradient(transparent 46%, black 52%)" } : undefined}>
          <div style={imageStyle} />
        </div>
        {articulated && (
          <div data-testid="mimi-head" style={{ position: "absolute", inset: 0, transformOrigin: "50% 55%", transform: `translate(${motion.x}px, ${motion.y}px) rotate(${motion.angle}deg) scale(${motion.scale})`, transition: still ? undefined : "transform 85ms linear" }}>
            <div style={{ maskImage: "linear-gradient(black 54%, transparent 60%)" }}>
              <div style={imageStyle} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** The gallery and floating pet share the same timing, including settling back
 *  to rest. Completing outside a React state updater avoids duplicate callbacks. */
export function MimiSheet({ name, onDone }: { name: Sheet; onDone?: () => void }) {
  const [step, setStep] = useState(0);
  const reduced = useReducedMotion();
  const done = useRef(onDone);
  useEffect(() => { done.current = onDone; }, [onDone]);
  const steps = PLAYBACK[name];
  useEffect(() => {
    let current = 0;
    let timer: number | undefined;
    setStep(0);
    if (reduced) {
      if (!SHEETS[name].loop) timer = window.setTimeout(() => done.current?.(), steps.reduce((sum, item) => sum + item.duration, 0));
    } else {
      const advance = () => {
        if (current + 1 === steps.length && !SHEETS[name].loop) {
          done.current?.();
          return;
        }
        current = (current + 1) % steps.length;
        setStep(current);
        timer = window.setTimeout(advance, steps[current].duration);
      };
      timer = window.setTimeout(advance, steps[0].duration);
    }
    return () => window.clearTimeout(timer);
  }, [name, steps, reduced]);
  const current = steps[reduced ? 0 : Math.min(step, steps.length - 1)];
  return <MimiSheetFrame name={name} frame={current.frame} rest={current.rest} still={reduced} />;
}
