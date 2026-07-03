/** Cloud vs local deploy helpers for Terminal UX defaults. */

export const DEMO_SPX_SESSION = {
  symbol: "^SPX",
  date: "2023-07-11",
  time: "13:00:00",
} as const;

export function isLocalDevHost(hostname = readHostname()): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function readHostname(): string {
  if (typeof window === "undefined") return "";
  return window.location.hostname;
}

/** True when snapshot is streaming or following the live intraday clock. */
export function isLiveSnapshotSource(
  source: string | undefined,
  liveFollow?: boolean,
): boolean {
  return source === "thetadata_live" || source === "vendor_live" || Boolean(liveFollow);
}

/** Demo needs local built intraday parquet for 2023-07-11 (not on vendor cloud). */
export function isDemoSessionInDates(dates: string[]): boolean {
  return dates.includes(DEMO_SPX_SESSION.date);
}
