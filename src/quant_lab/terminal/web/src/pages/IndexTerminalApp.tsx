import { useCallback, useEffect, useRef, useState } from "react";

import { useDates, useSnapshot } from "../hooks/useTerminalQueries";
import { useTheme } from "../hooks/useTheme";
import { navigateTo } from "../lib/appRoute";

import { TopBar } from "../components/TopBar";
import { InstrumentStrip } from "../components/InstrumentStrip";
import { ModelAssumptionStrip } from "../components/ModelAssumptionStrip";
import { PriceLadder } from "../components/PriceLadder";
import { HeatmapSection } from "../components/HeatmapSection";
import { RightRail } from "../components/RightRail";
import { SessionHoldPanel } from "../components/SessionHoldPanel";
import { LoadingShell, LoadProgressBar } from "../components/LoadingShell";
import { KeyboardHints } from "../components/KeyboardHints";

import type { ExposureMetric, HeatmapViewMode } from "../types/snapshot";
import { loadChainFlowMode, saveChainFlowMode } from "../lib/chainFlowMode";
import { isLivePollCandidate, lastTradingSessionEt, pickInitialDate } from "../lib/liveSymbols";
import type { ChainFlowMode } from "../types/snapshot";
import {
  isLiveSessionTime,
  LIVE_SESSION_TIME,
  PIN_SESSION_TIMES,
} from "../lib/sessionTime";

const DEMO_SPX = { symbol: "^SPX", date: "2023-07-11", time: "13:00:00" };

