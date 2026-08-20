/** The floating Mimi companion — a tiny always-on-top window the desktop shell
 * shows when the main window is minimized or closed to tray.
 *
 * The metaphor is deliberate: while the coworker is BUSY, Mimi sleeps ("work is
 * running, nothing to do but wait"); the moment the last task finishes she wakes
 * up — a glance at the corner of the screen answers "is it done yet?". Clicking
 * her restores the app.
 *
 * State comes from the sidecar: GET /v1/activity for the initial snapshot, then
 * {"type":"activity"} frames on /ws/events whenever the app-wide busy boolean
 * flips. Sprites are the QualiTaTi Mimi pet sheets (horizontal strips).
 */
import { useEffect, useRef, useState } from "react";
import { connectEvents, getActivity } from "../api";
import sleepSheet from "../assets/mimi-pet/mimi-sleep.png";
import wakeSheet from "../assets/mimi-pet/mimi-wake-16.png";
import idleSheet from "../assets/mimi-pet/mimi-idle-stable-48.png";

type Phase = "sleep" | "wake" | "idle";

const SHEETS: Record<Phase, { src: string; frames: number; fps: number; loop: boolean }> = {
  sleep: { src: sleepSheet, frames: 8, fps: 8, loop: true },
  wake: { src: wakeSheet, frames: 16, fps: 10, loop: false },
  idle: { src: idleSheet, frames: 48, fps: 12, loop: true },
};

const SIZE = 110; // displayed sprite size in px (frames are square)

function Sprite({ phase, onDone }: { phase: Phase; onDone?: () => void }) {
  const [frame, setFrame] = useState(0);
  const sheet = SHEETS[phase];
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    setFrame(0);
    const id = window.setInterval(() => {
      setFrame((f) => {
        const next = f + 1;
        if (next >= sheet.frames) {
          if (sheet.loop) return 0;
          window.clearInterval(id);
          doneRef.current?.();
          return f;
        }
        return next;
      });
    }, 1000 / sheet.fps);
    return () => window.clearInterval(id);
  }, [phase, sheet.frames, sheet.fps, sheet.loop]);

  return (
    <div
      data-testid="companion-sprite"
      data-phase={phase}
      style={{
        width: SIZE,
        height: SIZE,
        backgroundImage: `url(${sheet.src})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${sheet.frames * SIZE}px ${SIZE}px`,
        backgroundPosition: `-${frame * SIZE}px 0`,
        filter: "drop-shadow(0 4px 10px rgba(0,0,0,0.25))",
      }}
    />
  );
}

export function MimiCompanion() {
  const [busy, setBusy] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const busyRef = useRef<boolean | null>(null);

  useEffect(() => {
    // Only the pet may paint: the window is transparent and frameless.
    document.documentElement.style.background = "transparent";
    document.body.style.background = "transparent";

    const apply = (nowBusy: boolean) => {
      const was = busyRef.current;
      busyRef.current = nowBusy;
      setBusy(nowBusy);
      if (nowBusy) setPhase("sleep");
      else if (was) setPhase("wake"); // busy → done: the wake-up moment
      else setPhase((p) => (p === "wake" ? p : "idle"));
    };

    getActivity()
      .then((a) => apply(a.busy))
      .catch(() => setBusy(false));
    const stop = connectEvents((msg) => {
      if (msg.type === "activity" && msg.data) apply(Boolean((msg.data as any).busy));
    });
    // Belt-and-suspenders: a missed frame (socket blip) self-heals within 15s.
    const poll = window.setInterval(() => {
      getActivity().then((a) => {
        if (a.busy !== busyRef.current) apply(a.busy);
      }).catch(() => undefined);
    }, 15000);
    return () => {
      stop();
      window.clearInterval(poll);
    };
  }, []);

  const restore = () => {
    (globalThis as any).__TAURI__?.core?.invoke?.("companion_restore");
  };
  const dismiss = (e: React.MouseEvent) => {
    e.stopPropagation(); // the ✕ must not ALSO restore the app
    (globalThis as any).__TAURI__?.core?.invoke?.("companion_dismiss");
  };

  const label = busy ? "Working… (Mimi is napping)" : phase === "wake" ? "All done!" : "Mimi";

  return (
    <div
      data-testid="mimi-companion"
      onClick={restore}
      title="Open MimiWork"
      style={{
        position: "relative",
        width: "100vw",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-end",
        cursor: "pointer",
        userSelect: "none",
        background: "transparent",
        overflow: "hidden",
      }}
    >
      <button
        data-testid="companion-dismiss"
        onClick={dismiss}
        title="Hide Mimi (until the app restarts — turn her off for good in Settings)"
        aria-label="Hide floating Mimi"
        style={{
          position: "absolute",
          top: 4,
          right: 8,
          border: "none",
          background: "rgba(255,255,255,0.85)",
          color: "#55696a",
          borderRadius: "50%",
          width: 20,
          height: 20,
          lineHeight: "18px",
          fontSize: 12,
          cursor: "pointer",
          boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
        }}
      >
        ×
      </button>
      {busy && (
        <div
          data-testid="companion-zzz"
          style={{
            fontSize: 18,
            fontWeight: 700,
            color: "#0d9488",
            textShadow: "0 1px 2px rgba(255,255,255,0.8)",
            animation: "companion-zzz 2.2s ease-in-out infinite",
          }}
        >
          z Z z
        </div>
      )}
      <Sprite phase={phase} onDone={() => setPhase("idle")} />
      <div
        style={{
          marginTop: 2,
          fontSize: 11,
          fontWeight: 600,
          color: "#374151",
          background: "rgba(255,255,255,0.85)",
          borderRadius: 8,
          padding: "2px 8px",
          boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
          whiteSpace: "nowrap",
        }}
        data-testid="companion-label"
      >
        {label}
      </div>
      <style>{`@keyframes companion-zzz { 0%,100% { opacity: .35; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-4px); } }`}</style>
    </div>
  );
}
