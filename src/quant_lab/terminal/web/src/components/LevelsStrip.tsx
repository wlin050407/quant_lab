import { fmtPrice } from "../lib/format";
import type { Levels } from "../types/snapshot";

const ENTRIES: { key: keyof Levels; label: string; cls: string }[] = [
  { key: "call_wall", label: "C-Wall", cls: "call" },
  { key: "king", label: "King", cls: "king" },
  { key: "flip", label: "Flip", cls: "flip" },
  { key: "put_wall", label: "P-Wall", cls: "put" },
];

export function LevelsStrip({ levels, spot }: { levels: Levels | null; spot: number }) {
  if (!levels) return null;

  return (
    <div className="levels-strip" aria-label="Key positioning levels">
      <span className="levels-strip-spot">
        Spot <strong>{fmtPrice(spot)}</strong>
      </span>
      {ENTRIES.map((e) => {
        const val = levels[e.key];
        if (val == null || Number.isNaN(val)) return null;
        return (
          <span key={e.key} className={`levels-chip ${e.cls}`}>
            <span className="levels-chip-lbl">{e.label}</span>
            <span className="levels-chip-val">{fmtPrice(val)}</span>
          </span>
        );
      })}
    </div>
  );
}
