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
  /** Which mode of working the turns fell into — see coworker/fivea.py. */
  five_a?: FiveAProfile;
}

/** The EDGE profile (Efficiency · Decisions · Growth · Empowerment) — four axes. */
export interface EdgePillar {
  key: string;
  label: string;
  blurb: string;
  minutes: number;
  percent: number;
}
export interface EdgeProfile {
  /** All four pillars — Efficiency, Decisions, Growth, Empowerment; shares sum to 100. */
  pillars: EdgePillar[];
  total_minutes: number;
  leading: string;
  /** False below ~30 minutes of attributed work: too little for a shape to mean anything. */
  ready: boolean;
}

/** The Five A's continuum (ch. 7) — Access → Assistants → Applications → Automation → Agents. */
export interface FiveALevel {
  key: string;
  label: string;
  blurb: string;
  turns: number;
  percent: number;
}
export interface FiveAProfile {
  levels: FiveALevel[];
  total_turns: number;
  leading: string;
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

/** "≈45 min" / "≈2.5 h" / "≈15 h" / "≈1.3 d" — short enough for a chip. Past a full
 *  day the unit turns into days of 24 hours (owner ask 2026-09-02), so "≈30 h" reads
 *  as "≈1.3 d" rather than a number nobody converts in their head. */
export function formatSaved(minutes: number): string {
  if (minutes < 60) return `≈${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 10) return `≈${(Math.round(hours * 10) / 10).toFixed(1)} h`;
  if (hours < 24) return `≈${Math.round(hours)} h`;
  return `≈${(Math.round((hours / 24) * 10) / 10).toFixed(1)} d`;
}

/** Whether the estimate is worth showing at all. */
export function worthShowing(t: TimeSaved | null | undefined): boolean {
  return !!t && t.saved_minutes >= MIN_SHOWN_MINUTES;
}
