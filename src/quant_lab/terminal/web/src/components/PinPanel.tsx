import { fmtGexBn, fmtPct, fmtPrice } from "../lib/format";
import type { DashboardSnapshot, PinMagnetRow } from "../types/snapshot";
import { PinScoreGauge } from "./PinScoreGauge";

const BREAKDOWN_LABELS: Record<string, string> = {
  oi_concentration: "OI concentration",
  magnet_proximity: "Magnet proximity",
  time_remaining: "Time to close",
  gamma_magnitude: "Gamma magnitude",
};

function tagLabel(tag: string): string {
  if (tag === "king") return "King";
  if (tag === "max_pain") return "Max pain";
  return tag;
}

function MagnetRow({ row }: { row: PinMagnetRow }) {
  const weight = row.weight_pct ?? 0;
  return (
    <li className={`pin-magnet-row${weight <= 0 ? " pin-magnet-row--anchor" : ""}`}>
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

export function PinPanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const pt = snapshot.pin_targets;

  if (!pt || !pt.rankings?.length) {
    return (
      <section className="rail-content pin-panel">
        <div className="panel-head">
          <h2>Pin Magnets</h2>
          <span className="panel-hint">0DTE</span>
        </div>
        <p className="pin-panel-empty">No 0DTE chain — pin magnets need dte≤1 OI + GEX.</p>
      </section>
    );
  }

  const breakdown = pt.pin_score_breakdown ?? {};

  return (
    <section className="rail-content pin-panel">
      <div className="panel-head">
        <h2>Pin Magnets</h2>
        <span className="panel-hint">|GEX|×OI weight</span>
      </div>

      <PinScoreGauge score={pt.pin_score ?? snapshot.metrics.pin_score} />

      {pt.primary_strike != null ? (
        <div className="pin-primary">
          <span className="pin-primary-k">Primary magnet</span>
          <strong>{fmtPrice(pt.primary_strike)}</strong>
          <span className="pin-primary-tag">{pt.primary_label === "king" ? "King" : "Top weight"}</span>
        </div>
      ) : null}

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
        <h3 className="pin-section-title">Strike magnet ladder</h3>
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

      <p className="pin-disclaimer">{pt.disclaimer}</p>
      <p className="pin-crosslink">Sizing &amp; entry gates → Playbook tab</p>
    </section>
  );
}
