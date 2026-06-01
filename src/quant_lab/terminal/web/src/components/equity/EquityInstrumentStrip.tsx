import { AnimatedPrice } from "../AnimatedPrice";
import type { EquityAnalyzeResponse } from "../../types/equity";
import { useLocale } from "../../hooks/useLocale";
import { getEquityStrings } from "../../lib/i18n/equityStrings";
import { computeChartStats } from "../../lib/equityChartTimeframes";
import { distFromSpot, formatAdv, sessionStatsFromBars, sourceBadge } from "../../lib/equityDisplay";
import { fmtPct, fmtPrice } from "../../lib/format";

interface EquityInstrumentStripProps {
  data: EquityAnalyzeResponse;
}

function LevelChip({
  label,
  cls,
  value,
  spot,
}: {
  label: string;
  cls: string;
  value: number;
  spot: number;
}) {
  const dist = distFromSpot(spot, value);
  return (
    <div className={`strip-chip strip-chip--${cls}`}>
      <span className="strip-chip-k">{label}</span>
      <span className="strip-chip-v">{fmtPrice(value)}</span>
      {dist ? <span className="strip-chip-d">{dist}</span> : null}
    </div>
  );
}

export function EquityInstrumentStrip({ data }: EquityInstrumentStripProps) {
  const { locale } = useLocale();
  const s = getEquityStrings(locale);
  const session = sessionStatsFromBars(data.chart.bars);
  const alignMap = s.alignmentMap as Record<string, { label: string; hint: string }>;
  const align = alignMap[data.horizons.alignment] ?? s.alignmentMap.mixed;
  const alignCls =
    data.horizons.alignment === "aligned"
      ? "long_gamma"
      : data.horizons.alignment === "conflicting"
        ? "short_gamma"
        : "undetermined";
  const volMap = s.volRegimeMap as Record<string, string>;
  const intraday = sourceBadge(data.provenance.intraday_bars);
  const isLive = intraday.quality === "live";
  const l2 = data.layers.L2;
  const l3 = data.layers.L3;
  const l5 = data.layers.L5;
  const l6 = data.layers.L6;
  const stats = computeChartStats(data);
  const chgUp = session ? session.change >= 0 : true;

  return (
    <section className={`instrument-strip equity-instrument-strip${isLive ? " is-live" : ""}`} aria-label={s.quoteAria}>
      <div className="instrument-strip-main">
        <div className={`strip-regime ${alignCls}`} title={align.hint}>
          <span className="strip-regime-v">{align.label}</span>
          <span className="strip-gate ok">{s.alignment}</span>
        </div>

        <div className="strip-quote">
          <div className="strip-quote-line1">
            <span className="strip-sym">{data.ticker}</span>
            {isLive ? <span className="strip-live">LIVE</span> : null}
            <span className="strip-time">{data.session_date}</span>
          </div>
          <div className="strip-quote-line2">
            <AnimatedPrice value={data.spot} className="strip-spot" />
            {session ? (
              <span className={chgUp ? "strip-chg strip-chg--up" : "strip-chg strip-chg--down"}>
                {session.change >= 0 ? "+" : ""}
                {session.change.toFixed(2)} ({fmtPct(session.changePct)})
              </span>
            ) : null}
          </div>
        </div>

        <div className="strip-levels-scroll">
          <LevelChip label="VWAP" cls="flip" value={data.chart.overlays.vwap} spot={data.spot} />
          <LevelChip label="POC" cls="king" value={l3.poc} spot={data.spot} />
          <LevelChip label="VAH" cls="call" value={l3.vah} spot={data.spot} />
          <LevelChip label="VAL" cls="put" value={l3.val} spot={data.spot} />
        </div>

        <div className="strip-exposure">
          {session ? (
            <>
              <span className="strip-kpi">
                <span className="strip-kpi-k">{s.open}</span>
                <span className="strip-kpi-v">{fmtPrice(session.open)}</span>
              </span>
              <span className="strip-kpi">
                <span className="strip-kpi-k">{s.high}</span>
                <span className="strip-kpi-v strip-kpi-v--up">{fmtPrice(session.high)}</span>
              </span>
              <span className="strip-kpi">
                <span className="strip-kpi-k">{s.low}</span>
                <span className="strip-kpi-v strip-kpi-v--down">{fmtPrice(session.low)}</span>
              </span>
            </>
          ) : null}
          <span className="strip-kpi">
            <span className="strip-kpi-k">RS 20d</span>
            <span className="strip-kpi-v">{fmtPct(l5.rs_20d)}</span>
          </span>
          <span className="strip-kpi">
            <span className="strip-kpi-k">{s.vsVwap}</span>
            <span className={`strip-kpi-v ${l2.above_vwap ? "strip-kpi-v--up" : "strip-kpi-v--down"}`}>
              {l2.above_vwap ? s.above : s.below} {fmtPct(l2.deviation_pct)}
            </span>
          </span>
        </div>
      </div>

      <div className="instrument-strip-foot">
        <span className="strip-foot-item">
          <span className="strip-foot-k">{s.fields.ma20}</span>
          <strong>{fmtPrice(l5.ma20)}</strong>
        </span>
        <span className="strip-foot-item">
          <span className="strip-foot-k">{s.fields.ma200}</span>
          <strong>{fmtPrice(l5.ma200)}</strong>
        </span>
        {stats.high52w != null ? (
          <span className="strip-foot-item">
            <span className="strip-foot-k">{s.contextDock.high52w}</span>
            <strong>{fmtPrice(stats.high52w)}</strong>
          </span>
        ) : null}
        {stats.low52w != null ? (
          <span className="strip-foot-item">
            <span className="strip-foot-k">{s.contextDock.low52w}</span>
            <strong>{fmtPrice(stats.low52w)}</strong>
          </span>
        ) : null}
        <span className="strip-foot-item">
          <span className="strip-foot-k">{s.fields.adv}</span>
          <strong>{formatAdv(data.layers.L0.adv_usd)}</strong>
        </span>
        {l6 ? (
          <span className="strip-foot-item">
            <span className="strip-foot-k">{s.fields.maxPain}</span>
            <strong>{fmtPrice(l6.max_pain)}</strong>
          </span>
        ) : null}
        <span className="strip-foot-item">
          <span className="strip-foot-k">{s.volRegime}</span>
          <strong>{volMap[data.horizons.vol_regime] ?? data.horizons.vol_regime}</strong>
        </span>
        <span className="strip-foot-item">
          <span className="strip-foot-k">{s.vsBench}</span>
          <strong>{data.benchmark}</strong>
        </span>
        <span className="strip-foot-meta">
          <span className={`strip-meta-pill strip-meta-pill--${isLive ? "live" : "eod"}`}>{intraday.label}</span>
          <span className="strip-meta-pill">{sourceBadge(data.provenance.daily_bars).label}</span>
          <span>{new Date(data.asof).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" })}</span>
        </span>
      </div>
    </section>
  );
}
