import { describe, expect, it } from "vitest";

import { buildBandSpotTicks, niceSpotStep } from "./gammaProfileAxis";

describe("niceSpotStep", () => {
  it("picks readable step for SPX ±10% range", () => {
    const range = 7580 * 0.2;
    expect(niceSpotStep(range, 18)).toBeLessThanOrEqual(200);
    expect(niceSpotStep(range, 18)).toBeGreaterThanOrEqual(50);
  });
});

describe("buildBandSpotTicks", () => {
  const minS = 6822;
  const maxS = 8338;
  const spot = 7580;
  const flip = 7610;

  it("includes major, minor, spot, and flip anchors", () => {
    const ticks = buildBandSpotTicks(minS, maxS, spot, flip, false);
    expect(ticks.some((t) => t.kind === "major" && t.showLabel)).toBe(true);
    expect(ticks.some((t) => t.kind === "minor" && !t.showLabel)).toBe(true);
    expect(ticks.find((t) => t.kind === "spot")?.spot).toBe(spot);
    expect(ticks.find((t) => t.kind === "flip")?.spot).toBe(flip);
  });

  it("produces more labeled majors in single than compact mode", () => {
    const single = buildBandSpotTicks(minS, maxS, spot, null, false);
    const compact = buildBandSpotTicks(minS, maxS, spot, null, true);
    const countMajors = (xs: typeof single) => xs.filter((t) => t.kind === "major" && t.showLabel).length;
    expect(countMajors(single)).toBeGreaterThanOrEqual(countMajors(compact));
  });
});
