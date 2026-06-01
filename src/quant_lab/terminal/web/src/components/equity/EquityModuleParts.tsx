import type { ReactNode } from "react";

import type { HorizonBias } from "../../types/equity";
import { useLocale } from "../../hooks/useLocale";
import { getEquityStrings } from "../../lib/i18n/equityStrings";

export function EquityBiasChip({ bias, compact }: { bias: HorizonBias; compact?: boolean }) {
  const { locale } = useLocale();
  const s = getEquityStrings(locale);
  const tone = bias === "bullish" ? "bull" : bias === "bearish" ? "bear" : "neutral";
  return (
    <span className={`equity-bias-chip equity-bias-chip--${tone}${compact ? " equity-bias-chip--compact" : ""}`}>
      {s.bias[bias]}
    </span>
  );
}

export function ModuleBiasHeader({
  layer,
  title,
  subtitle,
  bias,
  grade,
}: {
  layer: string;
  title: string;
  subtitle: string;
  bias: HorizonBias;
  grade?: string;
}) {
  return (
    <header className="equity-mod__head">
      <div className="equity-mod__titles">
        <span className="equity-mod__layer">{layer}</span>
        <h3 className="equity-mod__title">{title}</h3>
        <p className="equity-mod__sub">{subtitle}</p>
      </div>
      <div className="equity-mod__badges">
        <EquityBiasChip bias={bias} />
        {grade ? <span className="equity-mod__grade">{grade}</span> : null}
      </div>
    </header>
  );
}

export function ModuleMetric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="equity-mod-metric">
      <span className="equity-mod-metric__k">{label}</span>
      <span className="equity-mod-metric__v">{value}</span>
    </div>
  );
}
