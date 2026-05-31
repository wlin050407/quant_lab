import type { ExposureMetric, HeatmapRow, Levels } from "../types/snapshot";

export const LEVEL_TOL = 0.51;

export function near(a: number | null | undefined, b: number | null | undefined): boolean {
  return a != null && b != null && Math.abs(a - b) < LEVEL_TOL;
}

export function distPct(spot: number, level: number | null | undefined): number | null {
  if (level == null || spot <= 0) return null;
  return ((level - spot) / spot) * 100;
}

export function sortedHeatmapRows(rows: HeatmapRow[]): HeatmapRow[] {
  return [...rows].sort((a, b) => b.strike - a.strike);
}

export function strikeRowFraction(sortedRowsDesc: HeatmapRow[], level: number | null): number | null {
  const n = sortedRowsDesc.length;
  if (!n || level == null || Number.isNaN(level)) return null;
  const strikes = sortedRowsDesc.map((r) => r.strike);
  const maxS = strikes[0];
  const minS = strikes[n - 1];

  if (level >= maxS) return 0;
  if (level <= minS) return n - 1;

  for (let i = 0; i < n - 1; i += 1) {
    const hi = strikes[i];
    const lo = strikes[i + 1];
    if (level <= hi && level >= lo) {
      if (hi === lo) return i;
      return i + (hi - level) / (hi - lo);
    }
  }
  return n - 1;
}

export function rowCenterPct(sortedRowsDesc: HeatmapRow[], level: number | null): number | null {
  const n = sortedRowsDesc.length;
  if (!n) return null;
  const frac = strikeRowFraction(sortedRowsDesc, level);
  if (frac == null) return null;
  return ((frac + 0.5) / n) * 100;
}

export function emZoneVars(
  rows: HeatmapRow[],
  levels: Levels | null | undefined,
): Record<string, string> | undefined {
  if (!levels?.expected_lower || !levels?.expected_upper || !rows.length) return undefined;
  const sorted = sortedHeatmapRows(rows);
  const n = sorted.length;
  const upperFrac = strikeRowFraction(sorted, levels.expected_upper);
  const lowerFrac = strikeRowFraction(sorted, levels.expected_lower);
  if (upperFrac == null || lowerFrac == null) return undefined;

  const top = (upperFrac / n) * 100;
  const bottom = ((lowerFrac + 1) / n) * 100;
  const height = Math.max(100 / n, bottom - top);
  return {
    "--em-top": `${top.toFixed(3)}%`,
    "--em-height": `${height.toFixed(3)}%`,
  };
}

export function spotTopPct(sortedRowsDesc: HeatmapRow[], spot: number | null): number | null {
  if (spot == null || sortedRowsDesc.length < 2) return null;
  const topPct = rowCenterPct(sortedRowsDesc, spot);
  if (topPct == null) return null;
  return Math.max(0.5, Math.min(99.5, topPct));
}

/** Strike row closest to spot (always one winner when rows non-empty). */
export function nearestStrikeToSpot(rows: HeatmapRow[], spot: number): number | null {
  if (!rows.length || spot == null || Number.isNaN(spot)) return null;
  let best = rows[0];
  for (const row of rows) {
    if (Math.abs(row.strike - spot) < Math.abs(best.strike - spot)) best = row;
  }
  return best.strike;
}

export function isNearestSpotStrike(strike: number, spot: number, rows: HeatmapRow[]): boolean {
  const nearest = nearestStrikeToSpot(rows, spot);
  return nearest != null && strike === nearest;
}

/** Stable strike key for DOM lookup (avoids float formatting mismatches). */
export function formatStrikeAttr(strike: number): string {
  const rounded = Math.round(strike * 10000) / 10000;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(4).replace(/\.?0+$/, "");
}

/** Scroll offset to center a row inside the scroll viewport. */
export function rowScrollTop(scrollEl: HTMLElement, rowEl: HTMLElement): number {
  const scrollRect = scrollEl.getBoundingClientRect();
  const rowRect = rowEl.getBoundingClientRect();
  const rowMid = scrollEl.scrollTop + (rowRect.top - scrollRect.top) + rowRect.height / 2;
  return Math.max(0, rowMid - scrollEl.clientHeight / 2);
}

/** Scroll offset to center spot on the strike canvas (px from top of scroll content). */
export function computeSpotScrollTop(
  viewportHeight: number,
  canvasHeight: number,
  spotPct: number,
): number {
  if (viewportHeight <= 0 || canvasHeight <= 0) return 0;
  const spotY = (spotPct / 100) * canvasHeight;
  return Math.max(0, spotY - viewportHeight / 2);
}

