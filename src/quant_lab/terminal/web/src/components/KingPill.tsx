import type { KingDistance } from "../types/snapshot";

export function KingPill({ kd }: { kd: KingDistance | null | undefined }) {
  if (!kd) return null;
  const arrow = kd.direction === "up" ? "↑" : kd.direction === "down" ? "↓" : "·";
  const cls = kd.direction === "up" ? "up" : kd.direction === "down" ? "down" : "flat";
  return (
    <div className="king-pill">
      <span className="king-mark" />
      <span className="king-label">King</span>
      <span className="king-pct">{kd.pct.toFixed(2)}%</span>
      <span className={`king-arrow ${cls}`}>{arrow}</span>
    </div>
  );
}
