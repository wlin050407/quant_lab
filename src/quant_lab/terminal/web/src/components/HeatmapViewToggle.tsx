import type { HeatmapViewMode } from "../types/snapshot";

interface HeatmapViewToggleProps {
  value: HeatmapViewMode;
  onChange: (mode: HeatmapViewMode) => void;
}

export function HeatmapViewToggle({ value, onChange }: HeatmapViewToggleProps) {
  return (
    <div className="heatmap-view-toggle" role="group" aria-label="Heatmap layout">
      <button
        type="button"
        className={`view-btn${value === "single" ? " active" : ""}`}
        aria-pressed={value === "single"}
        title="Single symbol (1)"
        onClick={() => onChange("single")}
      >
        Single
      </button>
      <button
        type="button"
        className={`view-btn${value === "trinity" ? " active" : ""}`}
        aria-pressed={value === "trinity"}
        title="Trinity — SPX · SPY · QQQ side by side (3)"
        onClick={() => onChange("trinity")}
      >
        Trinity
      </button>
    </div>
  );
}
