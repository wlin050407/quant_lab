import type { DashboardSnapshot } from "../types/snapshot";
import { distPct } from "../lib/heatmap";
import { DEALER_LEVELS, isValidLevel } from "../lib/levels";
import { fmtPct, fmtPrice } from "../lib/format";
import { PanelShell } from "./PanelShell";

const LADDER_ENTRIES = DEALER_LEVELS;
export function PriceLadder({ snapshot }: { snapshot: DashboardSnapshot }) {
  const spot = snapshot.spot;
  const L = snapshot.levels;
  const M = snapshot.metrics;

  if (spot == null || !Number.isFinite(spot)) {
    return (
      <PanelShell className="ladder-panel" spotlightColor="rgba(20, 184, 166, 0.05)">
        <div className="panel-head">
          <h2>Price Ladder</h2>
        </div>
        <p className="panel-empty-hint">Levels appear when the session chain is available.</p>
      </PanelShell>
    );
  }

  const entries = LADDER_ENTRIES.map((e) => ({ ...e, val: L[e.key] }))
    .filter((e) => isValidLevel(e.val as number | null))
    .sort((a, b) => (b.val as number) - (a.val as number));

  return (
    <PanelShell className="ladder-panel" spotlightColor="rgba(20, 184, 166, 0.05)">
      <div className="panel-head">
        <h2>Price Ladder</h2>
        <span className="panel-hint">Levels</span>
      </div>
      <div className="price-ladder">
        {entries.map((e) => {
          const d = distPct(spot, e.val);
          const side = d != null && d > 0 ? "above" : d != null && d < 0 ? "below" : "at";
          return (
            <div key={e.key} className={`ladder-row ${e.cls} ${side}`}>
              <span className="ladder-lbl">{e.label}</span>
              <span className="ladder-px">{fmtPrice(e.val)}</span>
              <span className="ladder-dist">{d != null ? fmtPct(d) : ""}</span>
            </div>
          );
        })}
        <div className="ladder-spot">
          <span className="ladder-lbl">Spot</span>
          <span className="ladder-px">{fmtPrice(spot)}</span>
          <span className="ladder-dist">NOW</span>
        </div>
      </div>
      <div className="em-band">
        {L.expected_move != null ? (
          <>
            <div className="em-title">Expected Move ±{L.expected_move.toFixed(2)}</div>
            <div className="em-range">
              {fmtPrice(L.expected_lower)} — {fmtPrice(L.expected_upper)}
            </div>
          </>
        ) : (
          "Expected move unavailable"
        )}
      </div>
      <div className="metrics-compact">
        <div>
          <label>P/C OI</label>
          <span>{M.pcr_oi != null ? M.pcr_oi.toFixed(2) : "—"}</span>
        </div>
        <div>
          <label>OI conc</label>
          <span>{M.oi_conc_dte1 != null ? `${(M.oi_conc_dte1 * 100).toFixed(0)}%` : "—"}</span>
        </div>
      </div>
    </PanelShell>
  );
}
