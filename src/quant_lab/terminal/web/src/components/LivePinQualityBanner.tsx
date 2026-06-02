import type { DashboardSnapshot } from "../types/snapshot";

const GRADE_CLASS: Record<string, string> = {
  degraded: "live-pin-quality--degraded",
  poor: "live-pin-quality--poor",
};

/** Shown only when live pin quality is degraded or poor — not on every ok poll. */
export function LivePinQualityBanner({ snapshot }: { snapshot: DashboardSnapshot }) {
  const lq = snapshot.pin_targets?.live_data_quality ?? snapshot.meta?.model_metadata?.live_pin_quality;
  if (!lq || !snapshot.meta?.live_follow) return null;

  const grade = lq.grade ?? "ok";
  if (grade === "ok") return null;

  const cls = GRADE_CLASS[grade] ?? GRADE_CLASS.degraded;
  const poll = snapshot.meta?.model_metadata?.live_chain_poll;
  const top = (lq.reasons ?? []).find((r) => !r.startsWith("Live 0DTE"));

  return (
    <p className={`live-pin-quality live-pin-quality--compact ${cls}`} role="status">
      <strong>Live pin {grade}</strong>
      {top ? ` — ${top}` : null}
      {poll?.stale_served ? " · stale cache" : null}
      {poll?.chain_age_seconds != null && Number(poll.chain_age_seconds) > 90
        ? ` · chain ${Number(poll.chain_age_seconds).toFixed(0)}s old`
        : null}
    </p>
  );
}
