import { describe, expect, it } from "vitest";
import {
  computeSpotScrollTop,
  formatStrikeAttr,
  isNearestSpotStrike,
  nearestStrikeToSpot,
  spotTopPct,
} from "./heatmap";
import type { HeatmapRow } from "../types/snapshot";

function row(strike: number): HeatmapRow {
  return { strike, net_gex: 0, net_vex: null, roc_pct: null, roc_pct_vex: null };
}

describe("nearestStrikeToSpot", () => {
  it("picks closest strike when spot is between $1 steps", () => {
    const rows = [row(445), row(444), row(443), row(442)];
    expect(nearestStrikeToSpot(rows, 443.72)).toBe(444);
    expect(nearestStrikeToSpot(rows, 443.27)).toBe(443);
  });

  it("marks nearest row even when spot is far from exact strike", () => {
    const rows = [row(450), row(445), row(440)];
    expect(isNearestSpotStrike(445, 447.2, rows)).toBe(true);
    expect(isNearestSpotStrike(450, 447.2, rows)).toBe(false);
  });
});

describe("computeSpotScrollTop", () => {
  it("centers spot line in viewport", () => {
    const pct = spotTopPct([row(450), row(445), row(440)], 447.2);
    expect(pct).not.toBeNull();
    const top = computeSpotScrollTop(400, 800, pct!);
    expect(top).toBeCloseTo((pct! / 100) * 800 - 200, 5);
  });
});

describe("formatStrikeAttr", () => {
  it("formats strike attrs without float drift", () => {
    expect(formatStrikeAttr(380)).toBe("380");
    expect(formatStrikeAttr(380.5)).toBe("380.5");
  });
});
