import type { EquityAnalyzeResponse, HorizonVerdict } from "../types/equity";
import { fmtMoney, fmtPct } from "./format";

export interface SessionStats {
  open: number;
  high: number;
  low: number;
  close: number;
  change: number;
  changePct: number;
  volume: number;
}

export function sessionStatsFromBars(
  bars: EquityAnalyzeResponse["chart"]["bars"],
): SessionStats | null {
  if (!bars.length) return null;
  const first = bars[0]!;
  const last = bars[bars.length - 1]!;
  if (!Number.isFinite(first.o) || !Number.isFinite(last.c)) return null;
  const high = Math.max(...bars.map((b) => b.h).filter(Number.isFinite));
  const low = Math.min(...bars.map((b) => b.l).filter(Number.isFinite));
  const volume = bars.reduce((sum, b) => sum + (Number.isFinite(b.v) ? b.v : 0), 0);
  const change = last.c - first.o;
  const changePct = first.o !== 0 ? (change / first.o) * 100 : 0;
  return { open: first.o, high, low, close: last.c, change, changePct, volume };
}

export function horizonEntries(
  horizons: EquityAnalyzeResponse["horizons"],
): Array<{ key: "short" | "mid" | "long"; verdict: HorizonVerdict }> {
  return [
    { key: "short", verdict: horizons.short },
    { key: "mid", verdict: horizons.mid },
    { key: "long", verdict: horizons.long },
  ];
}

export function sourceBadge(source: string): { label: string; quality: "live" | "delayed" | "na" } {
  if (source === "thetadata") return { label: "ThetaData", quality: "live" };
  if (source === "yfinance") return { label: "yfinance", quality: "delayed" };
  if (source === "unavailable") return { label: "N/A", quality: "na" };
  return { label: source, quality: "delayed" };
}

export function distFromSpot(spot: number, level: number | null | undefined): string | null {
  if (level == null || !Number.isFinite(level) || !Number.isFinite(spot) || spot === 0) return null;
  return fmtPct(((level - spot) / spot) * 100);
}

export function formatAdv(adv: number | undefined): string {
  if (adv == null || !Number.isFinite(adv)) return "—";
  return fmtMoney(adv);
}

export function formatRs(v: number | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return fmtPct(v);
}

export function maVsSpot(spot: number, ma: number | undefined): "above" | "below" | "unknown" {
  if (ma == null || !Number.isFinite(ma) || !Number.isFinite(spot)) return "unknown";
  return spot >= ma ? "above" : "below";
}

export function formatVolumeShares(v: number): string {
  if (!Number.isFinite(v)) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}
