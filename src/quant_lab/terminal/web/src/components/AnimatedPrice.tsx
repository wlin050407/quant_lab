import { useEffect, useRef } from "react";
import gsap from "gsap";

import { fmtPrice } from "../lib/format";

interface AnimatedPriceProps {
  value: number | null;
  className?: string;
}

/** Spot price with brief crossfade on value change (GSAP). */
export function AnimatedPrice({ value, className = "" }: AnimatedPriceProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(value);

  useEffect(() => {
    const el = ref.current;
    if (!el || prev.current === value) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      prev.current = value;
      return;
    }
    gsap.fromTo(
      el,
      { opacity: 0.35, y: 3 },
      { opacity: 1, y: 0, duration: 0.22, ease: "power2.out" },
    );
    prev.current = value;
  }, [value]);

  return (
    <span ref={ref} className={className}>
      {value != null && Number.isFinite(value) ? fmtPrice(value) : "—"}
    </span>
  );
}
