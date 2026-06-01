import { useId, useMemo, useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

import { fmtGexBn, fmtPrice } from "../lib/format";
import {
  buildBandSpotTicks,
  fmtStrikeAxis,
  xTickAnchor,
} from "../lib/gammaProfileAxis";
import {
  getChartPalette,
} from "../lib/chartPalette";
import type { GammaProfilePoint, Levels } from "../types/snapshot";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { useTheme } from "../hooks/useTheme";

gsap.registerPlugin(useGSAP);

const VIEW_W = 800;
const VIEW_H = 210;
const VIEW_H_COMPACT = 96;
/** Wide panoramic viewBox — matches regime band container aspect (~8:1). */
const VIEW_W_BAND = 1000;
const VIEW_H_BAND = 136;
const PAD = { top: 18, right: 16, bottom: 30, left: 52 };
const PAD_COMPACT = { top: 12, right: 10, bottom: 18, left: 36 };
const PAD_BAND = { top: 10, right: 12, bottom: 42, left: 34 };

function areaToZero(pts: { x: number; y: number }[], zeroY: number): string {
  if (!pts.length) return "";
  const head = pts
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(" ");
  const last = pts[pts.length - 1];
  const first = pts[0];
  return `${head} L ${last.x.toFixed(2)} ${zeroY} L ${first.x.toFixed(2)} ${zeroY} Z`;
}

function nearestNetGexBn(curve: GammaProfilePoint[], spot: number): number | null {
  if (!curve.length) return null;
  let best = curve[0];
  let bestDist = Math.abs(curve[0].spot - spot);
  for (const p of curve) {
    const d = Math.abs(p.spot - spot);
    if (d < bestDist) {
      best = p;
      bestDist = d;
    }
  }
  return best.net_gex_bn;
}

interface GammaProfileChartProps {
  curve: GammaProfilePoint[];
  spot: number;
  levels: Levels | null;
  flipLevel: number | null;
  animateKey: string | number;
  embedded?: boolean;
  compact?: boolean;
  /** Regime toolbar band — wide strip with spot axis + level pills. */
  band?: boolean;
  fillWidth?: boolean;
}

export function GammaProfileChart({
  curve,
  spot,
  levels,
  flipLevel,
  animateKey,
  embedded = false,
  compact = false,
  band = false,
  fillWidth = false,
}: GammaProfileChartProps) {
  const rootRef = useRef<SVGSVGElement>(null);
  const reducedMotion = useReducedMotion();
  const { theme } = useTheme();
  const palette = useMemo(() => getChartPalette(), [theme]);
  const uid = useId().replace(/:/g, "");

  const viewW = band ? VIEW_W_BAND : VIEW_W;
  const viewH = band ? VIEW_H_BAND : compact ? VIEW_H_COMPACT : VIEW_H;
  const pad = band ? PAD_BAND : compact ? PAD_COMPACT : PAD;
  const showMarkers = !compact || band;
  const bandCompact = band && compact;

  const model = useMemo(() => {
    if (curve.length < 2) return null;
    const spots = curve.map((p) => p.spot);
    const vals = curve.map((p) => p.net_gex_bn);
    const minS = Math.min(...spots);
    const maxS = Math.max(...spots);
    const maxAbs = Math.max(...vals.map(Math.abs), 0.01);
    const innerW = viewW - pad.left - pad.right;
    const innerH = viewH - pad.top - pad.bottom;
    const zeroY = pad.top + innerH / 2;
    const halfH = innerH / 2 - 4;
    const plotBottom = viewH - pad.bottom;

    const xScale = (s: number) => pad.left + ((s - minS) / (maxS - minS)) * innerW;
    const yScale = (v: number) => zeroY - (v / maxAbs) * halfH;

    const linePath = curve
      .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.spot).toFixed(2)} ${yScale(p.net_gex_bn).toFixed(2)}`)
      .join(" ");

    const linePts = curve.map((p) => ({
      x: xScale(p.spot),
      y: yScale(p.net_gex_bn),
      bn: p.net_gex_bn,
    }));
    const posPts = linePts.map((p) => ({ x: p.x, y: p.bn >= 0 ? p.y : zeroY }));
    const negPts = linePts.map((p) => ({ x: p.x, y: p.bn < 0 ? p.y : zeroY }));
    const posArea = areaToZero(posPts, zeroY);
    const negArea = areaToZero(negPts, zeroY);

    const flipX =
      flipLevel != null && flipLevel >= minS && flipLevel <= maxS ? xScale(flipLevel) : null;

    const xTickSpecs = band ? buildBandSpotTicks(minS, maxS, spot, flipLevel, bandCompact) : [];
    const labeledTicks = xTickSpecs.filter((t) => t.showLabel);

    return {
      linePath,
      posArea,
      negArea,
      zeroY,
      plotBottom,
      plotLeft: pad.left,
      plotRight: viewW - pad.right,
      spotX: xScale(spot),
      flipX,
      netAtSpot: nearestNetGexBn(curve, spot),
      yTicks: [
        { y: yScale(maxAbs), label: fmtGexBn(maxAbs) },
        { y: zeroY, label: "0" },
        { y: yScale(-maxAbs), label: fmtGexBn(-maxAbs) },
      ],
      xTicks: xTickSpecs.map((spec) => {
        const labelIdx = labeledTicks.findIndex((t) => t.spot === spec.spot);
        const anchor =
          !spec.showLabel || spec.kind === "flip" || spec.kind === "spot"
            ? "middle"
            : xTickAnchor(labelIdx, labeledTicks.length);
        return {
          x: xScale(spec.spot),
          label: fmtStrikeAxis(spec.spot),
          kind: spec.kind,
          showLabel: spec.showLabel,
          anchor,
        };
      }),
      points: curve.map((p) => ({
        x: xScale(p.spot),
        y: yScale(p.net_gex_bn),
        spot: p.spot,
        bn: p.net_gex_bn,
      })),
      kingStrike: levels?.king ?? null,
      kingX:
        levels?.king != null && levels.king >= minS && levels.king <= maxS
          ? xScale(levels.king)
          : null,
    };
  }, [curve, spot, levels?.king, flipLevel, compact, band, bandCompact, viewW, viewH, pad]);

  useGSAP(
    () => {
      if (!model || reducedMotion || !rootRef.current) return;
      const line = rootRef.current.querySelector<SVGPathElement>(".gamma-profile-line");
      const areas = rootRef.current.querySelectorAll<SVGPathElement>(".gamma-profile-area");
      const dots = rootRef.current.querySelectorAll<SVGCircleElement>(".gamma-profile-dot");

      areas.forEach((path) => {
        gsap.fromTo(path, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power2.out" });
      });
      if (line) {
        const len = line.getTotalLength();
        gsap.fromTo(
          line,
          { strokeDasharray: len, strokeDashoffset: len },
          { strokeDashoffset: 0, duration: 0.7, ease: "power2.inOut" },
        );
      }
      if (dots.length) {
        gsap.fromTo(
          dots,
          { opacity: 0, scale: 0 },
          { opacity: 1, scale: 1, duration: 0.35, stagger: 0.015, ease: "power2.out" },
        );
      }
    },
    { dependencies: [model, animateKey, reducedMotion], scope: rootRef },
  );

  if (!model) return null;

  const posGrad = `gamma-profile-fill-pos-${uid}`;
  const negGrad = `gamma-profile-fill-neg-${uid}`;

  const aspectRatio =
    band || fillWidth ? "xMidYMid slice" : "xMidYMid meet";

  return (
    <div
      className={`gamma-profile-wrap${embedded ? " gamma-profile-wrap--embedded" : ""}${band ? " gamma-profile-wrap--band" : ""}`}
    >
      {embedded && band ? (
        <div className="regime-band-head">
          <div className="regime-band-head-left">
            <span className="regime-band-title">Gamma regime</span>
            <span className="regime-band-hint">what-if net GEX · ±10% spot</span>
          </div>
          <div className="regime-band-stats">
            {model.netAtSpot != null ? (
              <span className="regime-band-stat">
                @ spot <strong>{fmtGexBn(model.netAtSpot)}</strong>
              </span>
            ) : null}
            {flipLevel != null ? (
              <span className="regime-band-stat regime-band-stat--flip">
                Flip <strong>{fmtPrice(flipLevel)}</strong>
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
      {!embedded ? (
        <div className="exposure-profile-head">
          <span className="exposure-profile-title">Gamma profile</span>
          <span className="exposure-profile-metric">Total net GEX · Bn / 1% move</span>
          <span className="exposure-profile-spot">
            Spot <strong>{fmtPrice(spot)}</strong>
            {flipLevel != null ? (
              <>
                {" "}
                · Flip <strong>{fmtPrice(flipLevel)}</strong>
              </>
            ) : null}
          </span>
        </div>
      ) : null}
      <svg
        ref={rootRef}
        className={`gamma-profile-chart${compact ? " gamma-profile-chart--compact" : ""}${band ? " gamma-profile-chart--band" : ""}`}
        viewBox={`0 0 ${viewW} ${viewH}`}
        preserveAspectRatio={aspectRatio}
        role="img"
        aria-label="SpotGamma-style gamma profile: total dealer net GEX versus hypothetical spot"
      >
        <defs>
          <linearGradient id={posGrad} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={palette.CHART_GAMMA_FILL_POS.top.color} stopOpacity={palette.CHART_GAMMA_FILL_POS.top.opacity} />
            <stop offset="100%" stopColor={palette.CHART_GAMMA_FILL_POS.base.color} stopOpacity={palette.CHART_GAMMA_FILL_POS.base.opacity} />
          </linearGradient>
          <linearGradient id={negGrad} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={palette.CHART_GAMMA_FILL_NEG.top.color} stopOpacity={palette.CHART_GAMMA_FILL_NEG.top.opacity} />
            <stop offset="100%" stopColor={palette.CHART_GAMMA_FILL_NEG.base.color} stopOpacity={palette.CHART_GAMMA_FILL_NEG.base.opacity} />
          </linearGradient>
        </defs>
        <rect x={0} y={0} width={viewW} height={viewH} className="profile-bg" rx={band ? 0 : 6} />

        {model.yTicks.map((tick) => (
          <g key={tick.label} className="profile-ytick">
            <line
              x1={model.plotLeft}
              y1={tick.y}
              x2={model.plotRight}
              y2={tick.y}
              className={`profile-grid-line${tick.label === "0" ? " profile-grid-line--zero" : ""}`}
            />
            {!compact || band ? (
              <text x={6} y={tick.y + 3} className="profile-axis-label profile-axis-label--y">
                {tick.label}
              </text>
            ) : null}
          </g>
        ))}

        {band ? (
          <line
            x1={model.plotLeft}
            y1={model.zeroY}
            x2={model.plotRight}
            y2={model.zeroY}
            className="profile-zero-axis"
          />
        ) : null}

        <path d={model.posArea} className="gamma-profile-area gamma-profile-area--pos" fill={`url(#${posGrad})`} />
        <path d={model.negArea} className="gamma-profile-area gamma-profile-area--neg" fill={`url(#${negGrad})`} />
        {!band
          ? model.points.map((p) => (
              <circle
                key={p.spot}
                cx={p.x}
                cy={p.y}
                r={compact ? 1.6 : 2.2}
                className={`gamma-profile-dot${p.bn >= 0 ? " pos" : " neg"}`}
              />
            ))
          : null}
        <path d={model.linePath} className="gamma-profile-line" fill="none" />

        {model.flipX != null ? (
          <g className="profile-marker profile-marker-flip">
            <line
              x1={model.flipX}
              y1={pad.top}
              x2={model.flipX}
              y2={model.plotBottom}
              className="profile-marker-line"
            />
            {showMarkers && !band ? (
              <text x={model.flipX} y={viewH - 6} className="profile-marker-label">
                Flip
              </text>
            ) : null}
          </g>
        ) : null}

        {model.kingX != null ? (
          <g className="profile-marker profile-marker-king">
            <line
              x1={model.kingX}
              y1={pad.top}
              x2={model.kingX}
              y2={model.plotBottom}
              className="profile-marker-line profile-marker-line-king"
            />
            {showMarkers && band ? (
              <>
                <rect
                  x={model.kingX - 16}
                  y={pad.top + 1}
                  width={32}
                  height={12}
                  rx={2}
                  className="profile-marker-pill profile-marker-pill--king"
                />
                <text x={model.kingX} y={pad.top + 10} className="profile-marker-label">
                  King
                </text>
              </>
            ) : null}
          </g>
        ) : null}

        {band ? (
          <g className="profile-x-axis">
            <line
              x1={model.plotLeft}
              y1={model.plotBottom}
              x2={model.plotRight}
              y2={model.plotBottom}
              className="profile-x-axis-line"
            />
            {model.xTicks.map((tick) => (
              <g
                key={`${tick.x}-${tick.kind}-${tick.label}`}
                className={`profile-xtick profile-xtick--${tick.kind}`}
              >
                <line
                  x1={tick.x}
                  y1={model.plotBottom}
                  x2={tick.x}
                  y2={model.plotBottom + (tick.kind === "minor" ? 3 : tick.kind === "flip" ? 9 : 5)}
                  className={`profile-x-tick-mark${tick.kind === "flip" ? " profile-x-tick-mark--flip" : ""}${tick.kind === "spot" ? " profile-x-tick-mark--spot" : ""}`}
                />
                {tick.showLabel && tick.kind === "flip" ? (
                  <>
                    <text
                      x={tick.x}
                      y={model.plotBottom + 17}
                      textAnchor="middle"
                      className="profile-axis-label profile-axis-label--flip"
                    >
                      {tick.label}
                    </text>
                    <text
                      x={tick.x}
                      y={model.plotBottom + 29}
                      textAnchor="middle"
                      className="profile-axis-flip-tag"
                    >
                      Flip
                    </text>
                  </>
                ) : null}
                {tick.showLabel && tick.kind !== "flip" ? (
                  <text
                    x={tick.x}
                    y={model.plotBottom + 17}
                    textAnchor={tick.anchor}
                    className={`profile-axis-label profile-axis-label--x profile-axis-label--${tick.kind}`}
                  >
                    {tick.label}
                  </text>
                ) : null}
              </g>
            ))}
          </g>
        ) : null}

        <g className="profile-spot">
          <line
            x1={model.spotX}
            y1={band ? pad.top - 1 : pad.top - 2}
            x2={model.spotX}
            y2={model.plotBottom}
            className="profile-spot-line"
          />
          {showMarkers && band ? (
            <polygon
              points={`${model.spotX - 4},${pad.top - 1} ${model.spotX + 4},${pad.top - 1} ${model.spotX},${pad.top + 5}`}
              className="profile-spot-arrow"
            />
          ) : null}
          {showMarkers ? (
            <text
              x={model.spotX + (band ? 5 : 4)}
              y={pad.top + (band ? 7 : 8)}
              className="profile-spot-label"
            >
              NOW
            </text>
          ) : null}
        </g>
      </svg>
      {!embedded ? (
        <p className="gamma-profile-caption">
          SpotGamma profile view: recomputes Γ at hypothetical spot (±10%). Zero crossing ≈ gamma flip.
          Strike plot below uses the same cohort at current spot.
        </p>
      ) : null}
    </div>
  );
}
