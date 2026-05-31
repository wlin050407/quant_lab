import { regimeDesc, regimeTitle } from "../lib/format";
import type { DashboardSnapshot } from "../types/snapshot";

export function RegimePanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const r = snapshot.regime;
  const g = snapshot.gate;
  const s = snapshot.strategy;

  return (
    <section className="rail-content regime-panel">
      <div className="panel-head">
        <h2>Regime Engine</h2>
        <span className="panel-hint">FlashAlpha</span>
      </div>
      <div className="regime-card">
        <div className={`regime-icon ${r}`} />
        <div>
          <div className="regime-title">{regimeTitle(r)}</div>
          <div className="regime-desc">{regimeDesc(r)}</div>
        </div>
      </div>
      <div className={`gate ${g.should_trade ? "ok" : "no"}`}>
        <span className="gate-icon">{g.should_trade ? "✓" : "✕"}</span>
        <div>
          <strong>{g.should_trade ? "Tradeable" : "Sit out"}</strong>
          <p>{g.reason}</p>
        </div>
      </div>
      <div className="strategy-card">
        <div className="strategy-head">
          <h3>{s.title}</h3>
          <span className="chip chip-conf">{s.confidence}</span>
        </div>
        <p>{s.summary}</p>
        <div className="strategy-structures">
          {(s.structures ?? []).map((x) => (
            <span key={x} className="chip">
              {x}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
