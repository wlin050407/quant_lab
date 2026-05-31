import { useCallback, useEffect, useRef, useState } from "react";

import type { HeatmapViewMode } from "../types/snapshot";

export type PanelSections = {
  gamma: boolean;
};

const STORAGE_KEYS: Record<HeatmapViewMode, string> = {
  single: "quantlab:trace-layout:single:v2",
  trinity: "quantlab:trace-layout:trinity:v2",
};

function defaultSections(): PanelSections {
  return { gamma: false };
}

function loadSections(viewMode: HeatmapViewMode): PanelSections {
  const defaults = defaultSections();
  try {
    const raw = localStorage.getItem(STORAGE_KEYS[viewMode]);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<PanelSections>;
    return { gamma: parsed.gamma ?? defaults.gamma };
  } catch {
    return defaults;
  }
}

export function usePanelSections(viewMode: HeatmapViewMode) {
  const [sections, setSections] = useState<PanelSections>(() => loadSections(viewMode));
  const prevViewRef = useRef(viewMode);

  useEffect(() => {
    if (prevViewRef.current !== viewMode) {
      prevViewRef.current = viewMode;
      setSections(defaultSections());
    }
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS[viewMode], JSON.stringify(sections));
  }, [sections, viewMode]);

  const toggleRegime = useCallback(() => {
    setSections((prev) => ({ gamma: !prev.gamma }));
  }, []);

  return {
    showRegime: sections.gamma,
    toggleRegime,
  };
}
