import { useEffect, useMemo, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { ThemeMode } from "../lib/theme";
import { useLocale } from "../hooks/useLocale";
import { getEquityStrings } from "../lib/i18n/equityStrings";
import {
  chartScaleForTimeframe,
  clampVisibleLogicalRange,
  computeSmaSeries,
  defaultVisibleLogicalRange,
  isIntradayTimeframe,
  prepareBarsForChart,
  type ChartOverlayConfig,
  type ChartTimeframe,
  type OhlcBar,
} from "../lib/equityChartTimeframes";

interface EquityPriceChartProps {
  bars: OhlcBar[];
  timeframe: ChartTimeframe;
  overlays: ChartOverlayConfig;
  vwap: number;
  poc: number;
  benchmarkOverlay: Array<{ t: string; v: number }>;
  benchmarkLabel: string;
  theme: ThemeMode;
  ticker: string;
}

function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function toChartTime(iso: string, intraday: boolean): Time {
  if (intraday) {
    return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
  }
  return iso.slice(0, 10);
}

function chartColors(theme: ThemeMode) {
  const dark = theme === "dark";
  return {
    text: cssVar("--text-muted", dark ? "#94a3b8" : "#64748b"),
    grid: cssVar("--chart-grid", dark ? "rgba(148,163,184,0.12)" : "#e2e8f0"),
    border: cssVar("--border-subtle", dark ? "#1a2438" : "#e2e8f0"),
    up: cssVar("--long", "#4ade80"),
    down: cssVar("--put", "#fb7185"),
    vwap: cssVar("--flip", "#2dd4bf"),
    poc: cssVar("--king", "#f59e0b"),
    ma20: cssVar("--call", "#38bdf8"),
    ma50: cssVar("--short", "#fbbf24"),
    ma200: cssVar("--put", "#fb7185"),
    benchmark: cssVar("--text-dim", "#94a3b8"),
    crosshair: cssVar("--text-dim", "#64748b"),
  };
}

const MIN_CHART_PX = 24;

export function EquityPriceChart({
  bars,
  timeframe,
  overlays,
  vwap,
  poc,
  benchmarkOverlay,
  benchmarkLabel,
  theme,
  ticker,
}: EquityPriceChartProps) {
  const s = getEquityStrings(useLocale().locale);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const cleanBars = useMemo(
    () => prepareBarsForChart(bars, isIntradayTimeframe(timeframe)),
    [bars, timeframe],
  );
  const scale = useMemo(
    () => chartScaleForTimeframe(timeframe, cleanBars.length),
    [timeframe, cleanBars.length],
  );
  const intraday = isIntradayTimeframe(timeframe);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !cleanBars.length) return;

    let chart: IChartApi | null = null;
    let disposed = false;
    let clamping = false;
    const barCount = cleanBars.length;
    const colors = chartColors(theme);

    const applyViewportClamp = (): void => {
      if (!chart || clamping) return;
      const range = chart.timeScale().getVisibleLogicalRange();
      if (!range) return;
      const next = clampVisibleLogicalRange(range, barCount, scale);
      if (!next) return;
      clamping = true;
      chart.timeScale().setVisibleLogicalRange(next);
      clamping = false;
    };

    const buildChart = (): void => {
      if (disposed) return;
      const width = el.clientWidth;
      const height = el.clientHeight;
      if (width < MIN_CHART_PX || height < MIN_CHART_PX) return;

      if (!chart) {
        chart = createChart(el, {
          width,
          height,
          layout: {
            background: { type: ColorType.Solid, color: "transparent" },
            textColor: colors.text,
            fontFamily: 'var(--mono), "IBM Plex Sans SC", ui-monospace, monospace',
            fontSize: 11,
          },
          grid: {
            vertLines: { color: colors.grid },
            horzLines: { color: colors.grid },
          },
          crosshair: {
            mode: CrosshairMode.Normal,
            vertLine: { color: colors.crosshair, labelBackgroundColor: colors.border },
            horzLine: { color: colors.crosshair, labelBackgroundColor: colors.border },
          },
          rightPriceScale: {
            borderColor: colors.border,
            scaleMargins: { top: 0.08, bottom: 0.22 },
            autoScale: true,
          },
          timeScale: {
            borderColor: colors.border,
            timeVisible: intraday,
            secondsVisible: false,
            barSpacing: scale.barSpacing,
            minBarSpacing: scale.minBarSpacing,
            rightOffset: scale.rightOffset,
            fixLeftEdge: true,
            fixRightEdge: true,
          },
          handleScroll: {
            mouseWheel: true,
            pressedMouseMove: true,
            horzTouchDrag: true,
          },
          handleScale: {
            axisPressedMouseMove: { time: true, price: true },
            axisDoubleClickReset: { time: true, price: true },
            mouseWheel: true,
            pinch: true,
          },
        });

        const candles = chart.addCandlestickSeries({
          upColor: colors.up,
          downColor: colors.down,
          borderUpColor: colors.up,
          borderDownColor: colors.down,
          wickUpColor: colors.up,
          wickDownColor: colors.down,
        });

        const volume = chart.addHistogramSeries({
          priceFormat: { type: "volume" },
          priceScaleId: "volume",
        });
        chart.priceScale("volume").applyOptions({
          scaleMargins: { top: 0.82, bottom: 0 },
        });

        const candleData: CandlestickData[] = cleanBars.map((b) => ({
          time: toChartTime(b.t, intraday),
          open: b.o,
          high: b.h,
          low: b.l,
          close: b.c,
        }));

        const volumeData: HistogramData[] = cleanBars.map((b) => ({
          time: toChartTime(b.t, intraday),
          value: b.v,
          color: b.c >= b.o ? `${colors.up}99` : `${colors.down}99`,
        }));

        candles.setData(candleData);
        volume.setData(volumeData);

        if (overlays.showVwap && Number.isFinite(vwap)) {
          const vwapLine = chart.addLineSeries({
            color: colors.vwap,
            lineWidth: 2,
            lineStyle: 2,
            title: s.chart.vwap,
            priceLineVisible: false,
            lastValueVisible: true,
          });
          vwapLine.setData(
            cleanBars.map(
              (b): LineData => ({
                time: toChartTime(b.t, intraday),
                value: vwap,
              }),
            ),
          );
        }

        if (overlays.showPoc && Number.isFinite(poc)) {
          candles.createPriceLine({
            price: poc,
            color: colors.poc,
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: s.chart.poc,
          });
        }

        if (overlays.showMa) {
          const addMa = (period: number, color: string, title: string) => {
            const series = computeSmaSeries(cleanBars, period);
            if (series.length < 2) return;
            const line = chart!.addLineSeries({
              color,
              lineWidth: 1,
              title,
              priceLineVisible: false,
              lastValueVisible: true,
            });
            line.setData(
              series.map(
                (p): LineData => ({
                  time: toChartTime(p.t, intraday),
                  value: p.v,
                }),
              ),
            );
          };
          addMa(20, colors.ma20, s.fields.ma20);
          addMa(50, colors.ma50, s.fields.ma50);
          addMa(200, colors.ma200, s.fields.ma200);
        }

        if (overlays.showBenchmark && benchmarkOverlay.length >= 2) {
          const benchLine = chart.addLineSeries({
            color: colors.benchmark,
            lineWidth: 1,
            lineStyle: 2,
            title: benchmarkLabel,
            priceLineVisible: false,
            lastValueVisible: true,
          });
          benchLine.setData(
            benchmarkOverlay.map(
              (p): LineData => ({
                time: toChartTime(p.t, intraday),
                value: p.v,
              }),
            ),
          );
        }

        chart.timeScale().setVisibleLogicalRange(defaultVisibleLogicalRange(barCount, scale.rightOffset));

        chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
          applyViewportClamp();
        });

        chartRef.current = chart;
      } else {
        chart.applyOptions({ width, height });
        chart.timeScale().applyOptions({
          barSpacing: scale.barSpacing,
          minBarSpacing: scale.minBarSpacing,
          rightOffset: scale.rightOffset,
        });
        applyViewportClamp();
      }
    };

    const ro = new ResizeObserver(() => buildChart());
    ro.observe(el);
    buildChart();

    return () => {
      disposed = true;
      ro.disconnect();
      chart?.remove();
      chartRef.current = null;
    };
  }, [
    benchmarkLabel,
    benchmarkOverlay,
    cleanBars,
    intraday,
    overlays,
    poc,
    s.chart.poc,
    s.chart.vwap,
    s.fields.ma20,
    s.fields.ma50,
    s.fields.ma200,
    scale,
    theme,
    timeframe,
    vwap,
  ]);

  if (!cleanBars.length) {
    return <div className="equity-candles equity-candles--empty">{s.chart.noBars}</div>;
  }

  const last = cleanBars[cleanBars.length - 1]!;
  const chg = last.c - last.o;
  const chgPct = last.o !== 0 ? (chg / last.o) * 100 : 0;
  const tfLabel = s.chart.timeframes[timeframe];

  return (
    <div className="equity-candles-wrap">
      <div className="equity-candles-head">
        <span className="equity-candles-head__ticker">{ticker}</span>
        <span className="equity-candles-head__tf">{tfLabel}</span>
        <span className="equity-candles-head__ohlc">
          O <b>{last.o.toFixed(2)}</b> H <b>{last.h.toFixed(2)}</b> L <b>{last.l.toFixed(2)}</b> C{" "}
          <b>{last.c.toFixed(2)}</b>
        </span>
        <span
          className={
            chg >= 0 ? "equity-candles-head__chg equity-candles-head__chg--up" : "equity-candles-head__chg equity-candles-head__chg--down"
          }
        >
          {chg >= 0 ? "+" : ""}
          {chg.toFixed(2)} ({chgPct >= 0 ? "+" : ""}
          {chgPct.toFixed(2)}%)
        </span>
        <span className="equity-candles-legend">
          {overlays.showVwap ? (
            <span className="equity-candles-legend__item equity-candles-legend__item--vwap">{s.chart.vwap}</span>
          ) : null}
          {overlays.showPoc ? (
            <span className="equity-candles-legend__item equity-candles-legend__item--poc">{s.chart.poc}</span>
          ) : null}
          {overlays.showMa ? (
            <>
              <span className="equity-candles-legend__item equity-candles-legend__item--ma20">{s.fields.ma20}</span>
              <span className="equity-candles-legend__item equity-candles-legend__item--ma50">{s.fields.ma50}</span>
              <span className="equity-candles-legend__item equity-candles-legend__item--ma200">{s.fields.ma200}</span>
            </>
          ) : null}
          {overlays.showBenchmark && benchmarkOverlay.length >= 2 ? (
            <span className="equity-candles-legend__item">{benchmarkLabel}</span>
          ) : null}
        </span>
        <span className="equity-candles-head__hint">{s.chart.zoomHint}</span>
      </div>
      <div ref={containerRef} className="equity-candles" role="img" aria-label={`${ticker} ${tfLabel} candlestick chart`} />
    </div>
  );
}

/** @deprecated use EquityPriceChart */
export const EquitySessionChart = EquityPriceChart;
