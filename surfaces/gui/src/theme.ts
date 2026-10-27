// Appearance: Light / Dark / Auto-as-system. The preference lives in localStorage only —
// it's per-device (like macOS appearance itself) and must apply before the sidecar is even
// reachable. index.html sets data-theme inline pre-paint with the same key, so the first
// frame is already the right color; this module keeps it current from then on.
import { useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "auto";

const KEY = "openwork-theme";
const PREF_EVENT = "openwork:theme-pref";
const media = window.matchMedia?.("(prefers-color-scheme: dark)");

export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "auto";
  } catch {
    return "auto";
  }
}

function apply(pref: ThemePref) {
  const dark = pref === "dark" || (pref === "auto" && !!media?.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function setThemePref(pref: ThemePref) {
  try {
    if (pref === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    /* private mode etc. — still applies for this session */
  }
  apply(pref);
  window.dispatchEvent(new CustomEvent(PREF_EVENT));
}

/** Call once at startup: applies the stored pref and follows macOS appearance while in auto. */
export function initTheme() {
  apply(getThemePref());
  media?.addEventListener("change", () => {
    if (getThemePref() === "auto") apply("auto");
  });
}

/** The settings control's hook — stays in sync if the pref changes elsewhere. */
export function useThemePref(): [ThemePref, (p: ThemePref) => void] {
  const [pref, setPref] = useState<ThemePref>(getThemePref);
  useEffect(() => {
    const sync = () => setPref(getThemePref());
    window.addEventListener(PREF_EVENT, sync);
    return () => window.removeEventListener(PREF_EVENT, sync);
  }, []);
  return [pref, setThemePref];
}

// Text size, font and background tint: per-device like the theme, and applied the same way —
// index.html sets font and background pre-paint from these keys, this keeps them current. Text
// size is a page zoom because the app's sizes are literal px throughout (a root rem would miss
// most). It is the desktop webview's own zoom, like Cmd-plus; CSS zoom on <html> would also
// scale 100vh and push the composer off screen, and a browser already has its own zoom.
export const TEXT_SIZES = { small: 0.9, default: 1, large: 1.1, larger: 1.25 } as const;
export const FONTS = ["default", "rounded", "serif"] as const;
export const BACKGROUNDS = ["plain", "warm", "cool", "mint"] as const;
export type TextSize = keyof typeof TEXT_SIZES;
export type FontPref = (typeof FONTS)[number];
export type BackgroundPref = (typeof BACKGROUNDS)[number];

const LOOK_EVENT = "openwork:look-pref";
const LOOK_KEYS = { size: "openwork-text-size", font: "openwork-font", bg: "openwork-background" };

function readLook<T extends string>(key: string, allowed: readonly T[]): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : allowed[0];
  } catch {
    return allowed[0];
  }
}

const SIZE_KEYS = ["default", "small", "large", "larger"] as const;
export const getLook = () => ({
  size: readLook<TextSize>(LOOK_KEYS.size, SIZE_KEYS),
  font: readLook<FontPref>(LOOK_KEYS.font, FONTS),
  bg: readLook<BackgroundPref>(LOOK_KEYS.bg, BACKGROUNDS),
});
type Look = ReturnType<typeof getLook>;

export function applyLook(look: Look = getLook()) {
  const root = document.documentElement;
  const webview = (globalThis as any).__TAURI__?.webview?.getCurrentWebview?.();
  if (webview) void webview.setZoom(TEXT_SIZES[look.size]).catch(() => undefined);
  root.dataset.font = look.font;
  root.dataset.bg = look.bg;
}

export function setLook<K extends keyof Look>(which: K, value: Look[K]) {
  try {
    localStorage.setItem(LOOK_KEYS[which], value);
  } catch {
    /* private mode etc. — still applies for this session */
  }
  applyLook();
  window.dispatchEvent(new CustomEvent(LOOK_EVENT));
}

export function useLook(): Look {
  const [look, setState] = useState<Look>(getLook);
  useEffect(() => {
    const sync = () => setState(getLook());
    window.addEventListener(LOOK_EVENT, sync);
    return () => window.removeEventListener(LOOK_EVENT, sync);
  }, []);
  return look;
}
