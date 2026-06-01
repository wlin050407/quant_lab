import { useCallback, useEffect, useMemo, useState } from "react";

import { BrandMark } from "../components/BrandMark";
import { BrandWordmark } from "../components/BrandWordmark";
import { EquityPriceChart } from "../components/EquitySessionChart";
import { EquityChartToolbar } from "../components/equity/EquityChartToolbar";
import { EquityErrorBoundary } from "../components/equity/EquityErrorBoundary";
import { EquityInstrumentStrip } from "../components/equity/EquityInstrumentStrip";
import { EquityResearchRail } from "../components/equity/EquityResearchRail";
import { LoadingShell, LoadProgressBar } from "../components/LoadingShell";
import { PanelShell } from "../components/PanelShell";
import { useEquityAnalyze } from "../hooks/useEquityAnalyze";
import { useLocale } from "../hooks/useLocale";
import { useTheme } from "../hooks/useTheme";
import {
  alignBenchmarkOverlay,
  availableTimeframes,
  defaultChartTimeframe,
  overlayConfigForTimeframe,
  resolveBenchmarkBars,
  resolveChartBars,
  type ChartTimeframe,
} from "../lib/equityChartTimeframes";
import { getEquityStrings } from "../lib/i18n/equityStrings";
import type { Locale } from "../lib/locale";
import { navigateTo } from "../lib/appRoute";

function tickerFromHash(): string {
  const q = window.location.hash.split("?")[1] ?? "";
  const params = new URLSearchParams(q);
  return (params.get("t") ?? "AAPL").trim().toUpperCase();
}

function LocaleSwitch({ locale, setLocale }: { locale: Locale; setLocale: (l: Locale) => void }) {
  return (
    <div className="equity-locale-switch" role="group" aria-label="Language">
      <button
        type="button"
        className={`equity-locale-switch__btn${locale === "zh" ? " is-active" : ""}`}
        aria-pressed={locale === "zh"}
        onClick={() => setLocale("zh")}
      >
        中文
      </button>
      <button
        type="button"
        className={`equity-locale-switch__btn${locale === "en" ? " is-active" : ""}`}
        aria-pressed={locale === "en"}
        onClick={() => setLocale("en")}
      >
        EN
      </button>
    </div>
  );
}

export function StockTerminalPage() {
  const [input, setInput] = useState(() => tickerFromHash());
  const [ticker, setTicker] = useState(() => tickerFromHash());
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("1d");
  const { theme, toggleTheme } = useTheme();
  const { locale, setLocale } = useLocale();
  const s = getEquityStrings(locale);
  const query = useEquityAnalyze(ticker, Boolean(ticker));

  useEffect(() => {
    const onHash = () => setInput(tickerFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const runAnalyze = useCallback(() => {
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    setTicker(sym);
    window.location.hash = `#/stock?t=${encodeURIComponent(sym)}`;
  }, [input]);

  const data = query.data;
  const sessionVol = data?.chart.bars.reduce((sum, b) => sum + (Number.isFinite(b.v) ? b.v : 0), 0);
  const timeframesAvailable = useMemo(() => (data ? availableTimeframes(data) : []), [data]);

  useEffect(() => {
    setTimeframe("1d");
  }, [ticker]);

  useEffect(() => {
    if (!data) return;
    if (!timeframesAvailable.includes(timeframe)) {
      setTimeframe(defaultChartTimeframe(data));
    }
  }, [data, timeframe, timeframesAvailable]);

  const chartBars = useMemo(() => (data ? resolveChartBars(data, timeframe) : []), [data, timeframe]);
  const benchmarkOverlay = useMemo(() => {
    if (!data) return [];
    const benchBars = resolveBenchmarkBars(data, timeframe);
    return alignBenchmarkOverlay(chartBars, benchBars);
  }, [chartBars, data, timeframe]);
  const chartOverlays = useMemo(() => overlayConfigForTimeframe(timeframe), [timeframe]);
  const chartMeta = s.chart.timeframeMeta[timeframe];
  const needsDailyRefresh = data != null && !timeframesAvailable.includes("1d");
  const loading = query.isFetching;

  return (
    <div className={`app equity-terminal${loading && data ? " is-loading" : ""}`}>
      <LoadProgressBar active={loading && Boolean(data)} ariaLabel={s.loading} />
      <header className="topbar equity-topbar">
        <div className="topbar-row">
          <div className="brand">
            <BrandMark size={28} />
            <BrandWordmark tagline={s.tagline} />
          </div>
          <div className="controls equity-topbar__controls">
          <input
            className="equity-ticker-input"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && runAnalyze()}
            placeholder={s.tickerPlaceholder}
            aria-label={s.tickerPlaceholder}
          />
          <button type="button" className="chip chip-action" onClick={runAnalyze} disabled={query.isFetching}>
            {s.analyze}
          </button>
          <button type="button" className="chip" onClick={() => void query.refreshBypassCache()} disabled={query.isFetching}>
            {s.refresh}
          </button>
          <LocaleSwitch locale={locale} setLocale={setLocale} />
          <button type="button" className="chip" onClick={toggleTheme} aria-label="Toggle theme">
            {theme === "dark" ? s.themeLight : s.themeDark}
          </button>
          <button type="button" className="chip" onClick={() => navigateTo("home")}>
            {s.home}
          </button>
          </div>
        </div>
      </header>

      {query.error ? (
        <div className="status-strip">
          <span className="chip chip-no">
            {s.errorPrefix}: {String(query.error)}
          </span>
        </div>
      ) : null}

      {loading && !data ? <LoadingShell tagline={s.loading} /> : null}

      {data ? (
        <EquityErrorBoundary
          fallback={
            <div className="equity-loading equity-loading--error">
              Render error — restart <code>python scripts/run_terminal.py --port 8765</code> and Ctrl+F5.
            </div>
          }
        >
          <div className="equity-terminal__body">
            {!data.modules ? (
              <div className="status-strip status-strip--compact">
                <span className="chip chip-no">Stale API — restart terminal for module signals.</span>
              </div>
            ) : null}

            <EquityInstrumentStrip data={data} />

            <div className="equity-workspace">
              <div className="equity-main-col">
                <PanelShell className="equity-chart-stage panel" spotlightColor="rgba(20, 184, 166, 0.04)">
                  <EquityChartToolbar
                    timeframe={timeframe}
                    onTimeframe={setTimeframe}
                    meta={chartMeta}
                    available={timeframesAvailable}
                    sessionVol={timeframe === "5m" ? sessionVol : null}
                    sessionVolLabel={s.sessionVol}
                    sharesLabel={s.shares}
                  />
                  {needsDailyRefresh ? (
                    <div className="equity-chart-hint">{s.chart.dailyStaleHint}</div>
                  ) : null}
                  <EquityPriceChart
                    bars={chartBars}
                    timeframe={timeframe}
                    overlays={chartOverlays}
                    vwap={data.chart.overlays.vwap}
                    poc={data.chart.overlays.poc}
                    benchmarkOverlay={benchmarkOverlay}
                    benchmarkLabel={`${data.benchmark} (${s.chart.benchmark})`}
                    theme={theme}
                    ticker={data.ticker}
                  />
                </PanelShell>
              </div>

              <EquityResearchRail data={data} />
            </div>
          </div>
        </EquityErrorBoundary>
      ) : null}
    </div>
  );
}
