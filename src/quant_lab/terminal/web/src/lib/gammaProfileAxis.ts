export type BandXTickKind = "major" | "minor" | "spot" | "flip";

export interface BandXTickSpec {
  spot: number;
  kind: BandXTickKind;
  showLabel: boolean;
}

export function niceSpotStep(range: number, targetCount: number): number {
  const rough = range / Math.max(targetCount, 2);
  if (rough <= 0) return 1;
  const exp = Math.floor(Math.log10(rough));
  const frac = rough / 10 ** exp;
  const niceFrac = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  return niceFrac * 10 ** exp;
}

function roundSpot(s: number): number {
  return Math.round(s * 100) / 100;
}

function near(a: number, b: number, tol: number): boolean {
  return Math.abs(a - b) < tol;
}

/** Hypothetical-spot X axis for regime band (±10% scan). */
export function buildBandSpotTicks(
  minS: number,
  maxS: number,
  spot: number,
  flipLevel: number | null,
  compact: boolean,
): BandXTickSpec[] {
  const range = maxS - minS;
  if (range <= 0) return [{ spot: minS, kind: "major", showLabel: true }];

  const majorStep = niceSpotStep(range, compact ? 12 : 18);
  let minorStep = majorStep / 2;
  if (range >= 400 && minorStep > 50) minorStep = 50;
  else if (range >= 200 && minorStep > 25) minorStep = 25;

  const majorSpots = new Set<number>();
  for (let s = Math.ceil(minS / majorStep) * majorStep; s <= maxS + 1e-6; s += majorStep) {
    majorSpots.add(roundSpot(s));
  }
  majorSpots.add(roundSpot(minS));
  majorSpots.add(roundSpot(maxS));

  const bySpot = new Map<number, BandXTickSpec>();

  for (let s = Math.ceil(minS / minorStep) * minorStep; s <= maxS + 1e-6; s += minorStep) {
    const key = roundSpot(s);
    if (majorSpots.has(key)) {
      bySpot.set(key, { spot: key, kind: "major", showLabel: true });
    } else {
      bySpot.set(key, { spot: key, kind: "minor", showLabel: false });
    }
  }

  bySpot.set(roundSpot(spot), { spot: roundSpot(spot), kind: "spot", showLabel: true });
  if (flipLevel != null && flipLevel >= minS && flipLevel <= maxS) {
    bySpot.set(roundSpot(flipLevel), { spot: roundSpot(flipLevel), kind: "flip", showLabel: true });
  }

  const anchorTol = Math.min(minorStep * 0.35, majorStep * 0.2);
  const anchors = [roundSpot(spot)];
  if (flipLevel != null && flipLevel >= minS && flipLevel <= maxS) {
    anchors.push(roundSpot(flipLevel));
  }

  for (const [key, tick] of [...bySpot.entries()]) {
    if (tick.kind === "spot" || tick.kind === "flip") continue;
    if (anchors.some((a) => near(key, a, anchorTol))) {
      bySpot.delete(key);
    }
  }

  return [...bySpot.values()].sort((a, b) => a.spot - b.spot);
}

export type XTickAnchor = "start" | "middle" | "end";

export function xTickAnchor(index: number, total: number): XTickAnchor {
  if (index === 0) return "start";
  if (index === total - 1) return "end";
  return "middle";
}

export function fmtStrikeAxis(s: number): string {
  return s >= 1000 ? s.toFixed(0) : s.toFixed(1);
}
