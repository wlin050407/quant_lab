import type { ReactNode } from "react";
import { regimeShort, vannaLabel } from "../lib/format";
import type { DashboardSnapshot, ExposureMetric } from "../types/snapshot";

interface StatusStripProps {
  snapshot: DashboardSnapshot;
  metric: ExposureMetric;
}

export function StatusStrip({ snapshot, metric }: StatusStripProps) {
  const M = snapshot.metrics;
  const t = snapshot.trinity;
  const g = snapshot.gate;
  const pin = M.pin_score != null ? Math.round(M.pin_score) : "—";

  const trinityChip =
    t.score != null && t.n_symbols >= 2 ? (
      <span className="chip chip-gold">Trinity {Math.round(t.score)}</span>
    ) : (
      <span className="chip chip-muted">Trinity N/A</span>
    );

  let netChips: ReactNode;
  if (metric === "compare") {
    netChips = (
      <>
        <span className="chip">
          GEX {M.net_gex_dte1_bn != null ? `${M.net_gex_dte1_bn.toFixed(2)} Bn` : "—"}
        </span>
        <span className="chip">
          VEX {M.net_vex_dte1_bn != null ? `${M.net_vex_dte1_bn.toFixed(2)} Bn` : "—"}
        </span>
        {M.vanna_interpretation ? (
          <span className="chip chip-muted">
            {vannaLabel(M.vanna_interpretation) ?? M.vanna_interpretation}
          </span>
        ) : null}
      </>
    );
  } else if (metric === "vex") {
    netChips = (
      <>
        <span className="chip">
          0DTE VEX {M.pct_vex_dte1 != null ? `${M.pct_vex_dte1.toFixed(0)}%` : "—"}
        </span>
        <span className="chip">
          Net {M.net_vex_dte1_bn != null ? `${M.net_vex_dte1_bn.toFixed(2)} Bn` : "—"}
        </span>
        {M.vanna_interpretation ? (
          <span className="chip chip-muted">
            {vannaLabel(M.vanna_interpretation) ?? M.vanna_interpretation}
          </span>
        ) : null}
      </>
    );
  } else {
    netChips = (
      <>
        <span className="chip">
          0DTE GEX {M.pct_gex_dte1 != null ? `${M.pct_gex_dte1.toFixed(0)}%` : "—"}
        </span>
        <span className="chip">
          Net {M.net_gex_dte1_bn != null ? `${M.net_gex_dte1_bn.toFixed(2)} Bn` : "—"}
        </span>
      </>
    );
  }

  return (
    <div className="status-strip">
      <span className={`chip chip-regime ${snapshot.regime}`}>{regimeShort(snapshot.regime)}</span>
      <span className="chip">Pin {pin}</span>
      {netChips}
      {trinityChip}
      <span className={`chip ${g.should_trade ? "chip-ok" : "chip-no"}`}>
        {g.should_trade ? "Tradeable" : "Sit out"}
      </span>
    </div>
  );
}
