/** Hash routing helpers for `#/stock` equity workspace. */

const DEFAULT_TICKER = "AAPL";

/**
 * Read ticker from `#/stock?ticker=IBM`, legacy `#/stock?t=IBM`, or `#/stock/IBM`.
 * Prefer `ticker` over `t` — single-letter `t` is stripped by some privacy extensions.
 */
export function parseEquityTickerFromHash(hash: string = window.location.hash): string {
  const raw = hash.replace(/^#/, "").replace(/^\//, "");
  const [pathPart, queryPart = ""] = raw.split("?", 2);
  const segments = pathPart.split("/").filter(Boolean);

  if (segments[0] === "stock" && segments.length >= 2) {
    const fromPath = decodeURIComponent(segments[1] ?? "")
      .trim()
      .toUpperCase();
    if (fromPath) {
      return fromPath;
    }
  }

  const params = new URLSearchParams(queryPart);
  const fromQuery = (params.get("ticker") ?? params.get("t") ?? "").trim().toUpperCase();
  if (fromQuery) {
    return fromQuery;
  }

  return DEFAULT_TICKER;
}

export function buildEquityStockHash(ticker: string): string {
  const sym = ticker.trim().toUpperCase();
  if (!sym) {
    return "#/stock";
  }
  return `#/stock?ticker=${encodeURIComponent(sym)}`;
}
