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
      <span className="chain-flow-toggle-label" title="两种模式都算 Pin；差别在 effective OI 用 ΔOI 还是成交">
        Pin OI
      </span>
      <button
        type="button"
        className={`chain-flow-pill${value === "pin" ? " active" : ""}`}
        disabled={disabled}
        onClick={() => onChange("pin")}
        title="Pin 完整计算 · effective OI = 结算 OI + |ΔOI| vs 09:30（较快，~15–30s）"
      >
        快速
      </button>
      <button
        type="button"
        className={`chain-flow-pill chain-flow-pill--precise${value === "full" ? " active" : ""}`}
        disabled={disabled}
        onClick={() => onChange("full")}
        title="Pin 完整计算 · effective OI 用整段 OPRA 成交流（更准，较慢，可能数分钟）"
      >
        精确
      </button>
    </div>
  );
}
