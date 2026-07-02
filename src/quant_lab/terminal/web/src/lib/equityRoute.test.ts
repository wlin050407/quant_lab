import { describe, expect, it } from "vitest";

import { buildEquityStockHash, parseEquityTickerFromHash } from "./equityRoute";

describe("parseEquityTickerFromHash", () => {
  it("reads ticker query param", () => {
    expect(parseEquityTickerFromHash("#/stock?ticker=IBM")).toBe("IBM");
    expect(parseEquityTickerFromHash("#/stock?ticker=AAPL")).toBe("AAPL");
  });

  it("supports legacy t param", () => {
    expect(parseEquityTickerFromHash("#/stock?t=IBM")).toBe("IBM");
  });

  it("reads path segment after stock", () => {
    expect(parseEquityTickerFromHash("#/stock/IBM")).toBe("IBM");
    expect(parseEquityTickerFromHash("#/stock/ge")).toBe("GE");
  });

  it("defaults when route has no ticker", () => {
    expect(parseEquityTickerFromHash("#/stock")).toBe("AAPL");
    expect(parseEquityTickerFromHash("#/")).toBe("AAPL");
  });

  it("prefers path over query when both present", () => {
    expect(parseEquityTickerFromHash("#/stock/IBM?ticker=MSFT")).toBe("IBM");
  });
});

describe("buildEquityStockHash", () => {
  it("uses ticker param", () => {
    expect(buildEquityStockHash("ibm")).toBe("#/stock?ticker=IBM");
  });
});
