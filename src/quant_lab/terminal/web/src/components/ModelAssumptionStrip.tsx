import { useState } from "react";

import type { DashboardSnapshot } from "../types/snapshot";

function fmtTMode(mode: string | undefined): string {
  switch (mode) {
    case "exact_intraday":
      return "intraday T";
    case "hours_to_close":
      return "session T";
    case "dte_over_365":
      return "calendar DTE";
    case "fallback_1h":
      return "~1h fallback T";
    default:
      return mode ?? "T?";
  }
}

function needsExpandedDetail(
  snapshot: DashboardSnapshot,
  warnings: string[],
): boolean {
  const mm = snapshot.meta?.model_metadata;
  const t = mm?.time_to_expiry;
  const lq = mm?.live_pin_quality ?? snapshot.pin_targets?.live_data_quality;
  return (
    warnings.length > 0 ||
    t?.fallback_used === true ||
    lq?.grade === "poor" ||
    lq?.grade === "degraded" ||
    snapshot.meta?.cohort_fallback === true
  );
}

export function ModelAssumptionStrip({ snapshot }: { snapshot: DashboardSnapshot }) {
  const mm = snapshot.meta?.model_metadata;
  const [expanded, setExpanded] = useState(false);
  if (!mm) return null;

  const warnings = mm.data_quality_warnings ?? [];
  const t = mm.time_to_expiry;
  const pricing = mm.pricing_inputs;
  const isLive = snapshot.meta?.live_follow === true;
  const autoExpand = needsExpandedDetail(snapshot, warnings);
  const showDetails = expanded || autoExpand;

  const tPart = t
    ? `${fmtTMode(t.mode)}${t.fallback_used ? " ⚠" : ""}${
        t.t_years_median != null ? ` · ${(t.t_years_median * 365 * 6.5).toFixed(1)}h` : ""
      }`
    : null;
  const rPart = pricing
    ? `r=${pricing.r?.toFixed(3)} (${pricing.rate_source})`
    : null;
  const flipPart = mm.gamma_flip?.confidence ? `flip ${mm.gamma_flip.confidence}` : null;
  const livePart =
    isLive && snapshot.meta?.hours_to_close != null
      ? `${Number(snapshot.meta.hours_to_close).toFixed(1)}h to close`
      : null;

  const summary = ["Model-implied", rPart, tPart, flipPart, livePart].filter(Boolean).join(" · ");

  if (!showDetails) {
    return (
      <p className="model-context-line" aria-label="Model assumptions">
        <span>{summary}</span>
        <button
          type="button"
          className="model-context-line__more"
          onClick={() => setExpanded(true)}
          aria-expanded={false}
        >
          Details
        </button>
      </p>
    );
  }

  return (
    <aside
      className={`model-assumption-strip${autoExpand ? " model-assumption-strip--alert" : ""}`}
      aria-label="Model assumptions"
    >
      <div className="model-assumption-strip__head">
        <span className="model-context-line__summary">{summary}</span>
        {!autoExpand ? (
          <button
            type="button"
            className="model-context-line__more"
            onClick={() => setExpanded(false)}
            aria-expanded
          >
            Hide
          </button>
        ) : null}
      </div>
      {warnings.length > 0 ? (
        <ul className="model-assumption-strip__warnings">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : (
        <p className="model-assumption-strip__note">
          Dealer positioning is inferred from OI + sign convention, not observed flow.
        </p>
      )}
    </aside>
  );
}
