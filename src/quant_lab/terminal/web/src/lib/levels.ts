import type { Levels } from "../types/snapshot";

export const DEALER_LEVELS: { key: keyof Levels; label: string; cls: string }[] = [
  { key: "call_wall", label: "Call Wall", cls: "call" },
  { key: "ceiling", label: "Ceiling", cls: "neutral" },
  { key: "king", label: "King", cls: "king" },
  { key: "flip", label: "Γ Flip", cls: "flip" },
  { key: "max_pain", label: "Max Pain", cls: "pain" },
  { key: "put_wall", label: "Put Wall", cls: "put" },
  { key: "floor", label: "Floor", cls: "neutral" },
];

export function isValidLevel(v: number | null | undefined): v is number {
  return v != null && typeof v === "number" && !Number.isNaN(v);
}

export function countValidLevels(levels: Levels | null | undefined): number {
  if (!levels) return 0;
  return DEALER_LEVELS.filter((e) => isValidLevel(levels[e.key])).length;
}
