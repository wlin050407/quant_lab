import { fmtPrice } from "../lib/format";
import type { AttractionRow, StructureSnapshot } from "../types/snapshot";

const SIDE_LABELS: Record<string, string> = {
  pin: "Pin",
  up: "Upside",
  down: "Downside",
};

function sideClass(side: string): string {
  if (side === "pin") return "attraction-side--pin";
  if (side === "up") return "attraction-side--up";
  return "attraction-side--down";
}

function AttractionBar({ row }: { row: AttractionRow }) {
  const side = row.side ?? "pin";
  return (
    <li className={`attraction-row${row.visual_strength >= 80 ? " attraction-row--primary" : ""}`}>
      <div className="attraction-row-head">
        <span className="attraction-strike">{fmtPrice(row.level)}</span>
        <span className={`attraction-side ${sideClass(side)}`}>{SIDE_LABELS[side] ?? side}</span>
        <span className="attraction-score">{row.score.toFixed(0)}</span>
      </div>
      <div className="attraction-bar-track">
        <div
          className="attraction-bar-fill"
          style={{ width: `${Math.min(100, row.visual_strength)}%` }}
        />
      </div>
      {row.sources?.length ? (
        <span className="attraction-sources">{row.sources.slice(0, 2).join(" · ")}</span>
      ) : null}
    </li>
  );
}

export function AttractionProfileCard({ structure }: { structure: StructureSnapshot | null | undefined }) {
  if (!structure?.attraction_profile?.length) {
    return (
      <section className="pin-section attraction-panel" aria-label="MM attraction profile">
        <h3 className="pin-section-title">MM attraction profile</h3>
        <p className="attraction-empty">GEXBot structure unavailable — enable vendor WS for MM lane.</p>
      </section>
    );
  }

  const primary = structure.primary_mm_target;
  const weights = structure.family_weights;
  const exec = structure.execution_state?.replace(/_/g, " ");

  return (
    <section className="pin-section attraction-panel" aria-label="MM attraction profile">
      <div className="attraction-head">
        <h3 className="pin-section-title">MM attraction profile</h3>
        <span className="panel-hint">{structure.structure_version ?? "p0"}</span>
      </div>

      {primary ? (
        <div className="attraction-primary">
          <span className="attraction-primary-k">Primary target</span>
          <strong>{fmtPrice(primary.level)}</strong>
          <span className="chip chip-muted">{primary.score.toFixed(0)} conf</span>
        </div>
      ) : null}

      <div className="attraction-meta">
        <span className={`chip chip-regime chip-regime--${structure.regime}`}>{structure.regime}</span>
        <span className="chip chip-muted">{structure.momentum_state?.replace(/_/g, " ")}</span>
        {exec ? <span className="chip chip-muted">{exec}</span> : null}
      </div>

      {weights ? (
        <p className="attraction-weights" title="Pin Play downweights vanna vs MM reference for fly center">
          Family mix γ {Math.round(weights.gamma * 100)}% · v {Math.round(weights.vex * 100)}% · iv{" "}
          {Math.round(weights.iv * 100)}%
        </p>
      ) : null}

      <ul className="attraction-list">
        {structure.attraction_profile.slice(0, 8).map((row) => (
          <AttractionBar key={row.level} row={row} />
        ))}
      </ul>

      <p className="attraction-disclaimer">
        Structure lane (GEXBot) — separate from local GEX heatmap. Playbook fly center uses fused pin_center.
      </p>
    </section>
  );
}
