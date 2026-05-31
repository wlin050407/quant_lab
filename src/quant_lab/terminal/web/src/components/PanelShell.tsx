import type { ReactNode } from "react";

import { SpotlightCard } from "./react-bits/SpotlightCard";

interface PanelShellProps {
  children: ReactNode;
  className?: string;
  /** Subtle cursor-follow tint (react-bits SpotlightCard). */
  spotlightColor?: string;
  id?: string;
}

/**
 * Terminal panel chrome — react-bits spotlight + Warp surface tokens.
 * Use for primary workspace panels (ladder, heatmap, right rail).
 */
export function PanelShell({
  children,
  className = "",
  spotlightColor = "rgba(20, 184, 166, 0.06)",
  id,
}: PanelShellProps) {
  return (
    <SpotlightCard
      id={id}
      className={`panel ${className}`.trim()}
      spotlightColor={spotlightColor}
    >
      {children}
    </SpotlightCard>
  );
}
