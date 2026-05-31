/** Per-strike exposure profile geometry (SpotGamma strike-level chart). */
import type { ExposureMetric, HeatmapRow } from "../types/snapshot";

export const EXPOSURE_VIEW_W = 800;
export const EXPOSURE_VIEW_H = 210;
export const EXPOSURE_VIEW_H_COMPACT = 148;
/** Min bar width (px) in Trinity scrollable profile — keeps strikes readable. */
export const EXPOSURE_COMPACT_BAR_W = 8;

export interface ExposurePoint {
  strike: number;
  valueBn: number;
}

export interface ExposureProfileModel {
  viewW: number;
  viewH: number;
  zeroY: number;
  plotLeft: number;
  plotRight: number;
  scrollable: boolean;
  bars: {
    strike: number;
    x: number;
    y: number;
    w: number;
    h: number;
    sign: "pos" | "neg";
    isSpot: boolean;
    isPeak: boolean;
  }[];
  linePath: string;
  posAreaPath: string;
  negAreaPath: string;
  vexLinePath: string | null;
  spotX: number | null;
  spotStrike: number | null;
  emBand: { x: number; w: number } | null;
  markers: { id: string; x: number; label: string; cls: string }[];
  yTicks: { y: number; label: string }[];
  xTicks: { x: number; label: string }[];
  peakStrike: number;
  peakAbsBn: number;
}

function strikeToX(strike: number, minS: number, maxS: number, left: number, innerW: number): number {
  if (maxS <= minS) return left + innerW / 2;
  return left + ((strike - minS) / (maxS - minS)) * innerW;
}

function valueToY(v: number, zeroY: number, halfH: number, maxAbs: number): number {
  return zeroY - (v / maxAbs) * halfH;
}