export function IndexTerminalApp() {
  const [symbol, setSymbol] = useState("^SPX");
  const [date, setDate] = useState("");
  const [intradayTime, setIntradayTime] = useState("13:00:00");
  const [chainFlowMode, setChainFlowMode] = useState<ChainFlowMode>(loadChainFlowMode);
  const [metric, setMetric] = useState<ExposureMetric>("gex");
  const [scrollToken, setScrollToken] = useState(0);
  const [focusMode, setFocusMode] = useState(false);
  const [heatmapView, setHeatmapView] = useState<HeatmapViewMode>("single");
  const { theme, toggleTheme } = useTheme();

  const datesQuery = useDates(symbol);
  const dates = datesQuery.data?.dates ?? [];
  const today = datesQuery.data?.today ?? "";

  const appliedSymbolRef = useRef("");
  useEffect(() => {
    const data = datesQuery.data;
    if (!data) return;
    if (appliedSymbolRef.current === symbol) return;
    appliedSymbolRef.current = symbol;
    setDate(pickInitialDate(symbol, data));
  }, [symbol, datesQuery.data]);

  const defaultDate = datesQuery.data
    ? (datesQuery.data.default_date ?? pickInitialDate(symbol, datesQuery.data))
    : "";

  const livePollCandidate = isLivePollCandidate(symbol, today, date, defaultDate);

  useEffect(() => {
    if (livePollCandidate && !isLiveSessionTime(intradayTime)) {
      const onPinSlot = PIN_SESSION_TIMES.includes(intradayTime as (typeof PIN_SESSION_TIMES)[number]);
      if (!onPinSlot) setIntradayTime(LIVE_SESSION_TIME);
    }
    if (!livePollCandidate && isLiveSessionTime(intradayTime)) {
      setIntradayTime("13:00:00");
    }
  }, [livePollCandidate, intradayTime]);

  useEffect(() => {
    saveChainFlowMode(chainFlowMode);
  }, [chainFlowMode]);

  const snapshotQuery = useSnapshot(symbol, date, intradayTime, Boolean(date), {
    livePollCandidate,
    includeTrinity: heatmapView === "trinity",
    chainFlowMode: symbol === "^SPX" ? chainFlowMode : "pin",
  });

  const snapshot = snapshotQuery.data;
  const sessionHold = snapshot?.availability === "hold";

  useEffect(() => {
    if (sessionHold || !snapshotQuery.error || !datesQuery.data) return;
    const latest = datesQuery.data.latest;
    if (!latest || date === latest) return;
    if (date === datesQuery.data.today) {
      setDate(pickInitialDate(symbol, datesQuery.data));
    }
  }, [sessionHold, snapshotQuery.error, date, symbol, datesQuery.data]);

  const loading = datesQuery.isFetching || snapshotQuery.isFetching;

  const bumpScroll = useCallback(() => {
    setScrollToken((t) => t + 1);
  }, []);

  useEffect(() => {
    if (snapshot) bumpScroll();
  }, [snapshot?.date, snapshot?.symbol, snapshot?.spot, metric, intradayTime, chainFlowMode, bumpScroll]);

  useEffect(() => {
    if (!snapshotQuery.isFetching && snapshotQuery.data) {
      bumpScroll();
    }
  }, [snapshotQuery.isFetching, snapshotQuery.dataUpdatedAt, bumpScroll]);

  const shiftDate = useCallback(
    (delta: number) => {
      const idx = dates.indexOf(date);
      if (idx < 0) return;
      setDate(dates[Math.max(0, Math.min(dates.length - 1, idx + delta))]);
    },
    [dates, date],
  );

  const shiftSessionTime = useCallback(
    (delta: number) => {
      if (livePollCandidate) {
        const slots = [LIVE_SESSION_TIME, ...PIN_SESSION_TIMES];
        const idx = slots.indexOf(intradayTime as (typeof slots)[number]);
        const cur = idx >= 0 ? idx : 0;
        const next = Math.max(0, Math.min(slots.length - 1, cur + delta));
        setIntradayTime(slots[next] ?? LIVE_SESSION_TIME);
        return;
      }
      const idx = PIN_SESSION_TIMES.indexOf(intradayTime as (typeof PIN_SESSION_TIMES)[number]);
      const cur = idx >= 0 ? idx : 1;
      const next = Math.max(0, Math.min(PIN_SESSION_TIMES.length - 1, cur + delta));
      setIntradayTime(PIN_SESSION_TIMES[next] ?? "13:00:00");
    },
    [intradayTime, livePollCandidate],
  );

  const loadDemo = useCallback(() => {
    setSymbol(DEMO_SPX.symbol);
    setDate(DEMO_SPX.date);
    setIntradayTime(DEMO_SPX.time);
  }, []);

  const loadLive = useCallback(() => {
    setSymbol("^SPX");
    setIntradayTime(LIVE_SESSION_TIME);
    if (today) {
      setDate(datesQuery.data?.default_date ?? lastTradingSessionEt(today));
    }
  }, [today, datesQuery.data?.default_date]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "ArrowLeft") shiftDate(-1);
      if (e.key === "ArrowRight") shiftDate(1);
      if (e.key === "g" || e.key === "G") setMetric("gex");
      if (e.key === "v" || e.key === "V") setMetric("vex");
      if (e.key === "c" || e.key === "C") setMetric("compare");
      if (e.key === "f" || e.key === "F") setFocusMode((v) => !v);
      if (e.key === "l" || e.key === "L") toggleTheme();
      if (e.key === "t" || e.key === "T") loadLive();
      if (e.key === "1") setHeatmapView("single");
      if (e.key === "3") setHeatmapView("trinity");
      if (e.key === "h" || e.key === "H") navigateTo("home");
      if (symbol === "^SPX") {
        if (e.key === "[") shiftSessionTime(-1);
        if (e.key === "]") shiftSessionTime(1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shiftDate, shiftSessionTime, symbol, loadLive, toggleTheme]);

  const error = sessionHold ? null : datesQuery.error ?? snapshotQuery.error;
  const workspaceClass = focusMode ? "workspace workspace--focus" : "workspace workspace--heatmap-focus";

  return (
    <div className={`app index-terminal${loading && snapshot ? " is-loading" : ""}${focusMode ? " app--focus" : ""}`}>
      <LoadProgressBar active={loading && Boolean(snapshot)} />
      <div className="app-mesh" aria-hidden />

      <TopBar
        symbol={symbol}
        date={date}
        intradayTime={intradayTime}
        chainFlowMode={chainFlowMode}
        onChainFlowModeChange={setChainFlowMode}
        dates={dates}
        focusMode={focusMode}
        theme={theme}
        onToggleTheme={toggleTheme}
        onSymbolChange={setSymbol}
        onDateChange={setDate}
        onIntradayTimeChange={setIntradayTime}
        onPrevDate={() => shiftDate(-1)}
        onNextDate={() => shiftDate(1)}
        onToggleFocus={() => setFocusMode((v) => !v)}
        onLoadDemo={loadDemo}
        onLoadLive={loadLive}
        onGoHome={() => navigateTo("home")}
        today={today}
        isLive={snapshot?.meta?.data_source === "thetadata_live"}
        livePollCandidate={livePollCandidate}
        effectiveIntradayTime={snapshot?.meta?.intraday_time ?? null}
        onRefresh={() => {
          void snapshotQuery.refetch();
          bumpScroll();
        }}
      />

      {error ? (
        <div className="status-strip">
          <span className="chip chip-no">Error: {String(error)}</span>
        </div>
      ) : null}

      {sessionHold && snapshot ? (
        <SessionHoldPanel
          snapshot={snapshot}
          onRefresh={() => {
            void snapshotQuery.refetch();
          }}
        />
      ) : snapshot ? (
        <>
          {!focusMode ? (
            <>
              <InstrumentStrip snapshot={snapshot} metric={metric} loading={loading} />
              <ModelAssumptionStrip snapshot={snapshot} />
            </>
          ) : null}
          <main className={workspaceClass}>
            {!focusMode ? <PriceLadder snapshot={snapshot} /> : null}
            <HeatmapSection
              snapshot={snapshot}
              metric={metric}
              viewMode={heatmapView}
              onMetricChange={setMetric}
              onViewModeChange={setHeatmapView}
              scrollKey={scrollToken}
            />
            {!focusMode ? <RightRail snapshot={snapshot} /> : null}
          </main>
        </>
      ) : loading ? (
        <LoadingShell />
      ) : null}

      <KeyboardHints focusMode={focusMode} symbol={symbol} />
    </div>
  );
}
