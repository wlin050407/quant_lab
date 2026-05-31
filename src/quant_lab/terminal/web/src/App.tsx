import { useCallback, useEffect, useRef, useState } from "react";

import { useDates, useSnapshot } from "./hooks/useTerminalQueries";

import { TopBar } from "./components/TopBar";

import { InstrumentStrip } from "./components/InstrumentStrip";

import { PriceLadder } from "./components/PriceLadder";

import { HeatmapSection } from "./components/HeatmapSection";

import { RightRail } from "./components/RightRail";

import { LoadingShell, LoadProgressBar } from "./components/LoadingShell";

import { KeyboardHints } from "./components/KeyboardHints";

import type { ExposureMetric, HeatmapViewMode } from "./types/snapshot";
import { isLivePollCandidate, pickInitialDate } from "./lib/liveSymbols";



const SESSION_TIMES = ["10:00:00", "13:00:00", "15:30:00"] as const;

const DEMO_SPX = { symbol: "^SPX", date: "2023-07-11", time: "13:00:00" };



export default function App() {

  const [symbol, setSymbol] = useState("^SPX");

  const [date, setDate] = useState("");

  const [intradayTime, setIntradayTime] = useState("13:00:00");

  const [metric, setMetric] = useState<ExposureMetric>("gex");

  const [scrollToken, setScrollToken] = useState(0);

  const [focusMode, setFocusMode] = useState(false);

  const [heatmapView, setHeatmapView] = useState<HeatmapViewMode>("single");



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

  const snapshotQuery = useSnapshot(symbol, date, intradayTime, Boolean(date), {
    livePollCandidate,
  });

  const snapshot = snapshotQuery.data;

  useEffect(() => {

    if (!snapshotQuery.error || !datesQuery.data) return;

    const latest = datesQuery.data.latest;

    if (!latest || date === latest) return;

    if (date === datesQuery.data.today) {

      setDate(pickInitialDate(symbol, datesQuery.data));

    }

  }, [snapshotQuery.error, date, symbol, datesQuery.data]);



  const loading = datesQuery.isFetching || snapshotQuery.isFetching;



  const bumpScroll = useCallback(() => {

    setScrollToken((t) => t + 1);

  }, []);



  useEffect(() => {

    if (snapshot) bumpScroll();

  }, [snapshot?.date, snapshot?.symbol, snapshot?.spot, metric, intradayTime, bumpScroll]);



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

      const idx = SESSION_TIMES.indexOf(intradayTime as (typeof SESSION_TIMES)[number]);

      const cur = idx >= 0 ? idx : 1;

      const next = Math.max(0, Math.min(SESSION_TIMES.length - 1, cur + delta));

      setIntradayTime(SESSION_TIMES[next]);

    },

    [intradayTime],

  );



  const loadDemo = useCallback(() => {

    setSymbol(DEMO_SPX.symbol);

    setDate(DEMO_SPX.date);

    setIntradayTime(DEMO_SPX.time);

  }, []);



  const loadLive = useCallback(() => {
    setSymbol("^SPX");
    if (today && dates.includes(today)) {
      setDate(today);
      return;
    }
    if (datesQuery.data?.default_date) {
      setDate(datesQuery.data.default_date);
    }
  }, [today, dates, datesQuery.data?.default_date]);



  useEffect(() => {

    const onKey = (e: KeyboardEvent) => {

      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;

      if (e.key === "ArrowLeft") shiftDate(-1);

      if (e.key === "ArrowRight") shiftDate(1);

      if (e.key === "g" || e.key === "G") setMetric("gex");

      if (e.key === "v" || e.key === "V") setMetric("vex");

      if (e.key === "c" || e.key === "C") setMetric("compare");

      if (e.key === "f" || e.key === "F") setFocusMode((v) => !v);
      if (e.key === "t" || e.key === "T") loadLive();
      if (e.key === "1") setHeatmapView("single");
      if (e.key === "3") setHeatmapView("trinity");

      if (symbol === "^SPX") {

        if (e.key === "[") shiftSessionTime(-1);

        if (e.key === "]") shiftSessionTime(1);

      }

    };

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);

  }, [shiftDate, shiftSessionTime, symbol, loadLive]);



  const error = datesQuery.error ?? snapshotQuery.error;

  const workspaceClass = focusMode

    ? "workspace workspace--focus"

    : "workspace workspace--heatmap-focus";



  return (

    <div className={`app${loading && snapshot ? " is-loading" : ""}${focusMode ? " app--focus" : ""}`}>
      <LoadProgressBar active={loading && Boolean(snapshot)} />
      <div className="app-mesh" aria-hidden />

      <TopBar
        symbol={symbol}
        date={date}
        intradayTime={intradayTime}
        dates={dates}
        focusMode={focusMode}

        onSymbolChange={setSymbol}

        onDateChange={setDate}

        onIntradayTimeChange={setIntradayTime}

        onPrevDate={() => shiftDate(-1)}

        onNextDate={() => shiftDate(1)}

        onToggleFocus={() => setFocusMode((v) => !v)}

        onLoadDemo={loadDemo}
        onLoadLive={loadLive}
        today={today}
        isLive={snapshot?.meta?.data_source === "thetadata_live"}

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



      {snapshot ? (

        <>

          {!focusMode ? <InstrumentStrip snapshot={snapshot} metric={metric} loading={loading} /> : null}

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


