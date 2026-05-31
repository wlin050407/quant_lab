export function fmtGexBn(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 100) return `${v >= 0 ? "+" : ""}${v.toFixed(0)} Bn`;
  if (abs >= 10) return `${v >= 0 ? "+" : ""}${v.toFixed(1)} Bn`;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)} Bn`;
}

export function fmtMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${Number(v).toFixed(2)}`;
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${Number(v).toFixed(digits)}%`;
}

export function fmtRoc(v: number | null | undefined): string | null {
  if (v == null || Number.isNaN(v)) return null;
  if (Math.abs(v) < 20) return null;
  const sign = v > 0 ? "+" : "";
  if (Math.abs(v) >= 1000) return `${sign}${(v / 1000).toFixed(1)}k%`;
  return `${sign}${Math.round(v)}%`;
}

export function vannaLabel(code: string | null | undefined): string | null {
  if (code === "vol_down_dealers_buy") return "Vol↓ → dealers buy";
  if (code === "vol_down_dealers_sell") return "Vol↓ → dealers sell";
  if (code === "neutral") return "VEX neutral";
  return null;
}

export function regimeShort(r: string): string {
  if (r === "long_gamma") return "+γ Long";
  if (r === "short_gamma") return "−γ Short";
  return "Regime ?";
}

export function regimeTitle(r: string): string {
  if (r === "long_gamma") return "Positive Gamma";
  if (r === "short_gamma") return "Negative Gamma";
  return "Undetermined";
}

export function regimeDesc(r: string): string {
  if (r === "long_gamma") return "Dealers dampen moves · favor range / premium selling";
  if (r === "short_gamma") return "Dealers amplify moves · avoid short vol";
  return "Wait for clearer 0DTE positioning";
}
