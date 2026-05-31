import { dataSourceLabel } from "../lib/snapshotMeta";
import { regimeShort } from "../lib/format";
import type { DashboardSnapshot } from "../types/snapshot";

/** @deprecated Merged into InstrumentStrip — kept for tests / legacy imports */
export function DataBadge({ snapshot }: { snapshot: DashboardSnapshot }) {
  const source = dataSourceLabel(snapshot);
  const isLive = snapshot.meta?.data_source === "thetadata_live";
  const isIntraday = Boolean(snapshot.meta?.intraday_time);
  const timeLabel = isIntraday ? `${snapshot.meta?.intraday_time} ET` : "EoD close";
  const strikes = snapshot.heatmap?.length ?? 0;
  const cohort = snapshot.meta?.cohort ?? "dte≤1";
  const regime = regimeShort(snapshot.regime);

  return (
    <div className="data-badge" role="status" aria-label="Data context">
      <span className={`data-badge-pill data-badge-pill--${isLive ? "live" : isIntraday ? "live" : "eod"}`}>{source}</span>
      <span className="data-badge-sep">·</span>
      <span className="data-badge-item">
        <span className="data-badge-k">as-of</span>
        {snapshot.date} {timeLabel}
      </span>
      <span className="data-badge-sep">·</span>
      <span className="data-badge-item">
        <span className="data-badge-k">strikes</span>
        {strikes}
      </span>
      <span className="data-badge-sep">·</span>
      <span className="data-badge-item">
        <span className="data-badge-k">cohort</span>
        {cohort}
      </span>
      <span className="data-badge-sep">·</span>
      <span className={`data-badge-pill data-badge-pill--regime ${snapshot.regime}`}>{regime}</span>
    </div>
  );
}

export { dataSourceLabel };
