import type { DashboardSnapshot } from "../types/snapshot";

/** Human-readable data source label for instrument strip / panel badges. */
export function dataSourceLabel(snapshot: DashboardSnapshot): string {
  const src = snapshot.meta?.data_source ?? "";
  if (src === "thetadata_live") {
    if (snapshot.meta?.live_follow) return "ThetaData live · follow";
    return "ThetaData live";
  }
  const mode = snapshot.meta?.data_mode ?? "";
  if (mode.includes("ThetaData")) return "ThetaData";
  if (mode.toLowerCase().includes("eod")) return "EoD chain";
  return "Research snapshot";
}

export function volumeSourceLabel(source: string | undefined): string {
  switch (source) {
    case "trade_signed":
      return "Vol: signed OPRA";
    case "trade":
      return "Vol: OPRA trades";
    case "quote_proxy":
      return "Vol: quote proxy";
    case "oi_delta":
      return "Flow: ΔOI";
    default:
      return "Vol: settled";
  }
}

export function oiModeLabel(mode: string | undefined): string {
  return mode === "effective" ? "OI: effective" : "OI: settled";
}
