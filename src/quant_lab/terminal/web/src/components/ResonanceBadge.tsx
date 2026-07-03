import {
  gateDetail,
  resonanceTierClass,
  resonanceTierLabel,
} from "../lib/resonance";
import type { DashboardSnapshot } from "../types/snapshot";

interface ResonanceBadgeProps {
  snapshot: DashboardSnapshot;
  compact?: boolean;
}

export function ResonanceBadge({ snapshot, compact = false }: ResonanceBadgeProps) {
  const resonance = snapshot.meta?.resonance;
  const gate = snapshot.gate;
  const tier = resonance?.tier;
  if (!tier || tier === "unavailable") return null;

  const score =
    resonance?.score != null && !Number.isNaN(resonance.score)
      ? Math.round(resonance.score * 100)
      : null;
  const divergences = resonance?.divergences ?? [];
  const tooltip = [
    resonance?.narrative,
    divergences.length > 0
      ? divergences.map((d) => `${d.field}: Δ${d.delta_pts?.toFixed(0) ?? "?"}pt`).join(" · ")
      : null,
    gate ? gateDetail(gate) : null,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <span
      className={`resonance-badge ${resonanceTierClass(tier)}${compact ? " resonance-badge--compact" : ""}`}
      title={tooltip}
    >
      <span className="resonance-badge-k">{compact ? "RES" : "Resonance"}</span>
      <span className="resonance-badge-v">{resonanceTierLabel(tier)}</span>
      {score != null && !compact ? <span className="resonance-badge-score">{score}%</span> : null}
    </span>
  );
}