function buildPath(points: { x: number; y: number }[]): string {
  if (!points.length) return "";
  const [first, ...rest] = points;
  return `M ${first.x.toFixed(2)} ${first.y.toFixed(2)}${rest.map((p) => ` L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join("")}`;
}

function areaToZero(points: { x: number; y: number }[], zeroY: number): string {
  if (!points.length) return "";
  const last = points[points.length - 1];
  const first = points[0];
  return `${buildPath(points)} L ${last.x.toFixed(2)} ${zeroY.toFixed(2)} L ${first.x.toFixed(2)} ${zeroY.toFixed(2)} Z`;
}

function pickXTicks(
  points: ExposurePoint[],
  minS: number,
  maxS: number,
  left: number,
  innerW: number,
  maxTicks = 5,
): { x: number; label: string }[] {
  if (!points.length) return [];
  const count = Math.min(maxTicks, points.length);
  const ticks: { x: number; label: string }[] = [];
  for (let i = 0; i < count; i += 1) {
    const idx = count === 1 ? 0 : Math.round((i / (count - 1)) * (points.length - 1));
    const p = points[idx];
    ticks.push({
      x: strikeToX(p.strike, minS, maxS, left, innerW),
      label: Number.isInteger(p.strike) ? String(p.strike) : p.strike.toFixed(1),
    });
  }
  return ticks;
}

function nearestStrike(strikes: number[], spot: number): number | null {
  if (!strikes.length) return null;
  let best = strikes[0];
  for (const s of strikes) {
    if (Math.abs(s - spot) < Math.abs(best - spot)) best = s;
  }
  return best;
}

export function exposurePoints(rows: HeatmapRow[], metric: ExposureMetric): ExposurePoint[] {
  return [...rows]
    .sort((a, b) => a.strike - b.strike)
    .map((row) => {
      if (metric === "vex") {
        const bn = row.net_vex_bn ?? (row.net_vex ?? 0) / 1e9;
        return { strike: row.strike, valueBn: bn };
      }
      const bn = row.net_gex_bn ?? (row.net_gex ?? 0) * 0.01 / 1e9;
      return { strike: row.strike, valueBn: bn };
    });
}

export function buildExposureProfileModel(
  rows: HeatmapRow[],
  metric: ExposureMetric,
  spot: number,
  levels: { expected_lower?: number | null; expected_upper?: number | null; flip?: number | null; king?: number | null } | null,
  options?: { compact?: boolean },
): ExposureProfileModel | null {
  const compact = options?.compact ?? false;
  const points = exposurePoints(rows, metric);
  if (points.length < 2) return null;

  const pad = { top: 16, right: 16, bottom: 28, left: 50 };
  const viewH = compact ? EXPOSURE_VIEW_H_COMPACT : EXPOSURE_VIEW_H;
  const scrollable = compact;

  let viewW: number;
  let innerW: number;
  let barW: number;

  if (scrollable) {
    barW = EXPOSURE_COMPACT_BAR_W;
    innerW = points.length * barW;
    viewW = pad.left + pad.right + innerW;
  } else {
    viewW = EXPOSURE_VIEW_W;
    innerW = viewW - pad.left - pad.right;
    barW = Math.max(2.5, Math.min(7, (innerW / points.length) * 0.62));
  }

  const innerH = viewH - pad.top - pad.bottom;
  const zeroY = pad.top + innerH / 2;
  const halfH = innerH / 2 - 3;

  const strikes = points.map((p) => p.strike);
  const minS = Math.min(...strikes);
  const maxS = Math.max(...strikes);
  let maxAbs = Math.max(...points.map((p) => Math.abs(p.valueBn)), 0.001);

  if (metric === "compare") {
    const vexAbs = Math.max(...rows.map((r) => Math.abs(r.net_vex_bn ?? (r.net_vex ?? 0) / 1e9)), 0.001);
    maxAbs = Math.max(maxAbs, vexAbs);
  }

  const peakPoint = points.reduce((best, p) =>
    Math.abs(p.valueBn) > Math.abs(best.valueBn) ? p : best,
  );
  const spotStrike = nearestStrike(strikes, spot);

  const bars = points.map((p) => {
    const x = strikeToX(p.strike, minS, maxS, pad.left, innerW) - barW / 2;
    const yTop = valueToY(p.valueBn, zeroY, halfH, maxAbs);
    const h = Math.abs(zeroY - yTop);
    return {
      strike: p.strike,
      x,
      y: Math.min(yTop, zeroY),
      w: barW,
      h: Math.max(h, p.valueBn === 0 ? 0 : 0.6),
      sign: p.valueBn >= 0 ? ("pos" as const) : ("neg" as const),
      isSpot: spotStrike != null && p.strike === spotStrike,
      isPeak: p.strike === peakPoint.strike,
    };
  });

  const linePts = points.map((p) => ({
    x: strikeToX(p.strike, minS, maxS, pad.left, innerW),
    y: valueToY(p.valueBn, zeroY, halfH, maxAbs),
  }));

  const posPts = linePts.map((pt, i) => ({
    x: pt.x,
    y: points[i].valueBn >= 0 ? pt.y : zeroY,
  }));
  const negPts = linePts.map((pt, i) => ({
    x: pt.x,
    y: points[i].valueBn < 0 ? pt.y : zeroY,
  }));

  let vexLinePath: string | null = null;
  if (metric === "compare") {
    const vexPts = exposurePoints(rows, "vex").map((p) => ({
      x: strikeToX(p.strike, minS, maxS, pad.left, innerW),
      y: valueToY(p.valueBn, zeroY, halfH, maxAbs),
    }));
    vexLinePath = buildPath(vexPts);
  }

  const markers: ExposureProfileModel["markers"] = [];
  const markerDefs = [
    { key: "flip" as const, label: "Flip", cls: "flip" },
    { key: "king" as const, label: "King", cls: "king" },
  ];
  for (const m of markerDefs) {
    const strike = levels?.[m.key];
    if (strike == null || Number.isNaN(strike) || strike < minS || strike > maxS) continue;
    markers.push({
      id: m.key,
      x: strikeToX(strike, minS, maxS, pad.left, innerW),
      label: m.label,
      cls: m.cls,
    });
  }

  let emBand: { x: number; w: number } | null = null;
  const lo = levels?.expected_lower;
  const hi = levels?.expected_upper;
  if (lo != null && hi != null && lo >= minS && hi <= maxS) {
    const x1 = strikeToX(lo, minS, maxS, pad.left, innerW);
    const x2 = strikeToX(hi, minS, maxS, pad.left, innerW);
    emBand = { x: Math.min(x1, x2), w: Math.abs(x2 - x1) };
  }

  const spotX = spot >= minS && spot <= maxS ? strikeToX(spot, minS, maxS, pad.left, innerW) : null;
  const fmtTick = (v: number) => {
    if (v === 0) return "0";
    if (!compact) return `${v > 0 ? "+" : ""}${v.toFixed(2)}`;
    const abs = Math.abs(v);
    let body: string;
    if (abs >= 10) body = abs.toFixed(0);
    else if (abs >= 1) body = abs.toFixed(1).replace(/\.0$/, "");
    else body = abs.toFixed(2).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    return v < 0 ? `-${body}` : `+${body}`;
  };

  return {
    viewW,
    viewH,
    zeroY,
    plotLeft: pad.left,
    plotRight: viewW - pad.right,
    scrollable,
    bars,
    linePath: buildPath(linePts),
    posAreaPath: areaToZero(posPts, zeroY),
    negAreaPath: areaToZero(negPts, zeroY),
    vexLinePath,
    spotX,
    spotStrike,
    emBand,
    markers,
    xTicks: pickXTicks(points, minS, maxS, pad.left, innerW, compact ? 3 : 5),
    peakStrike: peakPoint.strike,
    peakAbsBn: Math.abs(peakPoint.valueBn),
    yTicks: [
      { y: valueToY(maxAbs, zeroY, halfH, maxAbs), label: `${fmtTick(maxAbs)}` },
      { y: zeroY, label: "0" },
      { y: valueToY(-maxAbs, zeroY, halfH, maxAbs), label: `${fmtTick(-maxAbs)}` },
    ],
  };
}
