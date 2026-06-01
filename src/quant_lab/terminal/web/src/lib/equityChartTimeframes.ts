import type { EquityAnalyzeResponse } from "../types/equity";

export type ChartTimeframe = "5m" | "5d" | "1d" | "1w" | "1m" | "1y";

export interface OhlcBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface ChartOverlayConfig {
  showVwap: boolean;
  showPoc: boolean;
  showMa: boolean;
  showBenchmark: boolean;
}

export interface ChartStats {
  high52w: number | null;
  low52w: number | null;
  avgVol20d: number | null;
}

function validBar(b: OhlcBar): boolean {
  return Number.isFinite(b.o) && Number.isFinite(b.h) && Number.isFinite(b.l) && Number.isFinite(b.c);
}

function bucketWeek(isoDate: string): string {
  const d = new Date(`${isoDate.slice(0, 10)}T12:00:00Z`);
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

function bucketMonth(isoDate: string): string {
  return isoDate.slice(0, 7);
}

function bucketYear(isoDate: string): string {
  return isoDate.slice(0, 4);
}

function aggregateBars(bars: OhlcBar[], bucketFn: (t: string) => string): OhlcBar[] {
  const groups = new Map<string, OhlcBar[]>();
  for (const b of bars.filter(validBar)) {
    const key = bucketFn(b.t);
    const list = groups.get(key) ?? [];
    list.push(b);
    groups.set(key, list);
  }
  const out: OhlcBar[] = [];
  for (const [, group] of groups) {
    const sorted = [...group].sort((a, b) => a.t.localeCompare(b.t));
    const first = sorted[0]!;
    const last = sorted[sorted.length - 1]!;
    out.push({
      t: last.t.slice(0, 10),
      o: first.o,
      h: Math.max(...sorted.map((x) => x.h)),
      l: Math.min(...sorted.map((x) => x.l)),
      c: last.c,
      v: sorted.reduce((s, x) => s + (Number.isFinite(x.v) ? x.v : 0), 0),
    });
  }
  return out.sort((a, b) => a.t.localeCompare(b.t));
}

export function hasDailyChartData(data: EquityAnalyzeResponse): boolean {
  return (data.chart.daily_bars ?? []).some(validBar);
}

export function availableTimeframes(data: EquityAnalyzeResponse): ChartTimeframe[] {
  const out: ChartTimeframe[] = [];
  if (data.chart.bars.some(validBar)) out.push("5m");
  const multi =
    (data.chart.bars_5d ?? []).filter(validBar).length > 1
      ? data.chart.bars_5d!
      : data.chart.bars;
  if (multi.filter(validBar).length > 0) out.push("5d");
  if (hasDailyChartData(data)) out.push("1d", "1w", "1m", "1y");
  return out.length ? out : ["5m"];
}

/** Prefer daily context on open; fall back to intraday when daily is unavailable. */
export function defaultChartTimeframe(data: EquityAnalyzeResponse): ChartTimeframe {
  const available = availableTimeframes(data);
  if (available.includes("1d")) return "1d";
  return available[0] ?? "5m";
}

export function resolveChartBars(data: EquityAnalyzeResponse, timeframe: ChartTimeframe): OhlcBar[] {
  const chart = data.chart;
  const session = chart.bars.filter(validBar);
  const multi5d = (chart.bars_5d ?? []).filter(validBar);
  const daily = (chart.daily_bars ?? []).filter(validBar);

  switch (timeframe) {
    case "5m":
      return session;
    case "5d":
      return multi5d.length > 1 ? multi5d : session;
    case "1d":
      return daily.slice(-252);
    case "1w":
      return aggregateBars(daily, bucketWeek).slice(-104);
    case "1m":
      return aggregateBars(daily, bucketMonth).slice(-60);
    case "1y":
      return aggregateBars(daily, bucketYear).slice(-20);
    default:
      return session;
  }
}

function resolveDailySource(data: EquityAnalyzeResponse, timeframe: ChartTimeframe): OhlcBar[] {
  const daily = (data.chart.daily_bars ?? []).filter(validBar);
  switch (timeframe) {
    case "1d":
      return daily.slice(-252);
    case "1w":
      return aggregateBars(daily, bucketWeek).slice(-104);
    case "1m":
      return aggregateBars(daily, bucketMonth).slice(-60);
    case "1y":
      return aggregateBars(daily, bucketYear).slice(-20);
    default:
      return daily;
  }
}

export function resolveBenchmarkBars(data: EquityAnalyzeResponse, timeframe: ChartTimeframe): OhlcBar[] {
  const bench = (data.chart.benchmark_daily_bars ?? []).filter(validBar);
  if (!bench.length || isIntradayTimeframe(timeframe)) return [];
  const proxy: EquityAnalyzeResponse = {
    ...data,
    chart: { ...data.chart, daily_bars: bench },
  };
  return resolveDailySource(proxy, timeframe);
}

export function alignBenchmarkOverlay(
  tickerBars: OhlcBar[],
  benchmarkBars: OhlcBar[],
): Array<{ t: string; v: number }> {
  if (!tickerBars.length || !benchmarkBars.length) return [];
  const benchByDate = new Map(benchmarkBars.map((b) => [b.t.slice(0, 10), b.c]));
  let benchStart: number | null = null;
  for (const bar of tickerBars) {
    const px = benchByDate.get(bar.t.slice(0, 10));
    if (px != null && Number.isFinite(px)) {
      benchStart = px;
      break;
    }
  }
  const tickerStart = tickerBars[0]?.c;
  if (benchStart == null || !Number.isFinite(tickerStart) || benchStart === 0) return [];
  const scale = tickerStart / benchStart;
  const out: Array<{ t: string; v: number }> = [];
  for (const bar of tickerBars) {
    const px = benchByDate.get(bar.t.slice(0, 10));
    if (px == null || !Number.isFinite(px)) continue;
    out.push({ t: bar.t, v: px * scale });
  }
  return out;
}

export function overlayConfigForTimeframe(timeframe: ChartTimeframe): ChartOverlayConfig {
  if (timeframe === "5m") {
    return { showVwap: true, showPoc: true, showMa: false, showBenchmark: false };
  }
  if (timeframe === "5d") {
    return { showVwap: false, showPoc: false, showMa: false, showBenchmark: false };
  }
  return { showVwap: false, showPoc: false, showMa: true, showBenchmark: true };
}

export function isIntradayTimeframe(timeframe: ChartTimeframe): boolean {
  return timeframe === "5m" || timeframe === "5d";
}

export function prepareBarsForChart(bars: OhlcBar[], intraday: boolean): OhlcBar[] {
  const sorted = [...bars.filter(validBar)].sort((a, b) => a.t.localeCompare(b.t));
  const seen = new Set<string>();
  const out: OhlcBar[] = [];
  for (const bar of sorted) {
    const key = intraday ? bar.t : bar.t.slice(0, 10);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(intraday ? bar : { ...bar, t: bar.t.slice(0, 10) });
  }
  // Collapse overnight / session gaps so 5D intraday does not leave huge empty bands.
  if (intraday && out.length > 0) {
    const baseSec = Math.floor(new Date(out[0]!.t).getTime() / 1000);
    const stepSec = 300;
    return out.map((b, i) => ({
      ...b,
      t: new Date((baseSec + i * stepSec) * 1000).toISOString(),
    }));
  }
  return out;
}

export interface ChartScaleConfig {
  barSpacing: number;
  minBarSpacing: number;
  rightOffset: number;
  /** Narrowest zoom window (bars visible). */
  minVisibleBars: number;
}

export function chartScaleForTimeframe(timeframe: ChartTimeframe, barCount: number): ChartScaleConfig {
  const n = Math.max(1, barCount);
  switch (timeframe) {
    case "5m":
      return {
        barSpacing: 10,
        minBarSpacing: 7,
        rightOffset: 3,
        minVisibleBars: Math.min(24, n),
      };
    case "5d":
      return {
        barSpacing: 5,
        minBarSpacing: 3,
        rightOffset: 3,
        minVisibleBars: Math.min(48, n),
      };
    case "1d":
      return {
        barSpacing: 8,
        minBarSpacing: 4,
        rightOffset: 3,
        minVisibleBars: Math.min(40, n),
      };
    case "1w":
      return {
        barSpacing: 9,
        minBarSpacing: 5,
        rightOffset: 2,
        minVisibleBars: Math.min(26, n),
      };
    case "1m":
      return {
        barSpacing: 10,
        minBarSpacing: 6,
        rightOffset: 2,
        minVisibleBars: Math.min(18, n),
      };
    case "1y":
      return {
        barSpacing: 12,
        minBarSpacing: 8,
        rightOffset: 1,
        minVisibleBars: Math.min(10, n),
      };
    default:
      return {
        barSpacing: 9,
        minBarSpacing: 5,
        rightOffset: 3,
        minVisibleBars: Math.min(30, n),
      };
  }
}

/** Initial view: full series, small right margin only — no empty left gutter. */
export function defaultVisibleLogicalRange(barCount: number, rightOffset: number): { from: number; to: number } {
  const last = Math.max(0, barCount - 1);
  return { from: 0, to: last + rightOffset };
}

export interface LogicalRange {
  from: number;
  to: number;
}

/** Keep pan/zoom inside [0 .. lastBar + rightPad]; block empty margins. */
export function clampVisibleLogicalRange(
  range: LogicalRange,
  barCount: number,
  scale: ChartScaleConfig,
): LogicalRange | null {
  if (barCount <= 0) return null;
  const last = barCount - 1;
  const maxTo = last + scale.rightOffset;
  const minFrom = 0;
  const maxWidth = maxTo - minFrom;
  const minWidth = Math.min(scale.minVisibleBars, maxWidth + 0.001);

  let from = range.from;
  let to = range.to;
  let width = to - from;

  if (width < minWidth) {
    const center = (from + to) / 2;
    width = minWidth;
    from = center - width / 2;
    to = center + width / 2;
  }

  if (width > maxWidth) {
    from = minFrom;
    to = maxTo;
  } else {
    if (from < minFrom) {
      to += minFrom - from;
      from = minFrom;
    }
    if (to > maxTo) {
      from -= to - maxTo;
      to = maxTo;
    }
    if (from < minFrom) {
      from = minFrom;
    }
  }

  if (Math.abs(from - range.from) < 0.001 && Math.abs(to - range.to) < 0.001) {
    return null;
  }
  return { from, to };
}

export function computeSmaSeries(bars: OhlcBar[], period: number): Array<{ t: string; v: number }> {
  const out: Array<{ t: string; v: number }> = [];
  for (let i = 0; i < bars.length; i++) {
    if (i + 1 < period) continue;
    const slice = bars.slice(i + 1 - period, i + 1);
    const avg = slice.reduce((s, b) => s + b.c, 0) / period;
    out.push({ t: bars[i]!.t, v: avg });
  }
  return out;
}

export function computeChartStats(data: EquityAnalyzeResponse): ChartStats {
  const daily = (data.chart.daily_bars ?? []).filter(validBar);
  const window = daily.slice(-252);
  if (!window.length) {
    return { high52w: null, low52w: null, avgVol20d: null };
  }
  const high52w = Math.max(...window.map((b) => b.h));
  const low52w = Math.min(...window.map((b) => b.l));
  const vol20 = daily.slice(-20);
  const avgVol20d =
    vol20.length > 0 ? vol20.reduce((s, b) => s + (Number.isFinite(b.v) ? b.v : 0), 0) / vol20.length : null;
  return { high52w, low52w, avgVol20d };
}

export const TIMEFRAME_ORDER: ChartTimeframe[] = ["5m", "5d", "1d", "1w", "1m", "1y"];
