// Shared time-formatting helpers. One home for the small time renderers that
// used to live privately in RightRail, ConnectorMessageCard, and Sidebar.

/** Absolute clock time from epoch seconds, e.g. "2:14 PM" (locale-aware). */
export function clockTime(tsSeconds: number): string {
  if (!tsSeconds || !isFinite(tsSeconds)) return "";
  return new Date(tsSeconds * 1000).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Coarse relative time from epoch seconds: "just now" / "5m ago" / "2h ago" / "3d ago" / a date. */
export function relativeTime(tsSeconds: number): string {
  if (!tsSeconds || !isFinite(tsSeconds)) return "";
  const then = tsSeconds * 1000;
  const diff = Date.now() - then;
  if (diff < 45_000) return "just now";
  const mins = Math.round(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(diff / 3_600_000);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(diff / 86_400_000);
  if (days < 7) return `${days}d ago`;
  return new Date(then).toLocaleDateString();
}

/** Compact age for timestamps (ISO strings): "now" / "5m" / "6h" / "3d" / "2w" / "4mo" / "2y". */
export function compactAge(iso?: string | null): string {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return "now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d`;
  const weeks = Math.floor(days / 7);
  if (days < 30) return `${weeks}w`;
  const months = Math.floor(days / 30);
  if (days < 365) return `${months}mo`;
  return `${Math.floor(days / 365)}y`;
}
