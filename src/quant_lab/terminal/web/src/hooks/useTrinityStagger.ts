import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { RefObject } from "react";

import type { HeatmapViewMode } from "../types/snapshot";

/**
 * GSAP stagger when Trinity columns appear or view mode changes.
 */
export function useTrinityStagger(
  containerRef: RefObject<HTMLDivElement | null>,
  viewMode: HeatmapViewMode,
  panelCount: number,
): void {
  useGSAP(
    () => {
      const el = containerRef.current;
      if (!el) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

      const panels = gsap.utils.toArray<HTMLElement>(el.querySelectorAll(".heatmap-panel"));
      if (!panels.length) return;

      gsap.killTweensOf([el, ...panels]);

      if (viewMode === "trinity" && panelCount >= 2) {
        gsap.fromTo(el, { opacity: 0.88 }, { opacity: 1, duration: 0.32, ease: "power2.out" });
        gsap.fromTo(
          panels,
          { opacity: 0, x: -18, scale: 0.97 },
          {
            opacity: 1,
            x: 0,
            scale: 1,
            duration: 0.44,
            stagger: { each: 0.1, from: "start" },
            ease: "power2.out",
            clearProps: "transform,opacity",
          },
        );
      } else {
        gsap.fromTo(
          panels,
          { opacity: 0.65, y: 6 },
          { opacity: 1, y: 0, duration: 0.28, ease: "power2.out", clearProps: "transform,opacity" },
        );
      }
    },
    { dependencies: [viewMode, panelCount], scope: containerRef },
  );
}
