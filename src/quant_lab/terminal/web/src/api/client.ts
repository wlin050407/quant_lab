import type { DatesResponse, DashboardSnapshot } from "../types/snapshot";
import type { EquityAnalyzeResponse } from "../types/equity";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const raw = await res.text();
    try {
      const parsed = JSON.parse(raw) as { detail?: string | Array<{ msg?: string }> };
      if (typeof parsed.detail === "string") {
        if (res.status === 404 && url.includes("/api/equity/")) {
          throw new Error(
            `${parsed.detail} — restart the terminal server (python scripts/run_terminal.py) after updating.`,
          );
        }
        throw new Error(parsed.detail);
      }
      if (Array.isArray(parsed.detail) && parsed.detail[0]?.msg) {
        throw new Error(parsed.detail[0].msg);
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("restart the terminal")) {
        throw e;
      }
    }
    throw new Error(raw || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function fetchDates(symbol: string): Promise<DatesResponse> {
  return fetchJson(`/api/dates?symbol=${encodeURIComponent(symbol)}`);
}

export function fetchSnapshot(
  symbol: string,
  date: string,
  time?: string,
): Promise<DashboardSnapshot> {
  const params = new URLSearchParams({
    symbol,
    date,
  });
  if (time) {
    params.set("time", time);
  }
  return fetchJson(`/api/snapshot?${params.toString()}`);
}

export function fetchEquityAnalyze(ticker: string, refresh = false): Promise<EquityAnalyzeResponse> {
  const params = new URLSearchParams({ ticker: ticker.trim().toUpperCase() });
  if (refresh) params.set("refresh", "1");
  return fetchJson(`/api/equity/analyze?${params.toString()}`);
}
