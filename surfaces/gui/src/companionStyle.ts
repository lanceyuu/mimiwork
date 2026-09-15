import { useSyncExternalStore } from "react";

export type CompanionStyle = "classic" | "teal";
export const COMPANION_STYLE_KEY = "mimiwork-companion-style";
const CHANGED = "mimiwork:companion-style";
let sessionStyle: CompanionStyle = "classic";

export function getCompanionStyle(): CompanionStyle {
  try {
    return localStorage.getItem(COMPANION_STYLE_KEY) === "teal" ? "teal" : "classic";
  } catch {
    return sessionStyle;
  }
}

export function setCompanionStyle(style: CompanionStyle) {
  sessionStyle = style;
  try {
    localStorage.setItem(COMPANION_STYLE_KEY, style);
  } catch {
    // Keep the choice usable for this window if device storage is unavailable.
  }
  window.dispatchEvent(new Event(CHANGED));
}

function subscribe(notify: () => void) {
  const storage = (event: StorageEvent) => {
    if (event.key === COMPANION_STYLE_KEY || event.key === null) notify();
  };
  // Settings and the floating pet share an origin but live in separate webviews.
  window.addEventListener("storage", storage);
  window.addEventListener(CHANGED, notify);
  return () => {
    window.removeEventListener("storage", storage);
    window.removeEventListener(CHANGED, notify);
  };
}

export function useCompanionStyle(): [CompanionStyle, typeof setCompanionStyle] {
  return [useSyncExternalStore(subscribe, getCompanionStyle), setCompanionStyle];
}
