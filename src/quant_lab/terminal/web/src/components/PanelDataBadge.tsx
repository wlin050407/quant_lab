import type { PanelSnapshot } from "../types/snapshot";

function sourceLabel(source: string | undefined): string {
  switch (source) {
    case "thetadata_live":
      return "Live";
    case "thetadata":
      return "Intraday";
    case "eod":
      return "EoD";
    case "unavailable":
      return "No data";
    default:
      return source ?? "—";
  }
}

export function PanelDataBadge({ panel, compact = false }: { panel: PanelSnapshot; compact?: boolean }) {
  const source = panel.data_source ?? "unavailable";
  const isLive = source === "thetadata_live";
  const isEod = source === "eod";
  const time = panel.intraday_time;
  const mode = panel.data_mode;

  return (
    <div
      className={`panel-data-badge panel-data-badge--${source}`}
      title={mode || undefined}
      aria-label={`Data source: ${mode || sourceLabel(source)}`}
    >
      <span className={`panel-data-badge-pill${isLive ? " is-live" : ""}${isEod ? " is-eod" : ""}`}>
        {sourceLabel(source)}
      </span>
      {time && !compact ? <span className="panel-data-badge-time">{time} ET</span> : null}
      {!time && isEod && !compact ? <span className="panel-data-badge-time">close</span> : null}
    </div>
  );
}
