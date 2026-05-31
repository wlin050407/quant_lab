import { useLayoutEffect, useRef, type CSSProperties } from "react";
import { fmtGexBn, fmtMoney, fmtPct, fmtPrice, fmtRoc } from "../lib/format";
import {
  compareDivergence,
  emZoneVars,
  heatClass,
  heatmapRowTitle,
  levelTags,
  near,
  nearestStrikeToSpot,
  scrollHeatmapToSpot,
  sortedHeatmapRows,
  spotTopPct,
  formatStrikeAttr,
  vexHeatClass,
} from "../lib/heatmap";
import { LIVE_INTRADAY_SYMBOLS } from "../lib/liveSymbols";
import type {
  ExposureMetric,
  HeatmapRow,
  HeatmapViewMode,
  Levels,
  PanelSnapshot,
} from "../types/snapshot";
import { usePanelSectionMotion } from "../hooks/usePanelSectionMotion";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { GammaProfileChart } from "./GammaProfileChart";
import { KingPill } from "./KingPill";
import { PanelDataBadge } from "./PanelDataBadge";

interface HeatmapPanelProps {
  panel: PanelSnapshot;
  levels: Levels | null;
  metric: ExposureMetric;
  viewMode: HeatmapViewMode;
  primary: boolean;
  scrollKey: number;
  chartCompact?: boolean;
  showRegime: boolean;
}

function formatExposure(row: HeatmapRow, metric: ExposureMetric): string {
  if (metric === "gex") {
    const bn = row.net_gex_bn ?? (row.net_gex ?? 0) * 0.01 / 1e9;
    return fmtGexBn(bn);
  }
  if (metric === "vex" && row.net_vex_bn != null) {
    return fmtGexBn(row.net_vex_bn);
  }
  return fmtMoney(exposureValue(row, metric));
}

function exposureValue(row: HeatmapRow, metric: ExposureMetric): number {
  if (metric === "vex") return row.net_vex ?? 0;
  return row.net_gex ?? 0;
}

function exposureRoc(row: HeatmapRow, metric: ExposureMetric): number | null {
  if (metric === "vex") return row.roc_pct_vex;
  return row.roc_pct;
}

