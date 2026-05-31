import { describe, expect, it } from "vitest";

import { buildExposureProfileModel, exposurePoints, EXPOSURE_COMPACT_BAR_W, EXPOSURE_VIEW_W } from "./exposureProfile";
import type { HeatmapRow } from "../types/snapshot";

const ROWS: HeatmapRow[] = [
  { strike: 4400, net_gex: -2e10, net_gex_bn: -0.2, net_vex: null, roc_pct: null, roc_pct_vex: null },
  { strike: 4500, net_gex: 3e10, net_gex_bn: 0.3, net_vex: null, roc_pct: null, roc_pct_vex: null },
];

describe("exposureProfile", () => {
  it("uses net_gex_bn for gex profile", () => {
    const pts = exposurePoints(ROWS, "gex");
    expect(pts[1].valueBn).toBe(0.3);
  });

  it("uses fewer x ticks in compact mode", () => {
    const full = buildExposureProfileModel(ROWS, "gex", 4500, null);
    const compact = buildExposureProfileModel(ROWS, "gex", 4500, null, { compact: true });
    expect(full?.xTicks.length).toBe(2);
    expect(compact?.xTicks.length).toBe(2);
    expect(compact?.yTicks[0].label).toBe("+0.3");
  });

  it("builds strike-axis model with spot marker", () => {
    const model = buildExposureProfileModel(ROWS, "gex", 4500, { flip: 4480, king: 4500 });
    expect(model?.spotX).not.toBeNull();
    expect(model?.bars.length).toBe(2);
    expect(model?.peakStrike).toBe(4500);
    expect(model?.bars.some((b) => b.isSpot)).toBe(true);
  });

  it("uses scrollable wide canvas in compact mode", () => {
    const rows: HeatmapRow[] = Array.from({ length: 96 }, (_, i) => ({
      strike: 4400 + i * 5,
      net_gex: 1e10,
      net_gex_bn: 0.1,
      net_vex: null,
      roc_pct: null,
      roc_pct_vex: null,
    }));
    const compact = buildExposureProfileModel(rows, "gex", 4500, null, { compact: true });
    expect(compact?.scrollable).toBe(true);
    expect(compact!.viewW).toBeGreaterThan(EXPOSURE_VIEW_W);
    expect(compact!.bars[0].w).toBe(EXPOSURE_COMPACT_BAR_W);
  });
});
