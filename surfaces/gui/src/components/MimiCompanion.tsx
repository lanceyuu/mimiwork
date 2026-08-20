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
import { connectEvents, getActivity, type Activity } from "../api";
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

// What Mimi says while she works — rotated so the bubble feels alive, not static.
const BUSY_LINES = [
  (what: string) => `Working on ${what}…`,
  (what: string) => `Still on ${what} — I'll nap till it's done 💤`,
  (what: string) => `${what} in progress… wake me when? I'll wake YOU.`,
];
const DONE_LINE = "All done! Click me to take a look 🎉";

export function MimiCompanion() {
  const [busy, setBusy] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [snap, setSnap] = useState<Activity | null>(null);
  const [lineIdx, setLineIdx] = useState(0);
  const [showDone, setShowDone] = useState(false);
  const busyRef = useRef<boolean | null>(null);

  // Rotate the busy line every 9s; show the done bubble for 45s after waking.
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => setLineIdx((i) => (i + 1) % BUSY_LINES.length), 9000);
    return () => window.clearInterval(id);
  }, [busy]);
  useEffect(() => {
    if (phase !== "wake") return;
    setShowDone(true);
    const id = window.setTimeout(() => setShowDone(false), 45000);
    return () => window.clearTimeout(id);
  }, [phase]);

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
      .then((a) => {
        setSnap(a);
        apply(a.busy);
      })
      .catch(() => setBusy(false));
    const stop = connectEvents((msg) => {
      if (msg.type === "activity" && msg.data) {
        setSnap(msg.data as unknown as Activity);
        apply(Boolean((msg.data as any).busy));
      }
    });
    // Belt-and-suspenders: a missed frame (socket blip) self-heals within 15s —
    // and keeps the bubble's detail fresh while busy.
    const poll = window.setInterval(() => {
      getActivity().then((a) => {
        setSnap(a);
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

  // The speech bubble: names the work while busy; celebrates when it lands.
  const what = snap?.detail
    ? `“${snap.detail}”`
    : snap && snap.running_sessions + snap.running_automations > 1
      ? `${snap.running_sessions + snap.running_automations} tasks`
      : "your task";
  const bubble = busy ? BUSY_LINES[lineIdx](what) : showDone ? DONE_LINE : null;

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
      {bubble && (
        <div
          data-testid="companion-bubble"
          style={{
            maxWidth: 200,
            background: "rgba(255,255,255,0.96)",
            color: "#16272a",
            fontSize: 12,
            fontWeight: 600,
            lineHeight: 1.35,
            borderRadius: 14,
            padding: "7px 11px",
            marginBottom: 8,
            boxShadow: "0 4px 14px rgba(0,0,0,0.16)",
            textAlign: "center",
            position: "relative",
            animation: "companion-bubble-in 0.3s cubic-bezier(0.25, 1, 0.5, 1)",
          }}
        >
          {bubble}
          <span
            aria-hidden
            style={{
              position: "absolute",
              bottom: -5,
              left: "50%",
              marginLeft: -5,
              width: 10,
              height: 10,
              background: "rgba(255,255,255,0.96)",
              transform: "rotate(45deg)",
              borderRadius: 2,
            }}
          />
        </div>
      )}
      {busy && (
        <div
          data-testid="companion-zzz"
          style={{
            fontSize: 16,
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
      <style>{`@keyframes companion-zzz { 0%,100% { opacity: .35; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-4px); } } @keyframes companion-bubble-in { from { opacity: 0; transform: translateY(4px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } } @media (prefers-reduced-motion: reduce) { [data-testid="companion-bubble"] { animation: none !important; } }`}</style>
    </div>
  );
}
