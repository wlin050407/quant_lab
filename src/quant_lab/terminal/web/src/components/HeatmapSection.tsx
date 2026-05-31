import { useEffect, useRef, type ReactNode } from "react";

import { HEATMAP_TITLES, TRINITY_ORDER } from "../lib/heatmap";

import type { DashboardSnapshot, ExposureMetric, HeatmapViewMode, PanelSnapshot } from "../types/snapshot";

import { usePanelSections } from "../hooks/usePanelSections";
import { HeatmapPanel } from "./HeatmapPanel";
import { HeatmapViewToggle } from "./HeatmapViewToggle";
import { useTrinityStagger } from "../hooks/useTrinityStagger";

interface HeatmapSectionProps {
  snapshot: DashboardSnapshot;
  metric: ExposureMetric;
  viewMode: HeatmapViewMode;
  onMetricChange: (metric: ExposureMetric) => void;
  onViewModeChange: (mode: HeatmapViewMode) => void;
  scrollKey: number;
}

function emptyPanel(symbol: string): PanelSnapshot {
  return {
    symbol,
    available: false,
    heatmap: [],
    gamma_profile: [],
    spot: 0,
    regime: "undetermined",
    king: NaN,
    flip: NaN,
    call_wall: NaN,
    put_wall: NaN,
    pin_score: NaN,
    king_distance: null,
    spot_change_pct: null,
    data_source: "unavailable",
    data_mode: "No chain for this date",
    intraday_time: null,
  };
}

