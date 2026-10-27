// "Mimi finished" / "Mimi needs you" alerts (Settings ▸ General ▸ Notifications). Per-device,
// like the theme: whether this machine should ping is a property of the machine, not the account.
import { useEffect, useState } from "react";
import { tr } from "./i18n";
import { isTauri, showNotification } from "./tauri";

export type AlertEvent = "done" | "attention";
export interface AlertPrefs {
  notify: boolean; // a system notification, only while MimiWork is in the background
  sound: boolean; // a short chime, whether or not the window is in front
  done: boolean;
  attention: boolean;
}
export const DEFAULT_ALERTS: AlertPrefs = { notify: true, sound: false, done: true, attention: true };

const KEY = "openwork-alerts";
const EVENT = "openwork:alert-prefs";

export function getAlertPrefs(): AlertPrefs {
  try {
    return { ...DEFAULT_ALERTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return DEFAULT_ALERTS;
  }
}

export function setAlertPrefs(next: AlertPrefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode — applies for this session only */
  }
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function useAlertPrefs(): [AlertPrefs, (p: AlertPrefs) => void] {
  const [prefs, setPrefs] = useState<AlertPrefs>(getAlertPrefs);
  useEffect(() => {
    const sync = () => setPrefs(getAlertPrefs());
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, []);
  return [prefs, setAlertPrefs];
}

// Synthesized, so no audio files ship and nothing depends on the OS sound set. The context is
// created on the first click as well, because a webview may refuse to start audio that no user
// gesture ever unlocked.
let audio: AudioContext | null = null;
const audioContext = () => (audio ??= typeof AudioContext === "undefined" ? null : new AudioContext());
window.addEventListener("pointerdown", () => void audioContext()?.resume().catch(() => undefined), { once: true });

const NOTES: Record<AlertEvent, number[]> = { done: [660, 880], attention: [880, 660, 880] };

export function playChime(kind: AlertEvent) {
  try {
    const ctx = audioContext();
    if (!ctx) return;
    void ctx.resume().catch(() => undefined);
    NOTES[kind].forEach((freq, i) => {
      const t = ctx.currentTime + i * 0.13;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.18, t + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.45);
    });
  } catch {
    /* no audio device */
  }
}

export async function notify(title: string, body: string): Promise<boolean> {
  if (isTauri()) return showNotification(title, body);
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "default") await Notification.requestPermission();
  if (Notification.permission !== "granted") return false;
  new Notification(title, { body });
  return true;
}

/** Ping the user per their prefs. `force` skips the in-front check (the Settings test button). */
export function alertUser(kind: AlertEvent, title: string, body: string, force = false) {
  const prefs = getAlertPrefs();
  if (!prefs[kind] && !force) return;
  if (prefs.sound) playChime(kind);
  // The user is looking at the window: a banner over it would only repeat what they see.
  if (prefs.notify && (force || document.hidden || !document.hasFocus())) void notify(tr(title), tr(body));
}
