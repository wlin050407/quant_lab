import type { ChartTimeframe } from "../../lib/equityChartTimeframes";
import { TIMEFRAME_ORDER } from "../../lib/equityChartTimeframes";
import { useLocale } from "../../hooks/useLocale";
import { getEquityStrings } from "../../lib/i18n/equityStrings";
import { formatVolumeShares } from "../../lib/equityDisplay";

interface EquityChartToolbarProps {
  timeframe: ChartTimeframe;
  onTimeframe: (tf: ChartTimeframe) => void;
  meta: string;
  available: ChartTimeframe[];
  sessionVol?: number | null;
  sessionVolLabel?: string;
  sharesLabel?: string;
}

export function EquityChartToolbar({
  timeframe,
  onTimeframe,
  meta,
  available,
  sessionVol,
  sessionVolLabel,
  sharesLabel,
}: EquityChartToolbarProps) {
  const { locale } = useLocale();
  const s = getEquityStrings(locale);
  const tfLabels = s.chart.timeframes as Record<ChartTimeframe, string>;

  return (
    <div className="equity-chart-toolbar">
      <div className="equity-chart-toolbar__left">
        <span className="equity-chart-toolbar__title">{s.intradayChart}</span>
        <span className="equity-chart-toolbar__meta">{meta}</span>
      </div>
      <div className="equity-tf-bar" role="tablist" aria-label={s.chart.timeframeAria}>
        {TIMEFRAME_ORDER.filter((tf) => available.includes(tf)).map((tf) => (
          <button
            key={tf}
            type="button"
            role="tab"
            className={`equity-tf-bar__btn${timeframe === tf ? " is-active" : ""}`}
            aria-selected={timeframe === tf}
            onClick={() => onTimeframe(tf)}
          >
            {tfLabels[tf]}
          </button>
        ))}
      </div>
      {sessionVol != null && sessionVol > 0 && sessionVolLabel && sharesLabel ? (
        <span className="equity-chart-toolbar__vol">
          {sessionVolLabel} {formatVolumeShares(sessionVol)} {sharesLabel}
        </span>
      ) : null}
    </div>
  );
}
