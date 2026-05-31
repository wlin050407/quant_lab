import type { DatesResponse, DashboardSnapshot } from "../types/snapshot";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(await res.text());
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
