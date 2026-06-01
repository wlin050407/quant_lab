import type { ChainFlowMode } from "../types/snapshot";

const STORAGE_KEY = "quant_lab_chain_flow_mode";

export function loadChainFlowMode(): ChainFlowMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "full" ? "full" : "pin";
  } catch {
    return "pin";
  }
}

export function saveChainFlowMode(mode: ChainFlowMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore quota / private mode */
  }
}

export function chainFlowModeLabel(mode: ChainFlowMode | string | undefined): string {
  return mode === "full" ? "Pin · Precise" : "Pin · Fast";
}
