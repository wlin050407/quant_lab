import { useId, useMemo, useRef, useEffect } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

import { buildExposureProfileModel } from "../lib/exposureProfile";
import { getChartPalette } from "../lib/chartPalette";
import { fmtGexBn, fmtPrice } from "../lib/format";
import type { ExposureMetric, HeatmapRow, Levels } from "../types/snapshot";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { useTheme } from "../hooks/useTheme";

gsap.registerPlugin(useGSAP);

interface ExposureProfileChartProps {
  rows: HeatmapRow[];
  spot: number;
  levels: Levels | null;
  metric: ExposureMetric;
  animateKey: string | number;
  compact?: boolean;
  embedded?: boolean;
  fillWidth?: boolean;
}

export function ExposureProfileChart({
  rows,
  spot,
  levels,
  metric,
  animateKey,
  compact = false,
  embedded = false,
  fillWidth = false,
}: ExposureProfileChartProps) {
  const rootRef = useRef<SVGSVGElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();
  const { theme } = useTheme();
  const palette = useMemo(() => getChartPalette(), [theme]);
  const uid = useId().replace(/:/g, "");

  const model = useMemo(
    () => buildExposureProfileModel(rows, metric, spot, levels, { compact }),
    [rows, metric, spot, levels, compact],
  );

  useGSAP(
    () => {
      if (!model || reducedMotion || !rootRef.current) return;
      const areas = rootRef.current.querySelectorAll<SVGPathElement>(".exposure-area");
      const line = rootRef.current.querySelector<SVGPathElement>(".exposure-line");
      const bars = rootRef.current.querySelectorAll<SVGRectElement>(".exposure-bar");

      areas.forEach((area) => {
        gsap.fromTo(area, { opacity: 0 }, { opacity: 1, duration: 0.42, ease: "power2.out" });
      });
      if (line) {
        const len = line.getTotalLength();
        gsap.fromTo(
          line,
          { strokeDasharray: len, strokeDashoffset: len, opacity: 0.4 },
          { strokeDashoffset: 0, opacity: 1, duration: 0.65, ease: "power2.inOut" },
        );
      }
      gsap.fromTo(
        bars,
        { opacity: 0 },
        { opacity: 1, duration: 0.28, stagger: 0.003, ease: "power1.out" },
      );
    },
    { dependencies: [model, animateKey, reducedMotion], scope: rootRef },
  );

  useEffect(() => {
    if (!model?.scrollable || model.spotX == null) return;
    const el = scrollRef.current;
    if (!el) return;
    const spotPx = (model.spotX / model.viewW) * el.scrollWidth;
    el.scrollLeft = Math.max(0, spotPx - el.clientWidth * 0.5);
  }, [model, animateKey]);

  if (!model) return null;

  const unitLabel =
    metric === "vex" ? "VEX Bn" : metric === "compare" ? "GEX · VEX overlay" : "GEX Bn / 1%";

  const posGrad = `exp-pos-${uid}`;
  const negGrad = `exp-neg-${uid}`;
  const barPosGrad = `exp-bar-pos-${uid}`;
  const barNegGrad = `exp-bar-neg-${uid}`;

  const chartSvg = (
    <svg
      ref={rootRef}
      className={`exposure-profile exposure-profile--strike${compact ? " exposure-profile--compact exposure-profile--scrollable" : ""}`}
      viewBox={`0 0 ${model.viewW} ${model.viewH}`}
      preserveAspectRatio={
        model.scrollable ? "xMinYMid meet" : fillWidth ? "xMidYMid slice" : "xMidYMid meet"
      }
      role="img"
      aria-label="Per-strike dealer exposure profile"
    >
        <defs>
          <linearGradient id={posGrad} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={palette.CHART_AREA_POS.top.color} stopOpacity={palette.CHART_AREA_POS.top.opacity} />
            <stop offset="55%" stopColor={palette.CHART_AREA_POS.mid.color} stopOpacity={palette.CHART_AREA_POS.mid.opacity} />
            <stop offset="100%" stopColor={palette.CHART_AREA_POS.base.color} stopOpacity={palette.CHART_AREA_POS.base.opacity} />
          </linearGradient>
          <linearGradient id={negGrad} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={palette.CHART_AREA_NEG.top.color} stopOpacity={palette.CHART_AREA_NEG.top.opacity} />
            <stop offset="55%" stopColor={palette.CHART_AREA_NEG.mid.color} stopOpacity={palette.CHART_AREA_NEG.mid.opacity} />
            <stop offset="100%" stopColor={palette.CHART_AREA_NEG.base.color} stopOpacity={palette.CHART_AREA_NEG.base.opacity} />
          </linearGradient>
          <linearGradient id={barPosGrad} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={palette.CHART_BAR_POS.top} stopOpacity="0.92" />
            <stop offset="100%" stopColor={palette.CHART_BAR_POS.bottom} stopOpacity={palette.CHART_BAR_POS.bottomOpacity} />
          </linearGradient>
          <linearGradient id={barNegGrad} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={palette.CHART_BAR_NEG.top} stopOpacity="0.9" />
            <stop offset="100%" stopColor={palette.CHART_BAR_NEG.bottom} stopOpacity={palette.CHART_BAR_NEG.bottomOpacity} />
          </linearGradient>
        </defs>

        <rect x={0} y={0} width={model.viewW} height={model.viewH} className="profile-bg profile-bg--exposure" rx={4} />

        {model.emBand ? (
          <rect
            x={model.emBand.x}
            y={10}
            width={model.emBand.w}
            height={model.viewH - 32}
            className="profile-em-band"
            rx={2}
          />
        ) : null}

        {model.yTicks.map((tick) => (
          <g key={tick.label} className="profile-ytick">
            <line
              x1={model.plotLeft}
              y1={tick.y}
              x2={model.plotRight}
              y2={tick.y}
              className={`profile-grid-line${tick.label === "0" ? " profile-grid-line--zero" : ""}`}
            />
            <text x={8} y={tick.y + 3} className="profile-axis-label profile-axis-label--y">
              {tick.label}
            </text>
          </g>
        ))}

        <line
          x1={model.plotLeft}
          y1={model.zeroY}
          x2={model.plotRight}
          y2={model.zeroY}
          className="profile-zero-axis"
        />

        <path d={model.posAreaPath} fill={`url(#${posGrad})`} className="exposure-area exposure-area--pos" />
        <path d={model.negAreaPath} fill={`url(#${negGrad})`} className="exposure-area exposure-area--neg" />

        {model.bars.map((bar) => (
          <rect
            key={bar.strike}
            x={bar.x}
            y={bar.y}
            width={bar.w}
            height={bar.h}
            data-sign={bar.sign}
            className={[
              "exposure-bar",
              `exposure-bar-${bar.sign}`,
              bar.isSpot ? "exposure-bar-spot" : "",
              bar.isPeak ? "exposure-bar-peak" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            fill={bar.sign === "pos" ? `url(#${barPosGrad})` : `url(#${barNegGrad})`}
            rx={1.5}
          />
        ))}

        <path d={model.linePath} className="exposure-line" fill="none" />
        {model.vexLinePath ? (
          <path d={model.vexLinePath} className="profile-vex-line" fill="none" />
        ) : null}

        {model.markers.map((m) => (
          <g key={m.id} className={`profile-marker profile-marker-${m.cls}`}>
            <line
              x1={m.x}
              y1={10}
              x2={m.x}
              y2={model.viewH - 28}
              className="profile-marker-line"
            />
            {!compact ? (
              <>
                <rect
                  x={m.x - 14}
                  y={model.viewH - 22}
                  width={28}
                  height={11}
                  rx={2}
                  className="profile-marker-pill"
                />
                <text x={m.x} y={model.viewH - 14} className="profile-marker-label">
                  {m.label}
                </text>
              </>
            ) : null}
          </g>
        ))}

        {model.xTicks.map((tick) => (
          <g key={`${tick.x}-${tick.label}`} className="profile-xtick">
            <line
              x1={tick.x}
              y1={model.viewH - 24}
              x2={tick.x}
              y2={model.viewH - 20}
              className="profile-x-tick-mark"
            />
            <text x={tick.x} y={model.viewH - 8} className="profile-axis-label profile-axis-label--x">
              {tick.label}
            </text>
          </g>
        ))}

        {model.spotX != null ? (
          <g className="profile-spot profile-spot--exposure">
            <line
              x1={model.spotX}
              y1={8}
              x2={model.spotX}
              y2={model.viewH - 26}
              className="profile-spot-line"
            />
            <polygon
              points={`${model.spotX - 4},8 ${model.spotX + 4},8 ${model.spotX},14`}
              className="profile-spot-arrow"
            />
            {!compact ? (
              <text x={model.spotX + 5} y={12} className="profile-spot-label">
                NOW
              </text>
            ) : null}
          </g>
        ) : null}
    </svg>
  );

  return (
    <div
      className={`exposure-profile-wrap exposure-profile-wrap--strike${compact ? " exposure-profile-wrap--compact" : ""}${embedded ? " exposure-profile-wrap--embedded" : ""}`}
    >
      {!embedded ? (
        <div className="exposure-profile-head">
          <span className="exposure-profile-title">Exposure profile</span>
          <span className="exposure-profile-metric">{unitLabel}</span>
          {!compact ? (
            <span className="exposure-profile-stat">
              Peak <strong>{model.peakStrike.toFixed(0)}</strong>
              <span className="exposure-profile-stat-sep">·</span>
              {fmtGexBn(model.peakAbsBn)}
            </span>
          ) : null}
          <span className="exposure-profile-spot">
            Spot <strong>{fmtPrice(spot)}</strong>
          </span>
          {compact ? (
            <span className="exposure-profile-scroll-hint">↔ scroll full chain</span>
          ) : null}
        </div>
      ) : null}
      {model.scrollable ? (
        <div ref={scrollRef} className="exposure-profile-scroll">
          {chartSvg}
        </div>
      ) : (
        chartSvg
      )}
    </div>
  );
}
