import { SessionTimeSlider } from "./SessionTimeSlider";
import { BrandMark } from "./BrandMark";
import { BrandWordmark } from "./BrandWordmark";
import { IconChevronLeft, IconChevronRight, IconMoon, IconRefresh, IconSun } from "./Icons";

interface TopBarProps {
  symbol: string;
  date: string;
  intradayTime: string;
  dates: string[];
  focusMode: boolean;
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onSymbolChange: (symbol: string) => void;
  onDateChange: (date: string) => void;
  onIntradayTimeChange: (time: string) => void;
  onPrevDate: () => void;
  onNextDate: () => void;
  onToggleFocus: () => void;
  onLoadDemo: () => void;
  onLoadLive: () => void;
  onGoHome?: () => void;
  today: string;
  isLive: boolean;
  livePollCandidate?: boolean;
  effectiveIntradayTime?: string | null;
  onRefresh: () => void;
}

export function TopBar({
  symbol,
  date,
  intradayTime,
  dates,
  focusMode,
  theme,
  onToggleTheme,
  onSymbolChange,
  onDateChange,
  onIntradayTimeChange,
  onPrevDate,
  onNextDate,
  onToggleFocus,
  onLoadDemo,
  onLoadLive,
  onGoHome,
  today,
  isLive,
  livePollCandidate = false,
  effectiveIntradayTime,
  onRefresh,
}: TopBarProps) {
  const idx = dates.indexOf(date);
  const canPrev = idx > 0;
  const canNext = idx >= 0 && idx < dates.length - 1;

  return (
    <header className="topbar">
      <div className="topbar-row">
        <div className="brand">
          {onGoHome ? (
            <button type="button" className="topbar-home-btn" onClick={onGoHome} title="Back to workspace home (H)">
              Home
            </button>
          ) : null}
          <BrandMark size={34} />
          <BrandWordmark tagline="Index · 0DTE" />
        </div>
        <div className="controls">
          <div className="ctrl-group">
            <select
              className="ctrl-select"
              aria-label="Symbol"
              value={symbol}
              onChange={(e) => onSymbolChange(e.target.value)}
            >
              <option value="SPY">SPY</option>
              <option value="^SPX">SPX</option>
            </select>
          </div>
          {symbol === "^SPX" ? (
            <SessionTimeSlider
              value={intradayTime}
              onChange={onIntradayTimeChange}
              liveMode={livePollCandidate}
              effectiveTime={effectiveIntradayTime}
            />
          ) : null}
          <div className="ctrl-group date-nav">
            <button type="button" className="ctrl-icon" aria-label="Previous day" disabled={!canPrev} onClick={onPrevDate}>
              <IconChevronLeft />
            </button>
            <input
              type="date"
              value={date}
              onChange={(e) => onDateChange(e.target.value)}
              list="terminal-dates"
            />
            <datalist id="terminal-dates">
              {dates.map((d) => (
                <option key={d} value={d} />
              ))}
            </datalist>
            <button type="button" className="ctrl-icon" aria-label="Next day" disabled={!canNext} onClick={onNextDate}>
              <IconChevronRight />
            </button>
          </div>
          <div className="ctrl-group ctrl-actions">
            <button
              type="button"
              className="btn-toolbar btn-toolbar--theme"
              onClick={onToggleTheme}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? <IconSun /> : <IconMoon />}
            </button>
            <button type="button" className="btn-toolbar" onClick={onRefresh}>
              <IconRefresh />
              <span>Refresh</span>
            </button>
            <button
              type="button"
              className={`btn-toolbar${focusMode ? " active" : ""}`}
              onClick={onToggleFocus}
              title="Toggle heatmap focus (F)"
            >
              {focusMode ? "Exit focus" : "Focus"}
            </button>
            <button
              type="button"
              className={`btn-toolbar btn-toolbar--live${isLive ? " active" : ""}`}
              onClick={onLoadLive}
              title={`Jump to latest ^SPX session via ThetaData (T)${today ? ` · ${today}` : ""}`}
            >
              {isLive ? <span className="live-dot" aria-hidden /> : null}
              Live
            </button>
            <button
              type="button"
              className="btn-toolbar btn-toolbar--demo"
              onClick={onLoadDemo}
              title="Load SPX Pin Play demo (2023-07-11 13:00)"
            >
              Demo
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