function SingleRow({
  row,
  spot,
  spotStrike,
  levels,
  metric,
  maxAbs,
}: {
  row: HeatmapRow;
  spot: number;
  spotStrike: number | null;
  levels: Levels | null;
  metric: ExposureMetric;
  maxAbs: number;
}) {
  const val = exposureValue(row, metric);
  const barVal =
    metric === "gex"
      ? (row.net_gex_bn ?? (row.net_gex ?? 0) * 0.01 / 1e9)
      : metric === "vex"
        ? (row.net_vex_bn ?? (row.net_vex ?? 0) / 1e9)
        : val;
  const intensity = Math.abs(barVal) / (maxAbs || 1);
  const cls = heatClass(intensity, val);
  const signPrefix = metric === "vex" ? "vex" : "gex";
  const tags = levelTags(row.strike, levels);
  const visibleTags = tags.slice(0, 2);
  const tagTitle = tags.map((t) => t.text).join(" · ");
  const roc = fmtRoc(exposureRoc(row, metric));
  const isSpot = spotStrike != null && row.strike === spotStrike;
  const isKing = levels ? near(row.strike, levels.king) : false;

  return (
    <div
      className={`hm-row hm-row-animate${isSpot ? " spot-row" : ""}${isKing ? " king-row" : ""}`}
      data-strike={formatStrikeAttr(row.strike)}
      title={heatmapRowTitle(row, spot, metric)}
    >
      <span className="hm-strike">{row.strike.toFixed(0)}</span>
      <div className="hm-bar-wrap hm-bar-wrap-mirror">
        <div className="hm-bar-zero" />
        <div
          className={`hm-bar hm-bar-mirror ${cls}${val >= 0 ? " mirror-pos" : " mirror-neg"}`}
          style={{
            width: `${(intensity * 50).toFixed(1)}%`,
            marginLeft: val >= 0 ? "50%" : `${(50 - intensity * 50).toFixed(1)}%`,
          }}
        />
      </div>
      <div className="hm-right">
        <span className={`hm-gex ${val >= 0 ? `${signPrefix}-pos` : `${signPrefix}-neg`}`}>
          {formatExposure(row, metric)}
        </span>
        {visibleTags.length > 0 ? (
          <span className="hm-tags" title={tagTitle || undefined}>
            {visibleTags.map((t) => (
              <span key={t.text} className={`lv-tag ${t.cls}`}>
                {t.text}
              </span>
            ))}
          </span>
        ) : null}
        {roc ? (
          <span className={`roc-badge ${(exposureRoc(row, metric) ?? 0) >= 0 ? "up" : "down"}`}>
            {roc}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function gexBn(row: HeatmapRow): number {
  return row.net_gex_bn ?? ((row.net_gex ?? 0) * 0.01) / 1e9;
}

function vexBn(row: HeatmapRow): number {
  return row.net_vex_bn ?? (row.net_vex ?? 0) / 1e9;
}

function CompareRow({
  row,
  spot,
  spotStrike,
  levels,
  maxGex,
  maxVex,
}: {
  row: HeatmapRow;
  spot: number;
  spotStrike: number | null;
  levels: Levels | null;
  maxGex: number;
  maxVex: number;
}) {
  const gexVal = gexBn(row);
  const vexVal = vexBn(row);
  const gInt = Math.abs(gexVal) / maxGex;
  const vInt = Math.abs(vexVal) / maxVex;
  const diverge = compareDivergence(gexVal, vexVal, maxGex, maxVex);
  const tags = levelTags(row.strike, levels);
  const visibleTags = tags.slice(0, 1);
  const tagTitle = tags.map((t) => t.text).join(" · ");
  const isSpot = spotStrike != null && row.strike === spotStrike;
  const isKing = levels ? near(row.strike, levels.king) : false;

  return (
    <div
      className={`hm-row hm-row-animate mode-compare${isSpot ? " spot-row" : ""}${isKing ? " king-row" : ""}${diverge ? " diverge-row" : ""}`}
      data-strike={formatStrikeAttr(row.strike)}
      title={heatmapRowTitle(row, spot, "gex")}
    >
      <span className="hm-strike">{row.strike.toFixed(0)}</span>
      <div className="hm-dual">
        <div className="hm-dual-row hm-dual-row--gex">
          <div className="hm-bar-wrap">
            <div
              className={`hm-bar ${heatClass(gInt, gexVal)}`}
              style={{ width: `${(gInt * 100).toFixed(1)}%` }}
            />
          </div>
        </div>
        <div className="hm-dual-row hm-dual-row--vex">
          <div className="hm-bar-wrap">
            <div
              className={`hm-bar ${vexHeatClass(vInt, vexVal)}`}
              style={{ width: `${(vInt * 100).toFixed(1)}%` }}
            />
          </div>
        </div>
      </div>
      <div className="hm-compare-right">
        <span className={`hm-gex hm-compare-gex ${gexVal >= 0 ? "gex-pos" : "gex-neg"}`}>
          {fmtGexBn(gexVal)}
        </span>
        <span className={`hm-gex hm-compare-vex ${vexVal >= 0 ? "vex-pos" : "vex-neg"}`}>
          {fmtGexBn(vexVal)}
        </span>
        {diverge ? <span className="diverge-badge">CLASH</span> : null}
        {visibleTags.length > 0 ? (
          <span className="hm-tags" title={tagTitle || undefined}>
            {visibleTags.map((t) => (
              <span key={t.text} className={`lv-tag ${t.cls}`}>
                {t.text}
              </span>
            ))}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function HeatmapPanel({
  panel,
  levels,
  metric,
  viewMode,
  primary,
  scrollKey,
  chartCompact = false,
  showRegime,
}: HeatmapPanelProps) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const heatmapBodyRef = useRef<HTMLDivElement>(null);
  const sym = panel.symbol.replace("^", "");
  const reducedMotion = useReducedMotion();

  usePanelSectionMotion(heatmapBodyRef, showRegime && metric === "gex", reducedMotion);

  useLayoutEffect(() => {
    if (scrollKey <= 0) return;
    const scrollEl = bodyRef.current;
    const canvasEl = canvasRef.current;
    const heatmap = panel.heatmap;
    if (!scrollEl || !canvasEl || !heatmap?.length || panel.spot <= 0) return;

    let cancelled = false;
    const runScroll = () => {
      if (!cancelled) scrollHeatmapToSpot(scrollEl, canvasEl, panel.spot, heatmap);
    };

    runScroll();
    const timers = [50, 200, 500, 900].map((ms) => window.setTimeout(runScroll, ms));
    const ro = new ResizeObserver(runScroll);
    ro.observe(canvasEl);

    return () => {
      cancelled = true;
      timers.forEach((t) => window.clearTimeout(t));
      ro.disconnect();
    };
  }, [scrollKey, panel.spot, panel.heatmap, panel.symbol, metric]);

  if (!panel.available || !panel.heatmap?.length) {
    const supportsLive =
      LIVE_INTRADAY_SYMBOLS.has(panel.symbol) || sym === "SPX" || sym === "SPXW";
    return (
      <div className={`heatmap-panel inactive${primary ? " primary" : ""}`}>
        <div className="heatmap-header">
          <div className="heatmap-header-top">
            <span className="sym">{sym}</span>
            <PanelDataBadge panel={panel} />
          </div>
        </div>
        <div className="empty-panel">
          <p>{panel.data_mode || "No option chain for this date"}</p>
          {supportsLive ? (
            <>
              <small>ThetaData live 0DTE · needs credentials + market hours</small>
              <div className="empty-panel-cta">Demo: 2023-07-11 · 13:00 ET</div>
            </>
          ) : (
            <small>No live path for this symbol</small>
          )}
        </div>
      </div>
    );
  }

  const spot = panel.spot;
  const rows = sortedHeatmapRows(panel.heatmap);
  const spotStrike = nearestStrikeToSpot(rows, spot);
  const maxGexBn = Math.max(...rows.map((r) => Math.abs(gexBn(r))), 0.001);
  const maxVexBn = Math.max(...rows.map((r) => Math.abs(vexBn(r))), 0.001);
  const maxAbs =
    metric === "compare"
      ? 1
      : metric === "gex"
        ? Math.max(
            ...rows.map((r) => Math.abs(r.net_gex_bn ?? (r.net_gex ?? 0) * 0.01 / 1e9)),
            0.001,
          )
        : metric === "vex"
          ? Math.max(
              ...rows.map((r) => Math.abs(r.net_vex_bn ?? (r.net_vex ?? 0) / 1e9)),
              0.001,
            )
          : Math.max(...rows.map((r) => Math.abs(exposureValue(r, metric))), 1);

  const lv =
    levels ??
    ({
      king: panel.king,
      flip: panel.flip,
      call_wall: panel.call_wall,
      put_wall: panel.put_wall,
    } as Levels);

  const emVars = emZoneVars(rows, levels ?? undefined);
  const spotPct = spotTopPct(rows, spot);
  const canvasClass = [
    "heatmap-canvas",
    metric === "compare" ? "mode-compare-canvas" : "",
    emVars ? "has-em" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const chg = panel.spot_change_pct;
  const regimeVisible = showRegime && metric === "gex";

  const compareLegend =
    metric === "compare" ? (
      <div className="compare-lens-legend" aria-hidden>
        <span className="compare-lens-legend__chip compare-lens-legend__chip--gex">GEX</span>
        <span className="compare-lens-legend__chip compare-lens-legend__chip--vex">VEX</span>
        <span className="compare-lens-legend__hint">top / bottom bar per strike</span>
      </div>
    ) : null;

  const strikeRows = (
    <>
      {compareLegend}
      <div className="strike-plot-trace__scroll" ref={bodyRef}>
        <div ref={canvasRef} className={canvasClass} style={emVars as CSSProperties | undefined}>
        {emVars ? <div className="em-zone" /> : null}
        {spotPct != null ? (
          <div className="spot-pointer" style={{ top: `${spotPct.toFixed(3)}%` }}>
            <span className="spot-pointer-label">{spot.toFixed(2)}</span>
          </div>
        ) : null}
        {metric === "compare"
          ? rows.map((r) => (
              <CompareRow
                key={r.strike}
                row={r}
                spot={spot}
                spotStrike={spotStrike}
                levels={lv}
                maxGex={maxGexBn}
                maxVex={maxVexBn}
              />
            ))
          : rows.map((r) => (
              <SingleRow
                key={r.strike}
                row={r}
                spot={spot}
                spotStrike={spotStrike}
                levels={lv}
                metric={metric}
                maxAbs={maxAbs}
              />
            ))}
        </div>
      </div>
    </>
  );

  const showPanelQuote = viewMode !== "single";

  return (
    <div
      className={[
        "heatmap-panel",
        "heatmap-panel--trace",
        primary ? "primary" : "",
        chartCompact ? "heatmap-panel--compact-charts" : "",
        viewMode === "single" ? "heatmap-panel--single" : "heatmap-panel--trinity",
        metric === "compare" ? "heatmap-panel--compare" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className={`heatmap-header${showPanelQuote ? "" : " heatmap-header--slim"}`}>
        <div className="heatmap-header-top">
          {showPanelQuote ? (
            <div className="heatmap-title">
              <span className="sym">{sym}</span>
              <span className="panel-spot">{fmtPrice(spot)}</span>
              {chg != null ? (
                <span
                  className={`spot-chg ${chg >= 0 ? "up" : "down"}`}
                  title="Day change vs previous trading day close"
                >
                  {fmtPct(chg)}
                </span>
              ) : null}
            </div>
          ) : (
            <span className="heatmap-header-slug">0DTE strikes</span>
          )}
          <PanelDataBadge panel={panel} compact={chartCompact || !showPanelQuote} />
        </div>
        {showPanelQuote && primary ? <KingPill kd={panel.king_distance} /> : null}
      </div>
      <div className="heatmap-body heatmap-body--trace" ref={heatmapBodyRef}>
        {regimeVisible ? (
          <div className="regime-band">
            <GammaProfileChart
              curve={panel.gamma_profile ?? []}
              spot={spot}
              levels={lv}
              flipLevel={levels?.flip ?? panel.flip ?? null}
              animateKey={`${scrollKey}-${sym}-gamma-regime`}
              embedded
              band
              compact={chartCompact}
              fillWidth
            />
          </div>
        ) : null}
        <div className="strike-plot-trace">{strikeRows}</div>
      </div>
    </div>
  );
}
