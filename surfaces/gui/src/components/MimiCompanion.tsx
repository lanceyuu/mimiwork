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
import { useCompanionStyle } from "../companionStyle";
import { TealMimiSprite } from "./TealMimiSprite";
import { SHEETS, SIZE, frameTransform, type Sheet } from "../mimiSheets";
import { MimiScene, SCENES, type SceneName } from "./MimiScenes";

// The state machine's phases. "sleep" is the historical name for BUSY (the coworker is
// working); "nap" is the real thing — nothing has happened for a few minutes.
type Phase = "sleep" | "wake" | "idle" | "alert" | "nap";

// What each phase shows when no vignette is playing. Busy is "thinking" now, as in
// QualiTaTi (the nap it replaced was a joke that read as "not working" — 2026-09-17);
// needs-the-user is the happy face + a gentle hop (CSS, on the container), friendlier
// than the scratch loop it replaced (owner call 2026-08-20).
const PHASE_SHEET: Record<Phase, Sheet> = {
  sleep: "thinking",
  wake: "wake",
  idle: "idle",
  alert: "happy",
  nap: "sleep",
};
// QualiTaTi's idle rotation (hooks/mimiPetState.js), minus its three scene prototypes.
// Advanced in order, never drawn at random: a random pick repeats.
export type IdleAction = Sheet | SceneName;
export const IDLE_ACTIONS: IdleAction[] = [
  "tired", "butterfly", "bubble", "yawn", "happyHop", "wink", "sniff", "tongue", "groom", "love", "sniff", "happy",
  "wink", "tired", "groom", "tongue", "sniff", "love", "wink", "yawn", "groom", "happy",
  "sniff", "tired", "wink", "scratch",
];
// The cadence, QualiTaTi's numbers. A test shortens them.
export const COMPANION_TIMING = { idleActionMin: 12_000, idleActionMax: 25_000, napMin: 180_000, napMax: 300_000 };

function Sprite({ phase, sheet: name, onDone }: { phase: Phase; sheet: Sheet; onDone?: () => void }) {
  const [frame, setFrame] = useState(0);
  const sheet = SHEETS[name];
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
  }, [name, sheet.frames, sheet.fps, sheet.loop]);

  return (
    <div
      data-testid="companion-sprite"
      data-phase={phase}
      data-sheet={name}
      data-style="classic"
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
          transform: frameTransform(name, frame),
          transformOrigin: "0 0",
        }}
      />
    </div>
  );
}

// What Mimi says while she works — rotated so the bubble feels alive, not static.
const BUSY_LINES = [
  (what: string) => `Working on ${what}…`,
  (what: string) => `Still on ${what} — thinking it through 🤔`,
  (what: string) => `${what} in progress — I'll tell you the moment it's done.`,
];
const DONE_LINE = "All done! Click me to take a look 🎉";
const ALERT_LINE = "I need your OK to continue — click me ✋";
const TEAL_BUSY_LINES = [
  (what: string) => `Working on ${what}…`,
  (what: string) => `Making progress on ${what}…`,
  (what: string) => `Still working on ${what}…`,
];

