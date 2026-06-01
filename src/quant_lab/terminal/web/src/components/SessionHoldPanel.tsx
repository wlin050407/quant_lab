import type { DashboardSnapshot } from "../types/snapshot";

interface SessionHoldPanelProps {
  snapshot: DashboardSnapshot;
  onRefresh: () => void;
}

export function SessionHoldPanel({ snapshot, onRefresh }: SessionHoldPanelProps) {
  const meta = snapshot.meta;
  const title =
    meta?.session_status_title ??
    meta?.session_status_detail_en ??
    "Session data unavailable";
  const message =
    meta?.session_status_message ??
    meta?.session_status_detail_en ??
    "Refresh again in a moment.";
  const clock = meta?.clock_et;

  return (
    <section className="session-hold-panel" aria-live="polite">
      <div className="session-hold-card">
        <p className="session-hold-kicker">{snapshot.date} · ET {clock ?? "—"}</p>
        <h2 className="session-hold-title">{title}</h2>
        <p className="session-hold-body">{message}</p>
        <p className="session-hold-hint">
          Pin and GEX run in both chain modes; display is paused until today&apos;s 0DTE chain is
          available.
        </p>
        <button type="button" className="btn-toolbar session-hold-refresh" onClick={onRefresh}>
          Refresh
        </button>
      </div>
    </section>
  );
}
