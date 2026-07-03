import type { Gate, ResonanceDivergence, ResonanceReport, VendorLevels } from "../types/snapshot";

export function resonanceTierLabel(tier: string | undefined): string {
  if (tier === "high") return "HIGH";
  if (tier === "medium") return "MED";
  if (tier === "low") return "LOW";
  return "—";
}

export function resonanceTierClass(tier: string | undefined): string {
  if (tier === "high") return "resonance-tier--high";
  if (tier === "medium") return "resonance-tier--med";
  if (tier === "low") return "resonance-tier--low";
  return "resonance-tier--na";
}

export function hasVendorOverlay(
  vendorLevels: VendorLevels | null | undefined,
  resonance: ResonanceReport | null | undefined,
): boolean {
  return Boolean(vendorLevels?.zero_gamma != null || resonance?.tier);
}

export function gateDetail(gate: Gate): string {
  if (gate.reason === "low_resonance" && gate.base_should_trade) {
    return "Base gate passed · blocked by low GEXBot/local alignment";
  }
  if (!gate.should_trade && gate.reason) {
    return gate.reason.replaceAll("_", " ");
  }
  return gate.should_trade ? "Trade window open" : "Gate closed";
}

export function divergenceSummary(d: ResonanceDivergence): string {
  const local = d.local != null ? d.local.toFixed(0) : "—";
  const vendor = d.vendor != null ? d.vendor.toFixed(0) : "—";
  const delta = d.delta_pts != null ? ` (${d.delta_pts.toFixed(0)}pt)` : "";
  if (d.field === "flip") return `Flip local ${local} vs GEXBot ${vendor}${delta}`;
  if (d.field === "magnet") return `Magnet local ${local} vs GEXBot wall ${vendor}${delta}`;
  if (d.field === "pin_prior_peak") return `Pin magnet ${local} vs GEXBot prior peak ${vendor}${delta}`;
  return `${d.field}: ${local} vs ${vendor}`;
}

export const RESONANCE_AXIS_LABELS: Record<string, string> = {
  flip_align: "Flip",
  magnet_align: "Magnet",
  pin_triangulate: "Pin × prior",
  wall_cage: "Wall cage",
  flow_regime: "Flow × γ",
};
