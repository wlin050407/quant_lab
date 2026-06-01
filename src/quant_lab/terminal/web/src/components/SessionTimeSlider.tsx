import {
  isLiveSessionTime,
  LIVE_SESSION_TIME,
  PIN_SESSION_LABELS,
  PIN_SESSION_MILESTONES,
  PIN_SESSION_TIMES,
} from "../lib/sessionTime";

interface SessionTimeSliderProps {
  value: string;
  onChange: (time: string) => void;
  /** When true, show Live (now) alongside pin-play snapshot slots. */
  liveMode?: boolean;
  /** Actual chain pull time from API (HH:MM) when in live follow mode. */
  effectiveTime?: string | null;
}

export function SessionTimeSlider({
  value,
  onChange,
  liveMode = false,
  effectiveTime,
}: SessionTimeSliderProps) {
  const liveActive = liveMode && isLiveSessionTime(value);
  const pinIdx = Math.max(0, PIN_SESSION_TIMES.indexOf(value as (typeof PIN_SESSION_TIMES)[number]));
  const activePinIdx = pinIdx >= 0 ? pinIdx : 1;

  if (liveMode) {
    return (
      <div className="session-slider session-slider--live" aria-label="Intraday session time">
        <span className="session-slider-title" title="US Eastern session times">
          Sess · ET
        </span>
        <div className="session-slider-live-row">
          <button
            type="button"
            className={`session-live-pill${liveActive ? " active" : ""}`}
            onClick={() => onChange(LIVE_SESSION_TIME)}
            title="Follow market now — refreshes every 30 seconds"
          >
            <span className="session-live-pill-k">Live</span>
            <span className="session-live-pill-v">
              {liveActive && effectiveTime ? `${effectiveTime} ET` : "now"}
            </span>
          </button>
          {!liveActive ? (
            <span className="session-replay-pill" title="Fixed snapshot — pin/GEX frozen at this clock">
              Replay {PIN_SESSION_LABELS[activePinIdx]} ET
            </span>
          ) : null}
          <span className="session-live-divider">·</span>
          <div className="session-slider-ticks session-slider-ticks--inline">
            {PIN_SESSION_LABELS.map((label, i) => (
              <button
                key={label}
                type="button"
                className={`session-tick session-tick--compact${!liveActive && i === activePinIdx ? " active" : ""}`}
                onClick={() => onChange(PIN_SESSION_TIMES[i])}
                title={`Replay ${PIN_SESSION_MILESTONES[i]}`}
              >
                <span className="session-tick-time">{label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="session-slider" aria-label="Intraday session time">
      <span className="session-slider-title" title="US Eastern session times">
        Sess · ET
      </span>
      <div className="session-slider-track-wrap">
        <div className="session-slider-track">
          <div
            className="session-slider-fill"
            style={{ width: `${(activePinIdx / (PIN_SESSION_TIMES.length - 1)) * 100}%` }}
          />
        </div>
        <input
          type="range"
          className="session-slider-input"
          min={0}
          max={PIN_SESSION_TIMES.length - 1}
          step={1}
          value={activePinIdx}
          onChange={(e) => onChange(PIN_SESSION_TIMES[Number(e.target.value)] ?? "13:00:00")}
          aria-valuetext={`${PIN_SESSION_LABELS[activePinIdx]} Eastern · ${PIN_SESSION_MILESTONES[activePinIdx]}`}
        />
        <div className="session-slider-ticks">
          {PIN_SESSION_LABELS.map((label, i) => (
            <button
              key={label}
              type="button"
              className={`session-tick${i === activePinIdx ? " active" : ""}`}
              onClick={() => onChange(PIN_SESSION_TIMES[i])}
              title={PIN_SESSION_MILESTONES[i]}
            >
              <span className="session-tick-time">{label}</span>
              <span className="session-tick-milestone">{PIN_SESSION_MILESTONES[i]}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
