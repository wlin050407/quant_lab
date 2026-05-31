import { fmtPrice } from "../lib/format";
import type { DashboardSnapshot } from "../types/snapshot";
import { PinScoreGauge } from "./PinScoreGauge";function fmtMult(v: number): string {
  return `${v.toFixed(2)}×`;
}

function phaseClass(phase: string): string {
  if (phase === "entry_window") return "phase-entry";
  if (phase === "manage") return "phase-manage";
  if (phase === "read_map" || phase === "pre_entry") return "phase-watch";
  return "phase-idle";
}

export function PlaybookPanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const pb = snapshot.pin_playbook;

  if (!pb) {
    return (
      <section className="rail-content playbook-panel">
        <div className="panel-head">
          <h2>Pin Playbook</h2>
          <span className="panel-hint">PIN_PLAY_SPEC</span>
        </div>
        <p className="playbook-fallback">Playbook unavailable for this snapshot.</p>
      </section>
    );
  }

  return (
    <section className="rail-content playbook-panel">
      <div className="panel-head">
        <h2>Pin Playbook</h2>
        <span className="panel-hint">Phase 4 · spec §3</span>
      </div>

      <div className={`playbook-phase ${phaseClass(pb.session_phase)}`}>
        <div className="playbook-phase-top">
          <span className="playbook-phase-title">{pb.phase_title}</span>
          <span className="playbook-clock">
            {pb.clock_et} ET · {pb.hours_to_close.toFixed(1)}h to close
          </span>
        </div>
        <p className="playbook-phase-detail">{pb.phase_detail}</p>
      </div>

      <PinScoreGauge score={snapshot.metrics.pin_score} />

      <div className={`playbook-size${pb.actionable ? " actionable" : ""}`}>
        <span className="playbook-size-label">Position size</span>
        <strong className="playbook-size-value">{fmtMult(pb.size_multiplier)}</strong>
        <span className="playbook-size-breakdown">
          pin {fmtMult(pb.pin_multiplier)} · γ {fmtMult(pb.regime_multiplier)} · gate{" "}
          {fmtMult(pb.gate_multiplier)}
        </span>
      </div>

      <p className="playbook-summary">{pb.summary}</p>

      <section className="playbook-section" aria-label="Gate checks">
        <h3 className="playbook-section-title">Gates</h3>
        <ul className="playbook-checks">
          {pb.checks.map((c) => (
            <li key={c.id} className={`playbook-check${c.passed ? " pass" : " fail"}`}>
              <span className="playbook-check-icon" aria-hidden>
                {c.passed ? "✓" : "✕"}
              </span>
              <div>
                <strong>{c.label}</strong>
                <p>{c.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {pb.structure ? (
        <section className="playbook-section" aria-label="Proposed structure">
          <h3 className="playbook-section-title">Structure</h3>
          <div className="playbook-structure">
            <div className="playbook-structure-row">
              <span>Body @ {fmtPrice(pb.structure.center)}</span>
              <span className="chip chip-muted">{pb.structure.center_source}</span>
            </div>
            <div className="playbook-structure-legs">
              <span>{pb.structure.long_put.toFixed(0)}P</span>
              <span className="playbook-body">short fly</span>
              <span>{pb.structure.long_call.toFixed(0)}C</span>
            </div>
            <p className="playbook-structure-note">Wing ±{pb.structure.wing_width.toFixed(0)}pt</p>
          </div>
        </section>
      ) : null}

      <section className="playbook-section" aria-label="Exit rules">
        <h3 className="playbook-section-title">Exit rules</h3>
        <ul className="playbook-exits">
          {pb.exits.map((e) => (
            <li key={e.id} className={`playbook-exit${e.active ? " active" : ""}`}>
              <span className="playbook-exit-dot" aria-hidden />
              <div>
                <strong>{e.label}</strong>
                <p>{e.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {pb.trinity_score != null ? (
        <div className="playbook-trinity">
          Trinity {Math.round(pb.trinity_score)}/100 · {pb.trinity_direction ?? "—"}
        </div>
      ) : null}
    </section>
  );
}
