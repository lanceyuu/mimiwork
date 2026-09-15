import { useEffect, useRef, useState } from "react";
import atlas from "../assets/mimi-teal/spritesheet.webp";

type Phase = "idle" | "sleep" | "wake" | "alert";
const ANIMATIONS: Record<Phase, { row: number; durations: number[]; loop: boolean }> = {
  idle: { row: 0, durations: [280, 110, 110, 140, 140, 320], loop: true },
  // The existing companion state machine calls busy "sleep". This puppy works instead.
  sleep: { row: 7, durations: [120, 120, 120, 120, 120, 220], loop: true },
  wake: { row: 4, durations: [140, 140, 140, 140, 280], loop: false },
  alert: { row: 6, durations: [150, 150, 150, 150, 150, 260], loop: true },
};
const HEIGHT = 110;
const WIDTH = HEIGHT * 192 / 208;

export function TealMimiSprite({ phase, onDone }: { phase: Phase; onDone: () => void }) {
  const [frame, setFrame] = useState(0);
  const [reduced, setReduced] = useState(() =>
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  const done = useRef(onDone);
  done.current = onDone;
  const animation = ANIMATIONS[phase];

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(media?.matches ?? false);
    media?.addEventListener("change", sync);
    return () => media?.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    setFrame(0);
    let timer: number | undefined;
    if (reduced) {
      if (!animation.loop) {
        timer = window.setTimeout(() => done.current(), animation.durations.reduce((a, b) => a + b));
      }
    } else {
      let current = 0;
      const advance = () => {
        if (current + 1 === animation.durations.length && !animation.loop) {
          done.current();
          return;
        }
        current = (current + 1) % animation.durations.length;
        setFrame(current);
        timer = window.setTimeout(advance, animation.durations[current]);
      };
      timer = window.setTimeout(advance, animation.durations[0]);
    }
    return () => window.clearTimeout(timer);
  }, [animation, reduced]);

  return (
    <div
      data-testid="companion-sprite"
      data-phase={phase}
      data-style="teal"
      data-row={animation.row}
      data-frame={frame}
      style={{ width: HEIGHT, height: HEIGHT, display: "flex", justifyContent: "center" }}
    >
      <div style={{
        width: WIDTH,
        height: HEIGHT,
        backgroundImage: `url(${atlas})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${WIDTH * 8}px ${HEIGHT * 11}px`,
        backgroundPosition: `${-Math.min(frame, animation.durations.length - 1) * WIDTH}px ${-animation.row * HEIGHT}px`,
      }} />
    </div>
  );
}
