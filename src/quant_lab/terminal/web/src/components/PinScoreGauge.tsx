interface PinScoreGaugeProps {
  score: number | null | undefined;
}

export function PinScoreGauge({ score }: PinScoreGaugeProps) {
  if (score == null || Number.isNaN(score)) return null;

  const pinPct = Math.min(100, Math.max(0, score));
  const pinLabel =
    pinPct >= 70 ? "Pin risk elevated" : pinPct >= 40 ? "Moderate pin" : "Low pin";

  return (
    <div className="pin-gauge pin-gauge--playbook">
      <div className="pin-head">
        <span>Pin score</span>
        <strong>{pinPct.toFixed(0)}</strong>
      </div>
      <div className="pin-track">
        <div className="pin-fill" style={{ width: `${pinPct}%` }} />
      </div>
      <div className="pin-caption">{pinLabel}</div>
    </div>
  );
}