export function HeatmapSection({
  snapshot,
  metric,
  viewMode,
  onMetricChange,
  onViewModeChange,
  scrollKey,
}: HeatmapSectionProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const primaryKey = snapshot.symbol.replace("^", "");
  const bySym: Record<string, PanelSnapshot> = {};
  (snapshot.panels ?? []).forEach((p) => {
    bySym[p.symbol.replace("^", "")] = p;
  });

  const activeTrinityPanels = TRINITY_ORDER.filter(
    (o) => bySym[o.key]?.available && (bySym[o.key]?.heatmap?.length ?? 0) > 0,
  );

  const primaryEntry = TRINITY_ORDER.find((o) => o.key === primaryKey) ?? TRINITY_ORDER[0];

  const panelsToShow =
    viewMode === "trinity" ? TRINITY_ORDER : [primaryEntry ?? TRINITY_ORDER[0]];

  const layoutClass = viewMode === "trinity" ? "layout-triple" : "layout-single";
  const multiColumn = viewMode === "trinity";
  const activeCount = activeTrinityPanels.length;

  const t = snapshot.trinity;
  const primaryLabel = primaryEntry?.label ?? primaryKey;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.classList.remove("heatmap-metric-enter");
    void el.offsetWidth;
    el.classList.add("heatmap-metric-enter");
  }, [metric]);

  useTrinityStagger(containerRef, viewMode, panelsToShow.length);

  const { showRegime, toggleRegime } = usePanelSections(viewMode);

  let banner: ReactNode = null;
  if (viewMode === "trinity") {
    const missing = TRINITY_ORDER.filter(
      (o) => !bySym[o.key]?.available || (bySym[o.key]?.heatmap?.length ?? 0) === 0,
    ).map((o) => o.label);

    if (t.score != null && activeCount >= 2) {
      banner = (
        <div className="trinity-banner trinity-banner--compact">
          <strong>Alignment {t.score.toFixed(0)}/100</strong>
          <span className="sep">·</span>
          {t.direction}
          <span className="sep">·</span>
          {activeCount}/3 live
        </div>
      );
    } else {
      banner = (
        <div className="trinity-banner trinity-banner--compact">
          <span className="muted">
            {activeCount}/3 with data
            {missing.length ? (
              <>
                <span className="sep">·</span>
                no chain: {missing.join(", ")}
              </>
            ) : null}
            {" · Regime toggle in toolbar"}
          </span>
        </div>
      );
    }
  } else if (activeCount === 0) {
    banner = (
      <div className="trinity-banner">
        <span className="muted">No heatmap data for {primaryLabel} on this date.</span>
      </div>
    );
  }

  const metrics: ExposureMetric[] = ["gex", "vex", "compare"];

  return (
    <div
      id="heatmap-section"
      className={`heatmap-stage heatmap-stage--${viewMode} heatmap-stage--metric-${metric}${metric === "compare" ? " mode-compare" : ""}`}
    >
      <div className="heatmap-stage-chrome">
        <div className="heatmap-stage-toolbar">
          <span className="heatmap-stage-title" id="heatmap-title">
            {HEATMAP_TITLES[metric]}
          </span>
          <HeatmapViewToggle value={viewMode} onChange={onViewModeChange} />
          <span className="strike-lens-label">Lens</span>
          <div className="exposure-toggle" role="tablist" aria-label="Strike plot lens">
            {metrics.map((m) => (
              <button
                key={m}
                type="button"
                className={`exp-btn exp-btn--${m}${metric === m ? " active" : ""}`}
                data-metric={m}
                role="tab"
                aria-selected={metric === m}
                onClick={() => onMetricChange(m)}
              >
                {m === "compare" ? "Compare" : m.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="regime-toggle" role="group" aria-label="Gamma regime band (GEX lens only)">
            <button
              type="button"
              className={`regime-btn${showRegime && metric === "gex" ? " active" : ""}`}
              aria-pressed={showRegime && metric === "gex"}
              disabled={metric !== "gex"}
              title={
                metric === "gex"
                  ? "Gamma regime band — what-if GEX curve (SpotGamma Heatmap lens)"
                  : "Regime band only applies to GEX lens"
              }
              onClick={toggleRegime}
            >
              Regime
            </button>
          </div>
        </div>
        {banner}
      </div>

      <div className="heatmap-stage-body">
        <div ref={containerRef} className={`heatmap-container ${layoutClass}`}>
          {panelsToShow.map((o) => {
            const p = bySym[o.key] ?? emptyPanel(o.key === "SPX" ? "^SPX" : o.key);
            const isPrimary = o.key === primaryKey;
            const hasHeatmap = p.available && (p.heatmap?.length ?? 0) > 0;
            return (
              <HeatmapPanel
                key={o.key}
                panel={p}
                levels={isPrimary ? snapshot.levels : null}
                metric={metric}
                viewMode={viewMode}
                primary={isPrimary}
                scrollKey={hasHeatmap ? scrollKey : 0}
                chartCompact={multiColumn}
                showRegime={showRegime}
              />
            );
          })}
        </div>
      </div>

      <footer className={`heatmap-stage-footer${viewMode === "trinity" ? " heatmap-stage-footer--trinity" : ""}`}>
        {metric === "gex" ? (
          <>
            <span className="legend-item legend-gex">
              <i className="dot dot-pos" />+GEX dampens
            </span>
            <span className="legend-item legend-gex">
              <i className="dot dot-neg" />−GEX amplifies
            </span>
          </>
        ) : null}
        {metric === "vex" ? (
          <>
            <span className="legend-item legend-vex">
              <i className="dot dot-vex-pos" />+VEX vol↑ sell
            </span>
            <span className="legend-item legend-vex">
              <i className="dot dot-vex-neg" />−VEX vol↓ buy
            </span>
          </>
        ) : null}
        {metric === "compare" ? (
          <>
            <span className="legend-item legend-compare">
              <i className="dot dot-pos" />
              GEX bar
            </span>
            <span className="legend-item legend-compare">
              <i className="dot dot-vex-pos" />
              VEX bar
            </span>
            <span className="legend-item legend-compare">
              <i className="dot dot-diverge" />
              Sign clash
            </span>
            <span className="legend-item legend-compare compare-hint">each bar 0–100% of day max</span>
          </>
        ) : null}
        <span className="legend-item legend-item--keep">
          <i className="dot dot-em" />
          Expected range
        </span>
        <span className="legend-item legend-item--keep">
          <i className="dot dot-flip" />
          Flip level
        </span>
        <span className="cohort legend-item--keep" id="cohort-label">
          {snapshot.meta?.cohort ?? "dte≤1"}
        </span>
      </footer>
    </div>
  );
}
