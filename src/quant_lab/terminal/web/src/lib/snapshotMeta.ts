import type { DashboardSnapshot } from "../types/snapshot";

/** Human-readable data source label for instrument strip / panel badges. */
export function dataSourceLabel(snapshot: DashboardSnapshot): string {
  const src = snapshot.meta?.data_source ?? "";
  if (src === "thetadata_live") return "ThetaData live";
  const mode = snapshot.meta?.data_mode ?? "";
  if (mode.includes("ThetaData")) return "ThetaData";
  if (mode.toLowerCase().includes("eod")) return "EoD chain";
  return "Research snapshot";
}
