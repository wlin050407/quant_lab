import { fmtPrice } from "../lib/format";
import {
  RESONANCE_AXIS_LABELS,
  divergenceSummary,
  hasVendorOverlay,
  resonanceTierClass,
  resonanceTierLabel,
} from "../lib/resonance";
import type { DashboardSnapshot } from "../types/snapshot";

export function VendorAlignmentCard({ snapshot }: { snapshot: DashboardSnapshot }) {
  const resonance = snapshot.meta?.resonance;
  const vendor = snapshot.meta?.vendor_levels;
  const ladder = snapshot.meta?.vendor_pin_ladder ?? [];
  const stream = snapshot.meta?.vendor_stream;
  const levels = snapshot.levels;

  if (!hasVendorOverlay(vendor, resonance)) return null;

  const axes = resonance?.axes ?? {};
  const axisEntries = Object.entries(RESONANCE_AXIS_LABELS)
    .map(([key, label]) => ({ key, label, value: axes[key] }))
    .filter((e) => e.value != null && !Number.isNaN(e.value));

  const flipDelta =
    levels?.flip != null && vendor?.zero_gamma != null
      ? Math.abs(levels.flip - vendor.zero_gamma)
      : null;
  const magnetDelta =
    levels?.king != null && vendor?.major_pos_oi != null
      ? Math.abs(levels.king - vendor.major_pos_oi)
      : null;

  return (
    <section className="vendor-alignment" aria-label="GEXBot vs local alignment">
      <div className="vendor-alignment-head">
        <h3 className="pin-section-title">Vendor alignment</h3>
        {resonance?.tier ? (
          <span className={`resonance-pill ${resonanceTierClass(resonance.tier)}`}>
            {resonanceTierLabel(resonance.tier)}
          </span>
        ) : null}
        {stream?.connection_status ? (
          <span className="vendor-stream-pill" title={stream.source ?? "gexbot"}>
            {stream.connection_status === "live" ? "WS" : stream.source ?? "REST"}
          </span>
        ) : null}
      </div>

      {resonance?.narrative ? <p className="vendor-alignment-narrative">{resonance.narrative}</p> : null}

      <div className="vendor-compare-grid">
        <div className="vendor-compare-row">
          <span className="vendor-compare-k">Flip</span>
          <span className="vendor-compare-local">{fmtPrice(levels?.flip)}</span>
          <span className="vendor-compare-vs">vs</span>
          <span className="vendor-compare-vendor">{fmtPrice(vendor?.zero_gamma)}</span>
          {flipDelta != null ? (
            <span className={`vendor-compare-delta${flipDelta > 15 ? " warn" : ""}`}>
              Δ{flipDelta.toFixed(0)}
            </span>
          ) : null}
        </div>
        <div className="vendor-compare-row">
          <span className="vendor-compare-k">Magnet</span>
          <span className="vendor-compare-local">{fmtPrice(levels?.king)}</span>
          <span className="vendor-compare-vs">vs</span>
          <span className="vendor-compare-vendor">{fmtPrice(vendor?.major_pos_oi)}</span>
          {magnetDelta != null ? (
            <span className={`vendor-compare-delta${magnetDelta > 1 ? " warn" : ""}`}>
              Δ{magnetDelta.toFixed(0)} stk
            </span>
          ) : null}
        </div>
      </div>

      {axisEntries.length > 0 ? (
        <ul className="resonance-axes">
          {axisEntries.map(({ key, label, value }) => (
            <li key={key} className="resonance-axis-row">
              <span className="resonance-axis-k">{label}</span>
              <div className="resonance-axis-track">
                <div
                  className="resonance-axis-fill"
                  style={{ width: `${Math.min(100, (value ?? 0) * 100)}%` }}
                />
              </div>
              <span className="resonance-axis-v">{Math.round((value ?? 0) * 100)}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {(resonance?.divergences?.length ?? 0) > 0 ? (
        <ul className="vendor-divergence-list">
          {resonance!.divergences.map((d) => (
            <li key={d.field} className={`vendor-divergence vendor-divergence--${d.severity}`}>
              {divergenceSummary(d)}
            </li>
          ))}
        </ul>
      ) : null}

      {ladder.length > 0 ? (
        <div className="vendor-prior-ladder">
          <span className="vendor-prior-k">GEXBot max_priors</span>
          <ul className="vendor-prior-rows">
            {ladder.slice(0, 3).map((row) => (
              <li key={row.strike} className="vendor-prior-row">
                <span>{fmtPrice(row.strike)}</span>
                <div className="vendor-prior-track">
                  <div
                    className="vendor-prior-fill"
                    style={{ width: `${Math.min(100, (row.weight_norm ?? 0) * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
