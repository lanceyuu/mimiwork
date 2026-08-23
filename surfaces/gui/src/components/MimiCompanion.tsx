/** The floating Mimi companion — a tiny always-on-top window the desktop shell
 * shows when the main window is minimized or closed to tray.
 *
 * The metaphor is deliberate: while the coworker is BUSY, Mimi sleeps ("work is
 * running, nothing to do but wait"); the moment the last task finishes she wakes
 * up — a glance at the corner of the screen answers "is it done yet?". Clicking
 * her restores the app; dragging moves the window anywhere on screen (the Rust
 * shell remembers the spot across restarts).
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
import happySheet from "../assets/mimi-pet/mimi-happy-subtle-24.png";

type Phase = "sleep" | "wake" | "idle" | "alert";

const SHEETS: Record<Phase, { src: string; frames: number; fps: number; loop: boolean }> = {
  sleep: { src: sleepSheet, frames: 8, fps: 8, loop: true },
  wake: { src: wakeSheet, frames: 16, fps: 10, loop: false },
  idle: { src: idleSheet, frames: 48, fps: 12, loop: true },
  // Needs-the-user: the happy face + a gentle hop (CSS, on the container)
  // reads as an excited "I have something for you!" — friendlier than the
  // scratch loop it replaced (owner call 2026-08-20).
  alert: { src: happySheet, frames: 24, fps: 12, loop: true },
};

const SIZE = 110; // displayed sprite size in px (frames are square)

// Per-frame pose geometry, ported from QualiTaTi's mimiPetAssets.js: the dog
// drifts inside the sheet from pose to pose (especially wake), so each frame
// is re-anchored to a fixed point — anchor x=96, feet at y=180, body height
// 165 — in the sheet's 192px logical space. Without this the pet visibly
// wobbles left/right between frames (owner report 2026-08-20).
type Geo = [anchorX: number, top: number, bottom: number];
const GEO: Record<Phase, Geo[]> = {
  idle: Array.from({ length: 48 }, () => [100.5, 12, 181] as Geo),
  sleep: [
    [104.5, 12, 184], [102.5, 12, 184], [102, 12, 184], [100.5, 12, 184],
    [104.5, 13, 184], [102.5, 13, 184], [102, 13, 184], [100.5, 13, 184],
  ],
  wake: [
    [106.5, 15, 190], [96, 15, 190], [90, 15, 190], [85.5, 15, 190],
    [105, 13, 189], [94.5, 13, 189], [89, 13, 189], [84.5, 13, 189],
    [106.5, 9, 189], [97, 9, 189], [91, 10, 189], [87.5, 10, 189],
    [106, 8, 184], [95.5, 8, 184], [89.5, 8, 184], [84.5, 8, 184],
  ],
  // happy-subtle-24 is a stable pose (same geometry every frame).
  alert: Array.from({ length: 24 }, () => [100.5, 12, 181] as Geo),
};
const TARGET = { anchorX: 96, bottom: 180, height: 165 };
const LOGICAL = 192; // the geometry's coordinate space (per source cell)

function frameTransform(phase: Phase, frame: number): string {
  const records = GEO[phase];
  const [anchorX, top, bottom] = records[Math.min(frame, records.length - 1)];
  const s = TARGET.height / (bottom - top);
  const f = SIZE / LOGICAL;
  const tx = (TARGET.anchorX - anchorX * s) * f;
  const ty = (TARGET.bottom - bottom * s) * f;
  return `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${s.toFixed(4)})`;
}

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
        overflow: "hidden",
        filter: "drop-shadow(0 4px 10px rgba(0,0,0,0.25))",
        animation: phase === "alert" ? "companion-hop 1.6s ease-in-out infinite" : undefined,
      }}
    >
      <div
        style={{
          width: SIZE,
          height: SIZE,
          backgroundImage: `url(${sheet.src})`,
          backgroundRepeat: "no-repeat",
          backgroundSize: `${sheet.frames * SIZE}px ${SIZE}px`,
          backgroundPosition: `-${frame * SIZE}px 0`,
          transform: frameTransform(phase, frame),
          transformOrigin: "0 0",
        }}
      />
    </div>
  );
}

// What Mimi says while she works — rotated so the bubble feels alive, not static.
const BUSY_LINES = [
  (what: string) => `Working on ${what}…`,
  (what: string) => `Still on ${what} — I'll nap till it's done 💤`,
  (what: string) => `${what} in progress… wake me when? I'll wake YOU.`,
];
const DONE_LINE = "All done! Click me to take a look 🎉";
const ALERT_LINE = "I need your OK to continue — click me ✋";

export function MimiCompanion() {
  const [busy, setBusy] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [snap, setSnap] = useState<Activity | null>(null);
  const [lineIdx, setLineIdx] = useState(0);
  const [showDone, setShowDone] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [dismissedBubble, setDismissedBubble] = useState("");
  const busyRef = useRef<boolean | null>(null);

  // Rotate the busy line every 9s; show the done bubble for 45s after waking.
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => setLineIdx((i) => (i + 1) % BUSY_LINES.length), 9000);
    return () => window.clearInterval(id);
  }, [busy]);
  // A dismissal only silences the message that was on screen: once Mimi moves on
  // to something else, the same line may come round again and should be heard.
  useEffect(() => {
    setDismissedBubble("");
  }, [phase, busy, lineIdx, showDone]);
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

    const apply = (nowBusy: boolean, pending: number) => {
      const was = busyRef.current;
      busyRef.current = nowBusy;
      setBusy(nowBusy);
      // Needing the user beats everything — a napping dog reads as "all under
      // control", which is exactly wrong while an approval sits parked.
      if (pending > 0) setPhase("alert");
      else if (nowBusy) setPhase("sleep");
      else if (was) setPhase("wake"); // busy → done: the wake-up moment
      else setPhase((p) => (p === "wake" ? p : "idle"));
    };

    getActivity()
      .then((a) => {
        setSnap(a);
        apply(a.busy, a.pending_input ?? 0);
      })
      .catch(() => setBusy(false));
    const stop = connectEvents((msg) => {
      if (msg.type === "activity" && msg.data) {
        const a = msg.data as unknown as Activity;
        setSnap(a);
        apply(Boolean(a.busy), a.pending_input ?? 0);
      }
    });
    // Belt-and-suspenders: a missed frame (socket blip) self-heals within 15s —
    // and keeps the bubble's detail fresh while busy.
    const poll = window.setInterval(() => {
      getActivity().then((a) => {
        setSnap(a);
        apply(a.busy, a.pending_input ?? 0);
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

  // Drag-to-move: pressing anywhere starts an OS window drag (the shell moves the
  // real always-on-top window; the Rust shell persists the dropped position). A
  // drop must not count as the click that restores the app.
  //
  // Measuring that in CLIENT coordinates does not work: during an OS drag the
  // window travels WITH the cursor, so the pointer keeps the same position
  // inside the webview and the drop looks like a stationary click — which is why
  // dropping Mimi used to open the app (owner report 2026-08-23). Screen
  // coordinates are the ones that actually move, and the shell's own "window
  // moved" event is the definitive signal; either one marks the gesture a drag.
  // In a plain browser (vite dev) there is no Tauri window: the client delta
  // still catches a drag there.
  const dragStartRef = useRef<{ cx: number; cy: number; sx: number; sy: number } | null>(null);
  const pressedRef = useRef(false);
  const movedRef = useRef(false);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let dead = false;
    const w = (globalThis as any).__TAURI__?.window?.getCurrentWindow?.();
    Promise.resolve(w?.onMoved?.(() => {
      if (pressedRef.current) movedRef.current = true; // ignore strays after the drop
    }))
      .then((fn: unknown) => {
        if (typeof fn === "function") {
          if (dead) (fn as () => void)();
          else unlisten = fn as () => void;
        }
      })
      .catch(() => undefined);
    return () => {
      dead = true;
      unlisten?.();
    };
  }, []);

  const startDrag = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    dragStartRef.current = { cx: e.clientX, cy: e.clientY, sx: e.screenX, sy: e.screenY };
    pressedRef.current = true;
    movedRef.current = false;
    (globalThis as any).__TAURI__?.window?.getCurrentWindow?.()?.startDragging?.();
  };
  const maybeRestore = (e: React.MouseEvent) => {
    const down = dragStartRef.current;
    const moved = movedRef.current;
    dragStartRef.current = null;
    pressedRef.current = false;
    if (moved) return; // the shell moved the window: that was a drag
    if (down) {
      const travelled = Math.max(
        Math.hypot(e.clientX - down.cx, e.clientY - down.cy),
        Math.hypot(e.screenX - down.sx, e.screenY - down.sy),
      );
      if (travelled > 6) return;
    }
    restore();
  };

  // The speech bubble: names the work while busy; celebrates when it lands.
  // (No permanent label under the pet — owner ask 2026-08-20: the bubble talks,
  // the pet stays clean.)
  const what = snap?.detail
    ? `“${snap.detail}”`
    : snap && snap.running_sessions + snap.running_automations > 1
      ? `${snap.running_sessions + snap.running_automations} tasks`
      : "your task";
  const said =
    phase === "alert"
      ? ALERT_LINE
      : busy
        ? BUSY_LINES[lineIdx](what)
        : showDone
          ? DONE_LINE
          : null;
  // Clicking a bubble dismisses THAT message (owner ask 2026-08-23); the next
  // thing Mimi says — a rotated busy line, the done cheer, an approval ping —
  // has a different key, so it speaks up again.
  const bubbleKey = phase === "alert" ? "alert" : busy ? `busy:${lineIdx}` : showDone ? "done" : "";
  const bubble = said && bubbleKey !== dismissedBubble ? said : null;

  return (
    <div
      data-testid="mimi-companion"
      onPointerDown={startDrag}
      onClick={maybeRestore}
      title="Open MimiWork (drag to move)"
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
      {bubble && (
        <div
          data-testid="companion-bubble"
          role="button"
          tabIndex={0}
          title="Click to dismiss"
          onPointerDown={(e) => e.stopPropagation()} // pressing the bubble must not drag the window
          onClick={(e) => {
            e.stopPropagation(); // reading a message is not "open the app"
            setDismissedBubble(bubbleKey);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              setDismissedBubble(bubbleKey);
            }
          }}
          style={{
            cursor: "pointer",
            maxWidth: 200,
            background: phase === "alert" ? "rgba(255,247,230,0.98)" : "rgba(255,255,255,0.96)",
            color: phase === "alert" ? "#92400e" : "#16272a",
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
              background: phase === "alert" ? "rgba(255,247,230,0.98)" : "rgba(255,255,255,0.96)",
              transform: "rotate(45deg)",
              borderRadius: 2,
            }}
          />
        </div>
      )}
      {busy && phase !== "alert" && (
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
      {/* Sprite + ✕ share one hover zone: the ✕ only appears while the mouse is on
        * Mimi (owner ask 2026-08-23), and hovering the ✕ itself keeps it visible
        * instead of flickering out from under the pointer. */}
      <div
        data-testid="companion-pet-zone"
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        style={{ position: "relative", width: SIZE + 84, height: SIZE }}
      >
        <div style={{ position: "absolute", bottom: 0, left: "50%", marginLeft: -SIZE / 2 }}>
          <Sprite phase={phase} onDone={() => setPhase("idle")} />
        </div>
        <button
          data-testid="companion-dismiss"
          data-visible={hovered ? "true" : "false"}
          onPointerDown={(e) => e.stopPropagation()} // pressing ✕ must not drag the window
          onClick={dismiss}
          onFocus={() => setHovered(true)}
          onBlur={() => setHovered(false)}
          title="Hide Mimi (until the app restarts — turn her off for good in Settings)"
          aria-label="Hide floating Mimi"
          style={{
            // Beside Mimi's leg (owner ask 2026-08-20), not floating high above her:
            // sprite is 110px wide, centered, feet at the window bottom.
            position: "absolute",
            bottom: 18,
            left: "calc(50% + 62px)",
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
            opacity: hovered ? 1 : 0,
            pointerEvents: hovered ? "auto" : "none",
            transition: "opacity 0.15s ease",
          }}
        >
          ×
        </button>
      </div>
      <style>{`@keyframes companion-zzz { 0%,100% { opacity: .35; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-4px); } } @keyframes companion-bubble-in { from { opacity: 0; transform: translateY(4px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } } @keyframes companion-hop { 0%, 60%, 100% { transform: translateY(0); } 70% { transform: translateY(-7px); } 80% { transform: translateY(0); } 88% { transform: translateY(-4px); } 94% { transform: translateY(0); } } @media (prefers-reduced-motion: reduce) { [data-testid="companion-bubble"], [data-testid="companion-sprite"] { animation: none !important; } }`}</style>
    </div>
  );
}
