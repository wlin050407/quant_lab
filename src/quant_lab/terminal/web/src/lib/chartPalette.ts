/** Shared chart palette — aligned with terminal --gex-pos / --gex-neg tokens. */

export const CHART_GEX_POS = "#a3c95a";
export const CHART_GEX_POS_MID = "#8fb340";
export const CHART_GEX_POS_SOFT = "#c4d96e";

export const CHART_GEX_NEG = "#9b8fd4";
export const CHART_GEX_NEG_MID = "#8578c4";
export const CHART_GEX_NEG_SOFT = "#b8a8e0";

export const CHART_LINE = "rgba(226, 232, 240, 0.68)";
export const CHART_GRID = "rgba(148, 163, 184, 0.14)";
export const CHART_ZERO = "rgba(148, 163, 184, 0.22)";

export const CHART_AREA_POS = {
  top: { color: CHART_GEX_POS_SOFT, opacity: 0.32 },
  mid: { color: CHART_GEX_POS, opacity: 0.14 },
  base: { color: CHART_GEX_POS_MID, opacity: 0.03 },
} as const;

export const CHART_AREA_NEG = {
  top: { color: CHART_GEX_NEG_SOFT, opacity: 0.28 },
  mid: { color: CHART_GEX_NEG, opacity: 0.12 },
  base: { color: CHART_GEX_NEG_MID, opacity: 0.03 },
} as const;

export const CHART_BAR_POS = {
  top: CHART_GEX_POS_SOFT,
  bottom: CHART_GEX_POS_MID,
  bottomOpacity: 0.62,
} as const;

export const CHART_BAR_NEG = {
  top: CHART_GEX_NEG_SOFT,
  bottom: CHART_GEX_NEG_MID,
  bottomOpacity: 0.62,
} as const;

export const CHART_GAMMA_FILL_POS = {
  top: { color: CHART_GEX_POS, opacity: 0.28 },
  base: { color: CHART_GEX_POS_MID, opacity: 0.04 },
} as const;

export const CHART_GAMMA_FILL_NEG = {
  top: { color: CHART_GEX_NEG, opacity: 0.24 },
  base: { color: CHART_GEX_NEG_MID, opacity: 0.04 },
} as const;
