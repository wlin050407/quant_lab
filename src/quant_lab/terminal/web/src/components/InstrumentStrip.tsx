import type { ReactNode } from "react";

import { distPct } from "../lib/heatmap";
import { countValidLevels, DEALER_LEVELS, isValidLevel } from "../lib/levels";
import { chainFlowModeLabel, dataSourceLabel, oiModeLabel, volumeSourceLabel } from "../lib/snapshotMeta";
import { fmtPct, fmtPrice, regimeDesc, regimeShort, vannaLabel } from "../lib/format";
import type { DashboardSnapshot, ExposureMetric } from "../types/snapshot";

import { AnimatedPrice } from "./AnimatedPrice";
import { KingPill } from "./KingPill";

interface InstrumentStripProps {
  snapshot: DashboardSnapshot;
  metric: ExposureMetric;
  loading: boolean;
}

function LevelChip({
  label,
  cls,
  value,
  spot,
}: {
  label: string;
  cls: string;
  value: number | null | undefined;
  spot: number | null;
}) {
  const ok = isValidLevel(value);
  const d = ok && spot != null ? distPct(spot, value) : null;
  return (
    <div className={`strip-chip strip-chip--${cls}${ok ? "" : " is-empty"}`}>
      <span className="strip-chip-k">{label}</span>
      <span className="strip-chip-v">{ok ? fmtPrice(value) : "—"}</span>
      {d != null ? <span className="strip-chip-d">{fmtPct(d)}</span> : null}
    </div>
  );
}

