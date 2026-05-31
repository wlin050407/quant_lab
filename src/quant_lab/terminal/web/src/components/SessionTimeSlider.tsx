const SESSION_TIMES = ["10:00:00", "13:00:00", "15:30:00"] as const;
const SESSION_LABELS = ["10:00", "13:00", "15:30"] as const;
const SESSION_MILESTONES = ["Read map", "Entry", "Flat"] as const;

interface SessionTimeSliderProps {
  value: string;
  onChange: (time: string) => void;
}

export function SessionTimeSlider({ value, onChange }: SessionTimeSliderProps) {
  const idx = Math.max(0, SESSION_TIMES.indexOf(value as (typeof SESSION_TIMES)[number]));
  const activeIdx = idx >= 0 ? idx : 1;

  return (
    <div className="session-slider" aria-label="Intraday session time">
      <span className="session-slider-title">Session</span>
      <div className="session-slider-track-wrap">
        <div className="session-slider-track">
          <div
            className="session-slider-fill"
            style={{ width: `${(activeIdx / (SESSION_TIMES.length - 1)) * 100}%` }}
          />
        </div>
        <input
          type="range"
          className="session-slider-input"
          min={0}
          max={SESSION_TIMES.length - 1}
          step={1}
          value={activeIdx}
          onChange={(e) => onChange(SESSION_TIMES[Number(e.target.value)] ?? "13:00:00")}
          aria-valuetext={`${SESSION_LABELS[activeIdx]} Eastern · ${SESSION_MILESTONES[activeIdx]}`}
        />
        <div className="session-slider-ticks">
          {SESSION_LABELS.map((label, i) => (
            <button
              key={label}
              type="button"
              className={`session-tick${i === activeIdx ? " active" : ""}`}
              onClick={() => onChange(SESSION_TIMES[i])}
              title={SESSION_MILESTONES[i]}
            >
              <span className="session-tick-time">{label}</span>
              <span className="session-tick-milestone">{SESSION_MILESTONES[i]}</span>
            </button>
          ))}
        </div>
      </div>
      <span className="session-slider-et">ET</span>
    </div>
  );
}
