/** Symbols with ThetaData live 0DTE chain on today's session. */
export const LIVE_INTRADAY_SYMBOLS = new Set(["^SPX", "SPY", "QQQ"]);

function weekdayEt(iso: string): number {
  const label = new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
  });
  const map: Record<string, number> = {
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
  };
  return map[label.slice(0, 3)] ?? 1;
}

/** Pick startup date — mirrors backend ``default_date`` with client fallback for stale API. */
export function pickInitialDate(
  symbol: string,
  data: { default_date?: string; today: string; latest: string; dates: string[] },
): string {
  if (data.default_date) return data.default_date;

  const { today, latest, dates } = data;
  if (!dates.length) return latest || today;

  if (LIVE_INTRADAY_SYMBOLS.has(symbol) && today && dates.includes(today)) {
    const wd = weekdayEt(today);
    if (wd >= 1 && wd <= 5) return today;
  }

  if (today && latest === today && (weekdayEt(today) === 0 || weekdayEt(today) === 6)) {
    const idx = dates.indexOf(today);
    if (idx > 0) return dates[idx - 1]!;
  }

  return latest;
}

/** True when backend chose today as the default (trading-day live session). */
export function isLiveDefault(defaultDate: string, today: string): boolean {
  return Boolean(today) && defaultDate === today;
}

export function isLivePollCandidate(
  symbol: string,
  today: string,
  date: string,
  defaultDate: string,
): boolean {
  return LIVE_INTRADAY_SYMBOLS.has(symbol) && date === today && isLiveDefault(defaultDate, today);
}