export function InstrumentStrip({ snapshot, metric, loading }: InstrumentStripProps) {
  const M = snapshot.metrics;
  const L = snapshot.levels;
  const t = snapshot.trinity;
  const g = snapshot.gate;
  const chg = snapshot.spot_change_pct;
  const spot = snapshot.spot;
  const sym = snapshot.symbol.replace("^", "");
  const pin = M.pin_score;
  const pinPct = pin != null && !Number.isNaN(pin) ? Math.min(100, Math.max(0, pin)) : null;
  const isLive = snapshot.meta?.data_source === "thetadata_live";
  const isIntraday = Boolean(snapshot.meta?.intraday_time);
  const timeLabel = isIntraday ? `${snapshot.meta?.intraday_time} ET` : "EoD";
  const strikes = snapshot.heatmap?.length ?? 0;
  const cohort = snapshot.meta?.cohort ?? "dte≤1";
  const source = dataSourceLabel(snapshot);
  const oiLabel = oiModeLabel(snapshot.meta?.oi_mode);
  const volLabel = volumeSourceLabel(snapshot.meta?.volume_source);
  const chainLabel = chainFlowModeLabel(snapshot.meta?.chain_mode);
  const levelCount = countValidLevels(L);

  let exposureBlock: ReactNode;
  if (metric === "compare") {
    exposureBlock = (
      <>
        <span className="strip-kpi">
          <span className="strip-kpi-k">GEX</span>
          <span className="strip-kpi-v">{M.net_gex_dte1_bn != null ? `${M.net_gex_dte1_bn.toFixed(2)}Bn` : "—"}</span>
        </span>
        <span className="strip-kpi">
          <span className="strip-kpi-k">VEX</span>
          <span className="strip-kpi-v">{M.net_vex_dte1_bn != null ? `${M.net_vex_dte1_bn.toFixed(2)}Bn` : "—"}</span>
        </span>
      </>
    );
  } else if (metric === "vex") {
    exposureBlock = (
      <>
        <span className="strip-kpi">
          <span className="strip-kpi-k">0D VEX</span>
          <span className="strip-kpi-v">{M.pct_vex_dte1 != null ? `${M.pct_vex_dte1.toFixed(0)}%` : "—"}</span>
        </span>
        <span className="strip-kpi">
          <span className="strip-kpi-k">Net</span>
          <span className="strip-kpi-v">{M.net_vex_dte1_bn != null ? `${M.net_vex_dte1_bn.toFixed(2)}Bn` : "—"}</span>
        </span>
      </>
    );
  } else {
    exposureBlock = (
      <>
        <span className="strip-kpi">
          <span className="strip-kpi-k">0D GEX</span>
          <span className="strip-kpi-v">{M.pct_gex_dte1 != null ? `${M.pct_gex_dte1.toFixed(0)}%` : "—"}</span>
        </span>
        <span className="strip-kpi">
          <span className="strip-kpi-k">Net</span>
          <span className="strip-kpi-v">{M.net_gex_dte1_bn != null ? `${M.net_gex_dte1_bn.toFixed(2)}Bn` : "—"}</span>
        </span>
      </>
    );
  }

  const warnings: string[] = [];
  if (snapshot.meta?.date_fallback && snapshot.meta.requested_date) {
    warnings.push(`No data for ${snapshot.meta.requested_date} · showing ${snapshot.date}`);
  }
  if (snapshot.meta?.cohort_fallback) warnings.push("Cohort fallback");
  if (!isIntraday && sym === "SPX") warnings.push("No intraday chain");
  if (strikes === 0) warnings.push("Empty chain");
  if (levelCount === 0) warnings.push("Levels need 0DTE chain");

  return (
    <section
      className={`instrument-strip${loading ? " is-pulse" : ""}${isLive ? " is-live" : ""}`}
      aria-label="Market context"
    >
      <div className="instrument-strip-main">
        <div className={`strip-regime ${snapshot.regime}`}>
          <span className="strip-regime-v">{regimeShort(snapshot.regime)}</span>
          <span className={`strip-gate ${g.should_trade ? "ok" : "no"}`}>
            {g.should_trade ? "OK" : "OUT"}
          </span>
        </div>

        <div className="strip-quote">
          <div className="strip-quote-line1">
            <span className="strip-sym">{sym}</span>
            {isLive ? (
              <span className="strip-live">
                <span className="live-dot" aria-hidden />
                LIVE
              </span>
            ) : (
              <span className="strip-session">{timeLabel}</span>
            )}
            <AnimatedPrice value={spot} className="strip-spot" />
            {chg != null ? (
              <span
                className={`strip-chg ${chg >= 0 ? "up" : "down"}`}
                title="Day change vs previous trading day close"
              >
                <span className="strip-chg-k">DoD</span>
                {fmtPct(chg)}
              </span>
            ) : null}
          </div>
          <div className="strip-quote-line2">
            <KingPill kd={snapshot.king_distance} />
            {M.spot_vs_flip_pct != null ? (
              <span className="strip-dist">vs flip {fmtPct(M.spot_vs_flip_pct)}</span>
            ) : null}
            {M.spot_vs_king_pct != null ? (
              <span className="strip-dist">vs king {fmtPct(M.spot_vs_king_pct)}</span>
            ) : null}
          </div>
        </div>

        <div className="strip-levels-scroll" aria-label="Key dealer strikes">
          {DEALER_LEVELS.map(({ key, label, cls }) => (
            <LevelChip key={key} label={label} cls={cls} value={L?.[key] as number | null} spot={spot} />
          ))}
        </div>

        <div className="strip-exposure">{exposureBlock}</div>
      </div>

      <div className="instrument-strip-foot">
        <span className="strip-foot-item strip-foot-em">
          <span className="strip-foot-k">EM</span>
          {isValidLevel(L?.expected_move) ? (
            <>
              <strong>±{L.expected_move!.toFixed(2)}</strong>
              <span className="strip-foot-sub">
                {fmtPrice(L.expected_lower)}–{fmtPrice(L.expected_upper)}
              </span>
            </>
          ) : (
            <span>—</span>
          )}
        </span>

        <span className="strip-foot-item">
          <span className="strip-foot-k">P/C</span>
          <strong>{M.pcr_oi != null ? M.pcr_oi.toFixed(2) : "—"}</strong>
        </span>

        <span className="strip-foot-item">
          <span className="strip-foot-k">OI conc</span>
          <strong>{M.oi_conc_dte1 != null ? `${(M.oi_conc_dte1 * 100).toFixed(0)}%` : "—"}</strong>
        </span>

        <span className="strip-foot-item strip-foot-pin">
          <span className="strip-foot-k">Pin</span>
          {pinPct != null ? (
            <>
              <div className="strip-pin-track">
                <div className="strip-pin-fill" style={{ width: `${pinPct}%` }} />
              </div>
              <strong>{pinPct.toFixed(0)}</strong>
            </>
          ) : (
            <strong>—</strong>
          )}
        </span>

        {t.score != null && t.n_symbols >= 2 ? (
          <span className="strip-foot-item strip-foot-trinity">
            <span className="strip-foot-k">Trinity</span>
            <strong>{Math.round(t.score)}</strong>
            <span className="strip-foot-sub">{t.direction}</span>
          </span>
        ) : null}

        {M.vanna_interpretation && metric !== "gex" ? (
          <span className="strip-foot-item strip-foot-vanna">{vannaLabel(M.vanna_interpretation)}</span>
        ) : null}

        <span className="strip-foot-meta">
          <span className={`strip-meta-pill strip-meta-pill--${isLive ? "live" : "eod"}`}>{source}</span>
          {snapshot.meta?.chain_mode ? (
            <span
              className={`strip-meta-pill strip-meta-pill--chain${snapshot.meta.chain_mode === "full" ? " strip-meta-pill--warn" : ""}`}
              title={
                snapshot.meta.chain_mode === "full"
                  ? "Pin 用 OPRA 成交流调整 effective OI（更准、较慢）"
                  : "Pin 用 |ΔOI| vs 09:30（较快）"
              }
            >
              {chainLabel}
            </span>
          ) : null}
          {snapshot.meta?.oi_mode === "effective" ? (
            <span className="strip-meta-pill strip-meta-pill--oi">{oiLabel}</span>
          ) : null}
          {snapshot.meta?.volume_source && snapshot.meta.volume_source !== "settled" ? (
            <span className="strip-meta-pill strip-meta-pill--vol">{volLabel}</span>
          ) : null}
          {isLive && snapshot.meta?.quote_granularity ? (
            <span className="strip-meta-pill strip-meta-pill--refresh">
              {snapshot.meta.quote_granularity} · ↻{snapshot.meta.live_refresh_seconds ?? 30}s
            </span>
          ) : null}
          {snapshot.meta?.trinity_live_panels != null && snapshot.meta.trinity_live_panels > 0 ? (
            <span className="strip-meta-pill strip-meta-pill--trinity">
              Trinity {snapshot.meta.trinity_live_panels}/3 live
            </span>
          ) : null}
          <span>{snapshot.date}</span>
          <span>{strikes} stk</span>
          <span>{cohort}</span>
          {warnings.length > 0 ? <span className="strip-foot-warn">{warnings.join(" · ")}</span> : null}
        </span>
      </div>

      <p className="strip-regime-hint">{regimeDesc(snapshot.regime)}</p>
    </section>
  );
}

/** @deprecated Use InstrumentStrip */
export const CommandDeck = InstrumentStrip;
