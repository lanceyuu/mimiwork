/** Mimi's sprite sheets and their per-frame geometry — shared by the floating companion,
 *  the playful scenes and the gallery. Data only. */
import sleepSheet from "./assets/mimi-pet/mimi-sleep.png";
import wakeSheet from "./assets/mimi-pet/mimi-wake-16.png";
import idleSheet from "./assets/mimi-pet/mimi-idle-stable-48.png";
import happySheet from "./assets/mimi-pet/mimi-happy-subtle-24.png";
import thinkingSheet from "./assets/mimi-pet/mimi-thinking-stable-48.png";
import winkSheet from "./assets/mimi-pet/mimi-wink-subtle-24.png";
import tiredSheet from "./assets/mimi-pet/mimi-tired-subtle-24.png";
import loveSheet from "./assets/mimi-pet/mimi-love-subtle-24.png";
import groomSheet from "./assets/mimi-pet/mimi-groom-face-48.png";
import yawnSheet from "./assets/mimi-pet/mimi-yawn-face-48.png";
import sniffSheet from "./assets/mimi-pet/mimi-sniff-face-36.png";
import happyHopSheet from "./assets/mimi-pet/mimi-happy-hop-48.png";

// Every sheet QualiTaTi's pet has (mimiPetAssets.js, ported 2026-09-17 — owner ask to
// bring its new animations over). Frames are square cells in a horizontal strip.
export type Sheet =
  | "idle" | "thinking" | "sleep" | "wake" | "happy" | "wink" | "tired" | "love"
  | "groom" | "yawn" | "sniff" | "happyHop";
export const SHEETS: Record<Sheet, { src: string; frames: number; fps: number; loop: boolean }> = {
  idle: { src: idleSheet, frames: 48, fps: 12, loop: true },
  thinking: { src: thinkingSheet, frames: 48, fps: 12, loop: true },
  sleep: { src: sleepSheet, frames: 8, fps: 8, loop: true },
  wake: { src: wakeSheet, frames: 16, fps: 10, loop: false },
  happy: { src: happySheet, frames: 24, fps: 12, loop: false },
  wink: { src: winkSheet, frames: 24, fps: 12, loop: false },
  tired: { src: tiredSheet, frames: 24, fps: 12, loop: false },
  love: { src: loveSheet, frames: 24, fps: 12, loop: false },
  groom: { src: groomSheet, frames: 48, fps: 12, loop: false },
  yawn: { src: yawnSheet, frames: 48, fps: 12, loop: false },
  sniff: { src: sniffSheet, frames: 36, fps: 12, loop: false },
  happyHop: { src: happyHopSheet, frames: 48, fps: 12, loop: false },
};
export const SIZE = 110; // displayed sprite size in px (frames are square)

// Per-frame pose geometry, ported from QualiTaTi's mimiPetAssets.js: the dog
// drifts inside the sheet from pose to pose (especially wake), so each frame
// is re-anchored to a fixed point — anchor x=96, feet at y=180, body height
// 165 — in the sheet's 192px logical space. Without this the pet visibly
// wobbles left/right between frames (owner report 2026-08-20).
type Geo = [anchorX: number, top: number, bottom: number];
const STABLE = (n: number): Geo[] => Array.from({ length: n }, () => [100.5, 12, 181] as Geo);
const GEO: Record<Sheet, Geo[]> = {
  idle: STABLE(48),
  thinking: STABLE(48),
  happy: STABLE(24),
  wink: STABLE(24),
  tired: STABLE(24),
  love: STABLE(24),
  groom: STABLE(48),
  yawn: STABLE(48),
  sniff: STABLE(36),
  happyHop: STABLE(48),
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
};
const TARGET = { anchorX: 96, bottom: 180, height: 165 };
const LOGICAL = 192; // the geometry's coordinate space (per source cell)

export function frameTransform(sheet: Sheet, frame: number): string {
  const records = GEO[sheet];
  const [anchorX, top, bottom] = records[Math.min(frame, records.length - 1)];
  const s = TARGET.height / (bottom - top);
  const f = SIZE / LOGICAL;
  const tx = (TARGET.anchorX - anchorX * s) * f;
  const ty = (TARGET.bottom - bottom * s) * f;
  return `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${s.toFixed(4)})`;
}

