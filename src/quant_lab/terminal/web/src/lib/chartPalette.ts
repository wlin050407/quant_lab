/** Shared chart palette — reads CSS variables so light/dark themes stay in sync. */

function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function cssVarFloat(name: string, fallback: number): number {
  const raw = cssVar(name, String(fallback));
  const parsed = parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function getChartPalette() {
  const pos = cssVar("--chart-gex-pos", "#a3c95a");
  const posMid = cssVar("--chart-gex-pos-mid", "#8fb340");
  const posSoft = cssVar("--chart-gex-pos-soft", "#c4d96e");
  const neg = cssVar("--chart-gex-neg", "#9b8fd4");
  const negMid = cssVar("--chart-gex-neg-mid", "#8578c4");
  const negSoft = cssVar("--chart-gex-neg-soft", "#b8a8e0");
  const gammaPosTopOpacity = cssVarFloat("--chart-gamma-pos-opacity-top", 0.28);
  const gammaPosBaseOpacity = cssVarFloat("--chart-gamma-pos-opacity-base", 0.04);
  const gammaNegTopOpacity = cssVarFloat("--chart-gamma-neg-opacity-top", 0.24);
  const gammaNegBaseOpacity = cssVarFloat("--chart-gamma-neg-opacity-base", 0.04);

  return {
    CHART_GEX_POS: pos,
    CHART_GEX_POS_MID: posMid,
    CHART_GEX_POS_SOFT: posSoft,
    CHART_GEX_NEG: neg,
    CHART_GEX_NEG_MID: negMid,
    CHART_GEX_NEG_SOFT: negSoft,
    CHART_LINE: cssVar("--chart-line", "rgba(226, 232, 240, 0.68)"),
    CHART_GRID: cssVar("--chart-grid", "rgba(148, 163, 184, 0.14)"),
    CHART_ZERO: cssVar("--chart-zero", "rgba(148, 163, 184, 0.22)"),
    CHART_AREA_POS: {
      top: { color: posSoft, opacity: 0.32 },
      mid: { color: pos, opacity: 0.14 },
      base: { color: posMid, opacity: 0.03 },
    },
    CHART_AREA_NEG: {
      top: { color: negSoft, opacity: 0.28 },
      mid: { color: neg, opacity: 0.12 },
      base: { color: negMid, opacity: 0.03 },
    },
    CHART_BAR_POS: {
      top: posSoft,
      bottom: posMid,
      bottomOpacity: 0.62,
    },
    CHART_BAR_NEG: {
      top: negSoft,
      bottom: negMid,
      bottomOpacity: 0.62,
    },
    CHART_GAMMA_FILL_POS: {
      top: { color: pos, opacity: gammaPosTopOpacity },
      base: { color: posMid, opacity: gammaPosBaseOpacity },
    },
    CHART_GAMMA_FILL_NEG: {
      top: { color: neg, opacity: gammaNegTopOpacity },
      base: { color: negMid, opacity: gammaNegBaseOpacity },
    },
  } as const;
}

/** @deprecated use getChartPalette() — kept for type re-exports in tests */
export const CHART_GEX_POS = "#a3c95a";
