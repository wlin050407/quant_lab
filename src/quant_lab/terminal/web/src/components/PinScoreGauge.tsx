interface PinScoreGaugeProps {
  score: number | null | undefined;
  adjustedScore?: number | null;
  reliability?: string | null;
  reliabilityDetail?: string | null;
}

const RELIABILITY_CLASS: Record<string, string> = {
  high: "pin-reliability--high",
  moderate: "pin-reliability--moderate",
  caution: "pin-reliability--caution",
  low: "pin-reliability--low",
  unknown: "pin-reliability--unknown",
};

export function PinScoreGauge({
  score,
  adjustedScore,
  reliability,
  reliabilityDetail,
}: PinScoreGaugeProps) {
  if (score == null || Number.isNaN(score)) return null;

  const displayScore =
    adjustedScore != null && !Number.isNaN(adjustedScore) ? adjustedScore : score;
  const pinPct = Math.min(100, Math.max(0, displayScore));
  const pinLabel =
    pinPct >= 70 ? "Pin risk elevated" : pinPct >= 40 ? "Moderate pin" : "Low pin";
  const relClass = RELIABILITY_CLASS[reliability ?? "unknown"] ?? RELIABILITY_CLASS.unknown;

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
      {adjustedScore != null && !Number.isNaN(adjustedScore) && Math.abs(adjustedScore - score) >= 1 ? (
        <div className="pin-adjusted-ref">Raw {score.toFixed(0)} → regime-adjusted</div>
      ) : null}
      {reliability ? (
        <div className={`pin-reliability ${relClass}`} title={reliabilityDetail ?? undefined}>
          {reliabilityDetail ?? reliability}
        </div>
      ) : null}
    </div>
  );
}
