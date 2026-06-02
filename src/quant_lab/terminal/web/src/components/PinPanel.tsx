import { fmtGexBn, fmtPct, fmtPrice } from "../lib/format";
import type { DashboardSnapshot, PinClusterPayload, PinMagnetRow } from "../types/snapshot";
import { LivePinQualityBanner } from "./LivePinQualityBanner";
import { PinScoreGauge } from "./PinScoreGauge";

const BREAKDOWN_LABELS: Record<string, string> = {
  oi_concentration: "OI concentration",
  magnet_proximity: "Magnet proximity",
  time_remaining: "Time to close",
  gamma_magnitude: "Gamma magnitude",
};

const ZONE_STATE_LABELS: Record<string, string> = {
  inside_zone: "Inside zone",
  testing_upside_exit: "Testing upside",
  testing_downside_exit: "Testing downside",
  above_break: "Above break",
  below_break: "Below break",
  unknown: "Zone state unknown",
};

function tagLabel(tag: string): string {
  if (tag === "king") return "King";
  if (tag === "max_pain") return "Max pain";
  if (tag === "cluster") return "Zone member";
  return tag;
}

function zoneStateClass(state: string | null | undefined): string {
  if (state === "inside_zone") return "pin-zone-state--inside";
  if (state === "testing_upside_exit" || state === "testing_downside_exit") return "pin-zone-state--testing";
  if (state === "above_break" || state === "below_break") return "pin-zone-state--break";
  return "pin-zone-state--unknown";
}

