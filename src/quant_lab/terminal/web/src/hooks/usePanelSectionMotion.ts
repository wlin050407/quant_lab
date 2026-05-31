import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { RefObject } from "react";

gsap.registerPlugin(useGSAP);

export function usePanelSectionMotion(
  containerRef: RefObject<HTMLDivElement | null>,
  showRegime: boolean,
  reducedMotion: boolean,
): void {
  useGSAP(
    () => {
      const root = containerRef.current;
      if (!root || reducedMotion || !showRegime) return;

      const band = root.querySelector<HTMLElement>(".regime-band");
      if (!band) return;

      gsap.fromTo(
        band,
        { opacity: 0, y: -4 },
        { opacity: 1, y: 0, duration: 0.28, ease: "power2.out", clearProps: "opacity,y" },
      );
    },
    { dependencies: [showRegime, reducedMotion], scope: containerRef },
  );
}
