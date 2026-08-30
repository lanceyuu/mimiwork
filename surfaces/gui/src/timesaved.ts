// The hours-saved estimate, as the interface renders it.
//
// The server does the arithmetic (coworker/timesaved.py, where the rates and their
// reasoning live); this file only formats it. Two rules follow the number wherever
// it appears: it always wears a "≈" so nobody mistakes it for a measurement, and it
// stays hidden below half an hour, because "≈3 min saved" invites an argument the
// feature cannot win and does not need to.

export interface TimeSaved {
  saved_minutes: number;
  human_minutes: number;
  collab_minutes: number;
  turns: number;
  approvals: number;
  by_category: Record<string, number>;
  /** The same minutes grouped by KIND of help — see coworker/edge.py. */
  edge?: EdgeProfile;
}

/** The EDGE profile (Efficiency · Decisions · Growth · Empowerment). */
export interface EdgePillar {
  key: string;
  label: string;
  blurb: string;
  minutes: number;
  percent: number;
}
export interface EdgeProfile {
  pillars: EdgePillar[];
  total_minutes: number;
  leading: string;
  /** False below ~30 minutes of attributed work: too little for a shape to mean anything. */
  ready: boolean;
}

export const MIN_SHOWN_MINUTES = 30;

export function emptyTimeSaved(): TimeSaved {
  return {
    saved_minutes: 0,
    human_minutes: 0,
    collab_minutes: 0,
    turns: 0,
    approvals: 0,
    by_category: {},
  };
}

/** "≈2.5 h" / "≈45 min" / "≈3 days" — short enough for a chip. */
export function formatSaved(minutes: number): string {
  if (minutes < 60) return `≈${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 10) return `≈${(Math.round(hours * 10) / 10).toFixed(1)} h`;
  if (hours < 40) return `≈${Math.round(hours)} h`;
  // Past a working week, days read better than a three-digit hour count.
  return `≈${(Math.round((hours / 8) * 10) / 10).toFixed(1)} days`;
}

/** Whether the estimate is worth showing at all. */
export function worthShowing(t: TimeSaved | null | undefined): boolean {
  return !!t && t.saved_minutes >= MIN_SHOWN_MINUTES;
}