export function scrollHeatmapToSpot(
  scrollEl: HTMLElement,
  canvasEl: HTMLElement,
  spot: number,
  rows: HeatmapRow[],
): void {
  const sorted = sortedHeatmapRows(rows);
  const pct = spotTopPct(sorted, spot);
  if (pct == null) return;

  const nearest = nearestStrikeToSpot(sorted, spot);
  const rowEl =
    nearest != null
      ? canvasEl.querySelector<HTMLElement>(`[data-strike="${formatStrikeAttr(nearest)}"]`)
      : null;

  const target =
    rowEl && rowEl.offsetHeight > 0
      ? rowScrollTop(scrollEl, rowEl)
      : computeSpotScrollTop(scrollEl.clientHeight, canvasEl.offsetHeight, pct);

  scrollEl.scrollTo({
    top: target,
    behavior: "auto",
  });
}

export function heatClass(intensity: number, sign: number): string {
  if (intensity >= 0.82) return sign >= 0 ? "heat-pos-max" : "heat-neg-max";
  if (intensity >= 0.55) return sign >= 0 ? "heat-pos-high" : "heat-neg-high";
  return sign >= 0 ? "heat-pos" : "heat-neg";
}

export function vexHeatClass(intensity: number, sign: number): string {
  if (intensity >= 0.82) return sign >= 0 ? "heat-vex-pos-max" : "heat-vex-neg-max";
  if (intensity >= 0.55) return sign >= 0 ? "heat-vex-pos-high" : "heat-vex-neg-high";
  return sign >= 0 ? "heat-vex-pos" : "heat-vex-neg";
}

export function compareDivergence(
  gexVal: number,
  vexVal: number,
  maxGex: number,
  maxVex: number,
): boolean {
  const gi = Math.abs(gexVal) / maxGex;
  const vi = Math.abs(vexVal) / maxVex;
  if (gi < 0.35 || vi < 0.35) return false;
  return Math.sign(gexVal) !== Math.sign(vexVal);
}

export type LevelTag = { text: string; cls: string };

export function levelTags(strike: number, levels: Levels | null | undefined): LevelTag[] {
  if (!levels) return [];
  const tags: LevelTag[] = [];
  if (near(strike, levels.king)) tags.push({ text: "KING", cls: "tag-king" });
  if (near(strike, levels.flip)) tags.push({ text: "FLIP", cls: "tag-flip" });
  if (near(strike, levels.call_wall)) tags.push({ text: "C-WALL", cls: "tag-call" });
  if (near(strike, levels.put_wall)) tags.push({ text: "P-WALL", cls: "tag-put" });
  if (near(strike, levels.max_pain)) tags.push({ text: "MAX-P", cls: "tag-pain" });
  return tags;
}

export const HEATMAP_TITLES = {
  gex: "Strike Plot · GEX",
  vex: "Strike Plot · VEX",
  compare: "Strike Plot · GEX + VEX",
} as const;

export const TRINITY_ORDER = [
  { key: "SPX", label: "SPXW" },
  { key: "SPY", label: "SPY" },
  { key: "QQQ", label: "QQQ" },
] as const;

export function heatmapRowTitle(
  row: HeatmapRow,
  spot: number,
  metric: ExposureMetric,
): string {
  const dist = spot > 0 ? ((row.strike - spot) / spot) * 100 : NaN;
  const distStr = Number.isFinite(dist) ? `${dist >= 0 ? "+" : ""}${dist.toFixed(2)}% vs spot` : "";
  const gex = row.net_gex;
  const vex = row.net_vex;
  const parts = [`Strike ${row.strike}`, distStr];
  if (metric === "vex" && vex != null) {
    parts.push(`VEX ${formatCompact(vex)}`);
  } else {
    parts.push(`GEX ${formatCompact(gex)}`);
  }
  if (row.total_oi != null && row.total_oi > 0) {
    parts.push(`OI ${Math.round(row.total_oi).toLocaleString()}`);
  }
  const roc = metric === "vex" ? row.roc_pct_vex : row.roc_pct;
  if (roc != null && Math.abs(roc) >= 20) {
    parts.push(`ROC ${roc >= 0 ? "+" : ""}${Math.round(roc)}%`);
  }
  return parts.filter(Boolean).join(" · ");
}

function formatCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}
