import { describe, expect, it } from "vitest";

import { vendorGuideLines } from "./heatmap";
import { gateDetail, resonanceTierClass, resonanceTierLabel } from "./resonance";
import type { HeatmapRow } from "../types/snapshot";

describe("resonanceTierClass", () => {
  it("maps tiers to css classes", () => {
    expect(resonanceTierClass("high")).toBe("resonance-tier--high");
    expect(resonanceTierLabel("medium")).toBe("MED");
  });
});

describe("gateDetail", () => {
  it("explains resonance gate block", () => {
    const msg = gateDetail({
      should_trade: false,
      reason: "low_resonance",
      base_should_trade: true,
      base_reason: "ok",
    });
    expect(msg).toContain("blocked");
  });
});

describe("vendorGuideLines", () => {
  const rows: HeatmapRow[] = [
    { strike: 7140, net_gex: 1, net_vex: 0, roc_pct: null, roc_pct_vex: null },
    { strike: 7130, net_gex: 1, net_vex: 0, roc_pct: null, roc_pct_vex: null },
    { strike: 7120, net_gex: 1, net_vex: 0, roc_pct: null, roc_pct_vex: null },
  ];

  it("returns guides for vendor levels inside strike range", () => {
    const guides = vendorGuideLines(rows, {
      zero_gamma: 7125,
      major_pos_oi: 7135,
      major_neg_oi: 7115,
    });
    expect(guides.length).toBe(3);
    expect(guides[0]?.cls).toContain("vendor-guide");
  });
});
