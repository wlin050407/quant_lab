import { describe, expect, it } from "vitest";

import {
  DEMO_SPX_SESSION,
  isDemoSessionInDates,
  isLiveSnapshotSource,
  isLocalDevHost,
} from "./terminalDeploy";

describe("terminalDeploy", () => {
  it("detects local dev hosts", () => {
    expect(isLocalDevHost("localhost")).toBe(true);
    expect(isLocalDevHost("127.0.0.1")).toBe(true);
    expect(isLocalDevHost("quantlab-terminal-production.up.railway.app")).toBe(false);
  });

  it("recognizes vendor and thetadata live sources", () => {
    expect(isLiveSnapshotSource("vendor_live")).toBe(true);
    expect(isLiveSnapshotSource("thetadata_live")).toBe(true);
    expect(isLiveSnapshotSource("vendor", true)).toBe(true);
    expect(isLiveSnapshotSource("vendor")).toBe(false);
  });

  it("demo availability follows ^SPX date list", () => {
    expect(isDemoSessionInDates([DEMO_SPX_SESSION.date])).toBe(true);
    expect(isDemoSessionInDates(["2026-07-01"])).toBe(false);
  });
});
