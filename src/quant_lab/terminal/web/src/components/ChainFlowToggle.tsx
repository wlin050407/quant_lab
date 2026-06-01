import type { ChainFlowMode } from "../types/snapshot";

interface ChainFlowToggleProps {
  value: ChainFlowMode;
  onChange: (mode: ChainFlowMode) => void;
  disabled?: boolean;
}

export function ChainFlowToggle({ value, onChange, disabled = false }: ChainFlowToggleProps) {
  return (
    <div
      className="chain-flow-toggle"
      role="group"
      aria-label="Pin effective-OI source (both modes compute full pin score)"
    >
      <span
        className="chain-flow-toggle-label"
        title="Both modes compute the full pin score; effective OI uses ΔOI vs trades"
      >
        Pin OI
      </span>
      <button
        type="button"
        className={`chain-flow-pill${value === "pin" ? " active" : ""}`}
        disabled={disabled}
        onClick={() => onChange("pin")}
        title="Full pin · effective OI = settled + |ΔOI| vs 09:30 (~15–30s)"
      >
        Fast
      </button>
      <button
        type="button"
        className={`chain-flow-pill chain-flow-pill--precise${value === "full" ? " active" : ""}`}
        disabled={disabled}
        onClick={() => onChange("full")}
        title="Full pin · effective OI from session OPRA trades (slower, may take minutes)"
      >
        Precise
      </button>
    </div>
  );
}
