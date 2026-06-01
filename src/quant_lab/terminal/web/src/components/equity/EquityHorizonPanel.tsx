import type { HorizonBias, HorizonVerdict } from "../../types/equity";
import { useLocale } from "../../hooks/useLocale";
import { getEquityStrings } from "../../lib/i18n/equityStrings";

interface EquityHorizonPanelProps {
  horizonKey: "short" | "mid" | "long";
  verdict: HorizonVerdict;
}

function biasClass(bias: HorizonBias): string {
  if (bias === "bullish") return "equity-bias equity-bias--bull";
  if (bias === "bearish") return "equity-bias equity-bias--bear";
  return "equity-bias equity-bias--neutral";
}

function ConfidenceMeter({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="equity-conf" aria-label={`${label} ${pct}%`}>
      <div className="equity-conf__track">
        <div className="equity-conf__fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="equity-conf__label">
        {pct}% {label}
      </span>
    </div>
  );
}

export function EquityHorizonPanel({ horizonKey, verdict }: EquityHorizonPanelProps) {
  const { locale } = useLocale();
  const s = getEquityStrings(locale);
  const meta = s.horizons[horizonKey];

  return (
    <article className="equity-horizon-panel panel">
      <header className="equity-horizon-panel__head">
        <div className="equity-horizon-panel__titles">
          <span className="equity-horizon-panel__window">{meta.window}</span>
          <h3>
            {meta.title} {s.horizonHorizon}
          </h3>
          <p className="equity-horizon-panel__focus">{meta.focus}</p>
        </div>
        <div className="equity-horizon-panel__badges">
          <span className={biasClass(verdict.bias)}>{s.bias[verdict.bias]}</span>
          <span className="equity-grade-badge">
            {s.grade} {verdict.grade}
          </span>
        </div>
      </header>

      <ConfidenceMeter value={verdict.confidence} label={s.confidence} />

      <p className="equity-horizon-panel__summary">{verdict.summary}</p>

      {verdict.drivers.length > 0 ? (
        <section className="equity-horizon-panel__section">
          <h4>{s.supporting}</h4>
          <ul className="equity-horizon-panel__list">
            {verdict.drivers.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {verdict.risks.length > 0 ? (
        <section className="equity-horizon-panel__section equity-horizon-panel__section--risk">
          <h4>{s.caveats}</h4>
          <ul className="equity-horizon-panel__list">
            {verdict.risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
