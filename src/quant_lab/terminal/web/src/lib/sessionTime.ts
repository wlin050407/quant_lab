/** Backend sentinel: pull 0DTE chain at current ET (live follow mode). */
export const LIVE_SESSION_TIME = "live";

export const PIN_SESSION_TIMES = ["10:00:00", "13:00:00", "15:30:00"] as const;

export const PIN_SESSION_LABELS = ["10:00", "13:00", "15:30"] as const;

export const PIN_SESSION_MILESTONES = ["Read map", "Entry", "Flat"] as const;

export function isLiveSessionTime(value: string): boolean {
  return value.trim().toLowerCase() === LIVE_SESSION_TIME;
}