function MagnetRow({ row }: { row: PinMagnetRow }) {
  const weight = row.weight_pct ?? 0;
  const inCluster = row.tags.includes("cluster");
  return (
    <li
      className={`pin-magnet-row${weight <= 0 ? " pin-magnet-row--anchor" : ""}${
        inCluster ? " pin-magnet-row--cluster" : ""
      }`}
    >
      <div className="pin-magnet-row-head">
        <span className="pin-magnet-strike">{fmtPrice(row.strike)}</span>
        <span className="pin-magnet-weight">{weight > 0 ? `${weight.toFixed(1)}%` : "—"}</span>
      </div>
      <div className="pin-magnet-bar-track">
        <div className="pin-magnet-bar-fill" style={{ width: `${Math.min(100, weight)}%` }} />
      </div>
      <div className="pin-magnet-meta">
        <span>{fmtGexBn(row.net_gex_bn)} GEX</span>
        <span>OI {(row.oi_share * 100).toFixed(0)}%</span>
        <span>{fmtPct(row.dist_pct)} vs spot</span>
        {row.tags.length > 0 ? (
          <span className="pin-magnet-tags">
            {row.tags.map((t) => (
              <span key={t} className={`pin-magnet-tag pin-magnet-tag--${t}`}>
                {tagLabel(t)}
              </span>
            ))}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function PinZoneHero({
  cluster,
  magnetShift,
  magnetPrevious,
  magnetDeltaPts,
}: {
  cluster: PinClusterPayload;
  magnetShift: boolean;
  magnetPrevious: number | null | undefined;
  magnetDeltaPts: number | null | undefined;
}) {
  const lo = cluster.lower;
  const hi = cluster.upper;
  const state = cluster.spot_zone_state;
  const stateLabel = state ? (ZONE_STATE_LABELS[state] ?? state) : null;

  return (
    <div className="pin-zone-hero">
      <div className="pin-zone-hero-head">
        <span className="pin-zone-k">Pinning zone</span>
        {cluster.cluster_strength && cluster.cluster_strength !== "none" ? (
          <span className={`pin-zone-strength pin-zone-strength--${cluster.cluster_strength}`}>
            {cluster.cluster_strength}
          </span>
        ) : null}
        {stateLabel ? (
          <span className={`pin-zone-state ${zoneStateClass(state)}`}>{stateLabel}</span>
        ) : null}
      </div>

      {lo != null && hi != null ? (
        <div className="pin-zone-range">
          <strong>{fmtPrice(lo)}</strong>
          <span className="pin-zone-dash">–</span>
          <strong>{fmtPrice(hi)}</strong>
        </div>
      ) : null}

      <div className="pin-zone-meta">
        {cluster.center != null ? <span>Center {fmtPrice(cluster.center)}</span> : null}
        {cluster.width != null ? <span>Width {cluster.width.toFixed(0)} pts</span> : null}
        {cluster.strength_ratio != null ? (
          <span>Strength {Math.round(cluster.strength_ratio * 100)}%</span>
        ) : null}
      </div>

      {cluster.up_break_level != null && cluster.down_break_level != null ? (
        <div className="pin-zone-breaks">
          <span>Up break {fmtPrice(cluster.up_break_level)}</span>
          <span>Down break {fmtPrice(cluster.down_break_level)}</span>
        </div>
      ) : null}

      {cluster.primary_strike != null && cluster.secondary_strike != null ? (
        <p className="pin-zone-members">
          Cluster members: {fmtPrice(cluster.primary_strike)} · {fmtPrice(cluster.secondary_strike)}
        </p>
      ) : null}

      {magnetShift && magnetPrevious != null ? (
        <span className="pin-magnet-shift" title="Magnet moved since last live poll">
          ↑ from {fmtPrice(magnetPrevious)}
          {magnetDeltaPts != null
            ? ` (${magnetDeltaPts >= 0 ? "+" : ""}${magnetDeltaPts.toFixed(0)} pts)`
            : null}
        </span>
      ) : null}

      {cluster.interpretation ? <p className="pin-zone-copy">{cluster.interpretation}</p> : null}
    </div>
  );
}

function PinSingleMagnet({
  pt,
  magnetShift,
  magnetPrevious,
  magnetDeltaPts,
}: {
  pt: NonNullable<DashboardSnapshot["pin_targets"]>;
  magnetShift: boolean;
  magnetPrevious: number | null | undefined;
  magnetDeltaPts: number | null | undefined;
}) {
  if (pt.primary_strike == null) return null;
  return (
    <div className="pin-primary">
      <span className="pin-primary-k">Primary magnet</span>
      <strong>{fmtPrice(pt.primary_strike)}</strong>
      <span className="pin-primary-tag">{pt.primary_label === "king" ? "King" : "Top weight"}</span>
      {magnetShift && magnetPrevious != null ? (
        <span className="pin-magnet-shift" title="Magnet moved since last live poll">
          ↑ from {fmtPrice(magnetPrevious)}
          {magnetDeltaPts != null
            ? ` (${magnetDeltaPts >= 0 ? "+" : ""}${magnetDeltaPts.toFixed(0)} pts)`
            : null}
        </span>
      ) : null}
    </div>
  );
}

export function PinPanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const pt = snapshot.pin_targets;

  if (!pt || !pt.rankings?.length) {
    return (
      <section className="rail-content pin-panel">
        <div className="panel-head">
          <h2>Pin magnets</h2>
          <span className="panel-hint">0DTE</span>
        </div>
        <p className="pin-panel-empty">No 0DTE chain — pin magnets need dte≤1 OI + GEX.</p>
      </section>
    );
  }

  const breakdown = pt.pin_score_breakdown ?? {};
  const magnetShift = snapshot.meta?.magnet_shift === true;
  const cluster = pt.pin_cluster;
  const showZone = cluster?.is_cluster === true;

  return (
    <section className="rail-content pin-panel">
      <div className="panel-head">
        <h2>{showZone ? "Pinning zone" : "Pin magnets"}</h2>
        <span className="panel-hint">{showZone ? "gamma cluster" : "|GEX|×OI weight"}</span>
      </div>

      <LivePinQualityBanner snapshot={snapshot} />

      <PinScoreGauge
        score={pt.pin_score ?? snapshot.metrics.pin_score}
        adjustedScore={pt.pin_score_adjusted}
        reliability={pt.pin_reliability}
        reliabilityDetail={pt.pin_reliability_detail}
      />

      {showZone && cluster ? (
        <PinZoneHero
          cluster={cluster}
          magnetShift={magnetShift}
          magnetPrevious={snapshot.meta?.magnet_previous}
          magnetDeltaPts={snapshot.meta?.magnet_delta_pts}
        />
      ) : (
        <PinSingleMagnet
          pt={pt}
          magnetShift={magnetShift}
          magnetPrevious={snapshot.meta?.magnet_previous}
          magnetDeltaPts={snapshot.meta?.magnet_delta_pts}
        />
      )}

      <section className="pin-section" aria-label="Pin score breakdown">
        <h3 className="pin-section-title">Pin score drivers</h3>
        <ul className="pin-breakdown">
          {Object.entries(BREAKDOWN_LABELS).map(([key, label]) => {
            const v = breakdown[key];
            if (v == null || Number.isNaN(v)) return null;
            return (
              <li key={key} className="pin-breakdown-row">
                <span className="pin-breakdown-k">{label}</span>
                <div className="pin-breakdown-track">
                  <div className="pin-breakdown-fill" style={{ width: `${Math.min(100, v)}%` }} />
                </div>
                <span className="pin-breakdown-v">{v.toFixed(0)}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="pin-section" aria-label="Magnet ranking">
        <h3 className="pin-section-title">
          {showZone ? "Zone strike ladder" : "Strike magnet ladder"}
        </h3>
        <ul className="pin-magnet-list">
          {pt.rankings.map((row) => (
            <MagnetRow key={row.strike} row={row} />
          ))}
        </ul>
        {pt.max_pain != null && !pt.rankings.some((r) => r.tags.includes("max_pain")) ? (
          <p className="pin-max-pain-ref">
            Max pain reference: <strong>{fmtPrice(pt.max_pain)}</strong>
          </p>
        ) : null}
      </section>

      <p className="pin-disclaimer">
        {showZone
          ? "Model-implied gamma concentration zone — not a precise price target or close probability."
          : pt.disclaimer}
      </p>
      <p className="pin-crosslink">Sizing &amp; entry gates → Playbook tab</p>
    </section>
  );
}