export function MimiCompanion() {
  const [petStyle] = useCompanionStyle();
  const [busy, setBusy] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  // A vignette (wink, yawn, groom…) playing over the idle loop, or null.
  const [vignette, setVignette] = useState<IdleAction | null>(null);
  const actionIdx = useRef(0);
  const [reduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const [snap, setSnap] = useState<Activity | null>(null);
  const [lineIdx, setLineIdx] = useState(0);
  const [showDone, setShowDone] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [dismissedBubble, setDismissedBubble] = useState("");
  const petRef = useRef<HTMLDivElement | null>(null);
  const bubbleRef = useRef<HTMLDivElement | null>(null);
  const busyRef = useRef<boolean | null>(null);

  // Rotate the busy line every 9s; show the done bubble for 45s after waking.
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => setLineIdx((i) => (i + 1) % BUSY_LINES.length), 9000);
    return () => window.clearInterval(id);
  }, [busy]);
  // The wake-up moment raises the done bubble…
  useEffect(() => {
    if (phase === "wake") setShowDone(true);
  }, [phase]);
  // …and the bubble times itself out. Keyed on showDone, NOT on phase: the Sprite's
  // wake sheet ends ~1.6s in and flips phase back to idle, and a timer keyed on phase
  // was cancelled by that cleanup every time — so "All done!" never expired at all
  // (review catch 2026-09-02).
  useEffect(() => {
    if (!showDone) return;
    const id = window.setTimeout(() => setShowDone(false), 45000);
    return () => window.clearTimeout(id);
  }, [showDone]);

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
      // A quiet poll changes nothing: a napping dog stays asleep until something happens.
      else setPhase((p) => (p === "wake" || p === "nap" ? p : "idle"));
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

  // Every sheet is fetched once up front: a vignette's first frame otherwise waited on
  // its image and the dog vanished for a beat (the white flash QualiTaTi fixed the same way).
  useEffect(() => {
    if (petStyle !== "classic") return;
    for (const { src } of Object.values(SHEETS)) {
      const img = new Image();
      img.src = src;
    }
  }, [petStyle]);
  // Idle vignettes on QualiTaTi's cadence, one after another in sequence — never while
  // anything else is going on, never under reduced motion, never for the teal puppy
  // (its atlas has no such poses).
  useEffect(() => {
    if (phase !== "idle" || vignette || reduced || petStyle !== "classic") {
      if (phase !== "idle") setVignette(null);
      return;
    }
    const { idleActionMin, idleActionMax } = COMPANION_TIMING;
    const delay = idleActionMin + Math.random() * Math.max(0, idleActionMax - idleActionMin);
    const id = window.setTimeout(() => {
      setVignette(IDLE_ACTIONS[actionIdx.current++ % IDLE_ACTIONS.length]);
    }, delay);
    return () => window.clearTimeout(id);
  }, [phase, vignette, reduced, petStyle]);
  // A real nap: after minutes of nothing, she curls up (zzz) until you hover or
  // something happens. Hovering wakes her, and the poll above leaves her be.
  useEffect(() => {
    if (phase !== "idle" || hovered) return;
    const { napMin, napMax } = COMPANION_TIMING;
    const id = window.setTimeout(() => setPhase("nap"), napMin + Math.random() * Math.max(0, napMax - napMin));
    return () => window.clearTimeout(id);
  }, [phase, hovered, vignette]);
  useEffect(() => {
    if (hovered) setPhase((p) => (p === "nap" ? "idle" : p));
  }, [hovered]);

  const restore = () => {
    (globalThis as any).__TAURI__?.core?.invoke?.("companion_restore");
    // Opening the app IS reading the news. Without this she kept cheering over a finish
    // the user had already reviewed and closed (owner report 2026-09-02: "i have checked
    // the work, and close the window, but mimi still give a note that my task is
    // finished"). Only the celebration is cleared — an approval still parked is an
    // "alert", which the next activity frame re-asserts.
    setShowDone(false);
    setPhase((p) => (p === "wake" ? "idle" : p));
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
    // Tell the shell the user is taking over: from here the window's own move events are
    // her chosen home and must be remembered, not treated as our own placement.
    (globalThis as any).__TAURI__?.core?.invoke?.("companion_drag_begin");
    (globalThis as any).__TAURI__?.window?.getCurrentWindow?.()?.startDragging?.();
  };
  // The release tells the shell the drag is over, so click-through can resume — it
  // stands down for the whole drag (see companion_drag_begin in lib.rs).
  const endDrag = () => {
    (globalThis as any).__TAURI__?.core?.invoke?.("companion_drag_end");
  };
  const maybeRestore = (e: React.MouseEvent) => {
    const down = dragStartRef.current;
    const moved = movedRef.current;
    dragStartRef.current = null;
    pressedRef.current = false;
    endDrag();
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
        ? (petStyle === "teal" ? TEAL_BUSY_LINES : BUSY_LINES)[lineIdx](what)
        : showDone
          ? DONE_LINE
          : null;
  // Clicking a bubble dismisses THAT message (owner ask 2026-08-23); the next
  // thing Mimi says — a rotated busy line, the done cheer, an approval ping —
  // has a different key, so it speaks up again.
  const bubbleKey = phase === "alert" ? "alert" : busy ? `busy:${lineIdx}` : showDone ? "done" : "";
  const bubble = said && bubbleKey !== dismissedBubble ? said : null;
  // A dismissal only silences the message that was on screen: when Mimi moves on to a
  // DIFFERENT message the same line may come round again and should be heard. Keyed on
  // the message's identity — the phase flip wake→idle 1.6s after a finish is not a new
  // message, and resetting on it brought back a bubble just clicked away.
  useEffect(() => {
    setDismissedBubble("");
  }, [bubbleKey]);

  // Tell the shell which part of this transparent window is actually alive, so it can let
  // the mouse through everywhere else (owner ask 2026-08-24: "just on the icon, not the
  // surrounding area"). The union of the pet and — while she is saying something — her
  // bubble; re-reported whenever either changes.
  useEffect(() => {
    const pet = petRef.current?.getBoundingClientRect();
    if (!pet) return;
    const parts = [pet, bubbleRef.current?.getBoundingClientRect()].filter(
      Boolean,
    ) as DOMRect[];
    const left = Math.min(...parts.map((r) => r.left));
    const top = Math.min(...parts.map((r) => r.top));
    const right = Math.max(...parts.map((r) => r.right));
    const bottom = Math.max(...parts.map((r) => r.bottom));
    (globalThis as any).__TAURI__?.core?.invoke?.("companion_hot_rect", {
      x: left,
      y: top,
      width: right - left,
      height: bottom - top,
    });
  }, [bubble, phase, hovered, petStyle]);

  return (
    <div
      data-testid="mimi-companion"
      style={{
        position: "relative",
        width: "100vw",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-end",
        // The window is a transparent box around a small dog. Only the dog (and what she
        // says) answers to the mouse — clicking the empty air beside her used to open the
        // app (owner ask 2026-08-24), which is startling when you meant to click what is
        // behind her. `default`, not `pointer`: the empty area isn't a control.
        cursor: "default",
        userSelect: "none",
        background: "transparent",
        overflow: "hidden",
      }}
    >
      {bubble && (
        <div
          data-testid="companion-bubble"
          ref={bubbleRef}
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
      {phase === "nap" && petStyle === "classic" && (
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
        ref={petRef}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        onPointerDown={startDrag}
        onPointerUp={endDrag}
        onClick={maybeRestore}
        title="Open MimiWork (drag to move)"
        style={{ position: "relative", width: SIZE + 84, height: SIZE, cursor: "pointer" }}
      >
        <div style={{ position: "absolute", bottom: 0, left: "50%", marginLeft: -SIZE / 2 }}>
          {petStyle === "teal" ? (
            <TealMimiSprite key={phase} phase={phase} onDone={() => setPhase("idle")} />
          ) : (
            vignette && vignette in SCENES ? (
              <MimiScene name={vignette as SceneName} onDone={() => setVignette(null)} />
            ) : (
              <Sprite
                phase={phase}
                sheet={(vignette as Sheet | null) ?? PHASE_SHEET[phase]}
                onDone={() => (vignette ? setVignette(null) : setPhase("idle"))}
              />
            )
          )}
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
