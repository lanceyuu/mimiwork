import back from "./assets/mimi-pose/mimi-back.png";
import doze from "./assets/mimi-pose/mimi-doze.png";
import fetch from "./assets/mimi-pose/mimi-fetch.png";
import lieSide from "./assets/mimi-pose/mimi-lie-side.png";
import lieUp from "./assets/mimi-pose/mimi-lie-up.png";
import sit from "./assets/mimi-pose/mimi-sit.png";
import sitSide from "./assets/mimi-pose/mimi-sit-side.png";
import sleep from "./assets/mimi-pose/mimi-sleep.png";
import stand from "./assets/mimi-pose/mimi-stand.png";
import walk from "./assets/mimi-pose/mimi-walk.png";

// Mimi's poses, in the order they cycle. Opening the app used to show a six-point star —
// correct as a mark, but it is the one moment the app has a face, and a star is nobody's
// face. You get a puppy instead, and a different one each time (owner ask 2026-08-31).
//
// Ordered awake → asleep so consecutive launches read as a day rather than a shuffle;
// the pose ADVANCES rather than being drawn at random, because true randomness repeats
// itself often enough to look broken ("why is it always the sleeping one?").
export const MIMI_POSES = [
  sit, sitSide, stand, walk, fetch, lieUp, lieSide, back, doze, sleep,
] as const;

const KEY = "mimi.pose.next";

/** The pose for this launch, advancing one step from the last. Falls back to the first
 *  pose whenever storage is unavailable (a private window, cleared data) — the splash
 *  must never be the thing that fails. */
export function nextPose(): string {
  let i = 0;
  try {
    const raw = window.localStorage.getItem(KEY);
    const n = raw === null ? NaN : Number(raw);
    i = Number.isFinite(n) ? ((n % MIMI_POSES.length) + MIMI_POSES.length) % MIMI_POSES.length : 0;
    window.localStorage.setItem(KEY, String((i + 1) % MIMI_POSES.length));
  } catch {
    i = 0;
  }
  return MIMI_POSES[i];
}
